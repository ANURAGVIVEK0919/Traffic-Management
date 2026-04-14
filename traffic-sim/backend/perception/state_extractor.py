from collections import defaultdict
from pathlib import Path
import math
import copy
import json

import cv2
import numpy as np

from backend.agent.yolo_detector import detect_vehicles_in_frame, reset_tracking_state
from backend.perception.video_pipeline import load_config

LANES = ("north", "south", "east", "west")
ALLOWED_CLASSES = {"car", "truck", "bus", "bike"}
BEST_CONFIG_PATH = Path(__file__).resolve().parents[0] / "config" / "best_config.json"

CONFIG = {
    "frame_skip": 2,
    "min_track_frames": 3,
    "movement_ratio": 0.003,
    "confidence_threshold": 0.35,
    "lane_vote_threshold": 2,
    "outlier_std_factor": 2.0,
    "smoothing_window": 3,
    "std_threshold": 2.0,
    "count_low_threshold": 1.0,
    "count_high_threshold": 12.0,
    "enable_confidence_weighting": False,
}

BEST_CONFIG = {
    "frame_skip": 2,
    "min_track_frames": 3,
    "movement_ratio": 0.003,
    "confidence_threshold": 0.35,
    "lane_vote_threshold": 2,
    "outlier_std_factor": 2.0,
    "smoothing_window": 3,
    "std_threshold": 2.0,
    "count_low_threshold": 1.0,
    "count_high_threshold": 12.0,
    "enable_confidence_weighting": False,
}


def _load_best_config():
    if not BEST_CONFIG_PATH.exists():
        return dict(BEST_CONFIG)
    try:
        with open(BEST_CONFIG_PATH, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        merged = dict(BEST_CONFIG)
        if isinstance(loaded, dict):
            merged.update(loaded)
        print("LOADED BEST CONFIG:", merged)
        return merged
    except Exception as exc:
        print(f"[CONFIG WARNING] Failed to load {BEST_CONFIG_PATH}: {exc}")
        return dict(BEST_CONFIG)


def _save_best_config(cfg):
    try:
        BEST_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BEST_CONFIG_PATH, "w", encoding="utf-8") as handle:
            json.dump(cfg, handle, indent=2)
        print("SAVED BEST CONFIG:", cfg)
    except Exception as exc:
        print(f"[CONFIG WARNING] Failed to save {BEST_CONFIG_PATH}: {exc}")


CONFIG = _load_best_config()


def _merged_config(overrides=None):
    merged = copy.deepcopy(CONFIG)
    if isinstance(overrides, dict):
        merged.update(overrides)
    return merged


def compute_movement(positions):
    if not positions or len(positions) < 2:
        return 0.0
    start_x, start_y = positions[0]
    end_x, end_y = positions[-1]
    return float(math.hypot(float(end_x) - float(start_x), float(end_y) - float(start_y)))


def remove_outliers(values, std_factor):
    if not values:
        return []
    if len(values) < 3:
        return list(values)
    mean = float(np.mean(values))
    std = float(np.std(values))
    if std <= 1e-9:
        return list(values)
    return [v for v in values if abs(float(v) - mean) <= (float(std_factor) * std)]


def smooth_series(values, window):
    if not values:
        return []
    w = max(1, int(window))
    if w <= 1:
        return list(values)
    smoothed = []
    for idx in range(len(values)):
        start = max(0, idx - w + 1)
        segment = values[start : idx + 1]
        smoothed.append(float(np.mean(segment)))
    return smoothed


def analyze_counts(lane_counts_per_frame):
    for lane in LANES:
        values = list(lane_counts_per_frame.get(lane, []))
        print(f"\nLANE: {lane}")
        if not values:
            print("Min:", 0)
            print("Max:", 0)
            print("Mean:", 0.0)
            print("Std:", 0.0)
            continue
        print("Min:", float(np.min(values)))
        print("Max:", float(np.max(values)))
        print("Mean:", float(np.mean(values)))
        print("Std:", float(np.std(values)))


