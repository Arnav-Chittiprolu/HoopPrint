from __future__ import annotations

from app.models.clip import ClipType
from app.services.features.drive import extract_drive_features
from app.services.features.geometry import parse_frames
from app.services.features.passing import extract_pass_features
from app.services.features.shot import extract_shot_features


def extract_clip_features(
    frames: list,
    clip_type: str,
    *,
    dominant_hand: str = "right",
    height_in: float | None = None,
) -> list[dict]:
    parsed = parse_frames(frames)
    if not parsed:
        raise ValueError("No keypoints to extract features from")

    kind = clip_type if isinstance(clip_type, str) else str(clip_type)
    if kind == ClipType.shot.value:
        return extract_shot_features(
            parsed, dominant_hand=dominant_hand, height_in=height_in
        )
    if kind == ClipType.pass_clip.value:
        return extract_pass_features(parsed, dominant_hand=dominant_hand)
    if kind == ClipType.drive.value:
        return extract_drive_features(parsed, height_in=height_in)
    raise ValueError(f"Unknown clip_type '{kind}'")
