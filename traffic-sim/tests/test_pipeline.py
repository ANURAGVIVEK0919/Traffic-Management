import os
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.append(os.path.abspath('.'))

from backend.agent import yolo_detector
from backend.agent.yolo_detector import detect_vehicles_in_frame, build_lane_state, reset_tracking_state
from backend.perception.homography import get_lane
from backend.perception.video_pipeline import build_smoothed_lane_state


print(f"[TEST DEBUG] cwd={os.getcwd()}")
print(f"[TEST DEBUG] test_file_exists={Path(__file__).exists()}")


class FakeBox:
    def __init__(self, bbox, confidence, class_id):
        self.xyxy = np.array([bbox], dtype=float)
        self.conf = np.array([confidence], dtype=float)
        self.cls = int(class_id)


class FakeResult:
    def __init__(self, boxes, names):
        self.boxes = boxes
        self.names = names


class FakeYOLOModel:
    def __init__(self, results):
        self._results = results

    def __call__(self, frame, verbose=False):
        return self._results


@pytest.fixture(autouse=True)
def reset_tracker_state():
    reset_tracking_state()
    yield
    reset_tracking_state()


@pytest.fixture
def dummy_frame():
    return np.zeros((800, 800, 3), dtype=np.uint8)


@pytest.fixture
def dummy_lane_regions():
    def make_region(lane_id, x1, y1, x2, y2):
        points = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
        return {
            'id': lane_id,
            'label': lane_id,
            'direction': 'incoming',
            'points': points,
            'polygon': points,
            'bounds': (x1, y1, x2, y2),
            'polygon_cv2': np.array(points, dtype=np.int32),
        }

    return {
        'north': make_region('north', 100, 0, 300, 250),
        'south': make_region('south', 100, 550, 300, 799),
        'east': make_region('east', 550, 100, 799, 300),
        'west': make_region('west', 0, 100, 250, 300),
    }


@pytest.fixture
def fake_yolo(monkeypatch):
    def install(detections):
        names = {0: 'car', 1: 'bus', 2: 'truck', 3: 'ambulance'}
        boxes = [FakeBox(*spec) for spec in detections]
        result = FakeResult(boxes, names)
        monkeypatch.setattr(yolo_detector, 'yolo_model', FakeYOLOModel([result]))

    return install


def test_detection_output_structure(dummy_frame, dummy_lane_regions, fake_yolo):
    # The detector should return a lane_state dict plus a list of detection payloads.
    fake_yolo([
        ([150, 50, 250, 150], 0.91, 0),
    ])

    lane_state, detections = detect_vehicles_in_frame(
        dummy_frame,
        dummy_lane_regions,
        return_debug=True,
        current_time=10.0,
    )

    assert isinstance(lane_state, dict)
    assert isinstance(detections, list)
    assert detections

    first = detections[0]
    assert 'bbox' in first
    assert 'track_id' in first
    assert 'confidence' in first
    assert 'bottom_center' in first
    assert isinstance(first['bbox'], list)
    assert len(first['bbox']) == 4
    assert isinstance(first['track_id'], int)
    assert isinstance(first['confidence'], float)
    assert isinstance(first['bottom_center'], list)
    assert len(first['bottom_center']) == 2


def test_tracking_id_stability(dummy_frame, dummy_lane_regions, fake_yolo):
    # Two identical frames should keep the same track_id.
    fake_yolo([
        ([150, 50, 250, 150], 0.92, 0),
    ])

    _, first_detections = detect_vehicles_in_frame(
        dummy_frame,
        dummy_lane_regions,
        return_debug=True,
        current_time=10.0,
    )
    _, second_detections = detect_vehicles_in_frame(
        dummy_frame,
        dummy_lane_regions,
        return_debug=True,
        current_time=10.5,
    )

    first_ids = [det['track_id'] for det in first_detections]
    second_ids = [det['track_id'] for det in second_detections]

    assert first_ids
    assert second_ids
    assert first_ids == second_ids
    assert all(isinstance(track_id, int) for track_id in first_ids)


def test_lane_mapping(dummy_lane_regions):
    # Known top-view coordinates should map to the expected lane.
    assert get_lane(200, 100, dummy_lane_regions) == 'north'
    assert get_lane(650, 200, dummy_lane_regions) == 'east'
    assert get_lane(200, 700, dummy_lane_regions) == 'south'
    assert get_lane(100, 200, dummy_lane_regions) == 'west'


