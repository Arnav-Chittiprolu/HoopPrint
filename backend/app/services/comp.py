"""Run style-space NBA comps from questionnaire + aggregated pose features."""

from __future__ import annotations

from typing import Any

from app.services.aggregate import compute_height_z, compute_height_z_nba
from app.services.nba_seed import DEFAULT_SEASON
from app.services.style import (
    build_user_style_vector,
    evidence_from_agg,
    filter_nba_pool,
    rank_matches,
)
from app.services.supabase_client import SupabaseService


class CompError(Exception):
    """Raised when a comp cannot be computed."""


async def run_style_comp(
    supabase: SupabaseService,
    user_id: str,
    *,
    season: str = DEFAULT_SEASON,
    top_k: int = 3,
) -> dict[str, Any]:
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

    # US-male z stays on the profile for display; comps use NBA/position z.
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

    # Older "done" clips may have keypoints/overlay but empty agg (pre–Phase 4
    # processing, or a silent agg failure). Rebuild from clip_features.
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
        # size alone is not enough for a meaningful style cosine
        raise CompError("Need pose features from a done clip to build a style vector")

    players = await supabase.list_nba_players(season=season)
    if not players:
        # Fall back to any seeded season
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

    mechanics = {
        row["feature_name"]: float(row["value"])
        for row in agg
        if isinstance(row.get("feature_name"), str)
        and isinstance(row.get("value"), (int, float))
    }

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
    }

    row = await supabase.insert_comp_result(user_id, matches_payload, summary=None)
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
    return {
        "id": row.get("id"),
        "user_id": row.get("user_id"),
        "created_at": row.get("created_at"),
        "summary": row.get("summary"),
        "season": matches.get("season"),
        "label": matches.get("label", "style"),
        "user_style": matches.get("user_style") or {},
        "evidence": matches.get("evidence") or {},
        "mechanics": matches.get("mechanics") or {},
        "overall": matches.get("overall") or [],
        "by_category": matches.get("by_category") or {},
        "pool_size": matches.get("pool_size") or 0,
    }
