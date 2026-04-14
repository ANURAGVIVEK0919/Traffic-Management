# pyright: reportMissingImports=false

import argparse
import json
from pathlib import Path

import cv2

from backend.perception.lane_processing import LANE_ORDER, make_lane_region, resize_polygon, region_points


def draw_text(frame, lane_index):
    lane_name = LANE_ORDER[lane_index]
    cv2.putText(
        frame,
        f"Draw {lane_name.upper()} polygon lane (>=3 points)",
        (20, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        "Keys: [c] close lane [n] next lane [u] undo [r] reset lane [s] save [q] quit",
        (20, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
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
    current_points = []
    lane_index = 0
    width_scale = 1.0
    depth_scale = 1.0
    depth_offset_px = 0.0

    def get_preview_points(points):
        return resize_polygon(points, frame.shape, width_scale, depth_scale, depth_offset_px)

    def draw_polygon(display, points, color):
        if len(points) >= 1:
            for px, py in points:
                cv2.circle(display, (px, py), 4, color, -1)
        if len(points) >= 2:
            for i in range(1, len(points)):
                cv2.line(display, tuple(points[i - 1]), tuple(points[i]), color, 2)

    def refresh_display():
        display = base.copy()
        draw_text(display, lane_index)

        cv2.putText(
            display,
            f"Resize: width={width_scale:.2f} depth={depth_scale:.2f} offset={depth_offset_px:.0f}px",
            (20, 88),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (180, 220, 255),
            1,
            cv2.LINE_AA,
        )

        for lane in LANE_ORDER:
            region = lane_regions.get(lane)
            if region:
                points = get_preview_points(region_points(region))
                draw_polygon(display, points, (0, 255, 0))
                cv2.line(display, tuple(points[-1]), tuple(points[0]), (0, 255, 0), 2)
                x, y = points[0]
                cv2.putText(
                    display,
                    f"{region.get('label', lane).upper()} / {region.get('direction', 'incoming').upper()}",
                    (x, max(20, y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )

        draw_polygon(display, current_points, (0, 180, 255))
        cv2.imshow('Lane Polygon Calibration', display)

    def mouse_callback(event, x, y, flags, param):
        nonlocal current_points
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        current_points.append([int(x), int(y)])
        refresh_display()

    cv2.namedWindow('Lane Polygon Calibration', cv2.WINDOW_NORMAL)
    cv2.setMouseCallback('Lane Polygon Calibration', mouse_callback)
    refresh_display()

    while True:
        key = cv2.waitKey(30) & 0xFF
        if key == ord('q'):
            break

        if key == ord('u'):
            if current_points:
                current_points.pop()
            refresh_display()

        if key == ord('r'):
            lane_regions[LANE_ORDER[lane_index]] = None
            current_points = []
            refresh_display()

        if key == ord('c'):
            if len(current_points) < 3:
                print('Need at least 3 points to close polygon.')
            else:
                lane_name = LANE_ORDER[lane_index]
                lane_regions[lane_name] = make_lane_region(
                    current_points,
                    frame.shape,
                    flow_direction='incoming',
                    lane_id=lane_name,
                    label=lane_name,
                )
                current_points = []
            refresh_display()

        if key == ord('n'):
            lane_index = min(len(LANE_ORDER) - 1, lane_index + 1)
            current_points = []
            refresh_display()

        if key == ord('['):
            width_scale = max(0.6, width_scale - 0.05)
            refresh_display()

        if key == ord(']'):
            width_scale = min(2.0, width_scale + 0.05)
            refresh_display()

        if key == ord('-'):
            depth_scale = max(0.6, depth_scale - 0.05)
            refresh_display()

        if key == ord('='):
            depth_scale = min(2.0, depth_scale + 0.05)
            refresh_display()

        if key == ord('8'):
            depth_offset_px = max(-200.0, depth_offset_px - 10.0)
            refresh_display()

        if key == ord('9'):
            depth_offset_px = min(200.0, depth_offset_px + 10.0)
            refresh_display()

        if key == ord('s'):
            if not all(lane_regions[lane] for lane in LANE_ORDER):
                print('Please close and define all lane polygons before saving.')
                continue
            saved_lane_regions = {}
            for lane in LANE_ORDER:
                region = lane_regions[lane]
                preview_points = get_preview_points(region['points'])
                saved_lane_regions[lane] = make_lane_region(
                    preview_points,
                    frame.shape,
                    flow_direction='incoming',
                    lane_id=lane,
                    label=lane,
                )
            payload = {
                'name': Path(video_path).stem,
                'timer_duration': int(timer_duration),
                'lane_regions': saved_lane_regions,
            }
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as file:
                json.dump(payload, file, indent=2)
            print(f'Saved polygon calibration config to: {output_path}')
            break

    cv2.destroyAllWindows()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Calibrate polygon lane ROIs from first video frame')
    parser.add_argument('--video', required=True, help='Path to video file')
    parser.add_argument('--output', default='backend/perception/config/junction_demo.json', help='Output json config path')
    parser.add_argument('--timer-duration', type=int, default=120, help='Timer duration in seconds for prototype run')
    args = parser.parse_args()

    run_calibration(
        video_path=Path(args.video),
        output_path=Path(args.output),
        timer_duration=args.timer_duration,
    )
