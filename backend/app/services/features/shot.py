from __future__ import annotations

from app.services.features.geometry import (
    LandmarkLookup,
    angle_at,
    side_names,
    standing_height_proxy,
    vector_elevation_deg,
)
from app.services.features.heuristics import find_shot_release_index, mean_standing_height


def extract_shot_features(
    frames: list[tuple[int, LandmarkLookup]],
    *,
    dominant_hand: str = "right",
    height_in: float | None = None,
) -> list[dict]:
    if not frames:
        raise ValueError("No pose frames for shot features")

    names = side_names(dominant_hand)
    release_idx = find_shot_release_index(frames, dominant_hand)
    if release_idx is None:
        raise ValueError("Could not find a shot release frame")

    frame_index, lookup = frames[release_idx]
    shoulder = lookup.xy(names["shoulder"])
    elbow = lookup.xy(names["elbow"])
    wrist = lookup.xy(names["wrist"])
    if shoulder is None or elbow is None or wrist is None:
        raise ValueError("Shooting arm landmarks missing at release")

    forearm = wrist - elbow
    release_angle = vector_elevation_deg(forearm)
    elbow_angle = angle_at(elbow, shoulder, wrist)

    standing = standing_height_proxy(lookup) or mean_standing_height(frames)
    left_ankle = lookup.xy("left_ankle")
    right_ankle = lookup.xy("right_ankle")
    if left_ankle is not None and right_ankle is not None:
        ankle_y = float((left_ankle[1] + right_ankle[1]) / 2.0)
    elif left_ankle is not None:
        ankle_y = float(left_ankle[1])
    elif right_ankle is not None:
        ankle_y = float(right_ankle[1])
    else:
        ankle_y = 0.0

    if standing is None or standing < 1e-6:
        release_height_ratio = 0.0
    else:
        release_height_ratio = (float(wrist[1]) - ankle_y) / standing

    wrist_after = []
    for _, later in frames[release_idx:]:
        later_wrist = later.xy(names["wrist"])
        if later_wrist is not None:
            wrist_after.append(float(later_wrist[1]))
    peak_after = max(wrist_after) if wrist_after else float(wrist[1])
    shot_arc = (peak_after - float(wrist[1])) / standing if standing else 0.0

    meta = {
        "release_frame_index": frame_index,
        "dominant_hand": names["wrist"].split("_")[0],
        "units": {
            "release_angle": "degrees from horizontal (90 = straight up)",
            "elbow_angle_at_release": "degrees (180 = fully extended)",
            "release_height_ratio": "wrist height above ankles / standing-height proxy",
            "shot_arc": "extra wrist rise after release / standing-height proxy",
        },
    }
    if height_in is not None and standing:
        approx = float(height_in) * release_height_ratio
        meta["approx_release_height_in"] = approx
        meta["height_in"] = float(height_in)

    return [
        {"feature_name": "release_angle", "value": float(release_angle), "meta": meta},
        {"feature_name": "elbow_angle_at_release", "value": float(elbow_angle), "meta": meta},
        {
            "feature_name": "release_height_ratio",
            "value": float(release_height_ratio),
            "meta": meta,
        },
        {"feature_name": "shot_arc", "value": float(max(shot_arc, 0.0)), "meta": meta},
    ]
