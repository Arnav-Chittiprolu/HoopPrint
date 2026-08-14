from __future__ import annotations

import numpy as np

from app.services.features.geometry import LandmarkLookup, angle_at, side_names
from app.services.features.heuristics import (
    find_catch_index,
    find_pass_release_index,
    local_maxima_indices,
)


def extract_pass_features(
    frames: list[tuple[int, LandmarkLookup]],
    *,
    dominant_hand: str = "right",
) -> list[dict]:
    if not frames:
        raise ValueError("No pose frames for pass features")

    names = side_names(dominant_hand)
    release_idx = find_pass_release_index(frames, dominant_hand)
    if release_idx is None:
        raise ValueError("Could not find a pass release frame")

    frame_index, lookup = frames[release_idx]
    shoulder = lookup.xy(names["shoulder"])
    elbow = lookup.xy(names["elbow"])
    wrist = lookup.xy(names["wrist"])
    if shoulder is None or elbow is None or wrist is None:
        raise ValueError("Passing arm landmarks missing at release")

    arm_extension = angle_at(elbow, shoulder, wrist)

    elbow_series: list[float | None] = []
    wrist_points: list[np.ndarray | None] = []
    for _, item in frames:
        s = item.xy(names["shoulder"])
        e = item.xy(names["elbow"])
        w = item.xy(names["wrist"])
        wrist_points.append(w)
        if s is None or e is None or w is None:
            elbow_series.append(None)
        else:
            try:
                elbow_series.append(angle_at(e, s, w))
            except ValueError:
                elbow_series.append(None)

    peaks = local_maxima_indices(elbow_series, min_prominence=8.0)
    peak_wrists = [wrist_points[i] for i in peaks if wrist_points[i] is not None]
    if len(peak_wrists) >= 2:
        stacked = np.stack(peak_wrists)
        consistency = float(np.mean(np.std(stacked, axis=0)))
    else:
        consistency = 0.0

    catch_idx = find_catch_index(frames, before_index=release_idx)
    if catch_idx is None:
        decision_frames = float(frames[release_idx][0] - frames[0][0])
        catch_frame = frames[0][0]
    else:
        decision_frames = float(frames[release_idx][0] - frames[catch_idx][0])
        catch_frame = frames[catch_idx][0]

    meta = {
        "release_frame_index": frame_index,
        "catch_frame_index": catch_frame,
        "pass_peak_count": len(peaks),
        "dominant_hand": names["wrist"].split("_")[0],
        "units": {
            "arm_extension_at_release": "elbow degrees at release (180 = straight)",
            "release_point_consistency": "mean stddev of wrist xy at pass peaks (0 = one pass / identical)",
            "decision_speed": "pose-frame index delta from catch proxy to release",
        },
    }

    return [
        {
            "feature_name": "arm_extension_at_release",
            "value": float(arm_extension),
            "meta": meta,
        },
        {
            "feature_name": "release_point_consistency",
            "value": float(consistency),
            "meta": meta,
        },
        {
            "feature_name": "decision_speed",
            "value": float(max(decision_frames, 0.0)),
            "meta": meta,
        },
    ]
