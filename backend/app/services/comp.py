"""Run role-profile NBA comps from gated events (Phase 10.5).

Legacy cosine matching lives in `run_style_comp` for tests/rollback only and
must not write production `comp_results`.
"""

from __future__ import annotations

import logging
import random
from typing import Any

from app.config import get_settings
from app.models.role_profile import ComparisonMode, EvidenceTier, UserRoleProfileRecord
from app.services.aggregate import compute_height_z, compute_height_z_nba
from app.services.explain import (
    annotate_matches_with_why,
    build_llm_prompt,
    build_recommendations,
)
from app.services.llm import get_llm_provider
from app.services.nba_seed import DEFAULT_SEASON
from app.services.role_profile.aggregate import aggregate_role_profile
from app.services.role_profile.archetype import classify_archetype
from app.services.role_profile.constants import (
    BOOTSTRAP_RANK_ITERATIONS,
    COMPARISON_MODE_ROLE,
    DISCLOSURE_VERSION,
    NBA_TRANSFORM_VERSION,
    ROLE_PROFILE_VERSION,
    ROLE_VECTOR_KEYS,
    TOP3_OVERLAP_MIN,
)
from app.services.role_profile.db import user_role_profile_from_row, user_role_profile_to_row
from app.services.role_profile.nba_transform import finalize_nba_role_rows, nba_role_vector
from app.services.role_profile.pool import select_nba_pool
from app.services.role_profile.recs import build_mechanics_recs, build_role_recs
from app.services.role_profile.score import (
    build_role_vector,
    rank_role_matches,
    user_quality_weights,
)
from app.services.role_profile.why import build_role_llm_prompt, build_role_why
from app.services.style import (
    build_user_style_vector,
    evidence_from_agg,
    filter_nba_pool,
    rank_matches,
)
from app.services.supabase_client import SupabaseService

logger = logging.getLogger(__name__)


class CompError(Exception):
    """Raised when a comp cannot be computed."""


async def _narrate_comp(
    *,
    questionnaire: dict[str, Any],
    mechanics: dict[str, float],
    user_style: dict[str, float],
    top_match: dict | None,
    why: dict | None,
    recommendations: list[dict],
) -> str | None:
    try:
        provider = get_llm_provider(get_settings())
    except Exception:
        return None
    if provider is None:
        return None
    prompt = build_llm_prompt(
        questionnaire=questionnaire,
        mechanics=mechanics,
        user_style=user_style,
        top_match=top_match,
        why=why,
        recommendations=recommendations,
    )
    try:
        text = await provider.generate(prompt)
    except Exception as exc:
        logger.warning("LLM narration failed: %s", exc)
        return None
    return text or None


async def _narrate_role_comp(
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
) -> str | None:
    try:
        provider = get_llm_provider(get_settings())
    except Exception:
        return None
    if provider is None:
        return None
    prompt = build_role_llm_prompt(
        questionnaire=questionnaire,
        mechanics=mechanics,
        user_role_vector=user_role_vector,
        archetype=archetype,
        top_match=top_match,
        why=why,
        mechanics_recs=mechanics_recs,
        role_recs=role_recs,
        evidence_tier=evidence_tier,
        named_matches_suppressed=named_matches_suppressed,
    )
    try:
        text = await provider.generate(prompt)
    except Exception as exc:
        logger.warning("LLM role narration failed: %s", exc)
        return None
    return text or None


