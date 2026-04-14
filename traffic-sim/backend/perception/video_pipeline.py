# pyright: reportMissingImports=false

import argparse
import json
import threading
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import requests

from backend.state.simulation_state import latest_results, latest_results_lock
from backend.agent.yolo_detector import detect_vehicles_in_frame, get_lane, reset_lane_wait_timer, reset_tracking_state
from backend.perception.homography import (
    HomographyLaneMapper,
    compute_homography,
    select_source_points,
)
from backend.perception.lane_processing import (
    draw_lane_polygons,
    normalize_lane_config,
    normalize_lane_regions,
)

# Debug mode: set to True to enable per-frame lane polygon visualization and logging
DEBUG_MODE = True

LANE_COLORS = {
    'north': (0, 255, 255),
    'east': (0, 165, 255),
    'south': (255, 0, 255),
    'west': (255, 128, 0),
}

COUNT_NORMALIZATION_SCALE = 10.0
WAIT_NORMALIZATION_SCALE = 30.0
TRAFFIC_DIRECTIONS = ('north', 'south', 'east', 'west')
WAIT_SPEED_THRESHOLD_PX = 3.0
DEFAULT_QUEUE_ROI_DEPTH_PX = 140

# Quick start:
# 1) Calibrate lanes from video first frame:
#    python -m backend.perception.calibrate_lanes --video path/to/video.mp4 --output backend/perception/config/junction_demo.json
#    or polygon mode:
#    python -m backend.perception.calibrate_lanes_polygon --video path/to/video.mp4 --output backend/perception/config/junction_demo.json
# 2) Run pipeline:
#    python -m backend.perception.video_pipeline --video path/to/video.mp4 --config backend/perception/config/junction_demo.json


def is_valid_region(region):
    if isinstance(region, dict):
        region = region.get('points')

    if not isinstance(region, list) or len(region) == 0:
        return False
    if len(region) == 4 and all(isinstance(value, (int, float)) for value in region):
        return True
    if all(isinstance(point, list) and len(point) == 2 and all(isinstance(v, (int, float)) for v in point) for point in region):
        return len(region) >= 3
    return False


def load_config(config_path):
    data = normalize_lane_config(config_path)
    lane_regions = data.get('lane_regions', {})
    normalized_lane_regions = normalize_lane_regions(lane_regions)
    for lane in ('north', 'east', 'south', 'west'):
        if lane not in normalized_lane_regions:
            raise ValueError(f"Missing lane region for: {lane}")
        if not is_valid_region(normalized_lane_regions[lane]):
            raise ValueError(
                f"Lane region for {lane} must be rectangle [x1,y1,x2,y2] or polygon [[x,y], ...]"
            )

    data['lane_regions'] = normalized_lane_regions

    settings = data.get('settings', {}) or {}
    data['settings'] = {
        'min_avg_confidence': float(settings.get('min_avg_confidence', 0.25)),
        'max_count_jump': int(settings.get('max_count_jump', 3)),
        'confidence_hold_ticks': int(settings.get('confidence_hold_ticks', 1)),
        'smooth_alpha': float(settings.get('smooth_alpha', 0.7)),
    }
    return data


def post_json(url, payload, timeout=20):
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _scale_points(points, scale_x=1.0, scale_y=1.0):
    return [[float(point[0]) * float(scale_x), float(point[1]) * float(scale_y)] for point in points]


def build_homography_mapper(config, cap, detect_width, detect_height, scale_x, scale_y, select_points=False):
    homography_config = config.get('homography', {}) or {}
    config_points = homography_config.get('source_points')
    use_homography = bool(homography_config.get('enabled')) or bool(select_points)
    if not use_homography:
        print('[HOMOGRAPHY] Disabled (homography.enabled is false)')
        return None

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    ok, first_frame = cap.read()
    if not ok or first_frame is None:
        raise RuntimeError('Could not read first frame for homography initialization')

    selected_points_capture = None
    if select_points:
        selected_points_capture = select_source_points(first_frame)
        print(f"[HOMOGRAPHY] Selected source points (capture space): {selected_points_capture}")

    src_points = selected_points_capture or config_points
    if not src_points or len(src_points) != 4:
        raise ValueError('Homography requires exactly 4 source points')

    point_space = str(homography_config.get('source_points_space', 'capture')).strip().lower()
    if selected_points_capture is not None:
        point_space = 'capture'

    if point_space == 'detect':
        src_points_detect = [[float(point[0]), float(point[1])] for point in src_points]
    else:
        src_points_detect = _scale_points(src_points, scale_x=scale_x, scale_y=scale_y)

    output_size_raw = homography_config.get('output_size', [800, 800])
    if not isinstance(output_size_raw, (list, tuple)) or len(output_size_raw) != 2:
        raise ValueError('homography.output_size must be [width, height]')
    output_size = (int(output_size_raw[0]), int(output_size_raw[1]))

    destination_points = homography_config.get('destination_points')
    if destination_points is not None:
        if not isinstance(destination_points, (list, tuple)) or len(destination_points) != 4:
            raise ValueError('homography.destination_points must contain exactly 4 points')
        destination_points = [[float(point[0]), float(point[1])] for point in destination_points]

    lane_regions_top_view = homography_config.get('lane_regions_top_view')
    if not lane_regions_top_view:
        raise ValueError('homography.lane_regions_top_view must be explicitly defined')
    H_matrix = compute_homography(
        src_points_detect,
        output_size=output_size,
        dst_points=destination_points,
    )
    mapper = HomographyLaneMapper(
        H_matrix,
        output_size=output_size,
        lane_regions_top_view=lane_regions_top_view,
    )

    print(f"[HOMOGRAPHY] Enabled with output_size={output_size}")
    print(f"[HOMOGRAPHY] source_points_detect={src_points_detect}")
    if destination_points is not None:
        print(f"[HOMOGRAPHY] destination_points={destination_points}")
    print(f"[HOMOGRAPHY] lane_regions_top_view keys={list(lane_regions_top_view.keys())}")

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    return mapper


def estimate_timer_duration(video_path):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    cap.release()
    if fps <= 0 or frame_count <= 0:
        return 120
    return max(30, int(frame_count / fps))


def build_smoothed_lane_state(raw_lane_state, previous_lane_state, alpha):
    smoothed_state = {}
    for lane_id in ('north', 'east', 'south', 'west'):
        lane_data = raw_lane_state.get(lane_id, {})
        raw_count = float(lane_data.get('count', 0))
        raw_wait = float(lane_data.get('avgWaitTime', 0.0))
        prev_lane_data = previous_lane_state.get(lane_id, {})
        prev_count = float(prev_lane_data.get('count', raw_count))
        prev_wait = float(prev_lane_data.get('avgWaitTime', raw_wait))

        smoothed_count = (float(alpha) * prev_count) + ((1.0 - float(alpha)) * raw_count)
        smoothed_wait = (float(alpha) * prev_wait) + ((1.0 - float(alpha)) * raw_wait)

        smoothed_state[lane_id] = {
            'count': int(max(0, round(smoothed_count))),
            'hasAmbulance': bool(lane_data.get('hasAmbulance', False)),
            'avgWaitTime': float(smoothed_wait),
        }

        print(
            f"[RL SMOOTH] lane={lane_id} raw_count={raw_count:.2f} smoothed_count={smoothed_count:.2f} "
            f"raw_wait={raw_wait:.2f} smoothed_wait={smoothed_wait:.2f} alpha={float(alpha):.2f}"
        )

    return smoothed_state


def validate_lane_state_structure(lane_state, context='video_pipeline'):
    expected_keys = {'count', 'avgWaitTime', 'hasAmbulance'}
    expected_lanes = ('north', 'east', 'south', 'west')

    if not isinstance(lane_state, dict):
        print(f"[RL STATE WARNING][{context}] lane_state must be a dict")
        return False

    ok = True
    for lane_id in expected_lanes:
        lane_data = lane_state.get(lane_id)
        if not isinstance(lane_data, dict):
            print(f"[RL STATE WARNING][{context}] missing or invalid lane: {lane_id}")
            ok = False
            continue

        missing = expected_keys.difference(lane_data.keys())
        extra = set(lane_data.keys()).difference(expected_keys)
        if missing or extra:
            print(
                f"[RL STATE WARNING][{context}] lane={lane_id} "
                f"missing={sorted(missing)} extra={sorted(extra)}"
            )
            ok = False

    return ok


def build_snapshot(
    lane_state,
    timestamp=None,
    active_green_lane=None,
    line_counts=None,
    wait_time_by_direction=None,
    queue_length_by_direction=None,
    signal_phases=None,
):
    if not isinstance(line_counts, dict):
        line_counts = {}
    if not isinstance(wait_time_by_direction, dict):
        wait_time_by_direction = {}
    if not isinstance(queue_length_by_direction, dict):
        queue_length_by_direction = {}
    if not isinstance(signal_phases, list):
        signal_phases = []

    safe_lane_state = {
        direction: {
            'count': int(lane_state.get(direction, {}).get('count', 0)),
            'hasAmbulance': bool(lane_state.get(direction, {}).get('hasAmbulance', False)),
            'avgWaitTime': float(wait_time_by_direction.get(direction, 0.0)),
        }
        for direction in TRAFFIC_DIRECTIONS
    }
    validate_lane_state_structure(lane_state)
    payload = {
        'lane_state': safe_lane_state,
        'line_counts': {
            direction: int(line_counts.get(direction, 0))
            for direction in TRAFFIC_DIRECTIONS
        },
        'wait_time_by_direction': {
            direction: float(wait_time_by_direction.get(direction, 0.0))
            for direction in TRAFFIC_DIRECTIONS
        },
        'queue_length_by_direction': {
            direction: int(queue_length_by_direction.get(direction, 0))
            for direction in TRAFFIC_DIRECTIONS
        },
    }
    if timestamp is not None:
        payload['timestamp'] = float(timestamp)
    if active_green_lane is not None:
        payload['active_green_lane'] = active_green_lane
    payload['signal_phases'] = list(signal_phases)
    return payload


