"""Reject MediaPipe false-positive poses when no person is in frame."""

from __future__ import annotations

CORE_LANDMARKS = (
    "nose",
    "left_shoulder",
    "right_shoulder",
    "left_hip",
    "right_hip",
    "left_ankle",
    "right_ankle",
)

MIN_MEAN_VISIBILITY = 0.5
MIN_CORE_VISIBLE = 5
MIN_CORE_VISIBILITY = 0.5
MIN_TORSO_HEIGHT = 0.12
MIN_POSE_SPAN = 0.18


def is_plausible_person(payload: dict) -> bool:
    """True if landmarks look like a visible standing/moving person.

    MediaPipe often returns a 33-point skeleton on empty frames. Those
    detections usually have low visibility, a tiny bbox, or hips not below
    shoulders.
    """
    points = payload.get("landmarks") or []
    if len(points) < 11:
        return False

    visibilities = [float(p.get("visibility") or 0.0) for p in points]
    mean_vis = sum(visibilities) / len(visibilities)
    if mean_vis < MIN_MEAN_VISIBILITY:
        return False

    by_name = {p.get("name"): p for p in points if p.get("name")}
    visible_core = 0
    xs: list[float] = []
    ys: list[float] = []
    for name in CORE_LANDMARKS:
        point = by_name.get(name)
        if point is None:
            continue
        if float(point.get("visibility") or 0.0) < MIN_CORE_VISIBILITY:
            continue
        visible_core += 1
        xs.append(float(point["x"]))
        ys.append(float(point["y"]))

    if visible_core < MIN_CORE_VISIBLE:
        return False

    span = max(max(xs) - min(xs), max(ys) - min(ys))
    if span < MIN_POSE_SPAN:
        return False

    def mean_y(*names: str) -> float | None:
        vals = []
        for name in names:
            point = by_name.get(name)
            if point is None:
                continue
            if float(point.get("visibility") or 0.0) < MIN_CORE_VISIBILITY:
                continue
            vals.append(float(point["y"]))
        if not vals:
            return None
        return sum(vals) / len(vals)

    # Image y increases downward: shoulders above hips above ankles.
    shoulder_y = mean_y("left_shoulder", "right_shoulder")
    hip_y = mean_y("left_hip", "right_hip")
    ankle_y = mean_y("left_ankle", "right_ankle")
    if shoulder_y is not None and hip_y is not None:
        if hip_y - shoulder_y < MIN_TORSO_HEIGHT:
            return False
    if hip_y is not None and ankle_y is not None:
        if ankle_y <= hip_y:
            return False

    return True
