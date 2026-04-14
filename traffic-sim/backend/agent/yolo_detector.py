# Import required modules
import logging
import os
import time

import cv2
import numpy as np
from ultralytics import YOLO

from backend.agent.stable_tracker import StableTracker
from backend.perception.lane_processing import (
    draw_lane_polygons,
    polygon_to_cv2,
    region_direction,
    region_label,
    region_points,
)

LOGGER = logging.getLogger(__name__)

# Constants for YOLO detection
CONFIDENCE_THRESHOLD = float(os.getenv('YOLO_CONFIDENCE_THRESHOLD', '0.25'))
YOLO_MODEL_SOURCE = os.getenv('YOLO_MODEL_SOURCE', 'local').strip().lower()
YOLO_LOCAL_MODEL_PATH = os.getenv('YOLO_LOCAL_MODEL_PATH', 'models/yolo_traffic.pt')
YOLO_HF_REPO_ID = os.getenv('YOLO_HF_REPO_ID', 'Perception365/VehicleNet-Y26s')
YOLO_HF_FILENAME = os.getenv('YOLO_HF_FILENAME', '').strip()
TRACK_MATCH_DISTANCE = float(os.getenv('TRACK_MATCH_DISTANCE', '80'))
TRACK_MAX_MISSED_FRAMES = int(os.getenv('TRACK_MAX_MISSED_FRAMES', '12'))
STABLE_TRACK_MAX_MISSED_FRAMES = int(os.getenv('STABLE_TRACK_MAX_MISSED_FRAMES', '12'))
LOST_TRACK_RESTORE_WINDOW_SECONDS = float(os.getenv('LOST_TRACK_RESTORE_WINDOW_SECONDS', '3.0'))
LOST_TRACK_RESTORE_DISTANCE_PX = float(os.getenv('LOST_TRACK_RESTORE_DISTANCE_PX', '80'))
LANE_ENTRY_BUFFER_PX = int(os.getenv('LANE_ENTRY_BUFFER_PX', '24'))
WAIT_SMOOTHING_WINDOW = int(os.getenv('WAIT_SMOOTHING_WINDOW', '5'))

VEHICLE_CLASSES = {
    'car', 'bike', 'ambulance', 'truck', 'bus', 'autorickshaw', 'motorcycle', 'van'
}
AMBULANCE_CLASSES = {'ambulance'}

# Track state across frames so every vehicle is counted once and its lane stays locked.
tracked_vehicles = {}
next_track_id = 1
lane_wait_reset_at = {lane: 0.0 for lane in ('north', 'east', 'south', 'west')}
_recently_lost = {}
stable_tracker = StableTracker(
    max_age=STABLE_TRACK_MAX_MISSED_FRAMES,
    match_distance=TRACK_MATCH_DISTANCE,
)
_debug_frame_saved = False

RED = ((483, 218), (778, 153))
YELLOW = ((829, 166), (1101, 334))
BROWN = ((687, 715), (1104, 393))
BLACK = ((423, 278), (543, 710))

# Map fine-grained labels (e.g., hatchback/sedan/SUV) to app classes.
LABEL_MAP = {
    'car': 'car',
    'hatchback': 'car',
    'sedan': 'car',
    'suv': 'car',
    'muv': 'car',
    'bike': 'bike',
    'bicycle': 'bike',
    'two_wheeler': 'bike',
    'two_wheelers': 'bike',
    'motorcycle': 'motorcycle',
    'scooter': 'bike',
    'autorickshaw': 'autorickshaw',
    'auto_rickshaw': 'autorickshaw',
    'three_wheeler': 'autorickshaw',
    'three_wheelers': 'autorickshaw',
    'bus': 'bus',
    'truck': 'truck',
    'van': 'van',
    'commercial_vehicle': 'truck',
    'ambulance': 'ambulance',
}


def normalize_label(label):
    return str(label).strip().lower().replace('-', '_').replace(' ', '_')