def build_lane_counts_from_detections(detections):
    lane_counts = {lane: 0 for lane in TRAFFIC_DIRECTIONS}
    for detection in detections or []:
        lane_id = detection.get('lane') if isinstance(detection, dict) else None
        if lane_id in lane_counts:
            lane_counts[lane_id] += 1
    return lane_counts


def get_center(detection):
    if not isinstance(detection, dict):
        return None
    point = detection.get('bbox_center') or detection.get('center') or detection.get('bottom_center')
    if isinstance(point, (list, tuple)) and len(point) == 2:
        return float(point[0]), float(point[1])
    bbox = detection.get('bbox')
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        x1, y1, x2, y2 = [float(v) for v in bbox]
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
    return None


def smooth_lane_state(raw_lane_state, prev_smoothed, alpha):
    smoothed = {}
    for lane in ('north', 'east', 'south', 'west'):
        raw_count = float(raw_lane_state.get(lane, {}).get('count', 0))
        prev_count = float(prev_smoothed.get(lane, {}).get('smoothed_count', raw_count))
        smoothed_count = alpha * raw_count + (1.0 - alpha) * prev_count

        raw_ambulance = 1.0 if raw_lane_state.get(lane, {}).get('hasAmbulance', False) else 0.0
        prev_ambulance = float(prev_smoothed.get(lane, {}).get('smoothed_ambulance', raw_ambulance))
        smoothed_ambulance = alpha * raw_ambulance + (1.0 - alpha) * prev_ambulance

        smoothed[lane] = {
            'count': int(max(0, round(smoothed_count))),
            'hasAmbulance': smoothed_ambulance >= 0.5,
            'avgWaitTime': float(raw_lane_state.get(lane, {}).get('avgWaitTime', 0.0)),
            'raw_count': raw_count,
            'smoothed_count': smoothed_count,
            'raw_ambulance': raw_ambulance,
            'smoothed_ambulance': smoothed_ambulance,
        }
    return smoothed


def clamp_lane_state(current_lane_state, previous_lane_state, max_count_jump):
    clamped = {}
    for lane in ('north', 'east', 'south', 'west'):
        current_count = int(current_lane_state.get(lane, {}).get('count', 0))
        previous_count = int(previous_lane_state.get(lane, {}).get('count', current_count))
        delta = current_count - previous_count
        if delta > max_count_jump:
            current_count = previous_count + max_count_jump
        elif delta < -max_count_jump:
            current_count = max(0, previous_count - max_count_jump)

        clamped[lane] = {
            **current_lane_state.get(lane, {}),
            'count': current_count,
            'avgWaitTime': float(current_lane_state.get(lane, {}).get('avgWaitTime', 0.0)),
        }
    return clamped


def build_virtual_lines(config, frame_width, frame_height):
    raw_lines = (config.get('virtual_lines') or []) if isinstance(config, dict) else []
    if raw_lines:
        normalized_lines = []
        for index, item in enumerate(raw_lines):
            if not isinstance(item, dict):
                continue
            start = item.get('start')
            end = item.get('end')
            if not isinstance(start, (list, tuple)) or len(start) != 2:
                continue
            if not isinstance(end, (list, tuple)) or len(end) != 2:
                continue
            line_id = str(item.get('id') or item.get('direction') or f'line_{index + 1}')
            direction = str(item.get('direction') or '').strip().lower()
            if direction not in TRAFFIC_DIRECTIONS:
                if line_id.endswith('_entry'):
                    direction = line_id.replace('_entry', '').strip().lower()
                elif line_id in TRAFFIC_DIRECTIONS:
                    direction = line_id
            if direction not in TRAFFIC_DIRECTIONS:
                continue
            normalized_lines.append(
                {
                    'id': line_id,
                    'direction': direction,
                    'start': (float(start[0]), float(start[1])),
                    'end': (float(end[0]), float(end[1])),
                }
            )
        if len(normalized_lines) == 4:
            return normalized_lines

    # Default 4 entry lines around the intersection center.
    cx = float(frame_width) * 0.5
    cy = float(frame_height) * 0.5
    span_x = float(frame_width) * 0.18
    span_y = float(frame_height) * 0.18
    offset_x = float(frame_width) * 0.06
    offset_y = float(frame_height) * 0.06

    return [
        {
            'id': 'north_entry',
            'direction': 'north',
            'start': (cx - span_x, cy - span_y - offset_y),
            'end': (cx + span_x, cy - span_y - offset_y),
        },
        {
            'id': 'south_entry',
            'direction': 'south',
            'start': (cx - span_x, cy + span_y + offset_y),
            'end': (cx + span_x, cy + span_y + offset_y),
        },
        {
            'id': 'east_entry',
            'direction': 'east',
            'start': (cx + span_x + offset_x, cy - span_y),
            'end': (cx + span_x + offset_x, cy + span_y),
        },
        {
            'id': 'west_entry',
            'direction': 'west',
            'start': (cx - span_x - offset_x, cy - span_y),
            'end': (cx - span_x - offset_x, cy + span_y),
        },
    ]


def line_side(line_start, line_end, point):
    ax, ay = float(line_start[0]), float(line_start[1])
    bx, by = float(line_end[0]), float(line_end[1])
    px, py = float(point[0]), float(point[1])
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)


def has_crossed_line(previous_point, current_point, line_start, line_end, eps=1e-6):
    prev_side = line_side(line_start, line_end, previous_point)
    curr_side = line_side(line_start, line_end, current_point)
    if abs(prev_side) <= eps or abs(curr_side) <= eps:
        return False
    return prev_side * curr_side < 0.0


def bottom_center_from_bbox(bbox):
    x1, y1, x2, y2 = [float(v) for v in bbox]
    return ((x1 + x2) / 2.0, y2)


def _normalize_direction_label(value):
    if value is None:
        return None
    text = str(value).strip().lower()
    for direction in TRAFFIC_DIRECTIONS:
        if direction in text:
            return direction
    return None


def _region_points(region):
    points = region.get('points') if isinstance(region, dict) else region
    if not isinstance(points, list):
        return []
    if len(points) == 4 and all(isinstance(value, (int, float)) for value in points):
        x1, y1, x2, y2 = [float(v) for v in points]
        return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
    if all(
        isinstance(point, (list, tuple)) and len(point) == 2
        for point in points
    ):
        return [[float(point[0]), float(point[1])] for point in points]
    return []


def _point_in_lane_region(point, region):
    polygon_points = _region_points(region)
    if len(polygon_points) < 3:
        return False
    polygon = np.array(polygon_points, dtype=np.float32)
    px, py = float(point[0]), float(point[1])
    return cv2.pointPolygonTest(polygon, (px, py), False) >= 0


def compute_detection_lane_counts(detections, lane_regions):
    counts = {direction: 0 for direction in TRAFFIC_DIRECTIONS}
    unmatched = 0

    for det in detections:
        bbox = det.get('bbox')
        if not bbox or len(bbox) != 4:
            continue

        point = bottom_center_from_bbox(bbox)
        direction = _normalize_direction_label(det.get('lane'))
        if direction is None:
            for candidate in TRAFFIC_DIRECTIONS:
                lane_region = lane_regions.get(candidate)
                if lane_region is not None and _point_in_lane_region(point, lane_region):
                    direction = candidate
                    break

        if direction in counts:
            counts[direction] += 1
        else:
            unmatched += 1

    return counts, unmatched


def point_line_distance(point, line_start, line_end):
    px, py = float(point[0]), float(point[1])
    x1, y1 = float(line_start[0]), float(line_start[1])
    x2, y2 = float(line_end[0]), float(line_end[1])
    dx = x2 - x1
    dy = y2 - y1
    denom = (dx * dx) + (dy * dy)
    if denom <= 1e-9:
        return float(np.hypot(px - x1, py - y1))
    t = ((px - x1) * dx + (py - y1) * dy) / denom
    t = max(0.0, min(1.0, t))
    cx = x1 + (t * dx)
    cy = y1 + (t * dy)
    return float(np.hypot(px - cx, py - cy))


def infer_direction_for_point(point, virtual_lines):
    nearest_direction = None
    nearest_distance = None
    for line in virtual_lines:
        direction = str(line.get('direction', '')).strip().lower()
        if direction not in TRAFFIC_DIRECTIONS:
            continue
        distance = point_line_distance(point, line['start'], line['end'])
        if nearest_distance is None or distance < nearest_distance:
            nearest_distance = distance
            nearest_direction = direction
    return nearest_direction


def build_queue_rois(virtual_lines, frame_width, frame_height, depth_px=DEFAULT_QUEUE_ROI_DEPTH_PX):
    depth = float(max(1, depth_px))
    rois = {direction: None for direction in TRAFFIC_DIRECTIONS}

    for line in virtual_lines:
        direction = str(line.get('direction', '')).strip().lower()
        if direction not in TRAFFIC_DIRECTIONS:
            continue

        x1, y1 = float(line['start'][0]), float(line['start'][1])
        x2, y2 = float(line['end'][0]), float(line['end'][1])
        min_x, max_x = min(x1, x2), max(x1, x2)
        min_y, max_y = min(y1, y2), max(y1, y2)

        if direction == 'north':
            roi = (min_x, max(0.0, min_y - depth), max_x, min(float(frame_height - 1), min_y))
        elif direction == 'south':
            roi = (min_x, max(0.0, max_y), max_x, min(float(frame_height - 1), max_y + depth))
        elif direction == 'east':
            roi = (max(0.0, max_x), min_y, min(float(frame_width - 1), max_x + depth), max_y)
        else:  # west
            roi = (max(0.0, min_x - depth), min_y, min(float(frame_width - 1), min_x), max_y)

        rois[direction] = roi

    return rois


