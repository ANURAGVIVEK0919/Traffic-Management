import math
import json
import shutil
from pathlib import Path

import cv2
import numpy as np

LANE_ORDER = ['north', 'east', 'south', 'west']
LANE_COLORS = {
    'north': (0, 255, 255),
    'east': (0, 165, 255),
    'south': (255, 0, 255),
    'west': (255, 128, 0),
}


def polygon_points(region):
    if isinstance(region, dict):
        return region.get('polygon') or region.get('points') or []
    return region or []


def polygon_bounds(points):
    if not points:
        return None
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def polygon_to_cv2(points):
    if not points:
        return None
    return np.array([(float(point[0]), float(point[1])) for point in points], dtype=np.int32)


def compute_polygon_center(points):
    count = len(points)
    if count == 0:
        return 0.0, 0.0
    sum_x = sum(float(point[0]) for point in points)
    sum_y = sum(float(point[1]) for point in points)
    return sum_x / count, sum_y / count


def compute_lane_label(points, frame_shape):
    height, width = frame_shape[:2]
    lane_x, lane_y = compute_polygon_center(points)
    center_x = width / 2.0
    center_y = height / 2.0
    dx = lane_x - center_x
    dy = center_y - lane_y
    angle = math.degrees(math.atan2(dy, dx))

    if -45 <= angle < 45:
        return 'east'
    if 45 <= angle < 135:
        return 'north'
    if angle >= 135 or angle < -135:
        return 'west'
    return 'south'


def prepare_lane_geometry(points):
    if not isinstance(points, list):
        raise ValueError('Lane points must be provided as a list')

    if not points:
        raise ValueError('Lane polygon must contain at least 2 points')

    # Already polygon format: [[x, y], [x, y], ...]
    if all(isinstance(point, (list, tuple)) and len(point) == 2 for point in points):
        normalized_points = [[float(point[0]), float(point[1])] for point in points]
    else:
        # Flat format: [x1, y1, x2, y2, ...] -> [[x1, y1], [x2, y2], ...]
        if len(points) % 2 != 0:
            raise ValueError('Flat lane points list must contain an even number of values')
        if not all(isinstance(value, (int, float)) for value in points):
            raise ValueError('Flat lane points list must contain only numeric values')
        normalized_points = [
            [float(points[index]), float(points[index + 1])]
            for index in range(0, len(points), 2)
        ]

    if len(normalized_points) < 2:
        raise ValueError('Lane polygon must contain at least 2 points')

    return {
        'polygon': normalized_points,
        'points': normalized_points,
        'center': compute_polygon_center(normalized_points),
        'bounds': polygon_bounds(normalized_points),
        'polygon_cv2': polygon_to_cv2(normalized_points),
    }


def resize_polygon(points, frame_shape, width_scale=1.0, depth_scale=1.0, depth_offset_px=0.0):
    if not points:
        return []

    center_x, center_y = compute_polygon_center(points)
    frame_center_x = frame_shape[1] / 2.0
    frame_center_y = frame_shape[0] / 2.0
    vector_x = center_x - frame_center_x
    vector_y = center_y - frame_center_y
    vector_length = math.hypot(vector_x, vector_y)
    if vector_length > 0:
        unit_x = vector_x / vector_length
        unit_y = vector_y / vector_length
    else:
        unit_x = 0.0
        unit_y = 0.0

    offset_x = unit_x * float(depth_offset_px)
    offset_y = unit_y * float(depth_offset_px)

    resized = []
    for point in points:
        px = float(point[0]) - center_x
        py = float(point[1]) - center_y
        scaled_x = px * float(width_scale)
        scaled_y = py * float(depth_scale)
        resized.append([int(round(center_x + offset_x + scaled_x)), int(round(center_y + offset_y + scaled_y))])
    return resized


def make_lane_region(points, frame_shape, flow_direction='incoming', lane_id=None, label=None):
    geometry = prepare_lane_geometry(points)
    region_label_value = label or compute_lane_label(points, frame_shape)
    region_id = lane_id or region_label_value
    return {
        'id': region_id,
        'label': region_label_value,
        'direction': flow_direction,
        'polygon': geometry['polygon'],
        'points': geometry['points'],
        'center': geometry['center'],
        'bounds': geometry['bounds'],
        'polygon_cv2': geometry['polygon_cv2'],
    }