def resolve_model_path():
    if YOLO_MODEL_SOURCE == 'local':
        if os.path.exists(YOLO_LOCAL_MODEL_PATH):
            return YOLO_LOCAL_MODEL_PATH
        LOGGER.warning('Local YOLO model not found at %s', YOLO_LOCAL_MODEL_PATH)
        return None

    if YOLO_MODEL_SOURCE == 'hf':
        try:
            from huggingface_hub import hf_hub_download
        except Exception:
            LOGGER.exception('huggingface_hub is required for YOLO_MODEL_SOURCE=hf')
            return None

        candidates = [YOLO_HF_FILENAME] if YOLO_HF_FILENAME else [
            'best.pt',
            'weights/best.pt',
        ]
        for filename in candidates:
            try:
                path = hf_hub_download(repo_id=YOLO_HF_REPO_ID, filename=filename)
                LOGGER.info('Loaded HF YOLO weights: %s (%s)', YOLO_HF_REPO_ID, filename)
                return path
            except Exception:
                continue
        LOGGER.error(
            'Failed to download model from %s. Set YOLO_HF_FILENAME to correct file path in repo.',
            YOLO_HF_REPO_ID,
        )
        return None

    LOGGER.error('Unsupported YOLO_MODEL_SOURCE: %s', YOLO_MODEL_SOURCE)
    return None


def map_detected_label(raw_label):
    normalized = normalize_label(raw_label)
    return LABEL_MAP.get(normalized)


def validate_model_labels(model):
    names = getattr(model, 'names', {}) or {}
    normalized = {normalize_label(value) for value in names.values()}
    mapped = {LABEL_MAP[label] for label in normalized if label in LABEL_MAP}
    missing = VEHICLE_CLASSES.difference(mapped)
    if missing:
        LOGGER.warning('Model label coverage missing app classes: %s', sorted(missing))


def get_bottom_center(x1, y1, x2, y2):
    # Bottom-center gives a more stable lane assignment for moving vehicles.
    return ((float(x1) + float(x2)) / 2.0, float(y2))


def line_side(p1, p2, point):
    x1, y1 = p1
    x2, y2 = p2
    x, y = point
    return (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)


def get_lane(point):
    lane = None
    x, y = float(point[0]), float(point[1])
    red_side = line_side(*RED, point)
    yellow_side = line_side(*YELLOW, point)
    brown_side = line_side(*BROWN, point)
    black_side = line_side(*BLACK, point)

    # 🔴 NORTH
    if red_side > 0 and y < 260:
        lane = 'north'
    # 🟡 EAST
    elif yellow_side > 0 and x >= 800:
        lane = 'east'
    # 🟤 SOUTH
    elif brown_side > 0 and y >= 500:
        lane = 'south'
    # ⚫ WEST
    elif black_side < 0 and x < 520 and y >= 180:
        lane = 'west'
    else:
        lane = 'north'

    print(f"POINT: {point} → LANE: {lane}")
    return lane


def assign_lane(center_x, center_y, lane_regions, track_id=None, homography_mapper=None):
    # Lane assignment is now exact line-based classification using image coordinates.
    point = (float(center_x), float(center_y))
    lane = get_lane(point)
    print(f"CENTER: ({float(center_x):.1f}, {float(center_y):.1f})")
    print(f"ASSIGNED LANE: track_id={track_id} → lane={lane}")
    if lane is None:
        print("⚠️ GAP DETECTED:", point)
        lane = 'north'
    return lane, point


def track_key(track_id):
    return f'track_{track_id}'


def reset_tracking_state():
    global tracked_vehicles, next_track_id, lane_wait_reset_at, stable_tracker, _recently_lost
    tracked_vehicles = {}
    next_track_id = 1
    lane_wait_reset_at = {lane: 0.0 for lane in ('north', 'east', 'south', 'west')}
    _recently_lost = {}
    stable_tracker.reset()


def reset_lane_wait_timer(lane_id, current_time):
    if lane_id in lane_wait_reset_at:
        lane_wait_reset_at[lane_id] = float(current_time)


def get_lane_direction(lane_regions, lane_id):
    lane_meta = lane_regions.get(lane_id, {})
    if isinstance(lane_meta, dict):
        return region_direction(lane_meta, 'incoming')
    return 'incoming'


