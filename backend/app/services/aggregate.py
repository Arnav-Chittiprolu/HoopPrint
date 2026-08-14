"""Aggregate per-clip pose features into a user profile vector.

Averages each feature_name across all successful (done) clips for the user.
Gameplay and individual clips are pooled together once both have features.
"""

from __future__ import annotations

from collections import defaultdict

# US adult male reference (questionnaire height_z on profiles)
US_MALE_HEIGHT_IN = 69.0
US_MALE_HEIGHT_SD = 3.0

# NBA population reference (style size + comp bands — NOT the same as US male)
NBA_LEAGUE_HEIGHT_IN = 78.0  # ~6'6"
NBA_LEAGUE_HEIGHT_SD = 3.5

# Position means for short/tall *within* that NBA role
NBA_POSITION_HEIGHT_IN: dict[str, float] = {
    "guard": 75.0,  # ~6'3"
    "wing": 78.0,  # ~6'6"
    "forward": 80.5,  # ~6'8.5"
    "center": 83.0,  # ~6'11"
}
NBA_POSITION_HEIGHT_SD = 2.75


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
    """Z-score vs average US adult male (~69 in, SD ~3). Stored on profiles."""
    if height_in is None:
        return None
    return (float(height_in) - US_MALE_HEIGHT_IN) / US_MALE_HEIGHT_SD


def compute_height_z_nba(
    height_in: float | None,
    position: str | None = None,
) -> float | None:
    """Z-score vs NBA heights — used for style `size` and comp height bands.

    With a questionnaire position, compare to that position's NBA mean.
    Otherwise compare to league-wide NBA mean (~78 in). This is intentionally
    different from `compute_height_z` (US male ~69 in).
    """
    if height_in is None:
        return None
    if position and position in NBA_POSITION_HEIGHT_IN:
        mean = NBA_POSITION_HEIGHT_IN[position]
        sd = NBA_POSITION_HEIGHT_SD
    else:
        mean = NBA_LEAGUE_HEIGHT_IN
        sd = NBA_LEAGUE_HEIGHT_SD
    return (float(height_in) - mean) / sd