def point_in_roi(point, roi):
    if roi is None:
        return False
    x, y = float(point[0]), float(point[1])
    min_x, min_y, max_x, max_y = roi
    return min_x <= x <= max_x and min_y <= y <= max_y


def vehicle_is_waiting(vehicle_direction, active_green_lane):
    direction = _normalize_direction_label(vehicle_direction)
    green = _normalize_direction_label(active_green_lane)
    if direction not in TRAFFIC_DIRECTIONS:
        return False
    if green is None:
        return True
    return direction != green


def compute_queue_length_by_direction(
    detections,
    last_direction_by_vehicle,
    active_green_lane=None,
):
    queue_ids = {direction: set() for direction in TRAFFIC_DIRECTIONS}

    for det in detections:
        track_id = det.get('track_id')
        bbox = det.get('bbox')
        if track_id is None or not bbox or len(bbox) != 4:
            continue

        vehicle_id = int(track_id)
        chosen_direction = _normalize_direction_label(det.get('lane')) or _normalize_direction_label(last_direction_by_vehicle.get(vehicle_id))
        print("Vehicle:", vehicle_id, "Direction:", chosen_direction)
        if chosen_direction not in TRAFFIC_DIRECTIONS:
            continue
        if vehicle_is_waiting(chosen_direction, active_green_lane):
            queue_ids[chosen_direction].add(vehicle_id)

    return {direction: len(queue_ids[direction]) for direction in TRAFFIC_DIRECTIONS}


def bbox_centroid(bbox):
    x1, y1, x2, y2 = [float(value) for value in bbox]
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def bbox_area(bbox):
    x1, y1, x2, y2 = [float(value) for value in bbox]
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def bbox_iou(a, b):
    ax1, ay1, ax2, ay2 = [float(value) for value in a]
    bx1, by1, bx2, by2 = [float(value) for value in b]

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    intersection_w = max(0.0, ix2 - ix1)
    intersection_h = max(0.0, iy2 - iy1)
    intersection = intersection_w * intersection_h
    if intersection <= 0.0:
        return 0.0

    union = bbox_area(a) + bbox_area(b) - intersection
    if union <= 1e-9:
        return 0.0
    return float(intersection / union)


def centroid_distance(a, b):
    return float(np.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1])))


def region_bounds(region):
    points = _region_points(region)
    if not points:
        return None
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def lane_exit_line(lane_id, lane_regions):
    region = lane_regions.get(lane_id)
    bounds = region_bounds(region)
    if bounds is None:
        return None

    min_x, min_y, max_x, max_y = bounds
    if lane_id == 'north':
        return ((min_x, max_y), (max_x, max_y))
    if lane_id == 'south':
        return ((min_x, min_y), (max_x, min_y))
    if lane_id == 'east':
        return ((min_x, min_y), (min_x, max_y))
    if lane_id == 'west':
        return ((max_x, min_y), (max_x, max_y))
    return None


def _point_in_region(x, y, polygon):
    points = _region_points(polygon)
    if len(points) < 3:
        return False

    inside = False
    n = len(points)
    px1, py1 = points[0]

    for i in range(n + 1):
        px2, py2 = points[i % n]
        if y > min(py1, py2):
            if y <= max(py1, py2):
                if x <= max(px1, px2):
                    if py1 != py2:
                        xinters = (y - py1) * (px2 - px1) / (py2 - py1 + 1e-9) + px1
                    if px1 == px2 or x <= xinters:
                        inside = not inside
        px1, py1 = px2, py2

    return inside


def _point_in_lane_region(point, lane_regions, lane_id):
    region = lane_regions.get(lane_id)
    if region is None:
        return False
    return _point_in_region(point[0], point[1], region)


