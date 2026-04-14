import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np
from ultralytics import YOLO


# COCO class IDs for vehicles.
VEHICLE_CLASS_IDS = {2, 3, 5, 7}  # car, motorcycle, bus, truck
CONFIDENCE_THRESHOLD = 0.4
INFERENCE_WIDTH = 960
DEFAULT_LANE_CONFIG_PATH = Path("backend/perception/config/junction_demo.json")
LANE_NAMES = ["NORTH", "SOUTH", "WEST", "EAST"]


def detect_and_annotate_vehicles(
    model: YOLO,
    frame: "cv2.Mat",
    conf_threshold: float = CONFIDENCE_THRESHOLD,
) -> Tuple["cv2.Mat", List[Tuple[int, int, int, int, str, float, int]]]:
    """
    Run YOLO tracking and return annotated frame plus valid vehicle detections.

    Each detection tuple contains:
    (x1, y1, x2, y2, class_name, confidence, track_id)
    """
    detections: List[Tuple[int, int, int, int, str, float, int]] = []

    results = model.track(frame, persist=True, conf=conf_threshold, verbose=False)
    annotated_frame = frame.copy()

    if not results:
        return annotated_frame, detections

    names = results[0].names
    boxes = results[0].boxes

    if boxes is None or len(boxes) == 0:
        return annotated_frame, detections

    for box in boxes:
        class_id = int(box.cls.item())
        confidence = float(box.conf.item())
        track_id = int(box.id[0]) if box.id is not None else None

        if class_id not in VEHICLE_CLASS_IDS:
            continue
        if confidence < conf_threshold:
            continue
        if track_id is None:
            continue

        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        class_name = names.get(class_id, str(class_id))
        detections.append((x1, y1, x2, y2, class_name, confidence, track_id))

        # Draw green bounding box and label text for valid vehicle detections.
        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = f"ID {track_id} | {class_name} {confidence:.2f}"
        text_y = max(y1 - 8, 20)
        cv2.putText(
            annotated_frame,
            label,
            (x1, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

    return annotated_frame, detections


def load_lanes(config_path: Path) -> Dict[str, List[Tuple[int, int]]]:
    """Load lane polygons from JSON and return normalized integer point lists."""
    with config_path.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    lanes = config.get("lanes")
    if lanes is None:
        lane_regions = config.get("lane_regions", {})
        normalized_lanes: Dict[str, List[Tuple[int, int]]] = {}
        for lane_id, region in lane_regions.items():
            if isinstance(region, list) and len(region) == 4:
                x1, y1, x2, y2 = region
                normalized_lanes[lane_id] = [
                    (int(x1), int(y1)),
                    (int(x2), int(y1)),
                    (int(x2), int(y2)),
                    (int(x1), int(y2)),
                ]
        return normalized_lanes

    normalized_lanes = {}
    for lane_id, points in lanes.items():
        if not isinstance(points, list) or len(points) < 3:
            continue
        normalized_points: List[Tuple[int, int]] = []
        for point in points:
            if not isinstance(point, list) or len(point) != 2:
                normalized_points = []
                break
            normalized_points.append((int(point[0]), int(point[1])))
        if normalized_points:
            normalized_lanes[lane_id] = normalized_points

    return normalized_lanes


def draw_lanes(frame: "cv2.Mat", lanes: Dict[str, List[Tuple[int, int]]]) -> "cv2.Mat":
    """Draw lane polygons and labels on the frame."""
    annotated_frame = frame.copy()

    for lane_id, polygon in lanes.items():
        if len(polygon) < 3:
            continue

        polygon_array = np.array(polygon, dtype=np.int32)
        cv2.polylines(annotated_frame, [polygon_array], isClosed=True, color=(255, 0, 0), thickness=2)

        label_x, label_y = polygon[0]
        cv2.putText(
            annotated_frame,
            lane_id,
            (label_x, max(label_y - 8, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 0, 0),
            2,
            cv2.LINE_AA,
        )

    return annotated_frame


def assign_lane_from_center(cx: float, cy: float, mid_x: int, mid_y: int) -> int:
    """Assign lane index from detection center using frame midpoint quadrants."""
    if cx < mid_x and cy < mid_y:
        return 0  # NORTH
    elif cx >= mid_x and cy < mid_y:
        return 1  # EAST
    elif cx < mid_x and cy >= mid_y:
        return 2  # WEST
    else:
        return 3  # SOUTH


def resize_to_width(frame: "cv2.Mat", target_width: int = INFERENCE_WIDTH) -> "cv2.Mat":
    """Resize frame while preserving aspect ratio."""
    height, width = frame.shape[:2]
    if width == target_width:
        return frame

    scale = target_width / float(width)
    target_height = int(height * scale)
    return cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)


def run_vehicle_detection(video_path: str, lane_config_path: Path) -> None:
    """Read a video, detect vehicles frame-by-frame, and display results live."""
    model = YOLO("yolov8s.pt")
    lanes = load_lanes(lane_config_path)
    vehicle_memory: Dict[int, Dict[str, object]] = {}
    lane_counts = [0, 0, 0, 0]

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 30.0

    frame_index = 0
    window_name = "YOLOv8 Vehicle Detection"

    try:
        while True:
            success, frame = cap.read()
            if not success:
                break

            frame_index += 1
            current_time = frame_index / fps
            resized_frame = resize_to_width(frame, target_width=INFERENCE_WIDTH)
            annotated_frame = draw_lanes(resized_frame, lanes)
            annotated_frame, vehicle_detections = detect_and_annotate_vehicles(
                model,
                annotated_frame,
                conf_threshold=CONFIDENCE_THRESHOLD,
            )

            lane_counts = [0, 0, 0, 0]
            lane_wait_times = {lane_name: [] for lane_name in LANE_NAMES}
            lane_active_counts = {lane_name: 0 for lane_name in LANE_NAMES}

            height, width = resized_frame.shape[:2]
            mid_x = width // 2
            mid_y = height // 2

            for x1, y1, x2, y2, class_name, confidence, track_id in vehicle_detections:
                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0

                if abs(cx - mid_x) < 30 and abs(cy - mid_y) < 30:
                    continue

                lane_index = assign_lane_from_center(cx, cy, mid_x, mid_y)
                lane_name = LANE_NAMES[lane_index]

                lane_counts[lane_index] += 1

                if track_id not in vehicle_memory:
                    vehicle_memory[track_id] = {
                        "lane": lane_name,
                        "counted": True,
                        "first_seen": current_time,
                    }

                first_seen = float(vehicle_memory[track_id]["first_seen"])
                vehicle_memory[track_id]["lane"] = lane_name
                wait_time = current_time - first_seen
                lane_wait_times[lane_name].append(wait_time)
                lane_active_counts[lane_name] += 1

                cv2.circle(annotated_frame, (int(cx), int(cy)), 4, (0, 255, 255), -1)
                cv2.putText(
                    annotated_frame,
                    lane_name,
                    (int(cx) + 6, max(int(cy) - 6, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 255, 255),
                    2,
                    cv2.LINE_AA,
                )

            y_offset = 30
            for lane_name in LANE_NAMES:
                wait_times = lane_wait_times.get(lane_name, [])
                avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0.0
                cv2.putText(
                    annotated_frame,
                    f"{lane_name}: {lane_active_counts[lane_name]} vehicles | avg wait: {avg_wait:.1f}s",
                    (20, y_offset),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
                y_offset += 30

            print(f"Frame {frame_index}: {sum(lane_counts)} vehicles counted")
            cv2.imshow(window_name, annotated_frame)

            # Exit if user presses 'q'.
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Real-time vehicle and lane counting from video using YOLOv8 (COCO)."
    )
    parser.add_argument("video_path", help="Path to input video file")
    parser.add_argument(
        "--lane-config",
        type=Path,
        default=DEFAULT_LANE_CONFIG_PATH,
        help="Path to the lane configuration JSON file",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_vehicle_detection(args.video_path, args.lane_config)