async def run_style_comp(
    supabase: SupabaseService,
    user_id: str,
    *,
    season: str = DEFAULT_SEASON,
    top_k: int = 3,
) -> dict[str, Any]:
    """Legacy cosine engine — do not call from production POST /me/comp."""
    profile = await supabase.get_profile(user_id)
    if profile is None:
        raise CompError("Profile not found")

    height_in = profile.get("height_in")
    position = profile.get("position")
    if height_in is None or position is None:
        raise CompError("Set height and position on your profile before running comps")

    try:
        height_in_f = float(height_in)
    except (TypeError, ValueError) as exc:
        raise CompError("Invalid height_in on profile") from exc

    position_s = str(position)

    height_z_us = profile.get("height_z")
    if height_z_us is None:
        height_z_us = compute_height_z(height_in_f)
    else:
        try:
            height_z_us = float(height_z_us)
        except (TypeError, ValueError):
            height_z_us = compute_height_z(height_in_f)

    height_z_nba = compute_height_z_nba(height_in_f, position_s)

    primary_skill = profile.get("primary_skill")
    agg = await supabase.list_user_profile_agg(user_id)
    evidence = evidence_from_agg(agg)

    if not any(evidence.values()):
        feature_rows = await supabase.list_done_clip_features_for_user(user_id)
        if feature_rows:
            from app.services.aggregate import average_features_by_name

            agg = average_features_by_name(feature_rows)
            await supabase.replace_user_profile_agg(user_id, agg)
            evidence = evidence_from_agg(agg)

    if not any(evidence.values()):
        raise CompError(
            "No pose features yet. Open Your clips and click Reprocess on a Done "
            "individual clip (or upload a new one), then run the comp again."
        )

    user_style = build_user_style_vector(
        height_in=height_in_f,
        aggregated_features=agg,
        position=position_s,
    )
    if len(user_style) <= 1 and "size" in user_style:
        raise CompError("Need pose features from a done clip to build a style vector")

    players = await supabase.list_nba_players(season=season)
    if not players:
        players = await supabase.list_nba_players()
        if players:
            season = str(players[0].get("season") or season)

    if not players:
        raise CompError(
            "NBA player database is empty — run: "
            "python -m app.scripts.seed_nba_players"
        )

    eligible = filter_nba_pool(
        players,
        position=position_s,
        height_in=height_in_f,
        height_z_nba=height_z_nba,
    )
    if not eligible:
        raise CompError(
            f"No NBA players in season pool match position={position_s} "
            f"within height band of {height_in_f:.1f} in"
        )

    ranked = rank_matches(
        eligible,
        user_style=user_style,
        user_height_in=height_in_f,
        height_z_nba=height_z_nba,
        primary_skill=str(primary_skill) if primary_skill else None,
        evidence=evidence,
        top_k=top_k,
    )
    ranked = annotate_matches_with_why(
        ranked,
        user_style=user_style,
        user_height_in=height_in_f,
        height_z_nba=height_z_nba,
        primary_skill=str(primary_skill) if primary_skill else None,
        evidence=evidence,
    )

    mechanics = {
        row["feature_name"]: float(row["value"])
        for row in agg
        if isinstance(row.get("feature_name"), str)
        and isinstance(row.get("value"), (int, float))
    }

    recommendations = build_recommendations(
        mechanics=mechanics,
        user_style=user_style,
        evidence=evidence,
        overall_matches=ranked["overall"],
        eligible=eligible,
        agg=agg,
    )

    top_match = ranked["overall"][0] if ranked["overall"] else None
    summary = await _narrate_comp(
        questionnaire={
            "height_in": height_in_f,
            "height_z_us": height_z_us,
            "height_z_nba": height_z_nba,
            "position": position_s,
            "primary_skill": primary_skill,
        },
        mechanics=mechanics,
        user_style=user_style,
        top_match=top_match,
        why=(top_match or {}).get("why") if top_match else None,
        recommendations=recommendations,
    )

    matches_payload = {
        "season": season,
        "label": "style",
        "user_style": user_style,
        "height_z_us": height_z_us,
        "height_z_nba": height_z_nba,
        "evidence": evidence,
        "mechanics": mechanics,
        "overall": ranked["overall"],
        "by_category": ranked["by_category"],
        "pool_size": ranked["pool_size"],
        "recommendations": recommendations,
    }

    row = await supabase.insert_comp_result(user_id, matches_payload, summary=summary)
    return {
        "id": row.get("id"),
        "user_id": row.get("user_id", user_id),
        "created_at": row.get("created_at"),
        "summary": row.get("summary"),
        **matches_payload,
    }


def _tier_allows_named(tier: EvidenceTier | str) -> bool:
    value = tier.value if isinstance(tier, EvidenceTier) else str(tier)
    return value in {EvidenceTier.established.value, EvidenceTier.strong.value}


def _bootstrap_top3_overlap(
    events: list[dict],
    *,
    user_id: str,
    players: list[dict],
    user_height_in: float,
    height_band_in: float,
    base_names: list[str],
    user_q: dict[str, float],
    n_iter: int = BOOTSTRAP_RANK_ITERATIONS,
) -> float | None:
    if len(events) < 5 or not base_names:
        return None
    rng = random.Random(17)
    hits = 0.0
    n = len(events)
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
    return hits / n_iter