class SimpleVehicleTracker:
    def __init__(
        self,
        lane_regions,
        min_seen_frames=2,
        max_missed_frames=8,
        match_iou_threshold=0.15,
        match_distance_px=90.0,
        history_size=5,
        smooth_alpha=0.7,
        max_count_jump=3,
    ):
        self.lane_regions = lane_regions
        self.min_seen_frames = int(min_seen_frames)
        self.max_missed_frames = int(max_missed_frames)
        self.match_iou_threshold = float(match_iou_threshold)
        self.match_distance_px = float(match_distance_px)
        self.history_size = int(history_size)
        self.smooth_alpha = float(smooth_alpha)
        self.max_count_jump = int(max_count_jump)
        self.tracked_objects = {}
        self.next_track_id = 1
        self.total_vehicles_crossed = 0
        self.crossed_by_lane = {lane: 0 for lane in TRAFFIC_DIRECTIONS}
        self.counted_ids = set()
        self.used_keys = {}  # key → last_used_time; allows reuse after KEY_LIFETIME
        self.key_lifetime = 3.0  # seconds; allow region reuse after this window
        self.count_history = {lane: deque(maxlen=self.history_size) for lane in TRAFFIC_DIRECTIONS}
        self.prev_smoothed_counts = {lane: 0.0 for lane in TRAFFIC_DIRECTIONS}
        self.exit_lines = {lane: lane_exit_line(lane, lane_regions) for lane in TRAFFIC_DIRECTIONS}
        self.frame_bounds = self._compute_frame_bounds(lane_regions)
        self.exit_zone_margin_px = 18.0
        self.boundary_margin_px = 24.0

    def reset(self):
        self.tracked_objects = {}
        self.next_track_id = 1
        self.total_vehicles_crossed = 0
        self.crossed_by_lane = {lane: 0 for lane in TRAFFIC_DIRECTIONS}
        self.counted_ids = set()
        self.used_keys = {}  # key → last_used_time; allows reuse after KEY_LIFETIME
        self.count_history = {lane: deque(maxlen=self.history_size) for lane in TRAFFIC_DIRECTIONS}
        self.prev_smoothed_counts = {lane: 0.0 for lane in TRAFFIC_DIRECTIONS}

    def _compute_frame_bounds(self, lane_regions):
        xs = []
        ys = []
        for lane_id in TRAFFIC_DIRECTIONS:
            bounds = region_bounds(lane_regions.get(lane_id))
            if bounds is None:
                continue
            min_x, min_y, max_x, max_y = bounds
            xs.extend([float(min_x), float(max_x)])
            ys.extend([float(min_y), float(max_y)])
        if not xs or not ys:
            return (0.0, 0.0, 0.0, 0.0)
        return (min(xs), min(ys), max(xs), max(ys))

    def _build_count_key(self, lane_id, centroid):
        bucket_x = int(float(centroid[0]) / 120.0)
        bucket_y = int(float(centroid[1]) / 120.0)
        return (str(lane_id), bucket_x, bucket_y)

    def _assign_lane(self, centroid):
        for lane_id in TRAFFIC_DIRECTIONS:
            if _point_in_lane_region(centroid, self.lane_regions, lane_id):
                return lane_id

        cx, cy = centroid
        best_lane = None
        best_distance = None
        for lane_id in TRAFFIC_DIRECTIONS:
            bounds = region_bounds(self.lane_regions.get(lane_id))
            if bounds is None:
                continue
            min_x, min_y, max_x, max_y = bounds
            center = ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)
            distance = centroid_distance((cx, cy), center)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_lane = lane_id
        return best_lane

    def _is_confirmed(self, track):
        return int(track.get('seen_frames', 0)) >= self.min_seen_frames and int(track.get('missed_frames', 0)) <= self.max_missed_frames

    def _crossed_exit_line(self, previous_centroid, current_centroid, lane_id):
        line = self.exit_lines.get(lane_id)
        if line is None:
            return False
        return has_crossed_line(previous_centroid, current_centroid, line[0], line[1])

    def _in_exit_zone_or_near_boundary(self, centroid, lane_id):
        bounds = region_bounds(self.lane_regions.get(lane_id))
        if bounds is None:
            return False

        min_x, min_y, max_x, max_y = bounds
        px, py = float(centroid[0]), float(centroid[1])
        frame_min_x, frame_min_y, frame_max_x, frame_max_y = self.frame_bounds

        if lane_id == 'north':
            return py <= (min_y + self.exit_zone_margin_px) or py <= (frame_min_y + self.boundary_margin_px)
        if lane_id == 'south':
            return py >= (max_y - self.exit_zone_margin_px) or py >= (frame_max_y - self.boundary_margin_px)
        if lane_id == 'east':
            return px >= (max_x - self.exit_zone_margin_px) or px >= (frame_max_x - self.boundary_margin_px)
        if lane_id == 'west':
            return px <= (min_x + self.exit_zone_margin_px) or px <= (frame_min_x + self.boundary_margin_px)
        return False

    def _count_track_once(self, track_id, lane_id, centroid, frame_index, reason):
        count_key = self._build_count_key(lane_id, centroid)
        track = self.tracked_objects.get(track_id)
        current_time = float(track.get('last_seen_time', 0.0)) if track is not None else 0.0

        print("DEDUP CHECK:", count_key, current_time)

        if track_id in self.counted_ids:
            return False

        # Time-windowed check: block key only if used recently (within KEY_LIFETIME)
        if count_key in self.used_keys:
            last_used_time = float(self.used_keys[count_key])
            if current_time - last_used_time < float(self.key_lifetime):
                return False
            # Key is stale; allow reuse

        if track is not None:
            track['counted'] = True
            track['counted_frame'] = int(frame_index)
            track['crossed_exit_line'] = (reason == 'exit_line' or reason == 'exit_zone_or_boundary')

        self.total_vehicles_crossed += 1
        self.crossed_by_lane[lane_id] += 1
        self.counted_ids.add(track_id)
        self.used_keys[count_key] = current_time  # store timestamp for time-windowed reuse
        return True

    def _match_detections(self, detections):
        if not self.tracked_objects or not detections:
            return [], list(self.tracked_objects.keys()), list(range(len(detections)))

        candidates = []
        for track_id, track in self.tracked_objects.items():
            if int(track.get('missed_frames', 0)) > self.max_missed_frames:
                continue
            for detection_index, detection in enumerate(detections):
                iou = bbox_iou(track['bbox'], detection['bbox'])
                distance = centroid_distance(track['centroid'], detection['centroid'])
                lane_bonus = 0.15 if track.get('lane') and track.get('lane') == detection.get('lane') else 0.0
                if iou < self.match_iou_threshold and distance > self.match_distance_px:
                    continue
                score = (iou * 100.0) + lane_bonus - (distance / max(1.0, self.match_distance_px))
                candidates.append((score, iou, -distance, track_id, detection_index))

        candidates.sort(reverse=True)
        matched_track_ids = set()
        matched_detection_indices = set()
        matches = []

        for _, _, _, track_id, detection_index in candidates:
            if track_id in matched_track_ids or detection_index in matched_detection_indices:
                continue
            matched_track_ids.add(track_id)
            matched_detection_indices.add(detection_index)
            matches.append((track_id, detection_index))

        unmatched_track_ids = [track_id for track_id in self.tracked_objects.keys() if track_id not in matched_track_ids]
        unmatched_detection_indices = [index for index in range(len(detections)) if index not in matched_detection_indices]
        return matches, unmatched_track_ids, unmatched_detection_indices

    def _create_track(self, detection, current_time, frame_index):
        centroid = detection['centroid']
        lane_id = detection.get('lane') or self._assign_lane(centroid)
        track_id = self.next_track_id
        self.next_track_id += 1

        track = {
            'id': track_id,
            'bbox': list(detection['bbox']),
            'centroid': (float(centroid[0]), float(centroid[1])),
            'prev_centroid': None,
            'lane': lane_id,
            'label': detection.get('label'),
            'confidence': detection.get('confidence'),
            'first_seen_time': float(current_time),
            'first_seen_frame': int(frame_index),
            'last_seen_time': float(current_time),
            'last_seen_frame': int(frame_index),
            'seen_frames': 1,
            'missed_frames': 0,
            'counted': False,
            'counted_frame': None,
            'crossed_exit_line': False,
            'history': deque(maxlen=self.history_size),
        }
        track['history'].append(track['centroid'])
        self.tracked_objects[track_id] = track
        return track_id

    def _update_track(self, track_id, detection, current_time, frame_index):
        track = self.tracked_objects[track_id]
        previous_centroid = track['centroid']
        current_centroid = (float(detection['centroid'][0]), float(detection['centroid'][1]))
        crossed_now = False

        track['prev_centroid'] = previous_centroid
        track['bbox'] = list(detection['bbox'])
        track['centroid'] = current_centroid
        track['label'] = detection.get('label', track.get('label'))
        track['confidence'] = detection.get('confidence', track.get('confidence'))
        track['last_seen_time'] = float(current_time)
        track['last_seen_frame'] = int(frame_index)
        track['seen_frames'] = int(track.get('seen_frames', 0)) + 1
        track['missed_frames'] = 0
        track['history'].append(current_centroid)

        if track.get('lane') is None:
            lane_id = detection.get('lane') or self._assign_lane(current_centroid)
            if lane_id is not None:
                track['lane'] = lane_id

        lane_id = track.get('lane')
        if lane_id is not None and not track.get('counted', False) and previous_centroid is not None:
            crossed_exit_line = self._crossed_exit_line(previous_centroid, current_centroid, lane_id)
            crossed_exit_zone = self._in_exit_zone_or_near_boundary(current_centroid, lane_id)
            if crossed_exit_line or crossed_exit_zone:
                counted = self._count_track_once(
                    track_id,
                    lane_id,
                    current_centroid,
                    frame_index,
                    reason='exit_line' if crossed_exit_line else 'exit_zone_or_boundary',
                )
                if counted:
                    crossed_now = True
                else:
                    track['counted'] = True
                    track['counted_frame'] = int(frame_index)
                    track['crossed_exit_line'] = bool(crossed_exit_line)

        return track, crossed_now

    def _age_tracks(self, unmatched_track_ids):
        removed_track_ids = []
        for track_id in unmatched_track_ids:
            track = self.tracked_objects.get(track_id)
            if track is None:
                continue
            track['missed_frames'] = int(track.get('missed_frames', 0)) + 1
            if int(track['missed_frames']) > self.max_missed_frames:
                lane_id = track.get('lane')
                if lane_id in TRAFFIC_DIRECTIONS and not bool(track.get('counted', False)):
                    self._count_track_once(
                        track_id,
                        lane_id,
                        track.get('centroid', (0.0, 0.0)),
                        int(track.get('last_seen_frame', 0)),
                        reason='disappeared',
                    )
                removed_track_ids.append(track_id)

        for track_id in removed_track_ids:
            self.tracked_objects.pop(track_id, None)
        return removed_track_ids

    def _compute_lane_counts(self, current_time):
        raw_counts = {lane: 0 for lane in TRAFFIC_DIRECTIONS}
        wait_time_by_direction = {lane: 0.0 for lane in TRAFFIC_DIRECTIONS}
        queue_length_by_direction = {lane: 0 for lane in TRAFFIC_DIRECTIONS}
        active_tracks_by_lane = {lane: [] for lane in TRAFFIC_DIRECTIONS}

        for track in self.tracked_objects.values():
            lane_id = track.get('lane')
            if lane_id not in TRAFFIC_DIRECTIONS:
                continue
            if track.get('counted', False):
                continue
            if not self._is_confirmed(track):
                continue

            raw_counts[lane_id] += 1
            queue_length_by_direction[lane_id] += 1
            active_tracks_by_lane[lane_id].append(track)
            first_seen_time = float(track.get('first_seen_time', current_time))
            wait_time_by_direction[lane_id] += max(0.0, float(current_time) - first_seen_time)

        lane_state_raw = {}
        for lane_id in TRAFFIC_DIRECTIONS:
            lane_tracks = active_tracks_by_lane[lane_id]
            lane_state_raw[lane_id] = {
                'count': int(raw_counts[lane_id]),
                'hasAmbulance': any(str(track.get('label')).lower() == 'ambulance' for track in lane_tracks),
                'avgWaitTime': float(wait_time_by_direction[lane_id] / len(lane_tracks)) if lane_tracks else 0.0,
            }

        return lane_state_raw, raw_counts, wait_time_by_direction, queue_length_by_direction

    def _smooth_counts(self, raw_counts):
        smoothed_counts = {}
        for lane_id in TRAFFIC_DIRECTIONS:
            current_raw = float(raw_counts.get(lane_id, 0))
            history = self.count_history[lane_id]
            history.append(current_raw)
            history_average = sum(history) / len(history)
            previous = float(self.prev_smoothed_counts.get(lane_id, current_raw))

            if previous <= 0.0 and current_raw > 0.0:
                smoothed_value = current_raw
            else:
                smoothed_value = (self.smooth_alpha * previous) + ((1.0 - self.smooth_alpha) * history_average)

            delta = smoothed_value - previous
            if abs(delta) > float(self.max_count_jump):
                smoothed_value = previous + (float(self.max_count_jump) if delta > 0 else -float(self.max_count_jump))

            smoothed_value = max(0.0, smoothed_value)
            smoothed_int = int(round(smoothed_value))
            if current_raw > 0.0 and smoothed_int == 0:
                smoothed_int = 1

            self.prev_smoothed_counts[lane_id] = float(smoothed_int)
            smoothed_counts[lane_id] = smoothed_int

        return smoothed_counts

    def update(self, detections, current_time, frame_index):
        normalized_detections = []
        for detection in detections or []:
            bbox = detection.get('bbox')
            if not bbox or len(bbox) != 4:
                continue
            centroid = detection.get('center') or detection.get('centroid') or bbox_centroid(bbox)
            lane_id = detection.get('lane')
            if lane_id not in TRAFFIC_DIRECTIONS:
                lane_id = self._assign_lane(centroid)
            normalized_detections.append(
                {
                    'bbox': [float(value) for value in bbox],
                    'centroid': (float(centroid[0]), float(centroid[1])),
                    'lane': lane_id,
                    'label': detection.get('label'),
                    'confidence': detection.get('confidence'),
                }
            )

        matches, unmatched_track_ids, unmatched_detection_indices = self._match_detections(normalized_detections)
        new_track_ids = []
        crossed_track_ids = []

        for track_id, detection_index in matches:
            _, crossed_now = self._update_track(track_id, normalized_detections[detection_index], current_time, frame_index)
            if crossed_now:
                crossed_track_ids.append(track_id)

        removed_track_ids = self._age_tracks(unmatched_track_ids)

        for detection_index in unmatched_detection_indices:
            track_id = self._create_track(normalized_detections[detection_index], current_time, frame_index)
            new_track_ids.append(track_id)

        lane_state_raw, raw_counts, wait_time_by_direction, queue_length_by_direction = self._compute_lane_counts(current_time)
        smoothed_counts = self._smooth_counts(raw_counts)

        lane_state_smoothed = {
            lane_id: {
                'count': int(smoothed_counts[lane_id]),
                'hasAmbulance': bool(lane_state_raw[lane_id]['hasAmbulance']),
                'avgWaitTime': float(lane_state_raw[lane_id]['avgWaitTime']),
            }
            for lane_id in TRAFFIC_DIRECTIONS
        }

        tracked_detections = []
        for track in self.tracked_objects.values():
            lane_id = track.get('lane')
            if lane_id not in TRAFFIC_DIRECTIONS:
                continue
            if not self._is_confirmed(track):
                continue

            tracked_detections.append(
                {
                    'label': track.get('label'),
                    'confidence': track.get('confidence'),
                    'bbox': [float(value) for value in track.get('bbox', [0.0, 0.0, 0.0, 0.0])],
                    'center': [float(track['centroid'][0]), float(track['centroid'][1])],
                    'bottom_center': [float(track['centroid'][0]), float(track['centroid'][1])],
                    'lane': lane_id,
                    'track_id': track.get('id'),
                    'temp_id': track.get('id'),
                    'wait_time': max(0.0, float(current_time) - float(track.get('first_seen_time', current_time))),
                    'moving_toward_intersection': not bool(track.get('counted', False)),
                    'inside_lane': not bool(track.get('counted', False)),
                    'counted': bool(track.get('counted', False)),
                }
            )

        return {
            'raw_counts': raw_counts,
            'smoothed_counts': smoothed_counts,
            'lane_state_raw': lane_state_raw,
            'lane_state': lane_state_smoothed,
            'wait_time_by_direction': wait_time_by_direction,
            'queue_length_by_direction': queue_length_by_direction,
            'tracked_detections': tracked_detections,
            'new_track_ids': new_track_ids,
            'crossed_track_ids': crossed_track_ids,
            'removed_track_ids': removed_track_ids,
            'tracked_count': len(self.tracked_objects),
            'total_vehicles_crossed': int(self.total_vehicles_crossed),
            'crossed_by_lane': dict(self.crossed_by_lane),
        }


