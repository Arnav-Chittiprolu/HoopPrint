"""Fetch full NBA roster style rows from nba_api (seed/cache only).

League-wide endpoints (not per-player live calls at comp time):
- PlayerIndex — position + height string fallback
- LeagueDashPlayerBioStats — height inches, AST_PCT
- LeagueDashPlayerStats (Scoring) — PCT_FGA_3PT, PCT_PTS_PAINT, PCT_UAST_FGM
- LeagueDashPtStats Drives / SpeedDistance / Passing / PullUpShot / CatchShoot
"""

from __future__ import annotations

import time
from typing import Any, Callable

from app.services.aggregate import compute_height_z, compute_height_z_nba
from app.services.style import clamp01, map_nba_position, size_from_height_in

DEFAULT_SEASON = "2025-26"


def _sleep(seconds: float = 0.7) -> None:
    time.sleep(seconds)


def _df_records(endpoint: Any) -> list[dict]:
    frame = endpoint.get_data_frames()[0]
    return frame.to_dict(orient="records")


def _minmax_norm(values: dict[Any, float]) -> dict[Any, float]:
    if not values:
        return {}
    lo = min(values.values())
    hi = max(values.values())
    if hi - lo < 1e-12:
        return {k: 0.5 for k in values}
    return {k: clamp01((v - lo) / (hi - lo)) for k, v in values.items()}


def _safe_float(row: dict, *keys: str) -> float | None:
    for key in keys:
        if key not in row or row[key] is None:
            continue
        try:
            return float(row[key])
        except (TypeError, ValueError):
            continue
    return None


def _parse_height_string(height: str | None) -> float | None:
    if not height or not isinstance(height, str) or "-" not in height:
        return None
    try:
        feet, inches = height.split("-", 1)
        return float(feet) * 12.0 + float(inches)
    except ValueError:
        return None


def build_nba_style_vector(raw: dict[str, Any]) -> dict[str, float]:
    """Map cached raw_stats → shared style slots in ~[0, 1]."""
    vector: dict[str, float] = {}

    height_in = raw.get("height_in")
    position = raw.get("position")
    size = size_from_height_in(
        float(height_in) if height_in is not None else None,
        str(position) if position else None,
    )
    if size is not None:
        vector["size"] = size

    pct_3 = raw.get("pct_fga_3pt")
    paint = raw.get("pct_pts_paint")
    peri_parts: list[float] = []
    if isinstance(pct_3, (int, float)):
        peri_parts.append(clamp01(float(pct_3)))
    if isinstance(paint, (int, float)):
        peri_parts.append(clamp01(1.0 - float(paint)))
    if peri_parts:
        vector["perimeter_vs_rim"] = sum(peri_parts) / len(peri_parts)

    uast = raw.get("pct_uast_fgm")
    pull = raw.get("pull_up_fga")
    catch = raw.get("catch_shoot_fga")
    creation_parts: list[float] = []
    if isinstance(uast, (int, float)):
        creation_parts.append(clamp01(float(uast)))
    if isinstance(pull, (int, float)) and isinstance(catch, (int, float)):
        denom = float(pull) + float(catch)
        if denom > 0:
            creation_parts.append(clamp01(float(pull) / denom))
    if creation_parts:
        vector["creation"] = sum(creation_parts) / len(creation_parts)

    drive_parts: list[float] = []
    if isinstance(raw.get("drives_norm"), (int, float)):
        drive_parts.append(clamp01(float(raw["drives_norm"])))
    if isinstance(raw.get("speed_off_norm"), (int, float)):
        drive_parts.append(clamp01(float(raw["speed_off_norm"])))
    if drive_parts:
        vector["drive_burst"] = sum(drive_parts) / len(drive_parts)

    pass_parts: list[float] = []
    if isinstance(raw.get("ast_pct"), (int, float)):
        pass_parts.append(clamp01(float(raw["ast_pct"])))
    pot = raw.get("potential_ast")
    passes = raw.get("passes_made")
    if isinstance(pot, (int, float)) and isinstance(passes, (int, float)) and float(passes) > 0:
        pass_parts.append(clamp01(float(pot) / float(passes)))
    if pass_parts:
        vector["passing"] = sum(pass_parts) / len(pass_parts)

    return vector


