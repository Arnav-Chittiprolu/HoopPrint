"""Video metadata helpers for role-profile gates."""

from __future__ import annotations


def probe_video_fps(path: str) -> float | None:
    """Return container FPS when readable (cv2/ffprobe)."""
    try:
        import cv2  # noqa: PLC0415

        capture = cv2.VideoCapture(path)
        if not capture.isOpened():
            return None
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        capture.release()
        if fps > 1e-3:
            return fps
    except ImportError:
        pass

    try:
        import subprocess  # noqa: PLC0415

        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=r_frame_rate",
                "-of",
                "csv=p=0",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            rate = result.stdout.strip().split("\n")[0].strip()
            if "/" in rate:
                num, den = rate.split("/", 1)
                den_f = float(den)
                if den_f > 0:
                    return float(num) / den_f
            return float(rate)
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired):
        pass

    return None
