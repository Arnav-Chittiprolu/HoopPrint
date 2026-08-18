"""Pose quality metrics for clip event gates."""

from __future__ import annotations

from app.services.features.geometry import LandmarkLookup, side_names
from app.services.pose_job import FrameKeypoints


def _frame_lookup(frame: FrameKeypoints | dict) -> LandmarkLookup:
    if isinstance(frame, FrameKeypoints):
        return LandmarkLookup(frame.keypoints)
    return LandmarkLookup(frame["keypoints"])


def frame_track_confidence(frame: FrameKeypoints | dict) -> float:
    if isinstance(frame, FrameKeypoints):
        return float(frame.track_confidence)
    return float(frame.get("track_confidence") or 1.0)


def mean_track_confidence(frames: list) -> float:
    if not frames:
        return 0.0
    return sum(frame_track_confidence(f) for f in frames) / len(frames)


def shooting_arm_visibility(
    lookup: LandmarkLookup,
    *,
    dominant_hand: str,
) -> float:
    names = side_names(dominant_hand)
    visibilities: list[float] = []
    for key in (names["shoulder"], names["elbow"], names["wrist"]):
        point = lookup.get(key)
        if point is None:
            continue
        visibilities.append(float(point.get("visibility") or 0.0))
    if not visibilities:
        return 0.0
    return sum(visibilities) / len(visibilities)


def hip_visibility(lookup: LandmarkLookup) -> float:
    visibilities: list[float] = []
    for key in ("left_hip", "right_hip"):
        point = lookup.get(key)
        if point is None:
            continue
        visibilities.append(float(point.get("visibility") or 0.0))
    if not visibilities:
        return 0.0
    return sum(visibilities) / len(visibilities)


def count_pose_samples_before_after(
    parsed: list[tuple[int, LandmarkLookup]],
    *,
    center_list_index: int,
    min_before: int,
    min_after: int,
) -> tuple[int, int]:
    before = center_list_index
    after = len(parsed) - center_list_index - 1
    return before, after
