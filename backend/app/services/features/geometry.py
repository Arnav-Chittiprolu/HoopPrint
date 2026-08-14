"""Geometry helpers for pose landmarks.

Coordinate conventions
----------------------
MediaPipe Pose uses normalized image coordinates:
- x in [0, 1], origin at left
- y in [0, 1], origin at **top** (y increases downward)
- z is MediaPipe's depth estimate (not used for Phase 3 angles)

All angles and vertical ratios in this package convert to a **y-up** plane
(`y_up = 1 - y`) so "higher off the floor" is a larger y.

Landmark indices follow MediaPipe's 33-point pose (see `pose_landmarks.py`).
Shooting/passing side defaults to the right arm; `dominant_hand="left"` swaps.
"""

from __future__ import annotations

import math

import numpy as np

from app.services.pose_landmarks import POSE_LANDMARK_NAMES

MIN_VISIBILITY = 0.3


class LandmarkLookup:
    """One frame of named landmarks."""

    def __init__(self, keypoints: dict) -> None:
        self._by_name: dict[str, dict] = {}
        for point in keypoints.get("landmarks") or []:
            name = point.get("name")
            if isinstance(name, str):
                self._by_name[name] = point

    def get(self, name: str) -> dict | None:
        return self._by_name.get(name)

    def xy(self, name: str, *, y_up: bool = True) -> np.ndarray | None:
        point = self.get(name)
        if point is None:
            return None
        if float(point.get("visibility") or 0.0) < MIN_VISIBILITY:
            return None
        x = float(point["x"])
        y = float(point["y"])
        if y_up:
            y = 1.0 - y
        return np.array([x, y], dtype=float)

    def visible(self, name: str) -> bool:
        return self.xy(name) is not None


def parse_frames(frames: list) -> list[tuple[int, LandmarkLookup]]:
    parsed: list[tuple[int, LandmarkLookup]] = []
    for frame in frames:
        if hasattr(frame, "frame_index"):
            parsed.append((int(frame.frame_index), LandmarkLookup(frame.keypoints)))
        else:
            parsed.append((int(frame["frame_index"]), LandmarkLookup(frame["keypoints"])))
    parsed.sort(key=lambda item: item[0])
    return parsed


def side_names(dominant_hand: str) -> dict[str, str]:
    hand = "left" if str(dominant_hand).lower().startswith("l") else "right"
    other = "left" if hand == "right" else "right"
    return {
        "wrist": f"{hand}_wrist",
        "elbow": f"{hand}_elbow",
        "shoulder": f"{hand}_shoulder",
        "hip": f"{hand}_hip",
        "other_wrist": f"{other}_wrist",
    }


def midpoint(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a + b) / 2.0


def distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))


def angle_at(vertex: np.ndarray, arm_a: np.ndarray, arm_b: np.ndarray) -> float:
    """Interior angle ABC (degrees) with vertex at B=`vertex`."""
    vec_a = arm_a - vertex
    vec_b = arm_b - vertex
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a < 1e-9 or norm_b < 1e-9:
        raise ValueError("Zero-length arm for angle")
    cosine = float(np.clip(np.dot(vec_a, vec_b) / (norm_a * norm_b), -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def vector_elevation_deg(vec: np.ndarray) -> float:
    """Angle of a 2D vector from +x (horizontal), 0–180°. 90° is straight up."""
    deg = math.degrees(math.atan2(float(vec[1]), float(vec[0])))
    if deg < 0:
        deg += 360.0
    if deg > 180:
        deg = 360.0 - deg
    return deg


def standing_height_proxy(lookup: LandmarkLookup) -> float | None:
    """Nose-to-mid-ankle distance in y-up normalized coords."""
    nose = lookup.xy("nose")
    left = lookup.xy("left_ankle")
    right = lookup.xy("right_ankle")
    if nose is None:
        return None
    if left is not None and right is not None:
        ankles = midpoint(left, right)
    elif left is not None:
        ankles = left
    elif right is not None:
        ankles = right
    else:
        return None
    height = distance(nose, ankles)
    return height if height > 1e-6 else None


def mid_hip(lookup: LandmarkLookup) -> np.ndarray | None:
    left = lookup.xy("left_hip")
    right = lookup.xy("right_hip")
    if left is not None and right is not None:
        return midpoint(left, right)
    return left if left is not None else right


assert len(POSE_LANDMARK_NAMES) == 33