def compute_quality_score(lane_counts_per_frame, final_counts):
    stability_score = 0.0
    accuracy_score = 0.0

    for lane in LANES:
        values = list(lane_counts_per_frame.get(lane, []))
        if not values:
            continue

        std = float(np.std(values))
        mean = float(np.mean(values))
        stability_score += 1.0 / (1.0 + std)

        if mean > 0:
            accuracy_score += 1.0 - (abs(float(final_counts.get(lane, 0)) - mean) / mean)

    score = float(stability_score + accuracy_score)
    total_count = int(sum(int(final_counts.get(lane, 0) or 0) for lane in LANES))
    if total_count < 3:
        score -= 2.0

    return float(score)


def _auto_tune_config(lane_counts_per_frame, lane_counts, cfg):
    tuned = dict(cfg)
    std_values = [float(np.std(values)) for values in lane_counts_per_frame.values() if values]
    avg_std = float(np.mean(std_values)) if std_values else 0.0
    if avg_std > float(cfg["std_threshold"]):
        tuned["smoothing_window"] = min(int(cfg["smoothing_window"]) + 1, 8)
    elif avg_std < max(0.1, float(cfg["std_threshold"]) * 0.25):
        tuned["smoothing_window"] = max(1, int(cfg["smoothing_window"]) - 1)

    lane_count_values = [int(lane_counts.get(lane, 0) or 0) for lane in LANES]
    avg_count = float(np.mean(lane_count_values)) if lane_count_values else 0.0
    if avg_count < float(cfg["count_low_threshold"]):
        tuned["movement_ratio"] = max(0.001, float(cfg["movement_ratio"]) * 0.8)
    if avg_count > float(cfg["count_high_threshold"]):
        tuned["confidence_threshold"] = min(0.9, float(cfg["confidence_threshold"]) + 0.05)

    return tuned


def _apply_adaptive_feedback(cfg, lane_counts_per_frame, lane_counts, all_confidences, track_movement, frame_width):
    tuned = dict(cfg)

    avg_conf = float(np.mean(all_confidences)) if all_confidences else 0.0
    if avg_conf < 0.4:
        tuned["confidence_threshold"] = max(0.2, float(tuned["confidence_threshold"]) - 0.05)
    elif avg_conf > 0.7:
        tuned["confidence_threshold"] = min(0.9, float(tuned["confidence_threshold"]) + 0.05)

    movement_values = [float(v) for v in track_movement.values()]
    avg_motion = float(np.mean(movement_values)) if movement_values else 0.0
    low_motion_threshold = float(frame_width) * 0.005
    high_motion_threshold = float(frame_width) * 0.03
    if avg_motion < low_motion_threshold:
        tuned["movement_ratio"] = max(0.001, float(tuned["movement_ratio"]) * 0.85)
    elif avg_motion > high_motion_threshold:
        tuned["movement_ratio"] = min(0.05, float(tuned["movement_ratio"]) * 1.10)

    std_values = [float(np.std(values)) for values in lane_counts_per_frame.values() if values]
    avg_std = float(np.mean(std_values)) if std_values else 0.0
    if avg_std > float(tuned["std_threshold"]):
        tuned["smoothing_window"] = min(8, int(tuned["smoothing_window"]) + 1)
    elif avg_std < max(0.1, float(tuned["std_threshold"]) * 0.25):
        tuned["smoothing_window"] = max(1, int(tuned["smoothing_window"]) - 1)

    lane_vals = [int(lane_counts.get(lane, 0) or 0) for lane in LANES]
    avg_count = float(np.mean(lane_vals)) if lane_vals else 0.0
    if avg_std > float(tuned["std_threshold"]):
        tuned["smoothing_window"] = min(8, int(tuned["smoothing_window"]) + 1)
    if avg_count < float(tuned["count_low_threshold"]):
        tuned["movement_ratio"] = max(0.001, float(tuned["movement_ratio"]) * 0.9)
        tuned["min_track_frames"] = max(2, int(tuned["min_track_frames"]) - 1)
    if avg_count > float(tuned["count_high_threshold"]):
        tuned["confidence_threshold"] = min(0.9, float(tuned["confidence_threshold"]) + 0.05)
        tuned["min_track_frames"] = min(12, int(tuned["min_track_frames"]) + 1)

    return tuned


