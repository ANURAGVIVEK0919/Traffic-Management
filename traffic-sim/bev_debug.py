import argparse
from pathlib import Path

import cv2
import numpy as np


def draw_grid(image, step=80, color=(80, 80, 80), thickness=1):
    height, width = image.shape[:2]
    for x in range(0, width, step):
        cv2.line(image, (x, 0), (x, height - 1), color, thickness, cv2.LINE_AA)
    for y in range(0, height, step):
        cv2.line(image, (0, y), (width - 1, y), color, thickness, cv2.LINE_AA)


def draw_vertical_guides(image, color=(120, 180, 255), thickness=2):
    height, width = image.shape[:2]
    guide_x = [int(width * 0.25), int(width * 0.50), int(width * 0.75)]
    for x in guide_x:
        cv2.line(image, (x, 0), (x, height - 1), color, thickness, cv2.LINE_AA)


def get_default_src_points(frame_width, frame_height):
    """Return TL, TR, BR, BL points for a road-surface trapezoid.

    Adjust these ratios only if your camera angle differs a lot.
    Keep all points on asphalt and avoid sidewalks/buildings.
    """
    w = float(frame_width)
    h = float(frame_height)
    center_x = w * 0.5

    # Keep a slight default tilt so lane-aligned mode does not start flat.
    top_left_y = h * 0.57
    top_right_y = h * 0.59
    bottom_y = h * 0.95
    top_half = w * 0.11
    bottom_half = w * 0.40

    return np.array(
        [
            [center_x - top_half, top_left_y],  # top-left (far lane edge)
            [center_x + top_half, top_right_y], # top-right (far lane edge)
            [center_x + bottom_half, bottom_y], # bottom-right (near lane edge)
            [center_x - bottom_half, bottom_y], # bottom-left (near lane edge)
        ],
        dtype=np.float32,
    )


def get_default_dst_points(width=500, height=700):
    return np.array(
        [
            [0.0, 0.0],
            [float(width - 1), 0.0],
            [float(width - 1), float(height - 1)],
            [0.0, float(height - 1)],
        ],
        dtype=np.float32,
    )


def align_top_edge(src_pts):
    """Make top-left and top-right share the same y-coordinate."""
    aligned = np.array(src_pts, dtype=np.float32, copy=True)
    top_y = float((aligned[0, 1] + aligned[1, 1]) * 0.5)
    aligned[0, 1] = top_y
    aligned[1, 1] = top_y
    return aligned


def preserve_lane_alignment(src_pts):
    """Keep the relative slope between top points instead of flattening it."""
    return np.array(src_pts, dtype=np.float32, copy=True)


def enforce_trapezoid_symmetry(src_pts, align_to_lane=True):
    """Keep a balanced trapezoid while optionally preserving top-edge tilt."""
    if align_to_lane:
        # In lane-aligned mode, never force horizontal top alignment.
        fixed = preserve_lane_alignment(src_pts)
    else:
        fixed = align_top_edge(src_pts)

    top_left = fixed[0]
    top_right = fixed[1]
    bottom_right = fixed[2]
    bottom_left = fixed[3]

    center_x = float((top_left[0] + top_right[0]) * 0.5)
    top_half = float(abs(top_right[0] - top_left[0]) * 0.5)
    bottom_half_left = float(center_x - bottom_left[0])
    bottom_half_right = float(bottom_right[0] - center_x)
    bottom_half = float((bottom_half_left + bottom_half_right) * 0.5)
    bottom_half = max(top_half + 10.0, bottom_half)

    if align_to_lane:
        # Lane-aligned mode: x-only correction, preserve all y values.
        fixed[0, 0] = center_x - top_half
        fixed[1, 0] = center_x + top_half
        fixed[2, 0] = center_x + bottom_half
        fixed[3, 0] = center_x - bottom_half
    else:
        # Horizontal mode: allow top flattening and mild bottom y correction.
        top_y = float(top_left[1])
        bottom_y = float((bottom_left[1] + bottom_right[1]) * 0.5)
        if bottom_y <= top_y + 20.0:
            bottom_y = top_y + 20.0
        fixed[2, 0] = center_x + bottom_half
        fixed[2, 1] = bottom_y
        fixed[3, 0] = center_x - bottom_half
        fixed[3, 1] = bottom_y

    return fixed


