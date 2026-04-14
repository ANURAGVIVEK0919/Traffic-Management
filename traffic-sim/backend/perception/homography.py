import cv2
import numpy as np

from backend.perception.lane_processing import point_in_region

DEFAULT_TOP_VIEW_SIZE = (800, 800)
LANE_ORDER = ('north', 'south', 'east', 'west')


def compute_homography(src_points, output_size=DEFAULT_TOP_VIEW_SIZE, dst_points=None):
    """Compute homography matrix from 4 image points to a top-view plane."""
    if src_points is None or len(src_points) != 4:
        raise ValueError('src_points must contain exactly 4 points')

    width, height = int(output_size[0]), int(output_size[1])
    src = np.array(src_points, dtype=np.float32)
    if dst_points is None:
        dst = np.array(
            [
                [0.0, 0.0],
                [float(width - 1), 0.0],
                [float(width - 1), float(height - 1)],
                [0.0, float(height - 1)],
            ],
            dtype=np.float32,
        )
    else:
        if len(dst_points) != 4:
            raise ValueError('dst_points must contain exactly 4 points')
        dst = np.array(dst_points, dtype=np.float32)

    H_matrix, _ = cv2.findHomography(src, dst, method=0)
    if H_matrix is None:
        raise RuntimeError('Failed to compute homography matrix')
    return H_matrix


def warp_frame(frame, H_matrix, output_size=DEFAULT_TOP_VIEW_SIZE):
    """Warp perspective frame into top-view frame."""
    width, height = int(output_size[0]), int(output_size[1])
    return cv2.warpPerspective(frame, H_matrix, (width, height))


def transform_point(x, y, H_matrix):
    """Transform a single point using homography matrix."""
    src = np.array([[[float(x), float(y)]]], dtype=np.float32)
    dst = cv2.perspectiveTransform(src, H_matrix)
    tx, ty = dst[0][0]
    return float(tx), float(ty)


def default_top_view_lanes(output_size=DEFAULT_TOP_VIEW_SIZE):
    width, height = int(output_size[0]), int(output_size[1])

    left_inner = int(width * 0.35)
    right_inner = int(width * 0.65)
    top_inner = int(height * 0.35)
    bottom_inner = int(height * 0.65)

    return {
        'north': [left_inner, 0, right_inner, top_inner],
        'south': [left_inner, bottom_inner, right_inner, height - 1],
        'west': [0, top_inner, left_inner, bottom_inner],
        'east': [right_inner, top_inner, width - 1, bottom_inner],
    }


def normalize_top_view_lanes(lane_regions_top_view, output_size=DEFAULT_TOP_VIEW_SIZE):
    if not lane_regions_top_view:
        raise ValueError('homography.lane_regions_top_view must be explicitly defined')

    regions = lane_regions_top_view
    normalized = {}

    for lane_id in LANE_ORDER:
        region = regions.get(lane_id)
        if region is None:
            continue

        if isinstance(region, dict):
            points = region.get('points') or region.get('polygon') or region.get('rect')
            label = region.get('label', lane_id)
        else:
            points = region
            label = lane_id

        if isinstance(points, list) and len(points) == 4 and all(isinstance(v, (int, float)) for v in points):
            x1, y1, x2, y2 = [float(v) for v in points]
            points = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
        elif isinstance(points, list) and all(isinstance(p, (list, tuple)) and len(p) == 2 for p in points):
            points = [[float(p[0]), float(p[1])] for p in points]
        else:
            raise ValueError(f'Invalid top-view lane region for lane: {lane_id}')

        normalized[lane_id] = {
            'id': lane_id,
            'label': label,
            'direction': 'incoming',
            'points': points,
            'polygon': points,
            'bounds': (
                min(p[0] for p in points),
                min(p[1] for p in points),
                max(p[0] for p in points),
                max(p[1] for p in points),
            ),
            'polygon_cv2': np.array(points, dtype=np.int32),
        }

    missing = [lane for lane in LANE_ORDER if lane not in normalized]
    if missing:
        raise ValueError(f'Missing top-view lanes: {missing}')

    return normalized


def _point_within_rect_strict(tx, ty, bounds):
    if bounds is None:
        return False
    min_x, min_y, max_x, max_y = bounds
    return float(min_x) < float(tx) < float(max_x) and float(min_y) < float(ty) < float(max_y)


def _point_within_frame(tx, ty, output_size):
    width, height = int(output_size[0]), int(output_size[1])
    return 0.0 <= float(tx) < float(width) and 0.0 <= float(ty) < float(height)


