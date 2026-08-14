"""Release-frame and motion-onset heuristics."""

from __future__ import annotations

import numpy as np

from app.services.features.geometry import (
    LandmarkLookup,
    angle_at,
    side_names,
    standing_height_proxy,
)


def _wrist_heights(frames: list[tuple[int, LandmarkLookup]], wrist_name: str) -> list[float | None]:
    heights: list[float | None] = []
    for _, lookup in frames:
        wrist = lookup.xy(wrist_name)
        heights.append(float(wrist[1]) if wrist is not None else None)
    return heights


def _elbow_angles(
    frames: list[tuple[int, LandmarkLookup]], names: dict[str, str]
) -> list[float | None]:
    angles: list[float | None] = []
    for _, lookup in frames:
        shoulder = lookup.xy(names["shoulder"])
        elbow = lookup.xy(names["elbow"])
        wrist = lookup.xy(names["wrist"])
        if shoulder is None or elbow is None or wrist is None:
            angles.append(None)
            continue
        try:
            angles.append(angle_at(elbow, shoulder, wrist))
        except ValueError:
            angles.append(None)
    return angles


def _first_valid_index(values: list[float | None]) -> int | None:
    for index, value in enumerate(values):
        if value is not None:
            return index
    return None


def argmax_valid(values: list[float | None]) -> int | None:
    best_index: int | None = None
    best_value = float("-inf")
    for index, value in enumerate(values):
        if value is not None and value > best_value:
            best_value = value
            best_index = index
    return best_index


def argmin_valid(values: list[float | None]) -> int | None:
    best_index: int | None = None
    best_value = float("inf")
    for index, value in enumerate(values):
        if value is not None and value < best_value:
            best_value = value
            best_index = index
    return best_index


def find_shot_release_index(
    frames: list[tuple[int, LandmarkLookup]], dominant_hand: str
) -> int | None:
    """Peak shooting-wrist height (y-up) — proxy for ball release."""
    names = side_names(dominant_hand)
    return argmax_valid(_wrist_heights(frames, names["wrist"]))


def find_pass_release_index(
    frames: list[tuple[int, LandmarkLookup]], dominant_hand: str
) -> int | None:
    """Most extended elbow — proxy for pass release."""
    names = side_names(dominant_hand)
    return argmax_valid(_elbow_angles(frames, names))


def find_catch_index(
    frames: list[tuple[int, LandmarkLookup]],
    *,
    before_index: int,
) -> int | None:
    """Hands closest together before release — proxy for 'ball reaches hands'."""
    best_index: int | None = None
    best_dist = float("inf")
    for index, (_, lookup) in enumerate(frames[: before_index + 1]):
        left = lookup.xy("left_wrist")
        right = lookup.xy("right_wrist")
        if left is None or right is None:
            continue
        dist = float(np.linalg.norm(left - right))
        if dist < best_dist:
            best_dist = dist
            best_index = index
    return best_index


def local_maxima_indices(values: list[float | None], *, min_prominence: float) -> list[int]:
    peaks: list[int] = []
    for index in range(1, len(values) - 1):
        current = values[index]
        prev = values[index - 1]
        nxt = values[index + 1]
        if current is None or prev is None or nxt is None:
            continue
        if current >= prev and current >= nxt and (current - min(prev, nxt)) >= min_prominence:
            peaks.append(index)
    if not peaks:
        fallback = argmax_valid(values)
        if fallback is not None:
            peaks.append(fallback)
    return peaks


def mean_standing_height(frames: list[tuple[int, LandmarkLookup]]) -> float | None:
    heights = [standing_height_proxy(lookup) for _, lookup in frames]
    valid = [height for height in heights if height is not None]
    if not valid:
        return None
    return float(sum(valid) / len(valid))


def first_valid_index(values: list[float | None]) -> int | None:
    return _first_valid_index(values)
