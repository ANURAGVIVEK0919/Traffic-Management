"""Quick script to regenerate preview from updated config."""
import json
import numpy as np
import cv2

VIDEO_PATH = r"e:\Traffic Managment\Traffic-Management\traffic-sim\uploads\WhatsApp Video 2026-04-15 at 5.07.17 PM.mp4"
CONFIG_PATH = r"e:\Traffic Managment\Traffic-Management\traffic-sim\backend\ai\perception\config\junction_demo.json"
OUTPUT_PATH = r"e:\Traffic Managment\Traffic-Management\traffic-sim\backend\ai\perception\config\calibration_preview.jpg"

cap = cv2.VideoCapture(VIDEO_PATH)
ok, frame = cap.read()
cap.release()

with open(CONFIG_PATH) as f:
    config = json.load(f)

colors = {"north": (0,255,255), "south": (255,0,255), "east": (0,165,255), "west": (255,128,0)}
for lane, region in config["lane_regions"].items():
    pts = np.array(region["points"], dtype=np.int32)
    color = colors.get(lane, (255,255,255))
    cv2.polylines(frame, [pts], True, color, 3)
    cx, cy = int(np.mean(pts[:,0])), int(np.mean(pts[:,1]))
    cv2.putText(frame, lane.upper(), (cx-25, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2, cv2.LINE_AA)

cv2.imwrite(OUTPUT_PATH, frame)
print("Preview saved!")