RED = ((483, 218), (778, 153))
YELLOW = ((829, 166), (1101, 334))
BROWN = ((687, 715), (1104, 393))
BLACK = ((423, 278), (543, 710))


def line_side(p1, p2, point):
    x1, y1 = p1
    x2, y2 = p2
    x, y = point
    return (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)


def get_lane(tx, ty, lane_regions_top_view):
    point = (float(tx), float(ty))
    x, y = point
    red_side = line_side(*RED, point)
    yellow_side = line_side(*YELLOW, point)
    brown_side = line_side(*BROWN, point)
    black_side = line_side(*BLACK, point)

    if red_side > 0 and y < 260:
        return 'north'
    if yellow_side > 0 and x >= 800:
        return 'east'
    if brown_side > 0 and y >= 500:
        return 'south'
    if black_side < 0 and x < 520 and y >= 180:
        return 'west'
    return 'north'


def select_source_points(frame, window_name='Homography Source Points'):
    """Pick exactly 4 points from frame: TL, TR, BR, BL."""
    selected_points = []
    clone = frame.copy()

    def on_mouse(event, x, y, _flags, _param):
        if event == cv2.EVENT_LBUTTONDOWN and len(selected_points) < 4:
            selected_points.append([float(x), float(y)])

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window_name, on_mouse)

    while True:
        canvas = clone.copy()
        for idx, point in enumerate(selected_points):
            px, py = int(point[0]), int(point[1])
            cv2.circle(canvas, (px, py), 6, (0, 255, 255), -1)
            cv2.putText(canvas, str(idx + 1), (px + 8, py - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)

        help_text = 'Click 4 points (TL,TR,BR,BL). c=confirm r=reset q=cancel'
        cv2.putText(canvas, help_text, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.imshow(window_name, canvas)

        key = cv2.waitKey(20) & 0xFF
        if key == ord('r'):
            selected_points.clear()
        elif key == ord('c') and len(selected_points) == 4:
            break
        elif key == ord('q'):
            selected_points = []
            break

    cv2.destroyWindow(window_name)

    if len(selected_points) != 4:
        raise RuntimeError('Homography point selection cancelled or incomplete')

    return selected_points


class HomographyLaneMapper:
    def __init__(self, H_matrix, output_size=DEFAULT_TOP_VIEW_SIZE, lane_regions_top_view=None):
        self.H_matrix = H_matrix
        self.output_size = (int(output_size[0]), int(output_size[1]))
        self.lane_regions_top_view = normalize_top_view_lanes(lane_regions_top_view, self.output_size)

    def warp_frame(self, frame):
        return warp_frame(frame, self.H_matrix, self.output_size)

    def transform_point(self, x, y):
        return transform_point(x, y, self.H_matrix)

    def is_point_in_output(self, tx, ty):
        return _point_within_frame(tx, ty, self.output_size)

    def get_lane(self, tx, ty):
        return get_lane(tx, ty, self.lane_regions_top_view)

    def point_in_lane(self, lane_id, tx, ty):
        region = self.lane_regions_top_view.get(lane_id)
        if region is None:
            return False
        return _point_within_rect_strict(tx, ty, region.get('bounds')) and point_in_region(float(tx), float(ty), region, buffer_px=0)

    def draw_debug(self, warped_frame, transformed_points, lane_counts):
        output = warped_frame.copy()

        lane_colors = {
            'north': (0, 255, 255),
            'east': (0, 180, 255),
            'south': (0, 255, 0),
            'west': (255, 180, 0),
        }

        for lane_id, region in self.lane_regions_top_view.items():
            polygon = region.get('polygon_cv2')
            if polygon is not None:
                cv2.polylines(output, [polygon], True, lane_colors.get(lane_id, (0, 220, 255)), 2)

            min_x, min_y, max_x, _ = region.get('bounds', (0, 0, 0, 0))
            label_text = f"{lane_id}: {int(lane_counts.get(lane_id, 0))}"
            cv2.putText(output, label_text, (int(min_x) + 8, int(min_y) + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, lane_colors.get(lane_id, (255, 255, 255)), 2)

        for point in transformed_points:
            tx, ty = point.get('top_view', (None, None))
            if tx is None or ty is None:
                continue
            lane = point.get('lane') or 'none'
            color = lane_colors.get(lane, (0, 0, 255)) if lane in LANE_ORDER else (0, 0, 255)
            cv2.circle(output, (int(tx), int(ty)), 4, color, -1)

        return output