def _extract_with_config(video_path, config_path, seconds_to_process, cfg):
    config = load_config(Path(config_path))
    lane_regions = config.get("lane_regions", {})

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    frame_width = float(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280.0)
    movement_threshold = max(2.0, float(cfg["movement_ratio"]) * frame_width)
    seconds = max(2.0, min(float(seconds_to_process), 5.0))
    max_frames = int(max(1, round(fps * seconds)))

    lane_vehicles = {lane: set() for lane in LANES}
    track_frame_count = defaultdict(int)
    track_positions = defaultdict(list)
    lane_votes = defaultdict(lambda: defaultdict(int))
    lane_counts_per_frame = defaultdict(list)
    weighted_score = defaultdict(float)
    all_confidences = []
    total_detections_seen = 0

    print("FRAME SKIP:", cfg["frame_skip"])
    print("MIN TRACK FRAMES:", cfg["min_track_frames"])
    print("MOVEMENT THRESHOLD:", movement_threshold)

    reset_tracking_state()

    processed_frames = 0
    try:
        for frame_index in range(max_frames):
            ok, frame = cap.read()
            if not ok or frame is None:
                break

            if int(cfg["frame_skip"]) > 1 and frame_index % int(cfg["frame_skip"]) != 0:
                continue

            current_time = frame_index / max(fps, 1e-6)
            _lane_state, detections = detect_vehicles_in_frame(
                frame,
                lane_regions,
                return_debug=True,
                current_time=current_time,
                active_green_lane=None,
                homography_mapper=None,
            )
            total_detections_seen += len(detections or [])

            for det in detections or []:
                track_id = det.get("track_id")
                lane = str(det.get("lane") or "").lower()
                label = str(det.get("label") or "").lower()
                confidence = float(det.get("confidence") or 0.0)

                if track_id is None:
                    continue
                if lane not in lane_vehicles:
                    continue
                if confidence < float(cfg["confidence_threshold"]):
                    continue
                if label not in ALLOWED_CLASSES:
                    continue

                tid = str(track_id)
                track_frame_count[tid] += 1
                lane_votes[tid][lane] += 1
                all_confidences.append(float(confidence))
                center = det.get("center") or det.get("bottom_center")
                if isinstance(center, (list, tuple)) and len(center) == 2:
                    track_positions[tid].append((float(center[0]), float(center[1])))
                weighted_score[lane] += float(confidence)

            frame_lane_ids = {lane: set() for lane in LANES}
            for det in detections or []:
                lane = str(det.get("lane") or "").lower()
                track_id = det.get("track_id")
                confidence = float(det.get("confidence") or 0.0)
                label = str(det.get("label") or "").lower()
                if lane not in frame_lane_ids:
                    continue
                if track_id is None:
                    continue
                if confidence < float(cfg["confidence_threshold"]):
                    continue
                if label not in ALLOWED_CLASSES:
                    continue
                frame_lane_ids[lane].add(str(track_id))

            for lane in LANES:
                lane_counts_per_frame[lane].append(len(frame_lane_ids[lane]))

            processed_frames += 1
    finally:
        cap.release()

    track_movement = {}
    valid_tracks = set()
    for track_id, seen_count in track_frame_count.items():
        movement = compute_movement(track_positions.get(track_id, []))
        track_movement[track_id] = movement
        # DEBUG: relaxed filtering
        if int(seen_count) >= 2:
            valid_tracks.add(track_id)

    for track_id in valid_tracks:
        votes = lane_votes.get(track_id, {})
        if not votes:
            continue
        final_lane = max(votes, key=votes.get)
        # DEBUG: accept all lane assignments
        if True:
            pass
        if final_lane not in lane_vehicles:
            continue
        lane_vehicles[final_lane].add(track_id)

    lane_counts = {}
    for lane in LANES:
        raw_counts = list(lane_counts_per_frame.get(lane, []))
        smoothed_counts = smooth_series(raw_counts, window=int(cfg["smoothing_window"]))
        filtered_counts = remove_outliers(smoothed_counts, std_factor=float(cfg["outlier_std_factor"]))

        if filtered_counts:
            median_count = int(np.median(filtered_counts))
        else:
            median_count = 0
        filtered_track_count = len(lane_vehicles[lane])

        # DEBUG: use raw track count
        final_count = filtered_track_count
        if bool(cfg.get("enable_confidence_weighting", False)) and filtered_track_count > 0:
            confidence_hint = int(round(float(weighted_score[lane]) / max(1.0, float(processed_frames))))
            final_count = int(min(filtered_track_count, max(final_count, confidence_hint)))

        lane_counts[lane] = max(0, int(final_count))

        print("RAW FRAME COUNTS:", raw_counts)
        print("FILTERED COUNTS:", filtered_counts)
        print("FINAL COUNT:", lane_counts[lane])

    print("TRACK DURATIONS:", dict(track_frame_count))
    print("TRACK MOVEMENTS:", track_movement)
    print("LANE VOTES:", {track_id: dict(votes) for track_id, votes in lane_votes.items()})
    print("LANE VEHICLES:", {lane: sorted(list(ids)) for lane, ids in lane_vehicles.items()})
    print("STATE_EXTRACTOR lane_counts:", lane_counts)
    print("FINAL COUNTS:", lane_counts)
    analyze_counts(lane_counts_per_frame)

    tuned_cfg = _auto_tune_config(lane_counts_per_frame, lane_counts, cfg)
    tuned_cfg = _apply_adaptive_feedback(
        tuned_cfg,
        lane_counts_per_frame,
        lane_counts,
        all_confidences,
        track_movement,
        frame_width,
    )
    if tuned_cfg != cfg:
        print("AUTO-TUNE SUGGESTION:", tuned_cfg)

    print("EXPECTED VS DETECTED (manual check needed)")
    quality_score = compute_quality_score(lane_counts_per_frame, lane_counts)
    print("FINAL CONFIG USED:", cfg)
    print("FINAL LANE COUNTS:", lane_counts)
    print("QUALITY SCORE:", quality_score)
    print("DEBUG ----")
    print("TOTAL DETECTIONS:", total_detections_seen)
    print("VALID TRACKS:", len(valid_tracks))
    print("LANE VEHICLES:", lane_vehicles)
    print("FINAL LANE COUNTS:", lane_counts)
    final_lane_counts_list = [int(lane_counts.get(lane, 0) or 0) for lane in LANES]
    print("FINAL LANE COUNTS:", final_lane_counts_list)
    root_cause, diagnosis_lines = diagnose_root_cause(total_detections_seen, valid_tracks, lane_vehicles, lane_counts)
    print(f"ROOT CAUSE: {root_cause}")
    for line in diagnosis_lines[:3]:
        print(line)

    return {
        "lane_vehicles": {lane: sorted(list(ids)) for lane, ids in lane_vehicles.items()},
        "lane_counts": lane_counts,
        "lane_counts_per_frame": {lane: list(lane_counts_per_frame.get(lane, [])) for lane in LANES},
        "simulation_state": build_simulation_state(lane_counts),
        "processed_frames": int(processed_frames),
        "fps": float(fps),
        "max_frames": int(max_frames),
        "seconds_processed": float(seconds),
        "config_used": dict(cfg),
        "tuned_config_suggestion": tuned_cfg,
        "quality_score": float(quality_score),
    }