def get_lane_geometry(lane_regions, lane_id):
    region = lane_regions.get(lane_id, {})
    if isinstance(region, dict):
        return region
    return {'points': region, 'label': lane_id, 'direction': 'incoming'}


def centroid_distance(a, b):
    return float(np.hypot(a[0] - b[0], a[1] - b[1]))


def cleanup_recently_lost(current_time):
    for lost_track_id, lost_data in list(_recently_lost.items()):
        lost_at = float(lost_data.get('lost_at', 0.0))
        if float(current_time) - lost_at > LOST_TRACK_RESTORE_WINDOW_SECONDS:
            _recently_lost.pop(lost_track_id, None)


def restore_recent_first_seen_time(observation_centroid, lane_id, current_time):
    cleanup_recently_lost(current_time)

    best_track_id = None
    best_distance = None
    observation_point = (float(observation_centroid[0]), float(observation_centroid[1]))

    for lost_track_id, lost_data in _recently_lost.items():
        lost_at = float(lost_data.get('lost_at', 0.0))
        if float(current_time) - lost_at > LOST_TRACK_RESTORE_WINDOW_SECONDS:
            continue

        last_lane = lost_data.get('last_lane')
        if lane_id is not None and last_lane not in (None, lane_id):
            continue

        last_centroid = lost_data.get('last_centroid')
        if not isinstance(last_centroid, (list, tuple)) or len(last_centroid) != 2:
            continue

        distance = centroid_distance(
            observation_point,
            (float(last_centroid[0]), float(last_centroid[1])),
        )
        if distance >= LOST_TRACK_RESTORE_DISTANCE_PX:
            continue

        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_track_id = lost_track_id

    if best_track_id is None:
        return None

    restored = _recently_lost.pop(best_track_id, None)
    if restored is None:
        return None

    print(f"[TRACKER] Restored wait time for re-entered vehicle")
    return float(restored.get('first_seen_time', current_time))


def toward_intersection(previous_center, current_center, frame_center):
    if previous_center is None:
        return True
    prev_distance = centroid_distance(previous_center, frame_center)
    current_distance = centroid_distance(current_center, frame_center)
    return current_distance <= prev_distance + 1.5


def match_observations_to_tracks(observations):
    return stable_tracker.associate(observations, tracked_vehicles)


def create_track(observation, lane_regions, current_time, frame_center, homography_mapper=None):
    global next_track_id
    transformed_centroid = None
    lane_point = observation.get('bbox_center') or observation['centroid']
    if homography_mapper is not None:
        transformed_centroid = homography_mapper.transform_point(observation['centroid'][0], observation['centroid'][1])

    track_id = next_track_id
    lane_id, bottom_center = assign_lane(
        lane_point[0],
        lane_point[1],
        lane_regions,
        track_id=track_id,
        homography_mapper=homography_mapper,
    )
    if lane_id is None and observation.get('bbox_center') is not None:
        fallback_point = observation['centroid']
        print(f"[LANE RETRY] track_id={track_id} trying bottom center point={fallback_point}")
        lane_id, bottom_center = assign_lane(
            fallback_point[0],
            fallback_point[1],
            lane_regions,
            track_id=track_id,
            homography_mapper=homography_mapper,
        )
    if lane_id is None:
        return None

    lane_direction = get_lane_direction(lane_regions, lane_id)
    moving_to_center = toward_intersection(None, observation['centroid'], frame_center)
    movement_ok = moving_to_center if lane_direction == 'incoming' else not moving_to_center
    if not movement_ok:
        return None

    restored_first_seen_time = restore_recent_first_seen_time(observation['centroid'], lane_id, current_time)
    first_seen_time = restored_first_seen_time if restored_first_seen_time is not None else float(current_time)

    track = {
        'id': track_id,
        'bbox': observation['bbox'],
        'centroid': bottom_center,
        'bottom_center': bottom_center,
        'bbox_center': observation.get('bbox_center'),
        'prev_centroid': None,
        'label': observation['label'],
        'confidence': observation['confidence'],
        'lane': lane_id,
        'direction': lane_direction,
        'inside_lane': True,
        'transformed_centroid': transformed_centroid if homography_mapper is not None else None,
        'entered_at': float(current_time),
        'first_seen_time': first_seen_time,
        'wait_started_at': max(float(current_time), float(lane_wait_reset_at.get(lane_id, 0.0))),
        'missed_frames': 0,
        'exit_frames': 0,
        'movement_ok': movement_ok,
        'history': [observation['centroid']],
    }
    tracked_vehicles[track_id] = track
    print(f"[TRACKER] New ID {track_id} at t={current_time:.2f}s")
    next_track_id += 1
    return track