def clip_src_points(src_pts, frame_width, frame_height):
    clipped = np.array(src_pts, dtype=np.float32, copy=True)
    clipped[:, 0] = np.clip(clipped[:, 0], 0.0, float(frame_width - 1))
    clipped[:, 1] = np.clip(clipped[:, 1], 0.0, float(frame_height - 1))
    return clipped


def limit_point_shift(old_pts, new_pts, max_shift=2.5):
    limited = np.array(old_pts, dtype=np.float32, copy=True)
    target = np.array(new_pts, dtype=np.float32, copy=True)
    deltas = target - limited
    magnitudes = np.linalg.norm(deltas, axis=1)
    for idx, magnitude in enumerate(magnitudes):
        if float(magnitude) > float(max_shift) and float(magnitude) > 0.0:
            scale = float(max_shift) / float(magnitude)
            deltas[idx] = deltas[idx] * scale
    return limited + deltas


def top_edge_error(src_pts):
    return float(abs(float(src_pts[0, 1]) - float(src_pts[1, 1])))


def top_edge_slope(src_pts):
    dx = float(src_pts[1, 0] - src_pts[0, 0])
    dy = float(src_pts[1, 1] - src_pts[0, 1])
    if abs(dx) < 1e-6:
        return 0.0
    return dy / dx


def top_edge_angle_degrees(src_pts):
    dx = float(src_pts[1, 0] - src_pts[0, 0])
    dy = float(src_pts[1, 1] - src_pts[0, 1])
    return float(np.degrees(np.arctan2(dy, dx)))


def format_src_points(src_pts):
    rounded = [[round(float(point[0]), 2), round(float(point[1]), 2)] for point in src_pts]
    return f"src_pts = np.float32({rounded})"


def save_src_points(src_pts, file_path="src_points.txt"):
    text = format_src_points(src_pts)
    with open(file_path, "w", encoding="utf-8") as output_file:
        output_file.write(text + "\n")
    print(text)
    print(f"Saved calibrated source points to {file_path}")


def parse_args():
    parser = argparse.ArgumentParser(description="Standalone BEV debugger for traffic video")
    parser.add_argument("--video", required=True, help="Path to input video file")
    parser.add_argument("--width", type=int, default=1280, help="Frame width after resize")
    parser.add_argument("--height", type=int, default=720, help="Frame height after resize")
    parser.add_argument("--bev-width", type=int, default=500, help="BEV output width")
    parser.add_argument("--bev-height", type=int, default=700, help="BEV output height")
    parser.add_argument("--save-frame", type=int, default=50, help="Frame index to auto-save debug image")
    parser.add_argument("--output", default="bev_debug.jpg", help="Output debug image path")
    parser.add_argument("--move-step", type=int, default=3, help="Point move step in pixels")
    parser.add_argument("--no-auto-fix", action="store_true", help="Disable automatic top-edge/symmetry correction")
    parser.add_argument(
        "--horizontal-top",
        action="store_true",
        help="Use old behavior: force horizontal top edge instead of lane-aligned tilt",
    )
    return parser.parse_args()


def build_homography(src_pts, dst_pts):
    homography, _ = cv2.findHomography(src_pts, dst_pts)
    if homography is None:
        raise RuntimeError("Failed to compute homography from the given points")
    return homography


def on_mouse(event, x, y, _flags, state):
    if event != cv2.EVENT_LBUTTONDOWN:
        return

    points = state["src_pts"]
    click = np.array([float(x), float(y)], dtype=np.float32)
    distances = np.linalg.norm(points - click, axis=1)
    closest = int(np.argmin(distances))

    if float(distances[closest]) < 35.0:
        state["selected_index"] = closest


