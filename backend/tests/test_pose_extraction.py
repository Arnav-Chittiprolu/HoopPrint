from __future__ import annotations

import tempfile

import cv2
import numpy as np
import pytest

from app.services.pose_extraction import FRAME_STEP, extract_pose_keypoints


def _make_blank_video(*, frames: int = 6, width: int = 320, height: int = 240) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=True) as tmp:
        writer = cv2.VideoWriter(
            tmp.name,
            cv2.VideoWriter_fourcc(*"mp4v"),
            10.0,
            (width, height),
        )
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        for _ in range(frames):
            writer.write(frame)
        writer.release()
        tmp.flush()
        with open(tmp.name, "rb") as handle:
            return handle.read()


def test_extract_pose_keypoints_runs_on_short_video():
    video_bytes = _make_blank_video(frames=8)
    sampled = extract_pose_keypoints(video_bytes, frame_step=FRAME_STEP)
    assert isinstance(sampled, list)
    for frame in sampled:
        assert frame.frame_index >= 0
        assert "landmarks" in frame.keypoints
        assert frame.keypoints["landmark_count"] == 33


def test_extract_pose_keypoints_rejects_invalid_step():
    video_bytes = _make_blank_video(frames=2)
    with pytest.raises(ValueError, match="frame_step"):
        extract_pose_keypoints(video_bytes, frame_step=0)
