"""CLI: python -m app.scripts.extract_pose --video FILE --out FILE --source individual|gameplay

Runs in a separate interpreter so MediaPipe cannot kill the API worker.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

os.environ.setdefault("MEDIAPIPE_DISABLE_GPU", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--source", required=True, choices=("individual", "gameplay"))
    parser.add_argument("--suffix", default=".mp4")
    parser.add_argument("--bbox", default="", help="x,y,w,h normalized, required for gameplay")
    args = parser.parse_args()

    import cv2

    from app.services.pose_extraction import (
        extract_pose_keypoints_from_path,
        extract_pose_keypoints_tracked_from_path,
    )
    from app.services.track import NormBox

    cv2.setNumThreads(1)

    from app.services.pose_overlay import prepare_working_video

    video_path = prepare_working_video(args.video)
    try:
        if args.source == "gameplay":
            parts = [float(p) for p in args.bbox.split(",")]
            if len(parts) != 4:
                print("gameplay requires --bbox x,y,w,h", file=sys.stderr)
                return 2
            frames = extract_pose_keypoints_tracked_from_path(
                video_path,
                NormBox(x=parts[0], y=parts[1], w=parts[2], h=parts[3]),
            )
        else:
            frames = extract_pose_keypoints_from_path(video_path)
    finally:
        if video_path != args.video:
            try:
                os.unlink(video_path)
            except OSError:
                pass

    payload = [
        {
            "frame_index": frame.frame_index,
            "keypoints": frame.keypoints,
            "track_confidence": frame.track_confidence,
        }
        for frame in frames
    ]
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
