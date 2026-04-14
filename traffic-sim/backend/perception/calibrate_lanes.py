# pyright: reportMissingImports=false

import argparse
import json
from pathlib import Path

import cv2

LANE_ORDER = ['north', 'east', 'south', 'west']


def draw_instructions(frame, lane_index):
    lane_name = LANE_ORDER[lane_index]
    text = f"Draw {lane_name.upper()} lane rectangle: click top-left then bottom-right"
    cv2.putText(
        frame,
        text,
        (20, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        "Keys: [n] next lane, [r] reset lane, [s] save, [q] quit",
        (20, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (200, 200, 200),
        1,
        cv2.LINE_AA,
    )


def run_calibration(video_path, output_path, timer_duration):
    cap = cv2.VideoCapture(str(video_path))
    ok, frame = cap.read()
    cap.release()

    if not ok:
        raise RuntimeError(f"Could not read first frame from {video_path}")

    base = frame.copy()
    lane_regions = {lane: None for lane in LANE_ORDER}
    clicks = []
    lane_index = 0

    def refresh_display():
        display = base.copy()
        draw_instructions(display, lane_index)

        for lane in LANE_ORDER:
            region = lane_regions.get(lane)
            if region:
                x1, y1, x2, y2 = region
                cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(
                    display,
                    lane.upper(),
                    (x1, max(20, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )

        if len(clicks) == 1:
            x1, y1 = clicks[0]
            cv2.circle(display, (x1, y1), 4, (0, 200, 255), -1)

        cv2.imshow('Lane Calibration', display)

    def mouse_callback(event, x, y, flags, param):
        nonlocal clicks, lane_regions, lane_index
        if event != cv2.EVENT_LBUTTONDOWN:
            return

        if len(clicks) == 0:
            clicks = [(x, y)]
        else:
            x1, y1 = clicks[0]
            rx1, ry1 = min(x1, x), min(y1, y)
            rx2, ry2 = max(x1, x), max(y1, y)
            lane = LANE_ORDER[lane_index]
            lane_regions[lane] = [int(rx1), int(ry1), int(rx2), int(ry2)]
            clicks = []

        refresh_display()

    cv2.namedWindow('Lane Calibration', cv2.WINDOW_NORMAL)
    cv2.setMouseCallback('Lane Calibration', mouse_callback)
    refresh_display()

    while True:
        key = cv2.waitKey(30) & 0xFF
        if key == ord('q'):
            break
        if key == ord('r'):
            lane_regions[LANE_ORDER[lane_index]] = None
            clicks = []
            refresh_display()
        if key == ord('n'):
            lane_index = min(len(LANE_ORDER) - 1, lane_index + 1)
            clicks = []
            refresh_display()
        if key == ord('s'):
            if not all(lane_regions[lane] for lane in LANE_ORDER):
                print('Please define all lane rectangles before saving.')
                continue
            payload = {
                'name': Path(video_path).stem,
                'timer_duration': int(timer_duration),
                'lane_regions': lane_regions,
            }
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as file:
                json.dump(payload, file, indent=2)
            print(f'Saved calibration config to: {output_path}')
            break

    cv2.destroyAllWindows()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Calibrate lane ROIs from first video frame')
    parser.add_argument('--video', required=True, help='Path to video file')
    parser.add_argument('--output', default='backend/perception/config/junction_demo.json', help='Output json config path')
    parser.add_argument('--timer-duration', type=int, default=120, help='Timer duration in seconds for prototype run')
    args = parser.parse_args()

    run_calibration(
        video_path=Path(args.video),
        output_path=Path(args.output),
        timer_duration=args.timer_duration,
    )
