from __future__ import annotations

import asyncio
import tempfile

import cv2
import numpy as np
import pytest
from fastapi import HTTPException

from app.services.clip_validation import MAX_DURATION_SECONDS, MAX_FILE_SIZE_BYTES, validate_clip_upload


class _FakeUpload:
    def __init__(self, filename: str, content: bytes, content_type: str = "video/mp4"):
        self.filename = filename
        self.content_type = content_type
        self._content = content

    async def read(self) -> bytes:
        return self._content


def _blank_video_bytes(*, frames: int, fps: float = 10.0) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=True) as tmp:
        writer = cv2.VideoWriter(tmp.name, cv2.VideoWriter_fourcc(*"mp4v"), fps, (80, 60))
        frame = np.zeros((60, 80, 3), dtype=np.uint8)
        for _ in range(frames):
            writer.write(frame)
        writer.release()
        tmp.flush()
        with open(tmp.name, "rb") as handle:
            return handle.read()


def test_validate_rejects_oversize():
    huge = b"x" * (MAX_FILE_SIZE_BYTES + 1)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(validate_clip_upload(_FakeUpload("big.mp4", huge)))  # type: ignore[arg-type]
    assert exc.value.status_code == 400
    assert "50MB" in str(exc.value.detail)


def test_validate_rejects_long_duration():
    frames = int(MAX_DURATION_SECONDS * 10) + 20
    content = _blank_video_bytes(frames=frames, fps=10.0)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(validate_clip_upload(_FakeUpload("long.mp4", content)))  # type: ignore[arg-type]
    assert exc.value.status_code == 400
    assert "exceeds" in str(exc.value.detail)


def test_validate_accepts_short_mp4():
    content = _blank_video_bytes(frames=8, fps=10.0)
    data, content_type = asyncio.run(
        validate_clip_upload(_FakeUpload("ok.mp4", content))  # type: ignore[arg-type]
    )
    assert content_type == "video/mp4"
    assert data == content