def fetch_nba_player_rows(
    season: str = DEFAULT_SEASON,
    *,
    sleep_fn: Callable[[], None] | None = None,
) -> list[dict]:
    """Pull all players for a season and return DB-ready nba_players rows."""
    from nba_api.stats.endpoints import (
        leaguedashplayerbiostats,
        leaguedashplayerstats,
        leaguedashptstats,
        playerindex,
    )

    pause = sleep_fn or _sleep

    index_rows = _df_records(playerindex.PlayerIndex(season=season))
    pause()
    bio_rows = _df_records(leaguedashplayerbiostats.LeagueDashPlayerBioStats(season=season))
    pause()
    scoring_rows = _df_records(
        leaguedashplayerstats.LeagueDashPlayerStats(
            season=season,
            per_mode_detailed="PerGame",
            measure_type_detailed_defense="Scoring",
        )
    )
    pause()
    drives_rows = _df_records(
        leaguedashptstats.LeagueDashPtStats(
            season=season,
            player_or_team="Player",
            pt_measure_type="Drives",
            per_mode_simple="PerGame",
        )
    )
    pause()
    speed_rows = _df_records(
        leaguedashptstats.LeagueDashPtStats(
            season=season,
            player_or_team="Player",
            pt_measure_type="SpeedDistance",
            per_mode_simple="PerGame",
        )
    )
    pause()
    passing_rows = _df_records(
        leaguedashptstats.LeagueDashPtStats(
            season=season,
            player_or_team="Player",
            pt_measure_type="Passing",
            per_mode_simple="PerGame",
        )
    )
    pause()
    pullup_rows = _df_records(
        leaguedashptstats.LeagueDashPtStats(
            season=season,
            player_or_team="Player",
            pt_measure_type="PullUpShot",
            per_mode_simple="PerGame",
        )
    )
    pause()
    catch_rows = _df_records(
        leaguedashptstats.LeagueDashPtStats(
            season=season,
            player_or_team="Player",
            pt_measure_type="CatchShoot",
            per_mode_simple="PerGame",
        )
    )

    index_by_id = {int(r["PERSON_ID"]): r for r in index_rows if r.get("PERSON_ID") is not None}
    bio_by_id = {int(r["PLAYER_ID"]): r for r in bio_rows if r.get("PLAYER_ID") is not None}
    scoring_by_id = {int(r["PLAYER_ID"]): r for r in scoring_rows if r.get("PLAYER_ID") is not None}
    drives_by_id = {int(r["PLAYER_ID"]): r for r in drives_rows if r.get("PLAYER_ID") is not None}
    speed_by_id = {int(r["PLAYER_ID"]): r for r in speed_rows if r.get("PLAYER_ID") is not None}
    passing_by_id = {int(r["PLAYER_ID"]): r for r in passing_rows if r.get("PLAYER_ID") is not None}
    pullup_by_id = {int(r["PLAYER_ID"]): r for r in pullup_rows if r.get("PLAYER_ID") is not None}
    catch_by_id = {int(r["PLAYER_ID"]): r for r in catch_rows if r.get("PLAYER_ID") is not None}

    drives_norm = _minmax_norm(
        {
            pid: v
            for pid, row in drives_by_id.items()
            if (v := _safe_float(row, "DRIVES")) is not None
        }
    )
    speed_norm = _minmax_norm(
        {
            pid: v
            for pid, row in speed_by_id.items()
            if (v := _safe_float(row, "AVG_SPEED_OFF", "AVG_SPEED")) is not None
        }
    )

    player_ids = sorted(set(index_by_id) | set(bio_by_id))
    rows: list[dict] = []

    for pid in player_ids:
        idx = index_by_id.get(pid, {})
        bio = bio_by_id.get(pid, {})
        scoring = scoring_by_id.get(pid, {})
        drives = drives_by_id.get(pid, {})
        speed = speed_by_id.get(pid, {})
        passing = passing_by_id.get(pid, {})
        pullup = pullup_by_id.get(pid, {})
        catch = catch_by_id.get(pid, {})

        name = (
            bio.get("PLAYER_NAME")
            or " ".join(
                p
                for p in [idx.get("PLAYER_FIRST_NAME"), idx.get("PLAYER_LAST_NAME")]
                if p
            ).strip()
            or None
        )
        if not name:
            continue

        height_in = _safe_float(bio, "PLAYER_HEIGHT_INCHES")
        if height_in is None:
            height_in = _parse_height_string(idx.get("HEIGHT"))
        position = map_nba_position(idx.get("POSITION"))
        if height_in is None or position is None:
            continue

        raw_stats: dict[str, Any] = {
            "player_id": pid,
            "height_in": height_in,
            "position": position,
            "height_z_us": compute_height_z(height_in),
            "height_z_nba": compute_height_z_nba(height_in, position),
            "nba_position_raw": idx.get("POSITION"),
            "team": bio.get("TEAM_ABBREVIATION") or idx.get("TEAM_ABBREVIATION"),
            "gp": _safe_float(bio, "GP") or _safe_float(scoring, "GP"),
            "ast_pct": _safe_float(bio, "AST_PCT"),
            "pct_fga_3pt": _safe_float(scoring, "PCT_FGA_3PT"),
            "pct_pts_paint": _safe_float(scoring, "PCT_PTS_PAINT"),
            "pct_uast_fgm": _safe_float(scoring, "PCT_UAST_FGM"),
            "drives": _safe_float(drives, "DRIVES"),
            "drives_norm": drives_norm.get(pid),
            "avg_speed_off": _safe_float(speed, "AVG_SPEED_OFF", "AVG_SPEED"),
            "speed_off_norm": speed_norm.get(pid),
            "passes_made": _safe_float(passing, "PASSES_MADE"),
            "potential_ast": _safe_float(passing, "POTENTIAL_AST"),
            "pull_up_fga": _safe_float(pullup, "PULL_UP_FGA"),
            "catch_shoot_fga": _safe_float(catch, "CATCH_SHOOT_FGA"),
            "sources": [
                "PlayerIndex",
                "LeagueDashPlayerBioStats",
                "LeagueDashPlayerStats:Scoring",
                "LeagueDashPtStats:Drives",
                "LeagueDashPtStats:SpeedDistance",
                "LeagueDashPtStats:Passing",
                "LeagueDashPtStats:PullUpShot",
                "LeagueDashPtStats:CatchShoot",
            ],
        }

        rows.append(
            {
                "player_id": pid,
                "name": name,
                "season": season,
                "position": position,
                "height_in": height_in,
                "raw_stats": raw_stats,
                "style_vector": build_nba_style_vector(raw_stats),
            }
        )

    return rows