def main():
    args = parse_args()
    video_path = Path(args.video)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    target_width = int(args.width)
    target_height = int(args.height)
    bev_width = int(args.bev_width)
    bev_height = int(args.bev_height)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    # Keep source points centralized here for easy manual adjustment.
    src_pts = get_default_src_points(target_width, target_height)
    # Clean top-down rectangle target.
    dst_pts = get_default_dst_points(bev_width, bev_height)

    state = {
        "src_pts": src_pts,
        "selected_index": 0,
        "move_step": max(1, int(args.move_step)),
        "fine_step": 1,
        "precision_mode": False,
        "auto_fix": not bool(args.no_auto_fix),
        "align_to_lane": not bool(args.horizontal_top),
    }

    window_name = "BEV Debug: Original | Top-Down"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window_name, on_mouse, state)

    save_done = False
    frame_index = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break

            frame = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_LINEAR)

            original_pts = np.array(state["src_pts"], dtype=np.float32, copy=True)
            if state["auto_fix"]:
                corrected_pts = enforce_trapezoid_symmetry(
                    original_pts,
                    align_to_lane=state["align_to_lane"],
                )
                corrected_pts = clip_src_points(corrected_pts, target_width, target_height)
                # Limit auto-fix movement per frame to avoid sudden jumps.
                state["src_pts"][:] = limit_point_shift(original_pts, corrected_pts, max_shift=1.0)

            if state["align_to_lane"]:
                assert not np.isclose(
                    state["src_pts"][0][1],
                    state["src_pts"][1][1],
                    atol=1e-6,
                ), "Top edge is being flattened incorrectly"

            # Recompute homography each frame so live tweaks update immediately.
            homography = build_homography(state["src_pts"], dst_pts)
            bev_frame = cv2.warpPerspective(frame, homography, (bev_width, bev_height))

            original_view = frame.copy()
            bev_view = bev_frame.copy()

            src_int = state["src_pts"].astype(np.int32)
            cv2.polylines(original_view, [src_int], True, (0, 255, 255), 2, cv2.LINE_AA)
            # Highlight top edge separately to make tilt easy to spot.
            cv2.line(
                original_view,
                tuple(src_int[0]),
                tuple(src_int[1]),
                (255, 80, 80),
                3,
                cv2.LINE_AA,
            )
            for index, point in enumerate(src_int):
                color = (0, 0, 255) if index == state["selected_index"] else (0, 255, 255)
                cv2.circle(original_view, tuple(point), 7, color, -1, cv2.LINE_AA)
                cv2.putText(
                    original_view,
                    str(index + 1),
                    (int(point[0]) + 8, int(point[1]) - 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    color,
                    2,
                    cv2.LINE_AA,
                )

            draw_grid(bev_view, step=80, color=(90, 90, 90), thickness=1)
            draw_vertical_guides(bev_view, color=(140, 220, 255), thickness=2)
            cv2.polylines(bev_view, [dst_pts.astype(np.int32)], True, (0, 255, 255), 2, cv2.LINE_AA)

            # Resize BEV for side-by-side display.
            bev_display = cv2.resize(bev_view, (target_width, target_height), interpolation=cv2.INTER_LINEAR)

            cv2.putText(original_view, "Original", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2, cv2.LINE_AA)
            cv2.putText(bev_display, "BEV", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2, cv2.LINE_AA)
            cv2.putText(
                original_view,
                "Tips: keep points on road only; make lane edges symmetric for vertical BEV lanes",
                (20, target_height - 45),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.58,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                original_view,
                "Controls: 1-4 select point | WASD move | I/K step +/- | R reset | ESC exit",
                (20, target_height - 18),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.58,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            cv2.putText(
                original_view,
                "F auto-fix | L lane-align | G precision mode | P print/save src_pts",
                (20, target_height - 72),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.58,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            edge_error = top_edge_error(state["src_pts"])
            slope = top_edge_slope(state["src_pts"])
            angle = top_edge_angle_degrees(state["src_pts"])
            print(f"Top edge slope: {slope:.6f}, angle: {angle:.2f}")
            slope_text = f"Top edge slope={slope:.4f} angle={angle:.2f} deg"
            cv2.putText(
                original_view,
                slope_text,
                (20, 75),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.72,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )

            bev_tilt_text = f"BEV tilt: {angle:.2f} deg"
            tilt_color = (0, 255, 0) if abs(angle) < 0.5 else (0, 220, 255)
            cv2.putText(
                bev_display,
                bev_tilt_text,
                (20, 75),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                tilt_color,
                2,
                cv2.LINE_AA,
            )

            if abs(angle) < 0.5:
                cv2.putText(
                    bev_display,
                    "Alignment OK",
                    (20, 105),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )

            if angle > 0.5:
                helper_text = "If BEV tilts right -> move P1 up & P2 down"
            elif angle < -0.5:
                helper_text = "If BEV tilts left -> move P1 down & P2 up"
            else:
                helper_text = "Fine-tune: adjust only P1/P2 in precision mode"

            cv2.putText(
                original_view,
                helper_text,
                (20, 195),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )

            if not state["align_to_lane"] and edge_error <= 0.5:
                warning_text = "Warning: top edge slope forced near zero (horizontal mode)"
                cv2.putText(
                    original_view,
                    warning_text,
                    (20, 105),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.75,
                    (0, 0, 255),
                    2,
                    cv2.LINE_AA,
                )
                if frame_index % 30 == 0:
                    print(warning_text)

            auto_fix_text = f"Auto-fix: {'ON' if state['auto_fix'] else 'OFF'} (press F to toggle)"
            cv2.putText(
                original_view,
                auto_fix_text,
                (20, 135),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )

            align_text = f"Align to lane: {'ON' if state['align_to_lane'] else 'OFF'} (press L to toggle)"
            cv2.putText(
                original_view,
                align_text,
                (20, 225),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )

            active_step = state["fine_step"] if state["precision_mode"] else state["move_step"]
            precision_text = f"Precision mode: {'ON' if state['precision_mode'] else 'OFF'} | step={active_step}px"
            cv2.putText(
                original_view,
                precision_text,
                (20, 255),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )

            combined = np.hstack((original_view, bev_display))
            cv2.imshow(window_name, combined)

            if (not save_done) and frame_index >= int(args.save_frame):
                saved = cv2.imwrite(str(args.output), combined)
                if saved:
                    print(f"Saved BEV debug image: {args.output}")
                else:
                    print(f"Failed to save BEV debug image: {args.output}")
                save_done = True

            key = cv2.waitKey(1) & 0xFF
            step = state["fine_step"] if state["precision_mode"] else state["move_step"]
            if key == 27:  # ESC
                break
            if key in (ord("1"), ord("2"), ord("3"), ord("4")):
                state["selected_index"] = int(chr(key)) - 1
            elif key == ord("w"):
                state["src_pts"][state["selected_index"]][1] -= step
            elif key == ord("s"):
                state["src_pts"][state["selected_index"]][1] += step
            elif key == ord("a"):
                state["src_pts"][state["selected_index"]][0] -= step
            elif key == ord("d"):
                state["src_pts"][state["selected_index"]][0] += step
            elif key == ord("i"):
                state["move_step"] = min(50, state["move_step"] + 1)
                print(f"Move step: {state['move_step']} px")
            elif key == ord("k"):
                state["move_step"] = max(1, state["move_step"] - 1)
                print(f"Move step: {state['move_step']} px")
            elif key == ord("g"):
                state["precision_mode"] = not state["precision_mode"]
                print(f"Precision mode: {state['precision_mode']}")
            elif key == ord("r"):
                state["src_pts"][:] = get_default_src_points(target_width, target_height)
                print("Source points reset to defaults")
            elif key == ord("f"):
                state["auto_fix"] = not state["auto_fix"]
                print(f"Auto-fix set to: {state['auto_fix']}")
            elif key == ord("l"):
                state["align_to_lane"] = not state["align_to_lane"]
                print(f"Align-to-lane set to: {state['align_to_lane']}")
            elif key == ord("p"):
                save_src_points(state["src_pts"], file_path="src_points.txt")

            # Keep points inside frame bounds.
            state["src_pts"][:] = clip_src_points(state["src_pts"], target_width, target_height)

            frame_index += 1
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
