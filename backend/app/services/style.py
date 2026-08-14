"""Style-space vectors and NBA similarity (Phase 5).

Do NOT map pose joints onto box-score percentages. Shared slots both sides can fill:

| Slot              | User (form + pose agg)                         | NBA (nba_api cache)                                      |
|-------------------|------------------------------------------------|----------------------------------------------------------|
| size              | height_z_nba (vs NBA/position mean, not US male) | listed height → same NBA z scale                         |
| perimeter_vs_rim  | release_angle + shot_arc (shot clips)          | PCT_FGA_3PT / (1 - paint share)                          |
| creation          | decision_speed (pass clips)                    | unassisted FGM% + pull-up share of pull-up+catch FGA     |
| drive_burst       | first_step_burst + COD (drive clips)           | drives/game + offensive avg speed (league min-max)       |
| passing           | arm_extension + release_point_consistency      | AST_PCT + potential assists / passes                     |

All slot values are stored in ~[0, 1] for cosine. Missing slots are omitted
from both vectors before scoring (category weight → 0 with no clip evidence).
"""

from __future__ import annotations

import math
from typing import Any, Iterable

from app.services.aggregate import compute_height_z, compute_height_z_nba

STYLE_DIMS = (
    "size",
    "perimeter_vs_rim",
    "creation",
    "drive_burst",
    "passing",
)

SHOT_FEATURES = frozenset({"release_angle", "shot_arc", "elbow_angle_at_release", "release_height_ratio"})
PASS_FEATURES = frozenset(
    {"decision_speed", "arm_extension_at_release", "release_point_consistency"}
)
DRIVE_FEATURES = frozenset({"first_step_burst", "change_of_direction_angle"})

CATEGORY_DIMS = {
    "shot": ("perimeter_vs_rim",),
    "pass": ("creation", "passing"),
    "drive": ("drive_burst",),
}


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def size_from_height_in(
    height_in: float | None,
    position: str | None = None,
) -> float | None:
    """Map height onto shared [0, 1] via NBA height_z (not US male).

    A 5'11" user is tall vs US men (height_z_us > 0) but short vs NBA guards
    (height_z_nba < 0). Comps use the NBA scale so size matches the pool.
    """
    hz = compute_height_z_nba(height_in, position)
    if hz is None:
        return None
    return clamp01((hz + 4.0) / 8.0)


