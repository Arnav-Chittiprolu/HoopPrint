"""Staged NBA comparison pool (§5.8). Height/position are eligibility only."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.role_profile.constants import (
    MIN_NAMED_MATCH_POOL,
    POOL_HEIGHT_BAND_STAGE1,
    POOL_HEIGHT_BAND_STAGE2,
    POOL_HEIGHT_BAND_STAGE3,
)
from app.services.role_profile.nba_transform import nba_role_vector

ADJACENT_GROUPS: dict[str, tuple[str, ...]] = {
    "guard": ("wing",),
    "wing": ("guard", "forward"),
    "forward": ("wing", "center"),
    "center": ("forward",),
}

POSITION_LABELS = {
    "guard": "guards",
    "wing": "wings",
    "forward": "forwards",
    "center": "centers",
}


@dataclass
class PoolSelection:
    players: list[dict[str, Any]]
    stage: int
    position_groups: list[str]
    height_band_in: float
    pool_sentence: str
    named_matches_allowed: bool
    disclosure: str | None = None
    cohort_definition: dict[str, Any] = field(default_factory=dict)


def _group(player: dict[str, Any]) -> str:
    return str(player.get("position_group") or player.get("position") or "")


def _eligible(
    players: list[dict[str, Any]],
    *,
    groups: set[str],
    height_in: float,
    band: float,
    require_role_vector: bool = True,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for player in players:
        if _group(player) not in groups:
            continue
        try:
            player_h = float(player["height_in"])
        except (KeyError, TypeError, ValueError):
            continue
        if abs(player_h - height_in) > band:
            continue
        if player.get("meets_min_sample") is False:
            continue
        if require_role_vector and not nba_role_vector(player):
            continue
        out.append(player)
    return out


def _sentence(
    *,
    groups: list[str],
    band: float,
    season: str | None,
    stage: int,
) -> str:
    labels = [POSITION_LABELS.get(g, g) for g in groups]
    if len(labels) == 1:
        who = labels[0]
    elif len(labels) == 2:
        who = f"{labels[0]} and {labels[1]}"
    else:
        who = ", ".join(labels[:-1]) + f", and {labels[-1]}"
    season_bit = f", using {season} public NBA role statistics" if season else ", using public NBA role statistics"
    return (
        f"Comparison pool: {who} within {band:g} inches of your reported height{season_bit}."
        + (" Adjacent position groups included because the same-position pool was too small." if stage >= 3 else "")
    )


def select_nba_pool(
    players: list[dict[str, Any]],
    *,
    position: str,
    height_in: float,
    season: str | None = None,
    min_pool: int = MIN_NAMED_MATCH_POOL,
) -> PoolSelection:
    """Widen height, then adjacent groups. Stage 4 = archetype only."""
    pos = position.strip().lower()
    stages: list[tuple[int, set[str], float, str | None]] = [
        (1, {pos}, POOL_HEIGHT_BAND_STAGE1, None),
        (2, {pos}, POOL_HEIGHT_BAND_STAGE2, None),
        (
            3,
            {pos, *ADJACENT_GROUPS.get(pos, ())},
            POOL_HEIGHT_BAND_STAGE3,
            "Pool widened to an adjacent position group because too few players matched.",
        ),
    ]

    last_players: list[dict[str, Any]] = []
    last_stage = 4
    last_groups: list[str] = [pos]
    last_band = POOL_HEIGHT_BAND_STAGE3
    last_disclosure: str | None = None

    for stage, groups, band, disclosure in stages:
        found = _eligible(players, groups=groups, height_in=height_in, band=band)
        last_players = found
        last_stage = stage
        last_groups = sorted(groups)
        last_band = band
        last_disclosure = disclosure if stage == 3 else None
        if len(found) >= min_pool:
            sentence = _sentence(groups=last_groups, band=band, season=season, stage=stage)
            return PoolSelection(
                players=found,
                stage=stage,
                position_groups=last_groups,
                height_band_in=band,
                pool_sentence=sentence,
                named_matches_allowed=True,
                disclosure=last_disclosure,
                cohort_definition={
                    "position_groups": last_groups,
                    "height_band_in": band,
                    "stage": stage,
                    "season": season,
                    "min_pool": min_pool,
                },
            )

    sentence = _sentence(groups=last_groups, band=last_band, season=season, stage=last_stage)
    if len(last_players) < min_pool:
        return PoolSelection(
            players=last_players,
            stage=4,
            position_groups=last_groups,
            height_band_in=last_band,
            pool_sentence=sentence + " Named player examples are withheld because the comparison pool is below the minimum size.",
            named_matches_allowed=False,
            disclosure="Comparison pool below minimum; archetype only.",
            cohort_definition={
                "position_groups": last_groups,
                "height_band_in": last_band,
                "stage": 4,
                "season": season,
                "min_pool": min_pool,
            },
        )

    return PoolSelection(
        players=last_players,
        stage=last_stage,
        position_groups=last_groups,
        height_band_in=last_band,
        pool_sentence=sentence,
        named_matches_allowed=True,
        disclosure=last_disclosure,
        cohort_definition={
            "position_groups": last_groups,
            "height_band_in": last_band,
            "stage": last_stage,
            "season": season,
            "min_pool": min_pool,
        },
    )
