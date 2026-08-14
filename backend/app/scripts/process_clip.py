"""CLI entrypoint: python -m app.scripts.process_clip <clip_id>"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.services.clip_processor import ClipProcessingError, process_individual_clip


async def _main(clip_id: str) -> int:
    try:
        result = await process_individual_clip(clip_id)
    except ClipProcessingError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "clip_id": result["clip"]["id"],
                "status": result["clip"]["status"],
                "frame_count": result["frame_count"],
            },
            indent=2,
        )
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Process an individual clip for pose keypoints")
    parser.add_argument("clip_id", help="UUID of the clip to process")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_main(args.clip_id)))


if __name__ == "__main__":
    main()
