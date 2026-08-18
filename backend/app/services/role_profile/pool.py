"""NBA comparison pool: role-first, body-plausibility eligibility only.

Height/position never decide how someone plays. They only drop bodies that
cannot be a named comparison (>9") and supply physical-context copy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.aggregate import NBA_POSITION_HEIGHT_IN
from app.services.role_profile.constants import (
    ALL_POSITION_GROUPS,
    BODY_EXCLUDE_IN,
    BODY_PRIMARY_MAX_IN,
    MIN_NAMED_MATCH_POOL,
    NBA_POSITION_FIT_IN,
)
from app.services.role_profile.nba_transform import nba_role_vector

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
    pool_confidence: str = "full"
    typical_groups: list[str] = field(default_factory=list)


def compatible_position_groups(height_in: float, listed: str | None = None) -> list[str]:
    """NBA role groups whose typical height is close to the user — context only."""
    scored: list[tuple[float, str]] = []
    for group in ALL_POSITION_GROUPS:
        mean = NBA_POSITION_HEIGHT_IN.get(group)
        if mean is None:
            continue
        scored.append((abs(float(height_in) - float(mean)), group))
    scored.sort()
    fits = [group for gap, group in scored if gap <= NBA_POSITION_FIT_IN]
    if not fits:
        fits = [scored[0][1]] if scored else list(ALL_POSITION_GROUPS)
    listed_norm = (listed or "").strip().lower()
    if listed_norm in fits:
        return [listed_norm, *[g for g in fits if g != listed_norm]]
    return fits


def _group(player: dict[str, Any]) -> str:
    return str(player.get("position_group") or player.get("position") or "")


def _format_height(height_in: float) -> str:
    inches = int(round(float(height_in)))
    feet, rem = divmod(inches, 12)
    return f"{feet} ft {rem} in"


def _who(groups: list[str]) -> str:
    labels = [POSITION_LABELS.get(g, g) for g in groups]
    if not labels:
        return "NBA players"
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def physical_context_sentence(
    *,
    height_in: float,
    listed: str,
    typical_groups: list[str],
    season: str | None,
    limited: bool,
) -> str:
    season_bit = (
        f" using {season} public NBA role statistics"
        if season
        else " using public NBA role statistics"
    )
    text = (
        f"Height does not determine how you play. Named comparisons start from clip "
        f"role resemblance, then keep physically realistic NBA bodies: within about "
        f"{BODY_PRIMARY_MAX_IN:g} inches of your listed {_format_height(height_in)} as "
        f"primary comps. Larger gaps (up to {BODY_EXCLUDE_IN:g} inches) appear only as "
        f"style-only references, not 'you are this player.' Players more than "
        f"{BODY_EXCLUDE_IN:g} inches taller or shorter are omitted from named lists"
        f"{season_bit}."
    )
    listed_n = (listed or "").strip().lower()
    if listed_n and listed_n not in typical_groups:
        text += (
            f" At your size, NBA players are mostly {_who(typical_groups)}, so a listed "
            f"{listed_n} is a weak preference, not a lock."
        )
    if limited:
        text += " The body-plausible set is small, so treat named examples as lower-confidence."
    return text


def select_nba_pool(
    players: list[dict[str, Any]],
    *,
    position: str,
    height_in: float,
    season: str | None = None,
    min_pool: int = MIN_NAMED_MATCH_POOL,
) -> PoolSelection:
    """Include anyone within 9\" who has a role vector. Do not lock listed position."""
    pos = position.strip().lower()
    typical = compatible_position_groups(height_in, pos)
    eligible: list[dict[str, Any]] = []
    groups: set[str] = set()
    for player in players:
        try:
            player_h = float(player["height_in"])
        except (KeyError, TypeError, ValueError):
            continue
        if abs(player_h - float(height_in)) > BODY_EXCLUDE_IN:
            continue
        if player.get("meets_min_sample") is False:
            continue
        if not nba_role_vector(player):
            continue
        eligible.append(player)
        g = _group(player)
        if g:
            groups.add(g)

    limited = len(eligible) < min_pool
    sentence = physical_context_sentence(
        height_in=height_in,
        listed=pos,
        typical_groups=typical,
        season=season,
        limited=limited and len(eligible) > 0,
    )
    if not eligible:
        sentence += " Named player examples are withheld because no NBA bodies are within 9 inches."

    return PoolSelection(
        players=eligible,
        stage=1,
        position_groups=sorted(groups) if groups else list(typical),
        height_band_in=BODY_EXCLUDE_IN,
        pool_sentence=sentence,
        named_matches_allowed=bool(eligible),
        disclosure=(
            "Small body-plausible set; named examples have lower confidence."
            if limited and eligible
            else ("No NBA players within 9 inches of listed height." if not eligible else None)
        ),
        cohort_definition={
            "position_groups": sorted(groups),
            "height_band_in": BODY_EXCLUDE_IN,
            "primary_band_in": BODY_PRIMARY_MAX_IN,
            "stage": 1,
            "season": season,
            "min_pool": min_pool,
            "listed_position": pos,
            "typical_groups": typical,
            "mode": "role_first_body_plausibility",
        },
        pool_confidence="limited" if limited else "full",
        typical_groups=typical,
    )