def build_simulation_state(lane_counts):
    lanes = {lane: [] for lane in LANES}
    for lane in LANES:
        count = int((lane_counts or {}).get(lane, 0) or 0)
        for index in range(count):
            vehicle_id = f"video-{lane}-{index + 1}"
            lanes[lane].append(
                {
                    "id": vehicle_id,
                    "vehicleId": vehicle_id,
                    "vehicleType": "car",
                    "laneId": lane,
                    "position": 0,
                    "spawnedAt": 0,
                }
            )
    return {"lanes": lanes}


def diagnose_root_cause(total_detections_seen, valid_tracks, lane_vehicles, lane_counts):
    assigned_tracks = sum(len(ids) for ids in lane_vehicles.values()) if isinstance(lane_vehicles, dict) else 0
    final_lane_total = sum(int((lane_counts or {}).get(lane, 0) or 0) for lane in LANES)

    if int(total_detections_seen) <= 0:
        return "detection", [
            "TOTAL DETECTIONS stayed at 0, so the detector never produced usable boxes.",
            "Downstream stages cannot recover once the detection stage is empty.",
        ]
    if len(valid_tracks) <= 0:
        return "tracking", [
            "Detections existed, but no track survived the tracker filters long enough to become valid.",
            "This points to matching, aging, or confirmation logic in the tracking stage.",
        ]
    if assigned_tracks <= 0:
        return "lane mapping", [
            "Tracks existed, but none were assigned to a lane.",
            "That means the center-point to lane-region mapping is failing before aggregation.",
        ]
    if final_lane_total <= 0:
        return "aggregation", [
            "Tracks were assigned to lanes, but the final lane counts still collapsed to zero.",
            "That suggests the final aggregation step is dropping or zeroing the lane totals.",
        ]
    return "unknown", [
        "The pipeline produced detections, tracks, lane assignments, and non-zero lane counts.",
        "The zero-count symptom does not reproduce in this short diagnostic pass.",
    ]


