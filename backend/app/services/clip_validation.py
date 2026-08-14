from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # matches Supabase bucket limit
MAX_DURATION_SECONDS = 25.0
ALLOWED_CONTENT_TYPES = {"video/mp4", "application/octet-stream", "video/quicktime"}


def _duration_seconds(path: Path) -> float | None:
    try:
        from mutagen import File as MutagenFile  # noqa: PLC0415

        media = MutagenFile(path)
        if media is not None and media.info is not None and media.info.length:
            return float(media.info.length)
    except Exception:
        pass

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired):
        pass

    try:
        import cv2  # noqa: PLC0415

        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            return None
        fps = capture.get(cv2.CAP_PROP_FPS)
        frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        capture.release()
        if fps and fps > 0 and frame_count >= 0:
            return frame_count / fps
    except ImportError:
        pass

    return None


async def validate_clip_upload(file: UploadFile) -> tuple[bytes, str]:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing filename")

    ext = Path(file.filename).suffix.lower()
    if ext not in {".mp4", ".mov"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .mp4 or .mov clips are supported",
        )

    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported content type: {content_type}",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB limit",
        )

    suffix = ".mp4" if ext == ".mp4" else ".mov"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        duration = await asyncio.to_thread(_duration_seconds, tmp_path)
        if duration is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not read clip duration. Install ffmpeg or upload a valid mp4.",
            )
        if duration > MAX_DURATION_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Clip duration {duration:.1f}s exceeds {MAX_DURATION_SECONDS:.0f}s limit",
            )
    finally:
        tmp_path.unlink(missing_ok=True)

    stored_type = "video/mp4" if ext == ".mp4" else "video/quicktime"
    return content, stored_type
