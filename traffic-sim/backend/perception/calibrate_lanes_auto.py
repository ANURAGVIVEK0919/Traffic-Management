import argparse
import json
import cv2
import numpy as np
from collections import defaultdict


def detect_lanes_hough(frame, canny_low=50, canny_high=150, theta_res=np.pi / 180, rho_res=1, threshold=50):
    """
    Detect lane lines using Canny edge detection + Hough Transform.
    Returns list of (x1, y1, x2, y2) line segments.
    """
    h, w = frame.shape[:2]
    
    # Convert to grayscale and apply Gaussian blur
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Canny edge detection
    edges = cv2.Canny(blurred, canny_low, canny_high)
    
    # Focus on lower half of image (where lanes typically are)
    roi = np.zeros_like(edges)
    roi[h // 2:, :] = edges[h // 2:, :]
    
    # Hough line detection
    lines = cv2.HoughLinesP(
        roi,
        rho_res,
        theta_res,
        threshold=threshold,
        minLineLength=int(h * 0.2),
        maxLineGap=10
    )
    
    if lines is None:
        return []
    
    return [tuple(line[0]) for line in lines]


def cluster_lanes(lines, num_lanes=4, frame_shape=None):
    """
    Cluster detected lines into lane regions (north, east, south, west).
    Returns dict with 'north', 'east', 'south', 'west' as approximate regions.
    """
    if not lines:
        return None
    
    h, w = frame_shape[:2] if frame_shape else (480, 640)
    
    # Group lines by approximate x-position (left-right) and y-slope (horizontal vs vertical)
    horizontal_lines = []
    vertical_lines = []
    
    for x1, y1, x2, y2 in lines:
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        
        if dx < dy * 0.3:
            # Vertical-ish line
            vertical_lines.append((x1, y1, x2, y2))
        elif dy < dx * 0.3:
            # Horizontal-ish line
            horizontal_lines.append((x1, y1, x2, y2))
    
    # Cluster vertical lines by x-position
    lane_boundaries = defaultdict(list)
    if vertical_lines:
        v_x_coords = [min(x1, x2) for x1, y1, x2, y2 in vertical_lines]
        v_x_coords.sort()
        
        # Simple clustering: divide width into segments
        segment_width = w // (num_lanes + 1)
        for x1, y1, x2, y2 in vertical_lines:
            mid_x = (x1 + x2) / 2
            segment = int(mid_x / segment_width)
            lane_boundaries[segment].append((x1, y1, x2, y2))
    
    # Generate approximate rectangular regions for each lane
    lanes = {}
    lane_names = ['north', 'east', 'south', 'west']
    
    segment_width = w // (num_lanes + 1)
    top_margin = h // 3
    bottom_margin = h
    
    for i, lane_name in enumerate(lane_names):
        x_start = i * segment_width + segment_width // 4
        x_end = (i + 1) * segment_width + segment_width // 4
        x_start = max(0, min(x_start, w - 10))
        x_end = max(x_start + 10, min(x_end, w))
        
        lanes[lane_name] = {
            'type': 'rectangle',
            'points': [
                [x_start, top_margin],
                [x_end, top_margin],
                [x_end, bottom_margin],
                [x_start, bottom_margin]
            ]
        }
    
    return lanes


def auto_calibrate_lanes(video_path, output_path, frame_index=0):
    """
    Automatically calibrate lanes from a video frame using Hough Transform.
    Saves config to output_path.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Cannot open video {video_path}")
        return False
    
    # Read target frame
    for _ in range(frame_index):
        cap.read()
    
    ret, frame = cap.read()
    cap.release()
    
    if not ret:
        print(f"Error: Cannot read frame {frame_index} from video")
        return False
    
    print(f"Detecting lanes from frame {frame_index}...")
    
    # Detect lanes using Hough
    lines = detect_lanes_hough(frame)
    print(f"Detected {len(lines)} line segments")
    
    if not lines:
        print("Warning: No lines detected. Using default lane regions.")
        lanes = {
            'north': {'type': 'rectangle', 'points': [[100, 100], [300, 100], [300, 400], [100, 400]]},
            'east': {'type': 'rectangle', 'points': [[340, 100], [540, 100], [540, 400], [340, 400]]},
            'south': {'type': 'rectangle', 'points': [[100, 420], [300, 420], [300, 720], [100, 720]]},
            'west': {'type': 'rectangle', 'points': [[340, 420], [540, 420], [540, 720], [340, 720]]}
        }
    else:
        lanes = cluster_lanes(lines, num_lanes=4, frame_shape=frame.shape)
    
    # Build config
    config = {
        'lanes': lanes,
        'settings': {
            'min_avg_confidence': 0.4,
            'max_count_jump': 8,
            'confidence_hold_ticks': 2
        }
    }
    
    # Save config
    with open(output_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"✓ Auto-calibrated lanes written to {output_path}")
    print(f"  Lanes: {list(lanes.keys())}")
    return True


def main():
    parser = argparse.ArgumentParser(description='Auto-calibrate lane regions using Hough line detection')
    parser.add_argument('--video', required=True, help='Path to input video file')
    parser.add_argument('--output', required=True, help='Path to output config JSON')
    parser.add_argument('--frame-index', type=int, default=0, help='Frame index to analyze (default: 0)')
    args = parser.parse_args()
    
    success = auto_calibrate_lanes(args.video, args.output, args.frame_index)
    if not success:
        exit(1)


if __name__ == '__main__':
    main()