def extract_initial_state(
    video_path,
    config_path,
    seconds_to_process=3.0,
    min_confidence=0.35,
    min_track_frames=3,
):
    global CONFIG
    config_override = {
        "confidence_threshold": float(min_confidence),
        "min_track_frames": int(min_track_frames),
    }
    cfg = _merged_config(config_override)
    result = _extract_with_config(video_path, config_path, seconds_to_process, cfg)
    suggested = result.get("tuned_config_suggestion")
    if isinstance(suggested, dict) and suggested != CONFIG:
        CONFIG = dict(suggested)
        _save_best_config(CONFIG)
    return result


def run_parameter_sweep(video_path, config_path=None, seconds_to_process=3.0):
    global CONFIG
    if config_path is None:
        config_path = Path(__file__).resolve().parents[0] / "config" / "junction_demo.json"

    sweeps = [
        {"movement_ratio": 0.005},
        {"movement_ratio": 0.01},
        {"movement_ratio": 0.02},
        {"min_track_frames": 3},
        {"min_track_frames": 5},
        {"min_track_frames": 8},
        {"confidence_threshold": 0.4},
        {"confidence_threshold": 0.5},
        {"confidence_threshold": 0.6},
        {"frame_skip": 2},
        {"frame_skip": 3},
        {"lane_vote_threshold": 2},
        {"lane_vote_threshold": 3},
        {"lane_vote_threshold": 4},
    ]

    sweep_results = []
    for override in sweeps:
        cfg = _merged_config(override)
        print("\n================ PARAMETER SWEEP ================")
        print("SWEEP CONFIG:", cfg)
        result = _extract_with_config(video_path, config_path, seconds_to_process, cfg)
        lane_counts = result.get("lane_counts", {})
        lane_counts_per_frame = result.get("lane_counts_per_frame", {})
        score = compute_quality_score(lane_counts_per_frame, lane_counts)
        sweep_results.append({"config": cfg, "lane_counts": lane_counts, "score": float(score)})
        print("SWEEP RESULT COUNTS:", lane_counts)
        print("SWEEP RESULT SCORE:", float(score))

    print("\n================ SWEEP SUMMARY ================")
    for item in sweep_results:
        print("CONFIG:", item["config"])
        print("COUNTS:", item["lane_counts"])
        print("SCORE:", item["score"])

    best = max(sweep_results, key=lambda x: x.get("score", float("-inf"))) if sweep_results else None
    if best is not None:
        print("BEST CONFIG:", best["config"])
        print("BEST SCORE:", best["score"])
        CONFIG = dict(best["config"])
        _save_best_config(CONFIG)

    print("\nPARAMETER GUIDANCE:")
    print("- movement_ratio too low -> noise, too high -> misses")
    print("- min_track_frames too low -> noise, too high -> misses")
    print("- confidence_threshold too low -> false positives, too high -> misses")
    print("- frame_skip too low -> noise, too high -> misses")
    print("- lane_vote_threshold too low -> wrong lane, too high -> missing assignments")

    if best is not None:
        print("FINAL CONFIG USED:", CONFIG)
        print("FINAL LANE COUNTS:", best["lane_counts"])
        print("QUALITY SCORE:", best["score"])

    print("EXPECTED VS DETECTED (manual check needed)")
    return sweep_results
