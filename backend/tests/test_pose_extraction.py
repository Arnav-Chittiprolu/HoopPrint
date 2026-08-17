from __future__ import annotations

import tempfile

import cv2
import numpy as np
import pytest

from app.services.pose_extraction import extract_pose_keypoints, scale_to_max_side


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


def test_extract_pose_keypoints_rejects_invalid_step():
    video_bytes = _make_blank_video(frames=2)
    with pytest.raises(ValueError, match="frame_step"):
        extract_pose_keypoints(video_bytes, frame_step=0)


def test_scale_to_max_side_shrinks_4k_and_keeps_aspect():
    frame = np.zeros((2160, 3840, 3), dtype=np.uint8)
    small = scale_to_max_side(frame, 640)
    assert small.shape[1] == 640
    assert small.shape[0] == 360