async def run_role_comp(
    supabase: SupabaseService,
    user_id: str,
    *,
    season: str = DEFAULT_SEASON,
    top_k: int = 3,
) -> dict[str, Any]:
    profile_row = await supabase.get_profile(user_id)
    if profile_row is None:
        raise CompError("Profile not found")

    height_in = profile_row.get("height_in")
    position = profile_row.get("position")
    if height_in is None or position is None:
        raise CompError("Set height and position on your profile before running comps")

    try:
        height_in_f = float(height_in)
    except (TypeError, ValueError) as exc:
        raise CompError("Invalid height_in on profile") from exc
    position_s = str(position)

    height_z_us = profile_row.get("height_z")
    if height_z_us is None:
        height_z_us = compute_height_z(height_in_f)
    else:
        try:
            height_z_us = float(height_z_us)
        except (TypeError, ValueError):
            height_z_us = compute_height_z(height_in_f)
    height_z_nba = compute_height_z_nba(height_in_f, position_s)

    role_row = await supabase.get_user_role_profile(user_id)
    events = await supabase.list_clip_events(user_id=user_id, gate_passed=True)
    role_profile: UserRoleProfileRecord | None = None
    if events:
        role_profile = aggregate_role_profile(events, user_id=user_id)
        saved = await supabase.upsert_user_role_profile(user_role_profile_to_row(role_profile))
        if saved.get("id"):
            role_profile.id = saved["id"]
    elif role_row:
        role_profile = user_role_profile_from_row(role_row)

    if role_profile is None:
        raise CompError(
            "No playing-style profile yet. Process clips so quality-checked events "
            "can build your role profile, then run the comparison again."
        )

    user_vector = build_role_vector(role_profile.role_vector.model_dump())
    active = [d.value for d in role_profile.active_dimensions]
    excluded = [k for k in ROLE_VECTOR_KEYS if k not in user_vector]
    user_q = user_quality_weights(role_profile)
    archetype = classify_archetype(
        user_vector,
        position=position_s,
        evidence_tier=role_profile.evidence_tier,
    )

    agg = await supabase.list_user_profile_agg(user_id)
    mechanics = {
        row["feature_name"]: float(row["value"])
        for row in agg
        if isinstance(row.get("feature_name"), str)
        and isinstance(row.get("value"), (int, float))
    }

    players = await supabase.list_nba_players(season=season)
    if not players:
        players = await supabase.list_nba_players()
        if players:
            season = str(players[0].get("season") or season)
    if not players:
        raise CompError(
            "NBA player database is empty — run: "
            "python -m app.scripts.seed_nba_players"
        )

    if not any(nba_role_vector(p) for p in players):
        players = finalize_nba_role_rows(players, season=season)

    pool = select_nba_pool(
        players,
        position=position_s,
        height_in=height_in_f,
        season=season,
    )

    ranked_all = rank_role_matches(
        pool.players,
        user_vector=user_vector,
        user_q=user_q,
        user_height_in=height_in_f,
        height_band_in=pool.height_band_in,
        top_k=max(top_k, 8),
    )
    base_names = [row["name"] for row in ranked_all[:3] if row.get("name")]
    overlap = _bootstrap_top3_overlap(
        events,
        user_id=user_id,
        players=pool.players,
        user_height_in=height_in_f,
        height_band_in=pool.height_band_in,
        base_names=base_names,
        user_q=user_q,
    )
    overall_stable = bool((role_profile.quality_summary or {}).get("overall_stable"))
    suppress_reason = None
    if not _tier_allows_named(role_profile.evidence_tier):
        suppress_reason = "evidence_tier"
    elif len(role_profile.active_dimensions) < 2:
        suppress_reason = "active_dimensions"
    elif not overall_stable:
        suppress_reason = "stability"
    elif overlap is not None and overlap < TOP3_OVERLAP_MIN:
        suppress_reason = "top3_overlap"
    elif not pool.named_matches_allowed:
        suppress_reason = "pool_size"
    elif len(user_vector) < 2:
        suppress_reason = "active_dimensions"

    named_ok = suppress_reason is None
    overall = []
    if named_ok:
        overall = ranked_all[:top_k]
        for match in overall:
            match["why"] = build_role_why(
                match=match,
                user_vector=user_vector,
                user_height_in=height_in_f,
                pool=pool,
                evidence_tier=role_profile.evidence_tier.value,
            )
            match["match_confidence"] = round(100 * float(match["score"]))

    top_match = overall[0] if overall else None
    mechanics_recs = build_mechanics_recs(mechanics, agg=agg)
    role_recs = build_role_recs(
        role_profile,
        archetype=archetype,
        named_match_name=top_match["name"] if top_match else None,
    )
    recommendations = [*mechanics_recs, *role_recs]

    summary = await _narrate_role_comp(
        questionnaire={
            "height_in": height_in_f,
            "height_z_us": height_z_us,
            "height_z_nba": height_z_nba,
            "position": position_s,
            "primary_skill": profile_row.get("primary_skill"),
        },
        mechanics=mechanics,
        user_role_vector=user_vector,
        archetype=archetype,
        top_match=top_match,
        why=(top_match or {}).get("why") if top_match else None,
        mechanics_recs=mechanics_recs,
        role_recs=role_recs,
        evidence_tier=role_profile.evidence_tier.value,
        named_matches_suppressed=not named_ok,
    )

    quality_dims = (role_profile.quality_summary or {}).get("dimensions") or {}
    stability_metrics = {
        "overall_stable": overall_stable,
        "top_3_overlap_rate": overlap,
        "active_role_dimensions": len(role_profile.active_dimensions),
        "bootstrap_dimension_sd": {
            dim: (quality_dims.get(dim) or {}).get("bootstrap_sd")
            for dim in ("catch_readiness", "rim_pressure", "playmaking")
        },
    }

    matches_payload = {
        "season": season,
        "label": "role_profile",
        "comparison_mode": COMPARISON_MODE_ROLE,
        "user_style": user_vector,
        "user_role_vector": user_vector,
        "height_z_us": height_z_us,
        "height_z_nba": height_z_nba,
        "evidence": {k: k in user_vector for k in ROLE_VECTOR_KEYS},
        "evidence_tier": role_profile.evidence_tier.value,
        "mechanics": mechanics,
        "overall": overall,
        "by_category": {},
        "pool_size": len(pool.players),
        "pool_sentence": pool.pool_sentence,
        "recommendations": recommendations,
        "mechanics_recs": mechanics_recs,
        "role_recs": role_recs,
        "archetype_result": archetype,
        "candidate_results": ranked_all[:8],
        "named_matches_suppressed": not named_ok,
        "suppression_reason": suppress_reason,
        "active_dimensions": active,
        "excluded_dimensions": excluded,
        "user_score_kind": "latent",
        "nba_score_kind": "cohort_percentile",
    }

    audit = {
        "user_role_profile_id": str(role_profile.id) if role_profile.id else None,
        "profile_version": ROLE_PROFILE_VERSION,
        "nba_seed_version": NBA_TRANSFORM_VERSION,
        "comparison_mode": ComparisonMode.role_profile_v1.value,
        "cohort_definition": pool.cohort_definition,
        "active_dimensions": active,
        "excluded_dimensions": excluded,
        "dimension_contributions": (top_match or {}).get("dimension_contributions") or {},
        "candidate_results": ranked_all[:8],
        "archetype_result": archetype,
        "evidence_tier": role_profile.evidence_tier.value,
        "stability_metrics": stability_metrics,
        "disclosure_version": DISCLOSURE_VERSION,
        "mechanics_recs": mechanics_recs,
        "role_recs": role_recs,
    }

    row = await supabase.insert_comp_result(
        user_id,
        matches_payload,
        summary=summary,
        audit=audit,
    )
    return {
        "id": row.get("id"),
        "user_id": row.get("user_id", user_id),
        "created_at": row.get("created_at"),
        "summary": row.get("summary"),
        **matches_payload,
    }


