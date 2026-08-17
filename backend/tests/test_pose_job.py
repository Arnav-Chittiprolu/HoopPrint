from __future__ import annotations

import asyncio
import os
import tempfile

import cv2
import numpy as np

from app.services.pose_job import extract_pose_isolated


def _write_blank_video(path: str, *, frames: int = 6) -> None:
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (80, 60))
    frame = np.zeros((60, 80, 3), dtype=np.uint8)
    for _ in range(frames):
        writer.write(frame)
    writer.release()


def test_isolated_individual_pose_on_blank_video():
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        path = tmp.name
    try:
        _write_blank_video(path)
        frames = asyncio.run(extract_pose_isolated(path, source="individual", suffix=".mp4"))
        assert frames == []
    finally:
        os.unlink(path)


def test_isolated_gameplay_pose_on_blank_video():
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        path = tmp.name
    try:
        _write_blank_video(path)
        frames = asyncio.run(
            extract_pose_isolated(
                path,
                source="gameplay",
                suffix=".mp4",
                bbox=(0.2, 0.2, 0.4, 0.5),
            )
        )
        assert isinstance(frames, list)
    finally:
        os.unlink(path)
