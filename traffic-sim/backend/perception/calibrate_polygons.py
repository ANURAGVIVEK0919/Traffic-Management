#!/usr/bin/env python
"""
Interactive lane polygon calibration tool.

Usage:
    python -m backend.perception.calibrate_polygons <video_path>

Example:
    python -m backend.perception.calibrate_polygons /path/to/video.mp4

Controls:
    LEFT CLICK  - Add a polygon point (draws green dot)
    RIGHT CLICK - Finish current lane polygon, move to next lane
    S KEY       - Save all polygons and quit
    ESC KEY     - Cancel calibration and quit without saving
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np

# Lane calibration order
LANE_ORDER = ["north", "south", "east", "west"]

# Colors for each lane (BGR format for OpenCV)
LANE_COLORS = {
    "north": (0, 255, 0),    # Green
    "south": (0, 0, 255),    # Red
    "east": (255, 0, 0),     # Blue
    "west": (0, 255, 255),   # Yellow
}

# Configuration file path
CONFIG_PATH = Path(__file__).parent / "config" / "junction_demo.json"


class PolygonCalibrator:
    def __init__(self, frame, config_path=CONFIG_PATH):
        """Initialize the calibrator with a video frame."""
        self.frame = frame.copy()
        self.display_frame = frame.copy()
        self.config_path = Path(config_path)
        
        # Load existing config to preserve non-region data
        self.existing_config = self._load_existing_config()
        
        # Current state
        self.lane_index = 0
        self.current_lane = LANE_ORDER[0]
        self.polygons = {lane: [] for lane in LANE_ORDER}
        self.done = False
        
        # Window setup
        self.window_name = "Lane Polygon Calibration"
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, 1200, 800)
        cv2.setMouseCallback(self.window_name, self._mouse_callback)
    
    def _load_existing_config(self):
        """Load existing junction_demo.json to preserve structure."""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"[WARNING] Could not load existing config: {e}")
        
        # Return default structure if file doesn't exist
        return {
            "name": "demo-junction",
            "timer_duration": 120,
            "settings": {
                "min_avg_confidence": 0.25,
                "max_count_jump": 3,
                "confidence_hold_ticks": 1
            },
            "homography": {
                "enabled": False,
                "source_points_space": "capture",
                "source_points": [],
                "output_size": [800, 800],
                "lane_regions_top_view": {}
            },
            "lane_regions": {}
        }
    
    def _update_display(self):
        """Update the display frame with current state."""
        self.display_frame = self.frame.copy()
        
        # Draw completed polygons
        for lane in LANE_ORDER[:self.lane_index]:
            if self.polygons[lane]:
                points = np.array(self.polygons[lane], dtype=np.int32)
                cv2.polylines(self.display_frame, [points], isClosed=True, 
                            color=LANE_COLORS[lane], thickness=2)
                # Fill with semi-transparent color
                overlay = self.display_frame.copy()
                cv2.fillPoly(overlay, [points], LANE_COLORS[lane])
                cv2.addWeighted(overlay, 0.3, self.display_frame, 0.7, 0, self.display_frame)
        
        # Draw current polygon in progress
        if self.polygons[self.current_lane]:
            points = np.array(self.polygons[self.current_lane], dtype=np.int32)
            cv2.polylines(self.display_frame, [points], isClosed=False, 
                        color=LANE_COLORS[self.current_lane], thickness=3)
            
            # Draw points
            for point in self.polygons[self.current_lane]:
                cv2.circle(self.display_frame, tuple(point), 5, 
                        LANE_COLORS[self.current_lane], -1)
        
        # Draw title with instructions
        title = f"Calibrating: {self.current_lane.upper()}"
        instruction = f"Points: {len(self.polygons[self.current_lane])} | LEFT=add | RIGHT=finish | S=save | ESC=cancel"
        
        cv2.putText(self.display_frame, title, (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        cv2.putText(self.display_frame, instruction, (10, 70), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)
        
        # Show current lane index progress
        progress = f"Lane {self.lane_index + 1}/4 ({', '.join(LANE_ORDER[:self.lane_index + 1])})"
        cv2.putText(self.display_frame, progress, (10, self.frame.shape[0] - 20), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 200, 255), 1)
    
    def _mouse_callback(self, event, x, y, flags, param):
        """Handle mouse events."""
        if event == cv2.EVENT_LBUTTONDOWN:
            # Left click: add point
            self.polygons[self.current_lane].append([x, y])
            print(f"[{self.current_lane.upper()}] Added point ({x}, {y})")
            self._update_display()
        
        elif event == cv2.EVENT_RBUTTONDOWN:
            # Right click: finish current lane and move to next
            if not self.polygons[self.current_lane]:
                print(f"[{self.current_lane.upper()}] Polygon is empty, cannot finish")
                return
            
            print(f"[{self.current_lane.upper()}] Finished with {len(self.polygons[self.current_lane])} points")
            
            if self.lane_index < len(LANE_ORDER) - 1:
                self.lane_index += 1
                self.current_lane = LANE_ORDER[self.lane_index]
                print(f"[CALIBRATOR] Moving to {self.current_lane.upper()}")
            else:
                print("[CALIBRATOR] All lanes done! Press S to save.")
            
            self._update_display()
    
    def run(self):
        """Run the calibration loop."""
        print("[CALIBRATOR] Starting polygon calibration")
        print(f"[CALIBRATOR] Order: {' → '.join([l.upper() for l in LANE_ORDER])}")
        print(f"[CALIBRATOR] Waiting for calibration of {self.current_lane.upper()}...")
        
        self._update_display()
        cv2.imshow(self.window_name, self.display_frame)
        
        while not self.done:
            key = cv2.waitKey(100) & 0xFF
            
            if key == ord('s') or key == ord('S'):
                # Save calibration
                if self._validate_all_polygons():
                    self._save_config()
                    print("[CALIBRATOR] Calibration saved successfully!")
                    self.done = True
                else:
                    print("[CALIBRATOR] ERROR: Not all lanes have been calibrated")
            
            elif key == 27:  # ESC
                print("[CALIBRATOR] Calibration cancelled")
                self.done = True
            
            cv2.imshow(self.window_name, self.display_frame)
        
        cv2.destroyWindow(self.window_name)
    
    def _validate_all_polygons(self):
        """Check if all lanes have at least 3 points."""
        for lane in LANE_ORDER:
            if len(self.polygons[lane]) < 3:
                print(f"[ERROR] Lane {lane} has only {len(self.polygons[lane])} points (need ≥3)")
                return False
        return True
    
    def _save_config(self):
        """Save the calibrated polygons to junction_demo.json."""
        config = self.existing_config.copy()
        
        # Update lane_regions with new polygons
        lane_regions = {}
        for lane in LANE_ORDER:
            points = [[float(x), float(y)] for x, y in self.polygons[lane]]
            lane_regions[lane] = {
                "id": lane,
                "label": lane,
                "direction": "incoming",
                "polygon": points,
                "points": points
            }
        
        config["lane_regions"] = lane_regions
        
        # Create directory if needed
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write config
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        # Print confirmation
        for lane in LANE_ORDER:
            pts = self.polygons[lane]
            print(f"[CALIBRATOR] Saved polygon for lane {lane}: {len(pts)} points")


def main():
    if len(sys.argv) < 2:
        print("Usage: python calibrate_polygons.py <video_path>")
        sys.exit(1)
    
    video_path = sys.argv[1]
    
    # Open video and read first frame
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] Could not open video: {video_path}")
        sys.exit(1)
    
    ok, frame = cap.read()
    cap.release()
    
    if not ok:
        print(f"[ERROR] Could not read first frame from {video_path}")
        sys.exit(1)
    
    print(f"[CALIBRATOR] Loaded frame: {frame.shape}")
    
    # Run calibrator
    calibrator = PolygonCalibrator(frame)
    calibrator.run()


if __name__ == "__main__":
    main()
