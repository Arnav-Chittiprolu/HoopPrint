"""Aggregate per-clip pose features into a user profile vector.

Averages each feature_name across all successful (done) clips for the user.
Gameplay and individual clips are pooled together once both have features.
"""

from __future__ import annotations

from collections import defaultdict


def average_features_by_name(
    feature_rows: list[dict],
) -> list[dict]:
    """Group clip_features rows by feature_name and compute mean + clip_count.

    Each input row needs at least: feature_name, value, and preferably clip_id
    so clip_count reflects distinct clips contributing to that feature.
    """
    values: dict[str, list[float]] = defaultdict(list)
    clips: dict[str, set[str]] = defaultdict(set)

    for row in feature_rows:
        name = row.get("feature_name")
        if not isinstance(name, str) or not name:
            continue
        try:
            value = float(row["value"])
        except (KeyError, TypeError, ValueError):
            continue
        values[name].append(value)
        clip_id = row.get("clip_id")
        if clip_id is not None:
            clips[name].add(str(clip_id))

    aggregated: list[dict] = []
    for name, nums in sorted(values.items()):
        if not nums:
            continue
        clip_count = len(clips[name]) if clips[name] else len(nums)
        aggregated.append(
            {
                "feature_name": name,
                "value": float(sum(nums) / len(nums)),
                "clip_count": clip_count,
            }
        )
    return aggregated


def compute_height_z(height_in: float | None) -> float | None:
    """Z-score vs average adult male height (~69 in, SD ~3 in)."""
    if height_in is None:
        return None
    return (float(height_in) - 69.0) / 3.0