def update_track(track_id, observation, lane_regions, current_time, frame_center, homography_mapper=None):
    track = tracked_vehicles[track_id]
    lane_point = observation.get('bbox_center') or observation['centroid']
    previous_centroid = track['centroid']
    track['prev_centroid'] = previous_centroid
    track['bbox'] = observation['bbox']
    track['centroid'] = observation['centroid']
    track['bottom_center'] = observation['centroid']
    track['bbox_center'] = observation.get('bbox_center')
    track['confidence'] = observation['confidence']
    track['missed_frames'] = 0
    track['history'].append(observation['centroid'])
    if len(track['history']) > WAIT_SMOOTHING_WINDOW:
        track['history'] = track['history'][-WAIT_SMOOTHING_WINDOW:]
    if 'first_seen_time' not in track:
        track['first_seen_time'] = float(current_time)

    lane_id = track.get('lane')
    transformed_centroid = track.get('transformed_centroid')

    if homography_mapper is not None:
        transformed_centroid = homography_mapper.transform_point(observation['centroid'][0], observation['centroid'][1])
        track['transformed_centroid'] = transformed_centroid

    if lane_id is None:
        lane_id, bottom_center = assign_lane(
            lane_point[0],
            lane_point[1],
            lane_regions,
            track_id=track_id,
            homography_mapper=homography_mapper,
        )
        if lane_id is None and observation.get('bbox_center') is not None:
            fallback_point = observation['centroid']
            print(f"[LANE RETRY] track_id={track_id} trying bottom center point={fallback_point}")
            lane_id, bottom_center = assign_lane(
                fallback_point[0],
                fallback_point[1],
                lane_regions,
                track_id=track_id,
                homography_mapper=homography_mapper,
            )
        if lane_id is not None:
            track['lane'] = lane_id
            track['direction'] = get_lane_direction(lane_regions, lane_id)
            track['bottom_center'] = bottom_center

    if lane_id is not None:
        inside_lane = get_lane(lane_point) == lane_id
        movement_to_center = toward_intersection(previous_centroid, observation['centroid'], frame_center)
        movement_ok = movement_to_center if track.get('direction') == 'incoming' else not movement_to_center
        if inside_lane and movement_ok:
            if not track['inside_lane']:
                track['entered_at'] = float(current_time)
                track['wait_started_at'] = max(float(current_time), float(lane_wait_reset_at.get(lane_id, 0.0)))
            track['inside_lane'] = True
            track['exit_frames'] = 0
            track['movement_ok'] = True
        else:
            track['exit_frames'] += 1
            track['movement_ok'] = False
            if track['exit_frames'] > TRACK_MAX_MISSED_FRAMES:
                track['inside_lane'] = False
    return track


def age_tracks(matched_track_ids, current_time):
    cleanup_recently_lost(current_time)
    expired_track_ids = []
    for track_id, track in list(tracked_vehicles.items()):
        if track_id in matched_track_ids:
            continue
        track['missed_frames'] += 1
        if track['missed_frames'] > STABLE_TRACK_MAX_MISSED_FRAMES:
            missed_count = int(track.get('missed_frames', 0))
            last_centroid = track.get('centroid')
            _recently_lost[track_id] = {
                'first_seen_time': float(track.get('first_seen_time', current_time)),
                'last_lane': track.get('lane'),
                'lost_at': float(current_time),
                'last_centroid': [float(last_centroid[0]), float(last_centroid[1])] if isinstance(last_centroid, (list, tuple)) and len(last_centroid) == 2 else None,
            }
            print(f"[TRACKER] Removed ID {track_id} after {missed_count} missed frames")
            expired_track_ids.append(track_id)
            tracked_vehicles.pop(track_id, None)
    return expired_track_ids


