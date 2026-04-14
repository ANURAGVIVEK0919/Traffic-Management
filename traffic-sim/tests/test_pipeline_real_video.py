import os
import sys
import time
from pathlib import Path

import cv2
import pytest

sys.path.append(os.path.abspath('.'))

from backend.agent.yolo_detector import detect_vehicles_in_frame, reset_tracking_state, yolo_model
from backend.perception.homography import HomographyLaneMapper, compute_homography, get_lane
from backend.perception.lane_processing import normalize_lane_config, normalize_lane_regions
from backend.perception.video_pipeline import build_smoothed_lane_state


LANES = ('north', 'east', 'south', 'west')


def _empty_lane_state():
    return {
        lane: {'count': 0, 'avgWaitTime': 0.0, 'hasAmbulance': False}
        for lane in LANES
    }


def _build_homography_mapper(config):
    homography_config = config.get('homography', {}) or {}
    source_points = homography_config.get('source_points')
    lane_regions_top_view = homography_config.get('lane_regions_top_view')

    if not source_points or not lane_regions_top_view:
        return None

    output_size_raw = homography_config.get('output_size', [800, 800])
    output_size = (int(output_size_raw[0]), int(output_size_raw[1]))
    h_matrix = compute_homography(source_points, output_size=output_size)
    return HomographyLaneMapper(
        h_matrix,
        output_size=output_size,
        lane_regions_top_view=lane_regions_top_view,
    )


@pytest.fixture
def real_video_path():
    uploads_dir = Path('uploads')
    videos = sorted(uploads_dir.glob('*.mp4'))
    if not videos:
        pytest.skip('No input video found at uploads/*.mp4')
    return videos[0]


@pytest.fixture
def max_frames():
    return 50


@pytest.fixture
def max_total_time_seconds():
    return float(os.getenv('PIPELINE_IT_MAX_SECONDS', '10'))


@pytest.fixture
def lane_setup():
    config_path = Path('backend/perception/config/junction_demo.json')
    if not config_path.exists():
        pytest.skip('Lane config not found at backend/perception/config/junction_demo.json')

    config = normalize_lane_config(config_path)
    lane_regions = normalize_lane_regions(config.get('lane_regions', {}))
    return config, lane_regions


def test_pipeline_real_video(real_video_path, lane_setup, max_frames, max_total_time_seconds):
    if yolo_model is None:
        pytest.skip('YOLO model is not available in this environment')

    config, lane_regions = lane_setup
    homography_mapper = _build_homography_mapper(config)

    cap = cv2.VideoCapture(str(real_video_path))
    if not cap.isOpened():
        pytest.skip(f'Could not open video: {real_video_path}')

    reset_tracking_state()

    frames_processed = 0
    frames_with_detections = 0
    total_detections = 0
    lane_counts_total = {lane: 0 for lane in LANES}
    smoothed_lane_state = _empty_lane_state()

    start_time = time.perf_counter()

    try:
        while frames_processed < max_frames:
            ok, frame = cap.read()
            if not ok or frame is None:
                break

            lane_state, detections = detect_vehicles_in_frame(
                frame,
                lane_regions,
                return_debug=True,
                current_time=time.monotonic(),
            )

            # Detection payload should remain a list of dict objects with bbox.
            assert isinstance(detections, list)
            assert all(isinstance(det, dict) for det in detections)

            # Lane state must remain RL-ready: 4 lanes and fixed keys/types.
            assert isinstance(lane_state, dict)
            assert set(lane_state.keys()) == set(LANES)
            for lane in LANES:
                lane_data = lane_state[lane]
                assert set(lane_data.keys()) == {'count', 'avgWaitTime', 'hasAmbulance'}
                assert isinstance(lane_data['count'], int)
                assert isinstance(lane_data['avgWaitTime'], float)
                assert isinstance(lane_data['hasAmbulance'], bool)
                lane_counts_total[lane] += lane_data['count']

            # Explicit bottom-center and lane mapping validation through get_lane.
            for det in detections:
                bbox = det.get('bbox')
                assert isinstance(bbox, list)
                assert len(bbox) == 4

                x1, y1, x2, y2 = [float(value) for value in bbox]
                center_x = (x1 + x2) / 2.0
                center_y = y2

                if homography_mapper is not None:
                    tx, ty = homography_mapper.transform_point(center_x, center_y)
                    lane_from_get_lane = (
                        get_lane(tx, ty, homography_mapper.lane_regions_top_view)
                        if homography_mapper.is_point_in_output(tx, ty)
                        else None
                    )
                else:
                    lane_from_get_lane = get_lane(center_x, center_y, lane_regions)

                assert lane_from_get_lane in set(LANES) | {None}

            # Smoothing call validates frame-to-frame integration without RL API calls.
            smoothed_lane_state = build_smoothed_lane_state(
                lane_state,
                smoothed_lane_state,
                alpha=0.7,
            )
            assert set(smoothed_lane_state.keys()) == set(LANES)

            frames_processed += 1
            total_detections += len(detections)
            if detections:
                frames_with_detections += 1

    finally:
        cap.release()
        reset_tracking_state()

    elapsed = time.perf_counter() - start_time
    fps = float(frames_processed) / elapsed if elapsed > 0 else 0.0

    print(f"[REAL VIDEO TEST] frames_processed={frames_processed}")
    print(f"[REAL VIDEO TEST] total_detections={total_detections}")
    print(f"[REAL VIDEO TEST] lane_counts={lane_counts_total}")
    print(f"[REAL VIDEO TEST] fps={fps:.2f}")
    print(f"[REAL VIDEO TEST] elapsed_seconds={elapsed:.2f}")

    if frames_processed == 0:
        pytest.skip('No frames were decoded from the selected video')

    # At least some frames should carry detections for meaningful integration coverage.
    assert frames_with_detections > 0
    assert total_detections > 0

    # Lightweight performance sanity checks for CI/dev environments.
    assert fps > 1.0
    assert elapsed < max_total_time_seconds