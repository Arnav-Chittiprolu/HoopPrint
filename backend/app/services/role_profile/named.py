"""Named-match eligibility (§5.6.2, §5.7). Pure — no DB I/O."""

from __future__ import annotations

import random
from typing import Any

from app.models.role_profile import EvidenceTier
from app.services.role_profile.aggregate import aggregate_role_profile
from app.services.role_profile.constants import BOOTSTRAP_RANK_ITERATIONS, TOP3_OVERLAP_MIN
from app.services.role_profile.score import build_role_vector, rank_role_matches


def decide_named_matches(
    *,
    evidence_tier: EvidenceTier | str,
    active_dimension_count: int,
    overall_stable: bool,
    top3_overlap_rate: float | None,
    pool_named_allowed: bool,
    vector_dim_count: int,
) -> tuple[bool, str | None]:
    """Return (show_names, suppression_reason)."""
    tier = evidence_tier.value if isinstance(evidence_tier, EvidenceTier) else str(evidence_tier)
    if tier not in {EvidenceTier.established.value, EvidenceTier.strong.value}:
        return False, "evidence_tier"
    if active_dimension_count < 2 or vector_dim_count < 2:
        return False, "active_dimensions"
    if not overall_stable:
        return False, "stability"
    if top3_overlap_rate is not None and top3_overlap_rate < TOP3_OVERLAP_MIN:
        return False, "top3_overlap"
    if not pool_named_allowed:
        return False, "pool_size"
    return True, None


def visible_named_matches(ranked: list[dict[str, Any]], *, allowed: bool, top_k: int = 3) -> list[dict[str, Any]]:
    if not allowed:
        return []
    return ranked[:top_k]


def bootstrap_top3_overlap(
    events: list[dict],
    *,
    user_id: str,
    players: list[dict],
    user_height_in: float,
    height_band_in: float,
    base_names: list[str],
    user_q: dict[str, float] | None = None,
    n_iter: int = BOOTSTRAP_RANK_ITERATIONS,
) -> float | None:
    if len(events) < 5 or not base_names:
        return None
    rng = random.Random(17)
    hits = 0.0
    n = len(events)
    scored = 0
    for _ in range(n_iter):
        sample = [events[rng.randrange(n)] for _ in range(n)]
        profile = aggregate_role_profile(sample, user_id=user_id, rng=rng, n_iter=1)
        vector = build_role_vector(profile.role_vector.model_dump())
        if len(vector) < 2:
            continue
        ranked = rank_role_matches(
            players,
            user_vector=vector,
            user_q=user_q,
            user_height_in=user_height_in,
            height_band_in=height_band_in,
            top_k=3,
        )
        names = {row["name"] for row in ranked if row.get("name")}
        hits += len(names & set(base_names)) / max(len(base_names), 1)
        scored += 1
    if scored == 0:
        return None
    return hits / scored