def build_lane_state(current_time):
    lane_state = get_empty_lane_state()
    lane_tracks = {lane: [] for lane in lane_state}

    for track in tracked_vehicles.values():
        lane_id = track.get('lane')
        if lane_id not in lane_state:
            continue
        if not track.get('inside_lane') or not track.get('movement_ok'):
            continue
        lane_tracks[lane_id].append(track)

    for lane_id, tracks in lane_tracks.items():
        lane_state[lane_id]['count'] = len(tracks)
        lane_state[lane_id]['hasAmbulance'] = any(track.get('label') in AMBULANCE_CLASSES for track in tracks)
        waits = []
        for track in tracks:
            first_seen_time = float(track.get('first_seen_time', track.get('entered_at', current_time)))
            wait_time = max(0.0, float(current_time) - first_seen_time)
            waits.append(wait_time)
            print(
                f"[WAIT DEBUG] vehicle_id={track.get('id')} lane={lane_id} "
                f"first_seen={first_seen_time:.3f} current={float(current_time):.3f} wait={wait_time:.3f}"
            )
        lane_state[lane_id]['avgWaitTime'] = float(sum(waits) / len(waits)) if waits else 0.0
        print(
            f"[WAIT DEBUG] lane={lane_id} avgWaitTime={lane_state[lane_id]['avgWaitTime']:.3f} "
            f"count={lane_state[lane_id]['count']}"
        )

    print("LANE COUNTS:", {lane: lane_state[lane]['count'] for lane in lane_state})

    return lane_state


def get_empty_lane_state():
    # Return default lane state with zeros and False.
    return {
        'north': {'count': 0, 'hasAmbulance': False, 'avgWaitTime': 0.0},
        'south': {'count': 0, 'hasAmbulance': False, 'avgWaitTime': 0.0},
        'east': {'count': 0, 'hasAmbulance': False, 'avgWaitTime': 0.0},
        'west': {'count': 0, 'hasAmbulance': False, 'avgWaitTime': 0.0},
    }


MODEL_PATH = resolve_model_path()
yolo_model = YOLO(MODEL_PATH) if MODEL_PATH else None
if yolo_model is not None:
    validate_model_labels(yolo_model)


