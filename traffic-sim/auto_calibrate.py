"""
Auto-generate lane config from video first frame.
Creates sensible quadrant-based lane regions for a typical 4-way intersection.
Run: python auto_calibrate.py
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

VIDEO_PATH = r"e:\Traffic Managment\Traffic-Management\traffic-sim\uploads\WhatsApp Video 2026-04-15 at 5.07.17 PM.mp4"
OUTPUT_PATH = r"e:\Traffic Managment\Traffic-Management\traffic-sim\backend\ai\perception\config\junction_demo.json"

def create_lane_config(width, height):
    """
    Create lane polygon regions for a typical 4-way intersection.
    
    Layout (top-down CCTV view):
    
         |  NORTH  |
    -----+----+----+-----
    WEST |    |    | EAST
    -----+----+----+-----
         |  SOUTH  |
    
    Each lane covers the incoming traffic area (arm of the intersection).
    """
    cx = width / 2
    cy = height / 2

    # Fractions for zone sizing
    # Intersection box in center: 30% of width, 30% of height
    box_w = 0.30  # fraction of width for center box
    box_h = 0.30  # fraction of height for center box

    # North lane — top arm (vehicles coming from top, moving towards center)
    north = [
        [int(cx * 0.45), 0],
        [int(cx * 1.55), 0],
        [int(cx * 1.35), int(cy * 0.80)],
        [int(cx * 0.65), int(cy * 0.80)],
    ]

    # South lane — bottom arm (vehicles coming from bottom, moving towards center)
    south = [
        [int(cx * 0.65), int(cy * 1.20)],
        [int(cx * 1.35), int(cy * 1.20)],
        [int(cx * 1.55), height],
        [int(cx * 0.45), height],
    ]

    # East lane — right arm (vehicles coming from right, moving towards center)
    east = [
        [int(cx * 1.20), int(cy * 0.50)],
        [width, int(cy * 0.45)],
        [width, int(cy * 1.55)],
        [int(cx * 1.20), int(cy * 1.50)],
    ]

    # West lane — left arm (vehicles coming from left, moving towards center)
    west = [
        [0, int(cy * 0.45)],
        [int(cx * 0.80), int(cy * 0.50)],
        [int(cx * 0.80), int(cy * 1.50)],
        [0, int(cy * 1.55)],
    ]

    return {
        "name": "auto_calibrated",
        "timer_duration": 180,
        "lane_regions": {
            "north": {
                "id": "north",
                "label": "north",
                "direction": "incoming",
                "points": north,
                "polygon": north,
            },
            "south": {
                "id": "south",
                "label": "south",
                "direction": "incoming",
                "points": south,
                "polygon": south,
            },
            "east": {
                "id": "east",
                "label": "east",
                "direction": "incoming",
                "points": east,
                "polygon": east,
            },
            "west": {
                "id": "west",
                "label": "west",
                "direction": "incoming",
                "points": west,
                "polygon": west,
            },
        },
        "settings": {
            "min_avg_confidence": 0.10,
            "max_count_jump": 5,
            "confidence_hold_ticks": 1,
            "smooth_alpha": 0.2,
            "tracker_min_seen_frames": 2,
            "tracker_max_missed_frames": 10,
        },
        "homography": {"enabled": False},
    }


def draw_preview(frame, config):
    """Draw lane polygons on frame so we can verify visually."""
    colors = {
        "north": (0, 255, 255),   # yellow
        "south": (255, 0, 255),   # magenta
        "east":  (0, 165, 255),   # orange
        "west":  (255, 128, 0),   # blue
    }
    lane_regions = config["lane_regions"]
    for lane, region in lane_regions.items():
        pts = np.array(region["points"], dtype=np.int32)
        color = colors.get(lane, (255, 255, 255))
        cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=3)
        cx = int(np.mean(pts[:, 0]))
        cy = int(np.mean(pts[:, 1]))
        cv2.putText(frame, lane.upper(), (cx - 20, cy),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2, cv2.LINE_AA)
    return frame


def main():
    cap = cv2.VideoCapture(VIDEO_PATH)
    if not cap.isOpened():
        print(f"ERROR: Cannot open video: {VIDEO_PATH}")
        sys.exit(1)

    ok, frame = cap.read()
    cap.release()
    if not ok:
        print("ERROR: Cannot read first frame")
        sys.exit(1)

    height, width = frame.shape[:2]
    print(f"Video dimensions: {width}x{height}")

    config = create_lane_config(width, height)

    # Save config
    out_path = Path(OUTPUT_PATH)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"Config saved: {out_path}")

    # Save preview image so user can verify lane positions
    preview = draw_preview(frame.copy(), config)
    preview_path = out_path.parent / "calibration_preview.jpg"
    cv2.imwrite(str(preview_path), preview)
    print(f"Preview image saved: {preview_path}")
    print("\nLane regions:")
    for lane, region in config["lane_regions"].items():
        print(f"  {lane}: {region['points']}")
    print("\nDone! Config is ready for video pipeline.")


if __name__ == "__main__":
    main()