def _agg_map(rows: Iterable[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in rows:
        name = row.get("feature_name")
        if not isinstance(name, str):
            continue
        try:
            out[name] = float(row["value"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def evidence_from_agg(agg: Iterable[dict]) -> dict[str, bool]:
    names = set(_agg_map(agg))
    return {
        "shot": bool(names & SHOT_FEATURES),
        "pass": bool(names & PASS_FEATURES),
        "drive": bool(names & DRIVE_FEATURES),
    }


def build_user_style_vector(
    *,
    height_in: float | None,
    aggregated_features: Iterable[dict],
    position: str | None = None,
) -> dict[str, float]:
    """Build user style slots from questionnaire + pose agg. Skip empty categories."""
    feats = _agg_map(aggregated_features)
    evidence = evidence_from_agg(aggregated_features)
    vector: dict[str, float] = {}

    size = size_from_height_in(height_in, position)
    if size is not None:
        vector["size"] = size

    if evidence["shot"]:
        release = feats.get("release_angle")
        arc = feats.get("shot_arc")
        parts: list[float] = []
        if release is not None:
            # ~20–70° → 0–1; higher release elevation ≈ more perimeter/arc profile
            parts.append(clamp01((release - 20.0) / 50.0))
        if arc is not None:
            parts.append(clamp01(arc / 0.5))
        if parts:
            vector["perimeter_vs_rim"] = sum(parts) / len(parts)

    if evidence["pass"]:
        decision = feats.get("decision_speed")
        if decision is not None:
            # Fewer frames catch→release → more creation / quicker decision
            vector["creation"] = clamp01(1.0 / (1.0 + max(decision, 0.0) / 30.0))

        arm = feats.get("arm_extension_at_release")
        consistency = feats.get("release_point_consistency")
        pass_parts: list[float] = []
        if arm is not None:
            pass_parts.append(clamp01((arm - 90.0) / 90.0))
        if consistency is not None:
            # Lower spatial std across release peaks → more consistent passer
            pass_parts.append(clamp01(1.0 / (1.0 + max(consistency, 0.0) * 10.0)))
        if pass_parts:
            vector["passing"] = sum(pass_parts) / len(pass_parts)

    if evidence["drive"]:
        burst = feats.get("first_step_burst")
        cod = feats.get("change_of_direction_angle")
        drive_parts: list[float] = []
        if burst is not None:
            drive_parts.append(clamp01(burst / 1.5))
        if cod is not None:
            drive_parts.append(clamp01(abs(cod) / 90.0))
        if drive_parts:
            vector["drive_burst"] = sum(drive_parts) / len(drive_parts)

    return vector


def map_nba_position(raw: str | None) -> str | None:
    """Map nba_api position strings onto questionnaire guard|wing|forward|center."""
    if not raw:
        return None
    token = raw.strip().upper().replace(" ", "")
    if token in {"G"}:
        return "guard"
    if token in {"G-F", "F-G", "GF", "FG"}:
        return "wing"
    if token in {"F"}:
        return "forward"
    if token in {"F-C", "FC"}:
        return "forward"
    if token in {"C-F", "CF"}:
        return "center"
    if token in {"C"}:
        return "center"
    # Fallbacks for longer labels ("Guard", "Center", …)
    lower = raw.strip().lower()
    if "guard" in lower and "forward" in lower:
        return "wing"
    if "guard" in lower:
        return "guard"
    if "center" in lower and "forward" in lower:
        return "forward"
    if "center" in lower:
        return "center"
    if "forward" in lower or "wing" in lower:
        return "forward"
    return None


def height_band_inches(height_z_nba: float | None) -> float:
    """Wider height filter when user is extreme vs NBA / position mean."""
    if height_z_nba is None:
        return 4.0
    az = abs(float(height_z_nba))
    if az >= 2.0:
        return 6.0
    if az >= 1.0:
        return 5.0
    return 4.0


def filter_nba_pool(
    players: list[dict],
    *,
    position: str,
    height_in: float,
    height_z_nba: float | None = None,
) -> list[dict]:
    band = height_band_inches(
        height_z_nba
        if height_z_nba is not None
        else compute_height_z_nba(height_in, position)
    )
    eligible: list[dict] = []
    for player in players:
        if player.get("position") != position:
            continue
        try:
            nba_h = float(player["height_in"])
        except (KeyError, TypeError, ValueError):
            continue
        if abs(nba_h - float(height_in)) <= band:
            eligible.append(player)
    return eligible


def cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float | None:
    keys = [k for k in STYLE_DIMS if k in a and k in b]
    if not keys:
        return None
    dot = sum(a[k] * b[k] for k in keys)
    na = math.sqrt(sum(a[k] * a[k] for k in keys))
    nb = math.sqrt(sum(b[k] * b[k] for k in keys))
    if na < 1e-12 or nb < 1e-12:
        return None
    return float(dot / (na * nb))


def size_similarity(user_height_in: float, nba_height_in: float, band: float) -> float:
    if band <= 0:
        return 0.0
    return clamp01(1.0 - abs(float(user_height_in) - float(nba_height_in)) / band)


def primary_skill_bonus(primary_skill: str | None, nba_style: dict[str, float]) -> float:
    if not primary_skill:
        return 0.0
    dim = {
        "shot": "perimeter_vs_rim",
        "pass": "passing",
        "drive": "drive_burst",
    }.get(primary_skill)
    if not dim or dim not in nba_style:
        return 0.0
    return clamp01(float(nba_style[dim]))


def score_player(
    user_style: dict[str, float],
    nba_style: dict[str, float],
    *,
    user_height_in: float,
    nba_height_in: float,
    height_z_nba: float | None,
    primary_skill: str | None,
    dims: tuple[str, ...] | None = None,
) -> float | None:
    if dims is not None:
        a = {k: user_style[k] for k in dims if k in user_style}
        b = {k: nba_style[k] for k in dims if k in nba_style}
    else:
        a, b = user_style, nba_style

    style = cosine_similarity(a, b)
    if style is None:
        return None

    band = height_band_inches(height_z_nba)
    size_term = size_similarity(user_height_in, nba_height_in, band)
    skill = primary_skill_bonus(primary_skill, nba_style)
    return float(0.75 * style + 0.20 * size_term + 0.05 * skill)


def _match_payload(player: dict, score: float) -> dict[str, Any]:
    style = player.get("style_vector") or {}
    if not isinstance(style, dict):
        style = {}
    return {
        "player_id": player.get("player_id"),
        "name": player.get("name"),
        "season": player.get("season"),
        "position": player.get("position"),
        "height_in": player.get("height_in"),
        "score": round(float(score), 4),
        "style_vector": {k: style[k] for k in STYLE_DIMS if k in style},
        "kind": "style",
    }


def rank_matches(
    players: list[dict],
    *,
    user_style: dict[str, float],
    user_height_in: float,
    height_z_nba: float | None,
    primary_skill: str | None,
    evidence: dict[str, bool],
    top_k: int = 3,
) -> dict[str, Any]:
    overall_scored: list[tuple[float, dict]] = []
    for player in players:
        style = player.get("style_vector") or {}
        if not isinstance(style, dict):
            continue
        try:
            nba_h = float(player["height_in"])
        except (KeyError, TypeError, ValueError):
            continue
        score = score_player(
            user_style,
            {k: float(v) for k, v in style.items() if isinstance(v, (int, float))},
            user_height_in=user_height_in,
            nba_height_in=nba_h,
            height_z_nba=height_z_nba,
            primary_skill=primary_skill,
        )
        if score is not None:
            overall_scored.append((score, player))

    overall_scored.sort(key=lambda item: item[0], reverse=True)
    overall = [_match_payload(p, s) for s, p in overall_scored[:top_k]]

    by_category: dict[str, list[dict]] = {}
    for category, dims in CATEGORY_DIMS.items():
        if not evidence.get(category):
            continue
        if not any(d in user_style for d in dims):
            continue
        cat_scored: list[tuple[float, dict]] = []
        for player in players:
            style = player.get("style_vector") or {}
            if not isinstance(style, dict):
                continue
            try:
                nba_h = float(player["height_in"])
            except (KeyError, TypeError, ValueError):
                continue
            score = score_player(
                user_style,
                {k: float(v) for k, v in style.items() if isinstance(v, (int, float))},
                user_height_in=user_height_in,
                nba_height_in=nba_h,
                height_z_nba=height_z_nba,
                primary_skill=primary_skill,
                dims=dims,
            )
            if score is not None:
                cat_scored.append((score, player))
        cat_scored.sort(key=lambda item: item[0], reverse=True)
        by_category[category] = [_match_payload(p, s) for s, p in cat_scored[:top_k]]

    return {
        "overall": overall,
        "by_category": by_category,
        "pool_size": len(players),
        "label": "style",
    }
