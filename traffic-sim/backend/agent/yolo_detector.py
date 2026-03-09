# Import required modules
from ultralytics import YOLO
import os
import numpy as np

# Constants for YOLO detection
YOLO_MODEL_PATH = 'models/yolo_traffic.pt'
CONFIDENCE_THRESHOLD = 0.4

# Indian vehicle class names
VEHICLE_CLASSES = ['car', 'bike', 'ambulance', 'truck', 'bus',
                  'autorickshaw', 'motorcycle', 'van']
AMBULANCE_CLASSES = ['ambulance']

# Load YOLO model if available
if os.path.exists(YOLO_MODEL_PATH):
    yolo_model = YOLO(YOLO_MODEL_PATH)
else:
    yolo_model = None  # Model not loaded if file missing


def detect_vehicles_in_frame(frame, lane_regions):
    # Return empty lane state if model not loaded
    if yolo_model is None:
        return get_empty_lane_state()
    # Run YOLO inference
    results = yolo_model(frame, conf=CONFIDENCE_THRESHOLD)
    lane_state = {lane: {'count': 0, 'hasAmbulance': False, 'avgWaitTime': 0.0, 'ambulanceWaitTime': 0.0}
                  for lane in lane_regions}
    for r in results:
        for box in r.boxes:
            cls = r.names[int(box.cls)]
            if cls not in VEHICLE_CLASSES:
                continue
            # Get center point of bounding box
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            # Check which lane region center falls into
            for lane, region in lane_regions.items():
                rx1, ry1, rx2, ry2 = region
                if rx1 <= cx <= rx2 and ry1 <= cy <= ry2:
                    lane_state[lane]['count'] += 1
                    if cls in AMBULANCE_CLASSES:
                        lane_state[lane]['hasAmbulance'] = True
                    break
    return lane_state


def get_empty_lane_state():
    # Return default lane state with zeros and False
    return {
        'north': {'count': 0, 'hasAmbulance': False, 'avgWaitTime': 0.0, 'ambulanceWaitTime': 0.0},
        'south': {'count': 0, 'hasAmbulance': False, 'avgWaitTime': 0.0, 'ambulanceWaitTime': 0.0},
        'east':  {'count': 0, 'hasAmbulance': False, 'avgWaitTime': 0.0, 'ambulanceWaitTime': 0.0},
        'west':  {'count': 0, 'hasAmbulance': False, 'avgWaitTime': 0.0, 'ambulanceWaitTime': 0.0}
    }
