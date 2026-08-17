"""Run pose extraction in a separate Python process (not multiprocessing).

MediaPipe's Metal/GL path can SIGSEGV. A spawned mp.Process still shares the
API worker's process group and has been taking the uvicorn worker down with it.
subprocess with start_new_session=True keeps the API alive.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

POSE_JOB_TIMEOUT_S = 180.0
BACKEND_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class FrameKeypoints:
    frame_index: int
    keypoints: dict
    track_confidence: float


async def extract_pose_isolated(
    video_path: str,
    *,
    source: str,
    suffix: str,
    bbox: tuple[float, float, float, float] | None = None,
    timeout_s: float = POSE_JOB_TIMEOUT_S,
) -> list[FrameKeypoints]:
    out_path = Path(video_path).with_suffix(".pose.json")
    cmd = [
        sys.executable,
        "-m",
        "app.scripts.extract_pose",
        "--video",
        video_path,
        "--out",
        str(out_path),
        "--source",
        source,
        "--suffix",
        suffix,
    ]
    if bbox is not None:
        cmd.extend(["--bbox", ",".join(str(v) for v in bbox)])

    env = os.environ.copy()
    env["MEDIAPIPE_DISABLE_GPU"] = "1"
    extra = str(BACKEND_DIR)
    env["PYTHONPATH"] = extra + os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else extra

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise TimeoutError(f"Pose extraction timed out after {int(timeout_s)}s") from None

    if proc.returncode != 0:
        detail = (stderr or stdout or b"").decode("utf-8", errors="replace")[-800:]
        logger.warning(
            "pose_subprocess_failed",
            extra={
                "event": "pose_subprocess_failed",
                "returncode": proc.returncode,
                "reason": detail,
            },
        )
        raise RuntimeError("Pose extractor crashed")

    if not out_path.is_file():
        raise RuntimeError("Pose extractor produced no output")
    try:
        payload = json.loads(out_path.read_text(encoding="utf-8"))
    finally:
        out_path.unlink(missing_ok=True)

    return [
        FrameKeypoints(
            frame_index=int(row["frame_index"]),
            keypoints=row["keypoints"],
            track_confidence=float(row["track_confidence"]),
        )
        for row in payload
    ]