def detect_vehicles_in_frame(frame, lane_regions, return_debug=False, current_time=None, active_green_lane=None, homography_mapper=None):
    # Return empty lane state if model not loaded.
    if yolo_model is None:
        empty = get_empty_lane_state()
        if return_debug:
            return empty, []
        return empty

    results = yolo_model(frame, verbose=False, conf=CONFIDENCE_THRESHOLD)
    print(f"[YOLO] Frame detections: {len(results[0].boxes)}")

    debug_detections = []
    if current_time is None:
        current_time = time.monotonic()
    frame_height, frame_width = frame.shape[:2]
    frame_center = (frame_width / 2.0, frame_height / 2.0)
    print("FRAME SIZE:", frame.shape)

    observations = []

    for r in results:
        boxes = getattr(r, 'boxes', None)
        if boxes is None or len(boxes) == 0:
            continue

        for box in boxes:
            raw_cls = r.names[int(box.cls)]
            cls = map_detected_label(raw_cls)
            if cls not in VEHICLE_CLASSES:
                continue

            x1, y1, x2, y2 = box.xyxy[0].tolist()
            bbox_center = ((float(x1) + float(x2)) / 2.0, (float(y1) + float(y2)) / 2.0)
            center_x, center_y = get_bottom_center(int(x1), int(y1), int(x2), int(y2))
            print("CENTER POINT:", (float(bbox_center[0]), float(bbox_center[1])))
            observations.append({
                'label': cls,
                'confidence': float(box.conf[0]) if box.conf is not None else None,
                'bbox': [float(x1), float(y1), float(x2), float(y2)],
                'centroid': (float(center_x), float(center_y)),
                'bbox_center': (float(bbox_center[0]), float(bbox_center[1])),
            })

    for detection in observations:
        bbox = detection.get('bbox', [0.0, 0.0, 0.0, 0.0])
        confidence = float(detection.get('confidence') or 0.0)
        print(
            f"DETECTED: {detection.get('label')} conf={confidence:.3f} "
            f"bbox=({float(bbox[0]):.1f},{float(bbox[1]):.1f},{float(bbox[2]):.1f},{float(bbox[3]):.1f})"
        )
    print(f"TOTAL DETECTIONS: {len(observations)}")

    global _debug_frame_saved
    if not _debug_frame_saved and observations:
        debug_frame = frame.copy()
        draw_lane_polygons(debug_frame, lane_regions)
        for obs in observations:
            bbox = obs.get('bbox') or [0.0, 0.0, 0.0, 0.0]
            x1, y1, x2, y2 = [int(float(v)) for v in bbox]
            cv2.rectangle(debug_frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
            bx, by = obs.get('bbox_center') or (0.0, 0.0)
            cv2.circle(debug_frame, (int(float(bx)), int(float(by))), 5, (0, 255, 0), -1)
            cx, cy = obs.get('centroid') or (0.0, 0.0)
            cv2.circle(debug_frame, (int(float(cx)), int(float(cy))), 4, (255, 255, 0), -1)
        cv2.imwrite("debug_frame.jpg", debug_frame)
        print("Saved lane debug frame: debug_frame.jpg")
        _debug_frame_saved = True

    matched_pairs, unmatched_track_ids, unmatched_observations = match_observations_to_tracks(observations)
    matched_track_ids = set()

    for observation_index, track_id in matched_pairs:
        matched_track_ids.add(track_id)
        update_track(
            track_id,
            observations[observation_index],
            lane_regions,
            current_time,
            frame_center,
            homography_mapper=homography_mapper,
        )

    age_tracks(matched_track_ids, current_time)

    for observation_index in unmatched_observations:
        create_track(
            observations[observation_index],
            lane_regions,
            current_time,
            frame_center,
            homography_mapper=homography_mapper,
        )

    lane_state = build_lane_state(current_time)

    for track in tracked_vehicles.values():
        lane_id = track.get('lane')
        if lane_id not in lane_state:
            continue
        first_seen_time = float(track.get('first_seen_time', track.get('entered_at', current_time)))
        wait_time = max(0.0, float(current_time) - first_seen_time)
        if return_debug:
            top_view_center = track.get('transformed_centroid') or track['centroid']
            debug_detections.append({
                'label': track.get('label'),
                'confidence': track.get('confidence'),
                'bbox': track.get('bbox'),
                'center': [float(track['centroid'][0]), float(track['centroid'][1])],
                'bottom_center': [float(track.get('bottom_center', track['centroid'])[0]), float(track.get('bottom_center', track['centroid'])[1])],
                'bbox_center': [float(track.get('bbox_center', track['centroid'])[0]), float(track.get('bbox_center', track['centroid'])[1])] if isinstance(track.get('bbox_center'), (list, tuple)) and len(track.get('bbox_center')) == 2 else [float(track['centroid'][0]), float(track['centroid'][1])],
                'lane': lane_id,
                'track_id': track.get('id'),
                'temp_id': track.get('id'),
                'top_view_center': [
                    float(top_view_center[0]),
                    float(top_view_center[1]),
                ],
                'wait_time': wait_time,
                'moving_toward_intersection': bool(track.get('movement_ok', False)),
                'inside_lane': bool(track.get('inside_lane', False)),
            })
            print(
                f"[WAIT DEBUG] track_id={track.get('id')} lane={lane_id} "
                f"wait_time={wait_time:.3f} label={track.get('label')}"
            )

    for track in tracked_vehicles.values():
        bbox = track.get('bbox') or [0.0, 0.0, 0.0, 0.0]
        print(
            f"TRACK ID: {track.get('id')} bbox=({float(bbox[0]):.1f},{float(bbox[1]):.1f},"
            f"{float(bbox[2]):.1f},{float(bbox[3]):.1f})"
        )
    print(f"VALID TRACKS: {len(debug_detections)}")

    if return_debug:
        return lane_state, debug_detections
    return lane_state
