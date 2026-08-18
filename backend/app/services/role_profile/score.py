"""Masked weighted percentile distance (§5.6.2). Never zero-fills missing dims."""

from __future__ import annotations

import math
from typing import Any, Iterable

from app.models.role_profile import validate_role_vector_payload
from app.services.role_profile.constants import (
    HEIGHT_TIEBREAK_WEIGHT,
    ROLE_DIM_WEIGHTS,
    ROLE_VECTOR_KEYS,
    Z_CLIP,
)
from app.services.role_profile.nba_transform import nba_reliability_weights, nba_role_vector
from app.services.role_profile.validate import build_role_vector

# Acklam inverse-normal coefficients
_A = (
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577509590705e02,
    -3.066479806614716e01,
    2.506628277459239e00,
)
_B = (
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
)
_C = (
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
)
_D = (
    7.784695709041462e-03,
    3.224671290700398e-01,
    2.445134137142996e00,
    3.754408661907416e00,
)


def percentile_to_z(p: float, clip: float = Z_CLIP) -> float:
    """Percentile → clipped standard-normal score."""
    p = min(1.0 - 1e-6, max(1e-6, float(p)))
    z = _norm_ppf(p)
    return max(-clip, min(clip, z))


def _norm_ppf(p: float) -> float:
    if p <= 0.0:
        return float("-inf")
    if p >= 1.0:
        return float("inf")
    plow = 0.02425
    phigh = 1.0 - plow
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
        )
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
        )
    q = p - 0.5
    r = q * q
    return (
        (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5])
        * q
        / (((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0)
    )


def shared_dimensions(
    user: dict[str, float],
    nba: dict[str, float],
) -> list[str]:
    return [k for k in ROLE_VECTOR_KEYS if k in user and k in nba]


def masked_distance(
    user: dict[str, float],
    nba: dict[str, float],
    *,
    user_q: dict[str, float] | None = None,
    nba_q: dict[str, float] | None = None,
    weights: dict[str, float] | None = None,
) -> float | None:
    """sqrt(sum w q_u q_p (z_u-z_p)^2 / sum w q_u q_p) over shared dims only."""
    validate_role_vector_payload(user)
    validate_role_vector_payload(nba)
    dims = shared_dimensions(user, nba)
    if not dims:
        return None
    wmap = weights or ROLE_DIM_WEIGHTS
    uq = user_q or {}
    nq = nba_q or {}
    num = 0.0
    den = 0.0
    for dim in dims:
        w = float(wmap.get(dim, 1.0))
        qu = max(0.0, float(uq.get(dim, 1.0)))
        qp = max(0.0, float(nq.get(dim, 1.0)))
        weight = w * qu * qp
        if weight <= 0:
            continue
        zu = percentile_to_z(user[dim])
        zp = percentile_to_z(nba[dim])
        num += weight * (zu - zp) ** 2
        den += weight
    if den <= 0:
        return None
    return math.sqrt(num / den)


def dimension_contributions(
    user: dict[str, float],
    nba: dict[str, float],
    *,
    user_q: dict[str, float] | None = None,
    nba_q: dict[str, float] | None = None,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    dims = shared_dimensions(user, nba)
    wmap = weights or ROLE_DIM_WEIGHTS
    uq = user_q or {}
    nq = nba_q or {}
    parts: dict[str, Any] = {}
    for dim in dims:
        w = float(wmap.get(dim, 1.0))
        qu = max(0.0, float(uq.get(dim, 1.0)))
        qp = max(0.0, float(nq.get(dim, 1.0)))
        zu = percentile_to_z(user[dim])
        zp = percentile_to_z(nba[dim])
        parts[dim] = {
            "user": round(user[dim], 4),
            "nba": round(nba[dim], 4),
            "user_z": round(zu, 4),
            "nba_z": round(zp, 4),
            "gap": round(abs(user[dim] - nba[dim]), 4),
            "weight": w,
            "user_q": round(qu, 4),
            "nba_q": round(qp, 4),
            "weighted_sq_z": round(w * qu * qp * (zu - zp) ** 2, 6),
        }
    omitted = [k for k in ROLE_VECTOR_KEYS if k not in dims]
    return {"shared": parts, "omitted": omitted}


def height_tiebreak(
    user_height_in: float,
    nba_height_in: float | None,
    *,
    band_in: float,
    weight: float = HEIGHT_TIEBREAK_WEIGHT,
) -> float:
    if nba_height_in is None or band_in <= 0:
        return 0.0
    frac = min(1.0, abs(float(user_height_in) - float(nba_height_in)) / float(band_in))
    return weight * frac


def resemblance_from_distance(distance: float) -> tuple[float, str]:
    score = 1.0 / (1.0 + float(distance))
    if distance < 0.75:
        band = "High"
    elif distance < 1.5:
        band = "Medium"
    else:
        band = "Low"
    return score, band


def user_quality_weights(profile: Any) -> dict[str, float]:
    """Map role-profile dimension confidence onto q_u,j."""
    mapping = {
        "catch_readiness": "catch_readiness",
        "rim_pressure_tendency": "rim_pressure",
        "playmaking_orientation": "playmaking",
    }
    out: dict[str, float] = {}
    for vec_key, attr in mapping.items():
        state = getattr(profile, attr, None)
        conf = getattr(state, "confidence", None) if state is not None else None
        if isinstance(conf, (int, float)):
            out[vec_key] = max(0.05, min(1.0, float(conf)))
        else:
            out[vec_key] = 0.5
    return out


def rank_role_matches(
    players: Iterable[dict[str, Any]],
    *,
    user_vector: dict[str, float],
    user_q: dict[str, float] | None = None,
    user_height_in: float,
    height_band_in: float,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    validate_role_vector_payload(user_vector)
    ranked: list[dict[str, Any]] = []
    for player in players:
        nba_vec = nba_role_vector(player)
        dist = masked_distance(
            user_vector,
            nba_vec,
            user_q=user_q,
            nba_q=nba_reliability_weights(player),
        )
        if dist is None:
            continue
        try:
            nba_h = float(player["height_in"])
        except (KeyError, TypeError, ValueError):
            nba_h = None
        tie = height_tiebreak(user_height_in, nba_h, band_in=height_band_in)
        ranking_distance = dist + tie
        score, band = resemblance_from_distance(dist)
        contrib = dimension_contributions(
            user_vector,
            nba_vec,
            user_q=user_q,
            nba_q=nba_reliability_weights(player),
        )
        ranked.append(
            {
                "player_id": player.get("player_id"),
                "name": player.get("name"),
                "season": player.get("season"),
                "position": player.get("position") or player.get("position_group"),
                "height_in": nba_h,
                "score": round(score, 4),
                "distance": round(dist, 4),
                "ranking_distance": round(ranking_distance, 4),
                "height_tiebreak": round(tie, 4),
                "resemblance_band": band,
                "role_vector": nba_vec,
                "style_vector": nba_vec,
                "kind": "role_profile",
                "dimension_contributions": contrib,
            }
        )
    ranked.sort(key=lambda row: (row["ranking_distance"], row["name"] or ""))
    return ranked[:top_k]
