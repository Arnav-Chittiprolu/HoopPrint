from __future__ import annotations

import math

import numpy as np

from app.services.features.geometry import LandmarkLookup, distance, mid_hip
from app.services.features.heuristics import mean_standing_height


def extract_drive_features(
    frames: list[tuple[int, LandmarkLookup]],
    *,
    height_in: float | None = None,
) -> list[dict]:
    if len(frames) < 3:
        raise ValueError("Need at least 3 pose frames for drive features")

    hips: list[np.ndarray | None] = [mid_hip(lookup) for _, lookup in frames]
    standing = mean_standing_height(frames) or 1.0

    speeds: list[float | None] = [None]
    for prev, curr in zip(hips, hips[1:]):
        if prev is None or curr is None:
            speeds.append(None)
        else:
            speeds.append(distance(prev, curr))

    valid_speeds = [speed for speed in speeds if speed is not None]
    if not valid_speeds:
        raise ValueError("Hip landmarks missing for drive features")

    peak = max(valid_speeds)
    threshold = max(peak * 0.3, 1e-4)
    onset = 0
    for index, speed in enumerate(speeds):
        if speed is not None and speed >= threshold:
            onset = max(index - 1, 0)
            break

    window = hips[onset : onset + 6]
    first = next((point for point in window if point is not None), None)
    last = next((point for point in reversed(window) if point is not None), None)
    if first is None or last is None:
        raise ValueError("Could not measure first-step hip displacement")

    raw = distance(first, last)
    first_step_burst = raw / standing

    headings: list[float] = []
    heading_frames: list[int] = []
    for index in range(1, len(hips)):
        prev = hips[index - 1]
        curr = hips[index]
        if prev is None or curr is None:
            continue
        delta = curr - prev
        if float(np.linalg.norm(delta)) < 1e-5:
            continue
        headings.append(math.degrees(math.atan2(float(delta[1]), float(delta[0]))))
        heading_frames.append(index)

    cod_angle = 0.0
    applicable = False
    if len(headings) >= 2:
        turns = []
        for a, b in zip(headings, headings[1:]):
            diff = abs(b - a) % 360.0
            turns.append(diff if diff <= 180 else 360.0 - diff)
        if turns:
            cod_angle = float(max(turns))
            applicable = cod_angle >= 25.0
            if not applicable:
                cod_angle = 0.0

    meta = {
        "onset_frame_index": frames[onset][0],
        "standing_height_proxy": standing,
        "height_in": height_in,
        "cod_applicable": applicable,
        "units": {
            "first_step_burst": "hip displacement over ~5 pose frames / standing-height proxy (body-lengths)",
            "change_of_direction_angle": "max heading change in degrees; 0 if turn < 25°",
        },
    }

    return [
        {"feature_name": "first_step_burst", "value": float(first_step_burst), "meta": meta},
        {
            "feature_name": "change_of_direction_angle",
            "value": float(cod_angle),
            "meta": meta,
        },
    ]
