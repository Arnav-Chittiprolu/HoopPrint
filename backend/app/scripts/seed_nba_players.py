"""CLI: python -m app.scripts.seed_nba_players [--season 2025-26]

Pulls the full current NBA roster from nba_api and upserts into nba_players.
Requires SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in backend/.env.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.config import get_settings
from app.services.nba_seed import DEFAULT_SEASON, fetch_nba_player_rows
from app.services.supabase_client import SupabaseService


async def _main(season: str) -> int:
    settings = get_settings()
    try:
        supabase = SupabaseService(settings)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Fetching NBA players for season {season} via nba_api...", flush=True)
    try:
        rows = await asyncio.to_thread(fetch_nba_player_rows, season)
    except Exception as exc:
        print(f"error fetching nba_api data: {exc}", file=sys.stderr)
        return 1

    print(f"Upserting {len(rows)} players into nba_players...", flush=True)
    try:
        saved = await supabase.replace_nba_players_for_season(season, rows)
    except Exception as exc:
        print(f"error writing to Supabase: {exc}", file=sys.stderr)
        return 1

    by_pos: dict[str, int] = {}
    with_role = 0
    for row in saved:
        pos = row.get("position") or "?"
        by_pos[pos] = by_pos.get(pos, 0) + 1
        rv = row.get("role_vector") or {}
        if isinstance(rv, dict) and rv:
            with_role += 1

    print(
        json.dumps(
            {
                "season": season,
                "count": len(saved),
                "with_role_vector": with_role,
                "transform_version": saved[0].get("transform_version") if saved else None,
                "by_position": by_pos,
            },
            indent=2,
        )
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed nba_players from nba_api")
    parser.add_argument(
        "--season",
        default=DEFAULT_SEASON,
        help=f"NBA season string (default {DEFAULT_SEASON})",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_main(args.season)))


if __name__ == "__main__":
    main()