def update_virtual_line_counts(
    detections,
    virtual_lines,
    prev_positions,
    counted_ids_by_line,
    line_counts,
    waiting_time_by_vehicle,
    last_direction_by_vehicle,
    vehicle_speed_by_id,
    delta_time,
    active_green_lane=None,
    speed_threshold_px=WAIT_SPEED_THRESHOLD_PX,
):
    current_ids = set()

    for det in detections:
        track_id = det.get('track_id')
        bbox = det.get('bbox')
        if track_id is None or not bbox or len(bbox) != 4:
            continue

        vehicle_id = int(track_id)
        current_point = bottom_center_from_bbox(bbox)
        current_ids.add(vehicle_id)

        previous_point = prev_positions.get(vehicle_id)
        inferred_direction = infer_direction_for_point(current_point, virtual_lines)
        detected_direction = _normalize_direction_label(det.get('lane'))
        if detected_direction in TRAFFIC_DIRECTIONS:
            last_direction_by_vehicle[vehicle_id] = detected_direction
        elif inferred_direction in TRAFFIC_DIRECTIONS:
            last_direction_by_vehicle[vehicle_id] = inferred_direction

        tracked_direction = _normalize_direction_label(last_direction_by_vehicle.get(vehicle_id))

        crossed_any_line = False
        if previous_point is not None:
            speed = float(np.hypot(current_point[0] - previous_point[0], current_point[1] - previous_point[1]))
            vehicle_speed_by_id[vehicle_id] = speed
            
            for line in virtual_lines:
                line_id = line['id']
                direction = str(line.get('direction', '')).strip().lower()
                if vehicle_id in counted_ids_by_line[line_id]:
                    continue
                if has_crossed_line(previous_point, current_point, line['start'], line['end']):
                    if direction in line_counts:
                        line_counts[direction] += 1
                    counted_ids_by_line[line_id].add(vehicle_id)
                    crossed_any_line = True
        else:
            vehicle_speed_by_id[vehicle_id] = float('inf')

        if tracked_direction in TRAFFIC_DIRECTIONS:
            if vehicle_is_waiting(tracked_direction, active_green_lane):
                waiting_time_by_vehicle[vehicle_id] = float(waiting_time_by_vehicle.get(vehicle_id, 0.0)) + float(delta_time)
            else:
                waiting_time_by_vehicle[vehicle_id] = 0.0

        if crossed_any_line:
            waiting_time_by_vehicle[vehicle_id] = 0.0

        prev_positions[vehicle_id] = current_point

    # Remove stale tracks to avoid unbounded dictionary growth.
    for vehicle_id in list(prev_positions.keys()):
        if vehicle_id not in current_ids:
            prev_positions.pop(vehicle_id, None)
            waiting_time_by_vehicle.pop(vehicle_id, None)
            last_direction_by_vehicle.pop(vehicle_id, None)
            vehicle_speed_by_id.pop(vehicle_id, None)


def aggregate_wait_time_by_direction(waiting_time_by_vehicle, last_direction_by_vehicle):
    totals = {direction: 0.0 for direction in TRAFFIC_DIRECTIONS}
    for vehicle_id, wait_seconds in waiting_time_by_vehicle.items():
        direction = last_direction_by_vehicle.get(vehicle_id)
        if direction in totals:
            totals[direction] += float(wait_seconds)
    return totals


