"""Deterministic why object for role-profile matches (Gemini narrates only)."""

from __future__ import annotations

import json
from typing import Any

from app.services.role_profile.constants import ROLE_VECTOR_KEYS
from app.services.role_profile.pool import PoolSelection
from app.services.role_profile.score import dimension_contributions


def build_role_why(
    *,
    match: dict[str, Any],
    user_vector: dict[str, float],
    user_height_in: float,
    pool: PoolSelection,
    evidence_tier: str,
    user_scale: str = "latent_0_1",
) -> dict[str, Any]:
    nba_vec = match.get("role_vector") or match.get("style_vector") or {}
    contrib = match.get("dimension_contributions") or dimension_contributions(user_vector, nba_vec)
    shared = contrib.get("shared") or {}
    slots = []
    for dim, row in shared.items():
        slots.append(
            {
                "dim": dim,
                "user": row.get("user"),
                "nba": row.get("nba"),
                "gap": row.get("gap"),
                "user_z": row.get("user_z"),
                "nba_z": row.get("nba_z"),
            }
        )
    slots.sort(key=lambda row: float(row.get("gap") or 0))
    omitted = contrib.get("omitted") or [k for k in ROLE_VECTOR_KEYS if k not in shared]

    return {
        "label": "role_profile",
        "filter": {
            "position_groups": pool.position_groups,
            "user_height_in": user_height_in,
            "nba_height_in": match.get("height_in"),
            "band_in": pool.height_band_in,
            "stage": pool.stage,
            "height_delta_in": (
                None
                if match.get("height_in") is None
                else round(abs(float(user_height_in) - float(match["height_in"])), 2)
            ),
        },
        "score_terms": {
            "distance": match.get("distance"),
            "height_tiebreak": match.get("height_tiebreak"),
            "ranking_distance": match.get("ranking_distance"),
            "resemblance_band": match.get("resemblance_band"),
            "total": match.get("score"),
            "user_scale": user_scale,
            "nba_scale": "cohort_percentile",
        },
        "slots": slots,
        "omitted_slots": omitted,
        "evidence_tier": evidence_tier,
        "pool_sentence": pool.pool_sentence,
        "note": (
            "Public-stat role resemblance within the comparison pool. "
            "Not shared mechanics, skill, or predicted performance."
        ),
    }


def build_role_llm_prompt(
    *,
    questionnaire: dict[str, Any],
    mechanics: dict[str, float],
    user_role_vector: dict[str, float],
    archetype: dict[str, Any] | None,
    top_match: dict | None,
    why: dict | None,
    mechanics_recs: list[dict],
    role_recs: list[dict],
    evidence_tier: str,
    named_matches_suppressed: bool,
) -> str:
    return (
        "You explain a basketball ROLE-PROFILE result that was already computed. "
        "Do not pick a different NBA player. Do not invent statistics. "
        "Do not say pose mechanics equal box-score percentages. "
        "Do not claim the user shoots, passes, or drives like the NBA player mechanically. "
        "Do not claim outcome prediction or NBA skill.\n\n"
        f"EVIDENCE_TIER: {evidence_tier}\n"
        f"NAMED_MATCHES_SUPPRESSED: {named_matches_suppressed}\n\n"
        f"QUESTIONNAIRE:\n{json.dumps(questionnaire, indent=2)}\n\n"
        f"USER_ROLE_VECTOR (latent / building-baseline — not NBA percentiles):\n"
        f"{json.dumps(user_role_vector, indent=2)}\n\n"
        f"ARCHETYPE:\n{json.dumps(archetype or {}, indent=2)}\n\n"
        f"MECHANICS (pose only — do not use for the NBA comparison):\n"
        f"{json.dumps(mechanics, indent=2)}\n\n"
        f"TOP_MATCH:\n{json.dumps(top_match or {}, indent=2, default=str)}\n\n"
        f"WHY:\n{json.dumps(why or {}, indent=2, default=str)}\n\n"
        f"MECHANICS_RECS:\n{json.dumps(mechanics_recs, indent=2)}\n\n"
        f"ROLE_RECS:\n{json.dumps(role_recs, indent=2)}\n\n"
        "Write exactly two sections:\n"
        "## Role resemblance\n"
        "1–2 short paragraphs. If named matches are suppressed, explain the archetype only. "
        "State that this is a public-stat role resemblance, not identical motion.\n\n"
        "## Next steps\n"
        "2–3 bullets. Mechanics bullets may only use MECHANICS_RECS (no NBA player names). "
        "Role bullets may only use ROLE_RECS. Do not add drills that are not in those lists.\n"
    )