def region_points(region):
    if isinstance(region, dict):
        return polygon_points(region)
    return region or []


def region_id(region, fallback=None):
    if isinstance(region, dict):
        return region.get('id') or fallback
    return fallback


def region_label(region, fallback=None):
    if isinstance(region, dict):
        return region.get('label') or region.get('direction') or fallback
    return fallback


def region_direction(region, fallback='incoming'):
    if isinstance(region, dict):
        return region.get('direction') or fallback
    return fallback


def normalize_lane_regions(lane_regions, frame_shape=None):
    normalized = {}
    if isinstance(lane_regions, list):
        lane_items = []
        for index, region in enumerate(lane_regions):
            lane_key = region.get('label') if isinstance(region, dict) else None
            if lane_key not in LANE_ORDER:
                lane_key = region.get('id') if isinstance(region, dict) else None
            lane_key = lane_key or f'lane_{index + 1}'
            lane_items.append((lane_key, region))
    else:
        lane_items = list((lane_regions or {}).items())

    for lane_key, region in lane_items:
        points = region_points(region)
        raw_label = region_label(region, lane_key)
        raw_direction = region_direction(region)
        canonical_key = raw_label if raw_label in LANE_ORDER else lane_key
        if canonical_key not in LANE_ORDER and isinstance(region, dict):
            region_id_value = region_id(region, lane_key)
            if region_id_value in LANE_ORDER:
                canonical_key = region_id_value
        if isinstance(region, dict) and 'label' not in region and raw_direction in LANE_ORDER:
            label = raw_direction
            direction = 'incoming'
        else:
            label = raw_label or lane_key
            direction = raw_direction or 'incoming'
        geometry = prepare_lane_geometry(points)
        normalized[canonical_key] = {
            'id': region_id(region, lane_key),
            'label': label,
            'direction': direction,
            'points': [point[:] for point in points],
            'polygon': [point[:] for point in points],
            'center': geometry['center'],
            'bounds': geometry['bounds'],
            'polygon_cv2': geometry['polygon_cv2'],
        }
        if frame_shape is not None and not normalized[canonical_key]['label']:
            normalized[canonical_key]['label'] = compute_lane_label(points, frame_shape)
    return normalized


def point_in_region(x, y, region, buffer_px=18):
    points = region_points(region)
    if not isinstance(points, list) or len(points) == 0:
        return False

    bounds = region.get('bounds') if isinstance(region, dict) else None
    if bounds is not None:
        min_x, min_y, max_x, max_y = bounds
        if x < min_x - buffer_px or x > max_x + buffer_px or y < min_y - buffer_px or y > max_y + buffer_px:
            return False

    if len(points) == 4 and all(isinstance(value, (int, float)) for value in points):
        rx1, ry1, rx2, ry2 = points
        return (rx1 - buffer_px) <= x <= (rx2 + buffer_px) and (ry1 - buffer_px) <= y <= (ry2 + buffer_px)

    if all(isinstance(point, list) and len(point) == 2 for point in points):
        polygon = region.get('polygon_cv2') if isinstance(region, dict) else None
        if polygon is None:
            polygon = polygon_to_cv2(points)
        return cv2.pointPolygonTest(polygon, (float(x), float(y)), True) >= -float(buffer_px)

    return False


def _normalize_polygon_values(raw_polygon):
    if not isinstance(raw_polygon, list):
        raise ValueError('Lane polygon must be a list')

    if raw_polygon and all(isinstance(point, (list, tuple)) and len(point) == 2 for point in raw_polygon):
        normalized_points = [[float(point[0]), float(point[1])] for point in raw_polygon]
    else:
        if len(raw_polygon) % 2 != 0:
            raise ValueError('Flat polygon list must contain an even number of values')
        if not all(isinstance(value, (int, float)) for value in raw_polygon):
            raise ValueError('Flat polygon list must contain only numeric values')
        normalized_points = [
            [float(raw_polygon[index]), float(raw_polygon[index + 1])]
            for index in range(0, len(raw_polygon), 2)
        ]

    if len(normalized_points) < 3:
        raise ValueError('Lane polygon must contain at least 3 points')
    return normalized_points


