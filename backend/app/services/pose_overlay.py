"""Draw MediaPipe-style skeleton overlays onto video frames."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

# MediaPipe Pose landmark connections (33-point model).
POSE_CONNECTIONS: tuple[tuple[int, int], ...] = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 7),
    (0, 4),
    (4, 5),
    (5, 6),
    (6, 8),
    (9, 10),
    (11, 12),
    (11, 13),
    (13, 15),
    (15, 17),
    (15, 19),
    (15, 21),
    (12, 14),
    (14, 16),
    (16, 18),
    (16, 20),
    (16, 22),
    (11, 23),
    (12, 24),
    (23, 24),
    (23, 25),
    (25, 27),
    (27, 29),
    (27, 31),
    (24, 26),
    (26, 28),
    (28, 30),
    (28, 32),
)

LINE_COLOR = (0, 255, 128)
POINT_COLOR = (0, 200, 255)
MIN_VIS = 0.4
OVERLAY_MAX_SIDE = 640


def overlay_storage_path(storage_path: str) -> str:
    path = Path(storage_path)
    return str(path.with_name(f"{path.stem}_overlay.mp4"))


def prepare_working_video(src_path: str, max_side: int = OVERLAY_MAX_SIDE) -> str:
    """Return src, or a downscaled H.264 copy if the source is larger than max_side.

    Caller must delete the returned path when it differs from src_path.
    """
    capture = cv2.VideoCapture(src_path)
    if not capture.isOpened():
        raise ValueError("Could not open video")
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    capture.release()
    if max(width, height) <= max_side:
        return src_path

    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("imageio-ffmpeg is required to downscale clips") from exc

    out_path = str(Path(src_path).with_name(Path(src_path).stem + ".work.mp4"))
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            src_path,
            "-vf",
            f"scale={max_side}:{max_side}:force_original_aspect_ratio=decrease",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "32",
            out_path,
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0 or not Path(out_path).is_file():
        detail = (result.stderr or b"").decode("utf-8", errors="replace")[-400:]
        raise RuntimeError(f"ffmpeg downscale failed: {detail}")
    return out_path


def _scale_to_max_side(frame: np.ndarray, max_side: int = OVERLAY_MAX_SIDE) -> np.ndarray:
    height, width = frame.shape[:2]
    longest = max(height, width)
    if longest <= max_side:
        new_w = width - (width % 2)
        new_h = height - (height % 2)
        return frame[:new_h, :new_w]
    scale = max_side / float(longest)
    new_w = max(2, int(round(width * scale)) & ~1)
    new_h = max(2, int(round(height * scale)) & ~1)
    return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _draw_pose(frame_bgr: np.ndarray, keypoints: dict) -> None:
    h, w = frame_bgr.shape[:2]
    points = keypoints.get("landmarks") or []
    by_index: dict[int, tuple[int, int, float]] = {}
    for point in points:
        index = int(point.get("index", -1))
        vis = float(point.get("visibility") or 0.0)
        if index < 0 or vis < MIN_VIS:
            continue
        x = int(float(point["x"]) * w)
        y = int(float(point["y"]) * h)
        by_index[index] = (x, y, vis)

    for a, b in POSE_CONNECTIONS:
        if a not in by_index or b not in by_index:
            continue
        cv2.line(frame_bgr, by_index[a][:2], by_index[b][:2], LINE_COLOR, 2, cv2.LINE_AA)

    for x, y, _vis in by_index.values():
        cv2.circle(frame_bgr, (x, y), 4, POINT_COLOR, -1, cv2.LINE_AA)


def render_pose_overlay_video(
    video_path: str,
    keypoint_rows: list[dict],
) -> bytes:
    """Replay the clip and draw stored pose keypoints, streaming H.264 to disk."""
    by_frame = {
        int(row["frame_index"]): row.get("keypoints") or {}
        for row in keypoint_rows
    }

    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("imageio-ffmpeg is required to encode overlay videos") from exc

    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise ValueError("Could not open video for overlay render")

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 24.0)
    if fps <= 1e-3:
        fps = 24.0

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        out_path = tmp.name

    proc: subprocess.Popen[bytes] | None = None
    wrote = 0
    try:
        ok, frame = capture.read()
        if not ok or frame is None:
            raise ValueError("Video contained no frames")
        frame = _scale_to_max_side(frame)
        height, width = frame.shape[:2]
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        proc = subprocess.Popen(
            [
                ffmpeg,
                "-y",
                "-f",
                "rawvideo",
                "-vcodec",
                "rawvideo",
                "-pix_fmt",
                "bgr24",
                "-s",
                f"{width}x{height}",
                "-r",
                str(fps),
                "-i",
                "-",
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "veryfast",
                "-crf",
                "28",
                "-movflags",
                "+faststart",
                out_path,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        assert proc.stdin is not None

        frame_index = 0
        while True:
            if frame_index in by_frame:
                _draw_pose(frame, by_frame[frame_index])
                cv2.putText(
                    frame,
                    "HoopPrint pose",
                    (16, 32),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
            proc.stdin.write(frame.tobytes())
            wrote += 1
            ok, next_frame = capture.read()
            if not ok:
                break
            frame = _scale_to_max_side(next_frame)
            if frame.shape[0] != height or frame.shape[1] != width:
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
            frame_index += 1

        proc.stdin.close()
        stderr = proc.communicate(timeout=120)[1]
        if proc.returncode != 0:
            detail = (stderr or b"").decode("utf-8", errors="replace")[-400:]
            raise RuntimeError(f"ffmpeg overlay encode failed: {detail}")
        if wrote == 0:
            raise ValueError("Video contained no frames")
        return Path(out_path).read_bytes()
    finally:
        capture.release()
        if proc is not None and proc.poll() is None:
            proc.kill()
        try:
            os.unlink(out_path)
        except OSError:
            pass
