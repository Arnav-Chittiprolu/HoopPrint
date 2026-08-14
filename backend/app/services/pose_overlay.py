"""Draw MediaPipe-style skeleton overlays onto video frames."""

from __future__ import annotations

import os
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


def overlay_storage_path(storage_path: str) -> str:
    path = Path(storage_path)
    return str(path.with_name(f"{path.stem}_overlay.mp4"))


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


def _encode_h264(frames_bgr: list[np.ndarray], fps: float) -> bytes:
    """Write browser-playable H.264 MP4 via imageio-ffmpeg if available."""
    if not frames_bgr:
        raise ValueError("No frames to encode")

    try:
        import imageio.v3 as iio
    except ImportError as exc:
        raise RuntimeError("imageio is required to encode overlay videos") from exc

    rgb_frames = [cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) for frame in frames_bgr]
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        out_path = tmp.name

    try:
        iio.imwrite(
            out_path,
            rgb_frames,
            fps=fps,
            codec="libx264",
            pixelformat="yuv420p",
            macro_block_size=1,
        )
        return Path(out_path).read_bytes()
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


def render_pose_overlay_video(
    video_bytes: bytes,
    keypoint_rows: list[dict],
    *,
    suffix: str = ".mp4",
) -> bytes:
    """Replay the clip and draw stored pose keypoints on matching frame indices."""
    by_frame = {
        int(row["frame_index"]): row.get("keypoints") or {}
        for row in keypoint_rows
    }

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(video_bytes)
        tmp.flush()
        src_path = tmp.name

    frames_out: list[np.ndarray] = []
    try:
        capture = cv2.VideoCapture(src_path)
        if not capture.isOpened():
            raise ValueError("Could not open video for overlay render")

        fps = float(capture.get(cv2.CAP_PROP_FPS) or 24.0)
        if fps <= 1e-3:
            fps = 24.0

        frame_index = 0
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
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
                frames_out.append(frame)
                frame_index += 1
        finally:
            capture.release()
    finally:
        try:
            os.unlink(src_path)
        except OSError:
            pass

    if not frames_out:
        raise ValueError("Video contained no frames")

    return _encode_h264(frames_out, fps)