def comp_from_stored_row(row: dict) -> dict[str, Any]:
    matches = row.get("matches") or {}
    if not isinstance(matches, dict):
        matches = {}
    mode = row.get("comparison_mode") or matches.get("comparison_mode") or "legacy_style"
    return {
        "id": row.get("id"),
        "user_id": row.get("user_id"),
        "created_at": row.get("created_at"),
        "summary": row.get("summary"),
        "season": matches.get("season"),
        "label": matches.get("label", "style"),
        "comparison_mode": mode,
        "user_style": matches.get("user_style") or matches.get("user_role_vector") or {},
        "user_role_vector": matches.get("user_role_vector") or matches.get("user_style") or {},
        "evidence": matches.get("evidence") or {},
        "evidence_tier": row.get("evidence_tier") or matches.get("evidence_tier"),
        "mechanics": matches.get("mechanics") or {},
        "overall": matches.get("overall") or [],
        "by_category": matches.get("by_category") or {},
        "pool_size": matches.get("pool_size") or 0,
        "pool_sentence": matches.get("pool_sentence"),
        "recommendations": matches.get("recommendations") or [],
        "mechanics_recs": row.get("mechanics_recs") or matches.get("mechanics_recs") or [],
        "role_recs": row.get("role_recs") or matches.get("role_recs") or [],
        "archetype_result": row.get("archetype_result") or matches.get("archetype_result") or {},
        "named_matches_suppressed": matches.get("named_matches_suppressed"),
        "suppression_reason": matches.get("suppression_reason"),
        "active_dimensions": row.get("active_dimensions") or matches.get("active_dimensions") or [],
        "excluded_dimensions": row.get("excluded_dimensions") or matches.get("excluded_dimensions") or [],
        "height_z_us": matches.get("height_z_us"),
        "height_z_nba": matches.get("height_z_nba"),
    }