def normalize_lane_config(config_path):
    config_file = Path(config_path)
    with open(config_file, 'r', encoding='utf-8') as file:
        config = json.load(file)

    lane_regions = config.get('lane_regions', {})
    normalized_regions = {}

    for lane_key, lane_region in (lane_regions or {}).items():
        if isinstance(lane_region, dict):
            lane_id = lane_region.get('id', lane_key)
            label = lane_region.get('label', lane_key)
            direction = lane_region.get('direction', 'incoming')
            raw_polygon = lane_region.get('polygon')
            if raw_polygon is None:
                raw_polygon = lane_region.get('points', [])
        else:
            lane_id = lane_key
            label = lane_key
            direction = 'incoming'
            raw_polygon = lane_region

        # Normalize old/new polygon formats and recover simple 2-point lane boxes.
        try:
            normalized_polygon = _normalize_polygon_values(raw_polygon)
        except ValueError:
            normalized_polygon = None

            # Nested 2-point format: [[x1, y1], [x2, y2]]
            if (
                isinstance(raw_polygon, list)
                and len(raw_polygon) == 2
                and all(isinstance(point, (list, tuple)) and len(point) == 2 for point in raw_polygon)
            ):
                x1 = float(raw_polygon[0][0])
                y1 = float(raw_polygon[0][1])
                x2 = float(raw_polygon[1][0])
                y2 = float(raw_polygon[1][1])
                normalized_polygon = [
                    [x1, y1],
                    [x2, y1],
                    [x2, y2],
                    [x1, y2],
                ]
                print(f"Auto-fixed 2-point polygon for lane: {lane_key}")

            # Flat 2-point format: [x1, y1, x2, y2]
            elif (
                isinstance(raw_polygon, list)
                and len(raw_polygon) == 4
                and all(isinstance(value, (int, float)) for value in raw_polygon)
            ):
                x1 = float(raw_polygon[0])
                y1 = float(raw_polygon[1])
                x2 = float(raw_polygon[2])
                y2 = float(raw_polygon[3])
                normalized_polygon = [
                    [x1, y1],
                    [x2, y1],
                    [x2, y2],
                    [x1, y2],
                ]
                print(f"Auto-fixed 2-point polygon for lane: {lane_key}")

            if normalized_polygon is None:
                print(f"Skipping invalid lane: {lane_key}")
                continue

        normalized_regions[lane_key] = {
            'id': lane_id,
            'label': label,
            'direction': direction,
            'polygon': normalized_polygon,
            'points': normalized_polygon,
        }

    config['lane_regions'] = normalized_regions

    backup_file = config_file.with_name(f"{config_file.stem}_backup{config_file.suffix}")
    shutil.copy2(config_file, backup_file)

    temp_file = config_file.with_suffix(f"{config_file.suffix}.tmp")
    with open(temp_file, 'w', encoding='utf-8') as file:
        json.dump(config, file, indent=2)
    temp_file.replace(config_file)

    return config


def draw_lane_polygons(frame, lanes, active_lane=None, lane_state=None):
    lane_state = lane_state or {}

    for lane_key, lane_region in (lanes or {}).items():
        points = region_points(lane_region)
        if not points:
            continue

        polygon = polygon_to_cv2(points)
        if polygon is None:
            continue

        color = LANE_COLORS.get(lane_key, (0, 0, 255))
        thickness = 3 if active_lane == lane_key else 2
        cv2.polylines(frame, [polygon], isClosed=True, color=color, thickness=thickness)

        label = region_label(lane_region, lane_key)
        center = lane_region.get('center') if isinstance(lane_region, dict) else None
        if center is None:
            center = compute_polygon_center(points)
        count = int(lane_state.get(lane_key, {}).get('count', 0))
        wait_time = float(lane_state.get(lane_key, {}).get('avgWaitTime', 0.0))

        text_x = int(center[0])
        text_y = int(center[1])
        cv2.putText(
            frame,
            f"{label}: {count} | wait: {wait_time:.1f}s",
            (text_x, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )

    return frame