def test_wait_time_calculation():
    # Wait time should be current_time minus first_seen_time for active tracks.
    yolo_detector.tracked_vehicles = {
        1: {
            'id': 1,
            'lane': 'north',
            'label': 'car',
            'inside_lane': True,
            'movement_ok': True,
            'first_seen_time': 5.0,
            'entered_at': 5.0,
            'centroid': (200.0, 100.0),
            'bbox': [150.0, 50.0, 250.0, 150.0],
            'confidence': 0.9,
        }
    }

    lane_state = build_lane_state(11.0)
    assert math.isclose(lane_state['north']['avgWaitTime'], 6.0, rel_tol=1e-6)
    assert lane_state['north']['count'] == 1
    assert lane_state['north']['hasAmbulance'] is False


def test_lane_state_format():
    # The detector lane_state contract should stay limited to the three RL fields.
    lane_state = build_lane_state(3.0)
    expected_keys = {'count', 'avgWaitTime', 'hasAmbulance'}

    assert set(lane_state.keys()) == {'north', 'south', 'east', 'west'}
    for lane_id, lane_data in lane_state.items():
        assert set(lane_data.keys()) == expected_keys
        assert isinstance(lane_data['count'], int)
        assert isinstance(lane_data['avgWaitTime'], float)
        assert isinstance(lane_data['hasAmbulance'], bool)


def test_smoothing_logic():
    # Exponential smoothing should blend previous and current lane values.
    previous_lane_state = {
        'north': {'count': 10, 'avgWaitTime': 20.0, 'hasAmbulance': False},
        'east': {'count': 4, 'avgWaitTime': 8.0, 'hasAmbulance': False},
        'south': {'count': 0, 'avgWaitTime': 0.0, 'hasAmbulance': False},
        'west': {'count': 2, 'avgWaitTime': 6.0, 'hasAmbulance': False},
    }
    current_lane_state = {
        'north': {'count': 0, 'avgWaitTime': 0.0, 'hasAmbulance': False},
        'east': {'count': 8, 'avgWaitTime': 16.0, 'hasAmbulance': True},
        'south': {'count': 1, 'avgWaitTime': 2.0, 'hasAmbulance': False},
        'west': {'count': 2, 'avgWaitTime': 6.0, 'hasAmbulance': False},
    }

    smoothed = build_smoothed_lane_state(current_lane_state, previous_lane_state, alpha=0.7)

    assert smoothed['north']['count'] == 7
    assert math.isclose(smoothed['north']['avgWaitTime'], 14.0, rel_tol=1e-6)
    assert smoothed['east']['count'] == 5
    assert math.isclose(smoothed['east']['avgWaitTime'], 10.4, rel_tol=1e-6)
    assert smoothed['east']['hasAmbulance'] is True


def test_pipeline_sanity(dummy_frame, dummy_lane_regions, fake_yolo):
    # End-to-end sanity: detection should produce lane counts and a valid RL-ready lane_state.
    fake_yolo([
        ([150, 50, 250, 150], 0.95, 0),
        ([600, 150, 700, 250], 0.88, 1),
    ])

    lane_state, detections = detect_vehicles_in_frame(
        dummy_frame,
        dummy_lane_regions,
        return_debug=True,
        current_time=12.0,
    )

    assert len(detections) == 2
    assert lane_state['north']['count'] == 1
    assert lane_state['east']['count'] == 1
    assert lane_state['south']['count'] == 0
    assert lane_state['west']['count'] == 0

    smoothed = build_smoothed_lane_state(
        lane_state,
        {
            'north': {'count': 0, 'avgWaitTime': 0.0, 'hasAmbulance': False},
            'east': {'count': 0, 'avgWaitTime': 0.0, 'hasAmbulance': False},
            'south': {'count': 0, 'avgWaitTime': 0.0, 'hasAmbulance': False},
            'west': {'count': 0, 'avgWaitTime': 0.0, 'hasAmbulance': False},
        },
        alpha=0.7,
    )

    assert set(smoothed.keys()) == {'north', 'east', 'south', 'west'}
    assert all(set(lane_data.keys()) == {'count', 'avgWaitTime', 'hasAmbulance'} for lane_data in smoothed.values())