def draw_overlay(
    frame,
    lane_regions,
    lane_state,
    decision,
    detections,
    tick,
    virtual_lines=None,
    line_counts=None,
    wait_time_by_direction=None,
    queue_length_by_direction=None,
):
    overlay = frame.copy()
    active_lane = (decision or {}).get('lane')
    draw_lane_polygons(overlay, lane_regions, active_lane=active_lane, lane_state=lane_state)

    for line in virtual_lines or []:
        start = (int(line['start'][0]), int(line['start'][1]))
        end = (int(line['end'][0]), int(line['end'][1]))
        cv2.line(overlay, start, end, (0, 120, 255), 2, cv2.LINE_AA)
        line_id = line.get('id', 'line')
        direction = str(line.get('direction') or '').lower()
        count_value = int((line_counts or {}).get(direction, 0))
        label = f"{line_id} [{direction}]: {count_value}"
        cv2.putText(
            overlay,
            label,
            (start[0] + 8, max(20, start[1] - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 120, 255),
            2,
            cv2.LINE_AA,
        )

    for det in detections:
        x1, y1, x2, y2 = [int(v) for v in det['bbox']]
        lane = det.get('lane') or 'none'
        track_id = det.get('track_id')
        point = det.get('bbox_center') or det.get('center') or det.get('bottom_center')
        if isinstance(point, (list, tuple)) and len(point) == 2:
            px, py = int(float(point[0])), int(float(point[1]))
        else:
            px, py = int((x1 + x2) / 2), int((y1 + y2) / 2)

        dlabel = f"ID {track_id} | lane: {lane}" if track_id is not None else f"lane: {lane}"
        color = LANE_COLORS.get(str(lane).lower(), (220, 220, 0))
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
        cv2.circle(overlay, (px, py), 5, (0, 255, 0), -1)
        cv2.putText(overlay, dlabel, (x1, max(15, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 0), 1, cv2.LINE_AA)

    selected_lane = (decision or {}).get('lane', 'n/a')
    debug = (decision or {}).get('debug', {}) or {}
    total_crossings = int(sum(int((line_counts or {}).get(direction, 0)) for direction in TRAFFIC_DIRECTIONS))
    info = f"Tick {tick} | GREEN: {selected_lane} | Crossings: {total_crossings}"
    cv2.putText(overlay, info, (16, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)

    counts_text = (
        f"N:{int((lane_state or {}).get('north', {}).get('count', 0))} "
        f"S:{int((lane_state or {}).get('south', {}).get('count', 0))} "
        f"E:{int((lane_state or {}).get('east', {}).get('count', 0))} "
        f"W:{int((lane_state or {}).get('west', {}).get('count', 0))}"
    )
    cv2.putText(overlay, counts_text, (16, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2, cv2.LINE_AA)

    wait_text = (
        f"Wait N:{float((wait_time_by_direction or {}).get('north', 0.0)):.1f}s "
        f"S:{float((wait_time_by_direction or {}).get('south', 0.0)):.1f}s "
        f"E:{float((wait_time_by_direction or {}).get('east', 0.0)):.1f}s "
        f"W:{float((wait_time_by_direction or {}).get('west', 0.0)):.1f}s"
    )
    cv2.putText(overlay, wait_text, (16, 112), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 200, 80), 2, cv2.LINE_AA)

    queue_text = (
        f"Queue N:{int((queue_length_by_direction or {}).get('north', 0))} "
        f"S:{int((queue_length_by_direction or {}).get('south', 0))} "
        f"E:{int((queue_length_by_direction or {}).get('east', 0))} "
        f"W:{int((queue_length_by_direction or {}).get('west', 0))}"
    )
    cv2.putText(overlay, queue_text, (16, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (180, 255, 120), 2, cv2.LINE_AA)

    lane_metrics = debug.get('lane_metrics') or {}
    lane_scores = debug.get('lane_scores') or {}
    selected_metrics = lane_metrics.get(selected_lane, {}) if isinstance(selected_lane, str) else {}
    reason_text = (
        f"Reason: count={selected_metrics.get('vehicle_count', selected_metrics.get('count', 0))}, "
        f"wait={float(selected_metrics.get('avg_wait_time', selected_metrics.get('avgWaitTime', 0.0))):.1f}s"
    )
    if lane_scores:
        reason_text += f" | score={float(lane_scores.get(selected_lane, 0.0)):.2f}"
    cv2.putText(overlay, reason_text, (16, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
    return overlay


def run_pipeline(
    video_path,
    config_path,
    base_url,
    sample_fps,
    preview=False,
    output_video=None,
    smooth_alpha=0.6,
    session_id=None,
    select_homography_points=False,
):
    config = load_config(config_path)
    lane_regions = config['lane_regions']
    settings = config.get('settings', {})
    min_avg_confidence = 0.1
    max_count_jump = int(settings.get('max_count_jump', 3))
    confidence_hold_ticks = int(settings.get('confidence_hold_ticks', 1))
    smooth_alpha = 0.2
    smooth_alpha = max(0.0, min(1.0, smooth_alpha))
    queue_roi_depth_px = int(settings.get('queue_roi_depth_px', DEFAULT_QUEUE_ROI_DEPTH_PX))

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    sample_every_n = max(1, int(round(fps / sample_fps)))
    tick_seconds = sample_every_n / fps
    frame_delta_time = 1.0 / fps

    timer_duration = config.get('timer_duration') or estimate_timer_duration(video_path)
    if session_id:
        print(f"PIPELINE session_id: {session_id}")
    else:
        session = post_json(f"{base_url}/simulation/start", {'timer_duration': int(timer_duration)})
        session_id = session['session_id']
        print(f"PIPELINE session_id: {session_id}")

    print(f"Session started: {session_id}")
    print(f"Video FPS: {fps:.2f}, sample every {sample_every_n} frames ({tick_seconds:.2f}s)")

    frame_index = 0
    tick = 0
    events = []
    run_start_ms = int(time.time() * 1000)
    smoothed_lane_state = {lane: {} for lane in ('north', 'east', 'south', 'west')}
    low_confidence_streak = 0
    active_tracks = set()
    previous_frame_tracks = set()
    track_metadata = {}
    pending_vehicle_added = set()
    pending_vehicle_crossed = set()
    writer = None
    active_green_lane = None
    phase_start_time = 0.0
    signal_phases = []

    detect_width = 640
    detect_height = 360
    capture_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or detect_width)
    capture_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or detect_height)
    scale_x = float(detect_width) / float(capture_width)
    scale_y = float(detect_height) / float(capture_height)
    inv_scale_x = float(capture_width) / float(detect_width)
    inv_scale_y = float(capture_height) / float(detect_height)

    virtual_lines = build_virtual_lines(config, capture_width, capture_height)
    queue_rois = build_queue_rois(virtual_lines, capture_width, capture_height, depth_px=queue_roi_depth_px)
    prev_positions = {}
    counted_ids_by_line = {line['id']: set() for line in virtual_lines}
    line_counts = {
        'north': 0,
        'south': 0,
        'east': 0,
        'west': 0,
    }
    waiting_time_by_vehicle = {}
    last_direction_by_vehicle = {}
    vehicle_speed_by_id = {}
    wait_time_by_direction = {direction: 0.0 for direction in TRAFFIC_DIRECTIONS}
    queue_length_by_direction = {direction: 0 for direction in TRAFFIC_DIRECTIONS}
    previous_counts = [0.0, 0.0, 0.0, 0.0]

    homography_mapper_detect = build_homography_mapper(
        config,
        cap,
        detect_width,
        detect_height,
        scale_x=scale_x,
        scale_y=scale_y,
        select_points=select_homography_points,
    )

    def scale_lane_regions_for_detection(regions):
        scaled = {}
        for lane_key, lane_region in (regions or {}).items():
            points = lane_region.get('points', []) if isinstance(lane_region, dict) else lane_region
            scaled_points = [[float(point[0]) * scale_x, float(point[1]) * scale_y] for point in points]
            if isinstance(lane_region, dict):
                scaled[lane_key] = {
                    **lane_region,
                    'points': scaled_points,
                    'polygon': scaled_points,
                    'center': None,
                    'bounds': None,
                    'polygon_cv2': None,
                }
            else:
                scaled[lane_key] = scaled_points
        return scaled

    scaled_lane_regions = scale_lane_regions_for_detection(lane_regions)

    default_lane_state = {
        lane: {'count': 0, 'hasAmbulance': False, 'avgWaitTime': 0.0}
        for lane in ('north', 'east', 'south', 'west')
    }

    last_lane_state_raw = {lane: values.copy() for lane, values in default_lane_state.items()}
    last_lane_state = {lane: {'count': 0, 'hasAmbulance': False, 'avgWaitTime': 0.0} for lane in ('north', 'east', 'south', 'west')}
    last_detections = []
    last_decision = {'lane': 'north', 'duration': 10, 'debug': {}}
    last_overlay = None

    shared_lock = threading.Lock()
    stop_event = threading.Event()
    shared_state = {
        'latest_frame': None,
        'latest_frame_seq': -1,
        'latest_frame_time': 0.0,
        'latest_detection_seq': -1,
        'latest_detections': [],
        'latest_lane_state': {lane: values.copy() for lane, values in default_lane_state.items()},
        'latest_lane_state_seq': -1,
        'latest_rl_lane_state': {lane: values.copy() for lane, values in default_lane_state.items()},
        'latest_rl_lane_state_seq': -1,
        'latest_decision': last_decision,
        'latest_decision_seq': -1,
        'active_green_lane': None,
        'latest_warped_debug': None,
        'latest_line_counts': {direction: 0 for direction in TRAFFIC_DIRECTIONS},
        'latest_wait_time_by_direction': {direction: 0.0 for direction in TRAFFIC_DIRECTIONS},
        'latest_queue_length_by_direction': {direction: 0 for direction in TRAFFIC_DIRECTIONS},
        'latest_signal_phases': [],
    }

    tracker = SimpleVehicleTracker(
        lane_regions,
        min_seen_frames=int(settings.get('tracker_min_seen_frames', 2)),
        max_missed_frames=int(settings.get('tracker_max_missed_frames', 8)),
        match_iou_threshold=0.15,
        match_distance_px=90.0,
        history_size=5,
        smooth_alpha=0.7,
        max_count_jump=max_count_jump,
    )

    show_preview = bool(preview)

    def detection_worker():
        last_processed_seq = -1
        while not stop_event.is_set():
            with shared_lock:
                frame = shared_state['latest_frame']
                frame_seq = shared_state['latest_frame_seq']
                frame_time = shared_state['latest_frame_time']
                worker_active_lane = shared_state['active_green_lane']

            if frame is None or frame_seq == last_processed_seq:
                time.sleep(0.002)
                continue

            detection_frame = cv2.resize(frame, (detect_width, detect_height), interpolation=cv2.INTER_LINEAR)
            lane_state_raw_detect, detections_detect = detect_vehicles_in_frame(
                detection_frame,
                scaled_lane_regions,
                return_debug=True,
                current_time=frame_time,
                active_green_lane=worker_active_lane,
                homography_mapper=homography_mapper_detect,
            )
            print("FRAME ID:", frame_seq)
            print("DETECTED OBJECTS:", detections_detect)

            lane_state_raw = {}
            for lane_id, lane_data in lane_state_raw_detect.items():
                lane_state_raw[lane_id] = {
                    'count': int(lane_data.get('count', 0)),
                    'hasAmbulance': bool(lane_data.get('hasAmbulance', False)),
                    'avgWaitTime': float(lane_data.get('avgWaitTime', 0.0)),
                }

            scaled_detections = []
            for det in detections_detect:
                bbox = det.get('bbox') or [0.0, 0.0, 0.0, 0.0]
                center = det.get('center') or [0.0, 0.0]
                top_view_center = det.get('top_view_center') or [float(center[0]), float(center[1])]
                scaled_detections.append(
                    {
                        **det,
                        'bbox': [
                            float(bbox[0]) * inv_scale_x,
                            float(bbox[1]) * inv_scale_y,
                            float(bbox[2]) * inv_scale_x,
                            float(bbox[3]) * inv_scale_y,
                        ],
                        'center': [float(center[0]) * inv_scale_x, float(center[1]) * inv_scale_y],
                        'top_view_center': [float(top_view_center[0]), float(top_view_center[1])],
                    }
                )

            warped_debug = None
            if homography_mapper_detect is not None:
                lane_counts = {
                    'north': int(lane_state_raw_detect.get('north', {}).get('count', 0)),
                    'south': int(lane_state_raw_detect.get('south', {}).get('count', 0)),
                    'east': int(lane_state_raw_detect.get('east', {}).get('count', 0)),
                    'west': int(lane_state_raw_detect.get('west', {}).get('count', 0)),
                }
                transformed_points = [
                    {
                        'lane': det.get('lane'),
                        'top_view': det.get('top_view_center'),
                    }
                    for det in detections_detect
                ]
                warped = homography_mapper_detect.warp_frame(detection_frame)
                warped_debug = homography_mapper_detect.draw_debug(warped, transformed_points, lane_counts)

            with shared_lock:
                shared_state['latest_detections'] = scaled_detections
                shared_state['latest_lane_state'] = lane_state_raw
                shared_state['latest_lane_state_seq'] = frame_seq
                shared_state['latest_detection_seq'] = frame_seq
                shared_state['latest_warped_debug'] = warped_debug

            last_processed_seq = frame_seq

    detection_thread = threading.Thread(target=detection_worker, name='detection_thread', daemon=True)

    reset_tracking_state()
    tracker.reset()

    if output_video:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720)
        writer = cv2.VideoWriter(str(output_video), fourcc, max(1.0, sample_fps), (width, height))

    if show_preview:
        cv2.namedWindow('Traffic RL Output', cv2.WINDOW_NORMAL)

    detection_thread.start()

    last_processed_detection_seq = -1
    active_vehicles = {}
    max_missing_frames = 10
    last_counts = {lane: 0 for lane in TRAFFIC_DIRECTIONS}
    last_tracked_detection_result = {
        'raw_counts': {lane: 0 for lane in TRAFFIC_DIRECTIONS},
        'smoothed_counts': {lane: 0 for lane in TRAFFIC_DIRECTIONS},
        'lane_state_raw': {lane: {'count': 0, 'hasAmbulance': False, 'avgWaitTime': 0.0} for lane in TRAFFIC_DIRECTIONS},
        'lane_state': {lane: {'count': 0, 'hasAmbulance': False, 'avgWaitTime': 0.0} for lane in TRAFFIC_DIRECTIONS},
        'wait_time_by_direction': {lane: 0.0 for lane in TRAFFIC_DIRECTIONS},
        'queue_length_by_direction': {lane: 0 for lane in TRAFFIC_DIRECTIONS},
        'tracked_detections': [],
        'new_track_ids': [],
        'removed_track_ids': [],
        'tracked_count': 0,
        'total_vehicles_crossed': 0,
        'crossed_by_lane': {lane: 0 for lane in TRAFFIC_DIRECTIONS},
    }

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            current_time = frame_index / fps
            with shared_lock:
                shared_state['latest_frame'] = frame.copy()
                shared_state['latest_frame_seq'] = frame_index
                shared_state['latest_frame_time'] = current_time

            with shared_lock:
                live_detection_seq = shared_state['latest_detection_seq']
                live_detections = shared_state['latest_detections']

            if live_detection_seq != last_processed_detection_seq:
                last_tracked_detection_result = tracker.update(live_detections, current_time, frame_index)
                last_processed_detection_seq = live_detection_seq
                last_lane_state_raw = last_tracked_detection_result['lane_state_raw']
                last_lane_state = last_tracked_detection_result['lane_state']
                last_detections = last_tracked_detection_result['tracked_detections']
                line_counts = dict(last_tracked_detection_result['crossed_by_lane'])
                wait_time_by_direction = dict(last_tracked_detection_result['wait_time_by_direction'])
                queue_length_by_direction = dict(last_tracked_detection_result['queue_length_by_direction'])
                pending_vehicle_added.update(str(track_id) for track_id in last_tracked_detection_result.get('new_track_ids', []))
                pending_vehicle_crossed.update(str(track_id) for track_id in last_tracked_detection_result.get('crossed_track_ids', []))
                new_crossings_this_frame = len(last_tracked_detection_result.get('crossed_track_ids', []))

                with shared_lock:
                    shared_state['latest_detections'] = list(last_detections)
                    shared_state['latest_lane_state'] = {
                        lane: dict(values) for lane, values in last_lane_state.items()
                    }
                    shared_state['latest_lane_state_seq'] = frame_index
                    shared_state['latest_line_counts'] = dict(line_counts)
                    shared_state['latest_wait_time_by_direction'] = dict(wait_time_by_direction)
                    shared_state['latest_queue_length_by_direction'] = dict(queue_length_by_direction)
                    shared_state['latest_signal_phases'] = list(signal_phases)

            detections = list(live_detections or [])
            tracks = list(last_tracked_detection_result.get('tracked_detections', []) or [])

            print("\n--- FRAME START ---")
            print("DETECTIONS:", len(detections))
            print("TRACKS:", len(tracks))
            if len(tracks) == 0:
                print("TRACKER EMPTY")

            for track in tracks:
                center = get_center(track)
                if center is None:
                    continue
                cx, cy = center
                lane = get_lane((cx, cy))
                if lane not in TRAFFIC_DIRECTIONS:
                    continue
                track_id = (
                    track.get('track_id')
                    or track.get('temp_id')
                    or track.get('id')
                    or f"track_{int(cx)}_{int(cy)}"
                )
                active_vehicles[str(track_id)] = {
                    'lane': lane,
                    'last_seen': int(frame_index),
                }

            active_vehicles = {
                track_id: data
                for track_id, data in active_vehicles.items()
                if int(frame_index) - int(data.get('last_seen', -10**9)) <= max_missing_frames
            }

            current_counts = {
                'north': 0,
                'south': 0,
                'east': 0,
                'west': 0,
            }
            print("LANE ASSIGNMENT INPUT:", tracks)
            print("LANE COUNTS BEFORE:", current_counts)
            print("INITIAL COUNTS:", current_counts)

            for vehicle in active_vehicles.values():
                lane = vehicle.get('lane')
                if lane in current_counts:
                    current_counts[lane] += 1

            print("LANE COUNTS AFTER:", current_counts)

            # Fallback to tracker-derived lane counts when per-track mapping collapses unexpectedly.
            tracker_lane_counts = build_lane_counts_from_detections(tracks)
            if sum(current_counts.values()) == 0 and sum(tracker_lane_counts.values()) > 0:
                print("LANE COUNT FALLBACK (tracker):", tracker_lane_counts)
                current_counts = {
                    'north': int(tracker_lane_counts.get('north', 0)),
                    'south': int(tracker_lane_counts.get('south', 0)),
                    'east': int(tracker_lane_counts.get('east', 0)),
                    'west': int(tracker_lane_counts.get('west', 0)),
                }

            # Secondary fallback from tracker-smoothed counts if active map and tracked detections are empty.
            if sum(current_counts.values()) == 0:
                smoothed_counts = last_tracked_detection_result.get('smoothed_counts', {}) or {}
                if any(int(smoothed_counts.get(direction, 0) or 0) > 0 for direction in TRAFFIC_DIRECTIONS):
                    print("LANE COUNT FALLBACK (smoothed):", smoothed_counts)
                    current_counts = {
                        'north': int(smoothed_counts.get('north', 0) or 0),
                        'south': int(smoothed_counts.get('south', 0) or 0),
                        'east': int(smoothed_counts.get('east', 0) or 0),
                        'west': int(smoothed_counts.get('west', 0) or 0),
                    }

            print("ACTIVE VEHICLES:", len(active_vehicles))
            if sum(current_counts.values()) == 0 and len(active_vehicles) > 0:
                print("Using memory fallback")
                current_counts = last_counts.copy()

            if sum(current_counts.values()) == 0 and len(active_vehicles) == 0:
                print("NO VEHICLES → sending zeros (no skip)")

            last_counts = current_counts.copy()
            print("LANE COUNTS:", current_counts)
            final_counts_array = [
                int(current_counts.get("north", 0)),
                int(current_counts.get("south", 0)),
                int(current_counts.get("east", 0)),
                int(current_counts.get("west", 0)),
            ]
            
            from backend.state.simulation_state import latest_results, latest_results_lock

            with latest_results_lock:
                latest_results["lane_counts"] = final_counts_array

            print("STORE UPDATE:", final_counts_array)
            payload = {
                'lane_counts': [
                    int(current_counts.get('north', 0)),
                    int(current_counts.get('south', 0)),
                    int(current_counts.get('east', 0)),
                    int(current_counts.get('west', 0)),
                ],
                'source': 'video_pipeline',
                'rl_call_timestamp': time.time(),
            }
            print("SENDING TO RL lane_counts:", payload['lane_counts'])
            print("FINAL RL PAYLOAD:", payload)
            print("RL CALL TIMESTAMP:", payload['rl_call_timestamp'])
            print(f"[LIVE RL INPUT] {payload}")
            print("LIVE COUNTS:", current_counts)
            try:
                live_decision = post_json(f"{base_url}/rl/decision", payload)
            except Exception as exc:
                print(f"[LIVE RL ERROR] {exc} - using fallback decision")
                live_decision = {'lane': 'north', 'duration': 10}

            if not isinstance(live_decision, dict):
                print("[LIVE RL ERROR] Invalid RL decision type - using fallback decision")
                live_decision = {'lane': 'north', 'duration': 10}

            print("RL OUTPUT:", live_decision)
            with shared_lock:
                shared_state['latest_decision'] = live_decision
                shared_state['latest_decision_seq'] = frame_index
                shared_state['latest_rl_lane_state'] = {
                    lane: dict(values) for lane, values in last_lane_state.items()
                }
                shared_state['latest_rl_lane_state_seq'] = frame_index

            sample_due = frame_index % sample_every_n == 0
            if sample_due:
                print("\n==================== TICK ====================")
                print(f"Frame: {frame_index}, Tick: {tick}")
                with shared_lock:
                    lane_state_raw = shared_state['latest_lane_state']
                    detections = shared_state['latest_detections']
                    decision = shared_state['latest_decision']
                    warped_debug = shared_state['latest_warped_debug']

                print("RAW LANE STATE:", lane_state_raw)

                if lane_state_raw:
                    last_lane_state_raw = lane_state_raw
                else:
                    lane_state_raw = last_lane_state_raw

                if detections:
                    last_detections = detections
                else:
                    detections = last_detections

                if decision:
                    last_decision = decision
                else:
                    decision = last_decision

                average_confidence = (
                    sum(det['confidence'] for det in detections if det.get('confidence') is not None) / len(detections)
                    if detections else 0.0
                )
                print("AVG CONFIDENCE:", average_confidence)

                if average_confidence < min_avg_confidence:
                    low_confidence_streak += 1
                    lane_state = last_lane_state
                    detections_for_overlay = []
                    print("LOW CONFIDENCE → USING OLD STATE")
                else:
                    low_confidence_streak = 0
                    detections_for_overlay = detections

                lane_state = last_lane_state

                tracked_ids = sorted(int(track_id) for track_id in tracker.tracked_objects.keys())
                new_crossings_this_frame = len(last_tracked_detection_result.get('crossed_track_ids', []))
                print("Tracked IDs:", tracked_ids)
                print("Tracked vehicles:", len(tracker.tracked_objects))
                print("Lane counts (raw):", last_tracked_detection_result['raw_counts'])
                print("Lane counts (smoothed):", last_tracked_detection_result['smoothed_counts'])
                print("Vehicles crossed:", last_tracked_detection_result['total_vehicles_crossed'])
                print("Crossed total:", last_tracked_detection_result['total_vehicles_crossed'])
                print("New crossings:", new_crossings_this_frame)
                print("SMOOTHED LANE STATE:", lane_state)
                print("DETECTIONS:", detections_for_overlay)
                print("LINE COUNTS:", line_counts)
                print("WAIT TIME:", wait_time_by_direction)
                print("QUEUE LENGTH:", queue_length_by_direction)
                print("WAIT TIMES:", wait_time_by_direction)
                print("QUEUES:", queue_length_by_direction)
                with shared_lock:
                    shared_state['latest_line_counts'] = dict(line_counts)
                    shared_state['latest_wait_time_by_direction'] = dict(wait_time_by_direction)
                    shared_state['latest_queue_length_by_direction'] = dict(queue_length_by_direction)
                    # Ensure RL worker snapshots use corrected lane_state.
                    shared_state['latest_lane_state'] = {
                        lane: dict(values) for lane, values in lane_state.items()
                    }
                    shared_state['latest_lane_state_seq'] = frame_index
                    shared_state['latest_rl_lane_state'] = {
                        lane: dict(values) for lane, values in lane_state.items()
                    }
                    shared_state['latest_rl_lane_state_seq'] = frame_index
                smoothed_lane_state = lane_state
                last_lane_state = lane_state

                decision = live_decision
                print("RL DECISION:", decision)

                next_green_lane = decision.get('lane') if isinstance(decision, dict) else None
                if next_green_lane != active_green_lane:
                    if active_green_lane is not None:
                        phase_duration = max(0.0, float(current_time) - float(phase_start_time))
                        signal_phases.append(
                            {
                                'lane': str(active_green_lane),
                                'duration': float(phase_duration),
                            }
                        )
                        events.append(
                            {
                                'eventType': 'signal_phase',
                                'laneId': str(active_green_lane),
                                'timestamp': run_start_ms + int(current_time * 1000),
                                'payload': {
                                    'lane': str(active_green_lane),
                                    'duration': float(phase_duration),
                                },
                            }
                        )
                    print(f"SWITCHING SIGNAL: {active_green_lane} → {next_green_lane}")
                    active_green_lane = next_green_lane
                    phase_start_time = float(current_time)
                    with shared_lock:
                        shared_state['active_green_lane'] = active_green_lane
                        shared_state['latest_signal_phases'] = list(signal_phases)

                print("\n===== RL DEBUG =====")
                print("LINE COUNTS:", line_counts)
                print("QUEUE:", queue_length_by_direction)
                print("WAIT:", wait_time_by_direction)
                print("LANE STATE:", lane_state)
                print("DECISION:", decision)
                print("====================\n")

                # Flush tracker-backed lifecycle events on the sample tick.
                event_ts = run_start_ms + int(current_time * 1000)

                for det in last_tracked_detection_result['tracked_detections']:
                    track_id = det.get('track_id')
                    lane_id = det.get('lane')
                    label = det.get('label')
                    if track_id is None or not lane_id:
                        continue

                    vehicle_id = str(track_id)
                    track_metadata[vehicle_id] = {
                        'laneId': lane_id,
                        'vehicleType': label,
                    }

                for vehicle_id in sorted(pending_vehicle_added):
                    metadata = track_metadata.get(vehicle_id, {})
                    events.append(
                        {
                            'eventType': 'vehicle_added',
                            'vehicleId': vehicle_id,
                            'vehicleType': metadata.get('vehicleType'),
                            'laneId': metadata.get('laneId'),
                            'timestamp': event_ts,
                            'payload': {},
                        }
                    )
                    active_tracks.add(vehicle_id)
                    pending_vehicle_added.discard(vehicle_id)

                for vehicle_id in sorted(pending_vehicle_crossed):
                    metadata = track_metadata.get(vehicle_id, {})
                    events.append(
                        {
                            'eventType': 'vehicle_crossed',
                            'vehicleId': vehicle_id,
                            'vehicleType': metadata.get('vehicleType'),
                            'laneId': metadata.get('laneId'),
                            'timestamp': event_ts,
                            'payload': {},
                        }
                    )
                    active_tracks.discard(vehicle_id)
                    track_metadata.pop(vehicle_id, None)
                    pending_vehicle_crossed.discard(vehicle_id)

                snapshot = build_snapshot(
                    lane_state,
                    timestamp=current_time,
                    active_green_lane=active_green_lane,
                    line_counts=line_counts,
                    wait_time_by_direction=wait_time_by_direction,
                    queue_length_by_direction=queue_length_by_direction,
                    signal_phases=signal_phases,
                )
                overlay = draw_overlay(
                    frame,
                    lane_regions,
                    lane_state,
                    decision,
                    detections_for_overlay,
                    tick,
                    virtual_lines=virtual_lines,
                    line_counts=line_counts,
                    wait_time_by_direction=wait_time_by_direction,
                    queue_length_by_direction=queue_length_by_direction,
                )
                last_overlay = overlay

                if warped_debug is not None and show_preview:
                    cv2.imshow('Traffic Top-View Debug', warped_debug)

                lane_counts_for_log = {
                    'north': int(lane_state.get('north', {}).get('count', 0)),
                    'south': int(lane_state.get('south', {}).get('count', 0)),
                    'east': int(lane_state.get('east', {}).get('count', 0)),
                    'west': int(lane_state.get('west', {}).get('count', 0)),
                }
                if DEBUG_MODE and tick % 30 == 0:
                    print(f"[LANES] north={lane_counts_for_log['north']} south={lane_counts_for_log['south']} "
                          f"east={lane_counts_for_log['east']} west={lane_counts_for_log['west']}")
                if tick % 60 == 0:
                    north_wait = float(lane_state.get('north', {}).get('avgWaitTime', 0.0))
                    south_wait = float(lane_state.get('south', {}).get('avgWaitTime', 0.0))
                    east_wait = float(lane_state.get('east', {}).get('avgWaitTime', 0.0))
                    west_wait = float(lane_state.get('west', {}).get('avgWaitTime', 0.0))
                    print(f"[WAIT TIMES] north={north_wait:.1f}s south={south_wait:.1f}s "
                          f"east={east_wait:.1f}s west={west_wait:.1f}s")

                event_ts = run_start_ms + int(tick * tick_seconds * 1000)
                events.append(
                    {
                        'eventType': 'rl_decision',
                        'laneId': decision.get('lane') if isinstance(decision, dict) else None,
                        'timestamp': event_ts,
                        'payload': {
                            'tick': tick,
                            'snapshot': snapshot,
                            'raw_lane_state': last_tracked_detection_result['lane_state_raw'],
                            'smoothed_lane_state': lane_state,
                            'average_confidence': average_confidence,
                            'confidence_filtered': average_confidence < min_avg_confidence,
                            'low_confidence_streak': low_confidence_streak,
                            'confidence_hold_ticks': confidence_hold_ticks,
                            'decision': decision,
                            'source': 'video-prototype',
                        },
                    }
                )
                tick += 1

                if tick * tick_seconds >= timer_duration:
                    break

                overlay_to_show = last_overlay if last_overlay is not None else frame
                if writer is not None:
                    writer.write(overlay_to_show)
                if show_preview:
                    cv2.imshow('Traffic RL Output', overlay_to_show)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

            frame_index += 1
    finally:
        stop_event.set()
        detection_thread.join(timeout=2.0)

    cap.release()

    if active_green_lane is not None:
        final_phase_duration = max(0.0, (float(frame_index) / float(max(fps, 1e-6))) - float(phase_start_time))
        signal_phases.append(
            {
                'lane': str(active_green_lane),
                'duration': float(final_phase_duration),
            }
        )
        events.append(
            {
                'eventType': 'signal_phase',
                'laneId': str(active_green_lane),
                'timestamp': run_start_ms + int((frame_index / max(fps, 1e-6)) * 1000),
                'payload': {
                    'lane': str(active_green_lane),
                    'duration': float(final_phase_duration),
                },
            }
        )

    # Flush any pending tracker lifecycle events at end of run.
    final_event_ts = run_start_ms + int((frame_index / fps) * 1000)
    for vehicle_id in sorted(pending_vehicle_added):
        metadata = track_metadata.get(vehicle_id, {})
        events.append(
            {
                'eventType': 'vehicle_added',
                'vehicleId': vehicle_id,
                'vehicleType': metadata.get('vehicleType'),
                'laneId': metadata.get('laneId'),
                'timestamp': final_event_ts,
                'payload': {},
            }
        )
    for vehicle_id in sorted(pending_vehicle_crossed):
        metadata = track_metadata.get(vehicle_id, {})
        events.append(
            {
                'eventType': 'vehicle_crossed',
                'vehicleId': vehicle_id,
                'vehicleType': metadata.get('vehicleType'),
                'laneId': metadata.get('laneId'),
                'timestamp': final_event_ts,
                'payload': {},
            }
        )
        track_metadata.pop(vehicle_id, None)

    if writer is not None:
        writer.release()
    if show_preview:
        cv2.destroyAllWindows()

    submit_url = f"{base_url}/simulation/submit-log"
    submit_payload = {'session_id': session_id, 'events': events}
    print("[POST SUBMIT]", submit_payload)
    print("[POST URL]", submit_url)
    submit_result = post_json(submit_url, submit_payload)
    print("[POST RESPONSE]", submit_result)

    if not isinstance(submit_result, dict) or submit_result.get('success') is not True:
        print(f"[POST ERROR] Failed to save simulation results for session {session_id}: {submit_result}")
        raise RuntimeError(f"Failed to save simulation results for session {session_id}: {submit_result}")

    print(f"Submitted {len(events)} decision events for session {session_id}")
    print(f"Submit result: {submit_result}")
    print(f"Decision logs endpoint: {base_url}/simulation/decision-log/{session_id}")
    print(f"Dashboard route: /dashboard/{session_id}")


main_pipeline_function = run_pipeline


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run video-to-RL prototype pipeline')
    parser.add_argument('--video', required=True, help='Path to input video file')
    parser.add_argument('--config', required=True, help='Path to lane config json')
    parser.add_argument('--base-url', default='http://localhost:8000', help='Backend API base URL')
    parser.add_argument('--sample-fps', type=float, default=5.0, help='How often to sample frames for decisions')
    parser.add_argument('--smooth-alpha', type=float, default=0.6, help='Smoothing factor for lane state [0..1]')
    parser.add_argument('--preview', action='store_true', help='Show real-time overlay preview (press q to stop)')
    parser.add_argument('--output-video', default='', help='Optional path to save overlay output video')
    parser.add_argument('--session-id', default='', help='Existing session id to reuse for submit-log and results')
    parser.add_argument(
        '--select-homography-points',
        action='store_true',
        help='Interactively select 4 source points from the first frame (TL,TR,BR,BL)',
    )
    args = parser.parse_args()

    run_pipeline(
        video_path=Path(args.video),
        config_path=Path(args.config),
        base_url=args.base_url.rstrip('/'),
        sample_fps=max(0.5, args.sample_fps),
        preview=args.preview,
        output_video=Path(args.output_video) if args.output_video else None,
        smooth_alpha=max(0.0, min(1.0, args.smooth_alpha)),
        session_id=args.session_id.strip() or None,
        select_homography_points=args.select_homography_points,
    )
