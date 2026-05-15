from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple


@dataclass
class AssociationCandidate:
    score: float
    distance: float
    observation_index: int
    track_id: int


class StableTracker:
    def __init__(
        self,
        max_age: int = 8,
        match_distance: float = 80.0,
        iou_threshold: float = 0.05,
        size_similarity_threshold: float = 0.15,
        debug: bool = True,
    ):
        self.max_age = int(max_age)
        self.match_distance = float(match_distance)
        self.iou_threshold = float(iou_threshold)
        self.size_similarity_threshold = float(size_similarity_threshold)
        self.debug = bool(debug)
        self.frame_index = 0
        self.last_matches: Dict[int, int] = {}

    @staticmethod
    def _bbox_from_track(track: Dict) -> List[float] | None:
        bbox = track.get('bbox')
        if not bbox or len(bbox) != 4:
            return None
        return [float(value) for value in bbox]

    @staticmethod
    def _bbox_center(bbox: Sequence[float]) -> Tuple[float, float]:
        x1, y1, x2, y2 = [float(value) for value in bbox]
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @staticmethod
    def _bbox_area(bbox: Sequence[float]) -> float:
        x1, y1, x2, y2 = [float(value) for value in bbox]
        return max(0.0, (x2 - x1)) * max(0.0, (y2 - y1))

    @staticmethod
    def _iou(bbox_a: Sequence[float], bbox_b: Sequence[float]) -> float:
        ax1, ay1, ax2, ay2 = [float(value) for value in bbox_a]
        bx1, by1, bx2, by2 = [float(value) for value in bbox_b]

        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)
        inter_w = max(0.0, inter_x2 - inter_x1)
        inter_h = max(0.0, inter_y2 - inter_y1)
        inter_area = inter_w * inter_h

        area_a = StableTracker._bbox_area(bbox_a)
        area_b = StableTracker._bbox_area(bbox_b)
        union_area = area_a + area_b - inter_area
        if union_area <= 0.0:
            return 0.0
        return float(inter_area / union_area)

    @staticmethod
    def _size_similarity(bbox_a: Sequence[float], bbox_b: Sequence[float]) -> float:
        area_a = StableTracker._bbox_area(bbox_a)
        area_b = StableTracker._bbox_area(bbox_b)
        if area_a <= 0.0 or area_b <= 0.0:
            return 0.0

        area_ratio = min(area_a, area_b) / max(area_a, area_b)

        aw = max(1.0, float(bbox_a[2]) - float(bbox_a[0]))
        ah = max(1.0, float(bbox_a[3]) - float(bbox_a[1]))
        bw = max(1.0, float(bbox_b[2]) - float(bbox_b[0]))
        bh = max(1.0, float(bbox_b[3]) - float(bbox_b[1]))
        aspect_a = aw / ah
        aspect_b = bw / bh
        aspect_ratio = min(aspect_a, aspect_b) / max(aspect_a, aspect_b)

        return float(max(0.0, min(1.0, 0.65 * area_ratio + 0.35 * aspect_ratio)))

    def _distance_similarity(self, bbox_a: Sequence[float], bbox_b: Sequence[float]) -> Tuple[float, float]:
        center_a = self._bbox_center(bbox_a)
        center_b = self._bbox_center(bbox_b)
        distance = ((center_a[0] - center_b[0]) ** 2 + (center_a[1] - center_b[1]) ** 2) ** 0.5
        if self.match_distance <= 0.0:
            return 0.0, float(distance)
        similarity = max(0.0, 1.0 - (distance / self.match_distance))
        return float(similarity), float(distance)

    def _match_score(self, observation: Dict, track: Dict) -> Tuple[float, float]:
        observation_bbox = observation.get('bbox')
        track_bbox = self._bbox_from_track(track)
        if not observation_bbox or track_bbox is None:
            return 0.0, float('inf')

        iou_score = self._iou(observation_bbox, track_bbox)
        distance_score, distance = self._distance_similarity(observation_bbox, track_bbox)
        size_score = self._size_similarity(observation_bbox, track_bbox)

        if iou_score < self.iou_threshold and distance_score < 0.25 and size_score < self.size_similarity_threshold:
            return 0.0, distance

        label_bonus = 0.05 if observation.get('label') == track.get('label') else 0.0
        score = (0.55 * iou_score) + (0.25 * distance_score) + (0.20 * size_score) + label_bonus
        return float(score), float(distance)

    def associate(self, observations: List[Dict], tracks: Dict[int, Dict]):
        self.frame_index += 1

        active_tracks = {
            track_id: track
            for track_id, track in tracks.items()
            if int(track.get('missed_frames', 0)) <= self.max_age
        }

        candidates: List[AssociationCandidate] = []
        for observation_index, observation in enumerate(observations):
            for track_id, track in active_tracks.items():
                score, distance = self._match_score(observation, track)
                if score <= 0.0:
                    continue
                candidates.append(
                    AssociationCandidate(
                        score=score,
                        distance=distance,
                        observation_index=observation_index,
                        track_id=track_id,
                    )
                )

        candidates.sort(key=lambda candidate: (-candidate.score, candidate.distance, candidate.observation_index, candidate.track_id))

        matched_observations = set()
        matched_tracks = set()
        matches: List[Tuple[int, int]] = []

        for candidate in candidates:
            if candidate.observation_index in matched_observations or candidate.track_id in matched_tracks:
                continue
            matched_observations.add(candidate.observation_index)
            matched_tracks.add(candidate.track_id)
            matches.append((candidate.observation_index, candidate.track_id))

        unmatched_tracks = [track_id for track_id in active_tracks if track_id not in matched_tracks]
        unmatched_observations = [index for index in range(len(observations)) if index not in matched_observations]

        continued_tracks = [track_id for _, track_id in matches if track_id in self.last_matches]
        new_tracks = [track_id for _, track_id in matches if track_id not in self.last_matches]

        if self.debug:
            print(
                f"[StableTracker] frame={self.frame_index} matches={matches} "
                f"continued={continued_tracks} new={new_tracks} "
                f"unmatched_tracks={unmatched_tracks} unmatched_observations={unmatched_observations}"
            )

        self.last_matches = {track_id: track_id for _, track_id in matches}
        return matches, unmatched_tracks, unmatched_observations

    def reset(self):
        self.frame_index = 0
        self.last_matches = {}