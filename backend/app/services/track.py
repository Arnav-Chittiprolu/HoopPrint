"""Single-object tracking for gameplay clips (CSRT, with a template fallback).

Never invent a second person. If the box is lost for several frames, skip
those frames instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

import cv2
import numpy as np

LOST_SKIP_FRAMES = 5
MIN_BOX_SIDE_PX = 12
MIN_BOX_AREA_FRAC = 0.004
SEARCH_PAD = 1.8
POSE_CROP_PAD = 0.10
POSE_KEEP_PAD = 0.08
MAX_CENTER_SHIFT_FRAC = 0.55
MAX_BOX_SCALE_CHANGE = 2.2
MIN_CORE_IN_BOX = 0.4
BOX_CORE_LANDMARKS = (
    "nose",
    "left_shoulder",
    "right_shoulder",
    "left_hip",
    "right_hip",
)


class TrackerLike(Protocol):
    def init(self, frame: np.ndarray, bbox: tuple[int, int, int, int]) -> bool: ...
    def update(self, frame: np.ndarray) -> tuple[bool, tuple[float, float, float, float]]: ...


@dataclass(frozen=True)
class NormBox:
    x: float
    y: float
    w: float
    h: float

    def clamp(self) -> "NormBox":
        x = min(max(self.x, 0.0), 0.98)
        y = min(max(self.y, 0.0), 0.98)
        w = min(max(self.w, 0.02), 1.0 - x)
        h = min(max(self.h, 0.02), 1.0 - y)
        return NormBox(x=x, y=y, w=w, h=h)

    def to_pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        box = self.clamp()
        x = int(round(box.x * width))
        y = int(round(box.y * height))
        w = max(int(round(box.w * width)), MIN_BOX_SIDE_PX)
        h = max(int(round(box.h * height)), MIN_BOX_SIDE_PX)
        w = min(w, width - x)
        h = min(h, height - y)
        return x, y, w, h


def validate_norm_box(x: float, y: float, w: float, h: float) -> NormBox:
    if w <= 0 or h <= 0:
        raise ValueError("Box width and height must be positive")
    if x < 0 or y < 0 or x > 1 or y > 1:
        raise ValueError("Box origin must be inside the frame (0–1)")
    if x + w > 1.02 or y + h > 1.02:
        raise ValueError("Box must stay inside the frame")
    if w < 0.03 or h < 0.03:
        raise ValueError("Box is too small — draw around your full body")
    return NormBox(x=float(x), y=float(y), w=float(w), h=float(h)).clamp()


def box_is_valid(box: tuple[float, float, float, float], width: int, height: int) -> bool:
    x, y, w, h = box
    if w < MIN_BOX_SIDE_PX or h < MIN_BOX_SIDE_PX:
        return False
    if x + w < MIN_BOX_SIDE_PX or y + h < MIN_BOX_SIDE_PX:
        return False
    if x > width - MIN_BOX_SIDE_PX or y > height - MIN_BOX_SIDE_PX:
        return False
    area = max(w, 0) * max(h, 0)
    if area < MIN_BOX_AREA_FRAC * width * height:
        return False
    return True


class TemplateTracker:
    """NCC template tracker — used when OpenCV CSRT is unavailable."""

    def __init__(self) -> None:
        self.template: np.ndarray | None = None
        self.box: tuple[int, int, int, int] | None = None

    def init(self, frame: np.ndarray, bbox: tuple[int, int, int, int]) -> bool:
        x, y, w, h = [int(v) for v in bbox]
        crop = _crop(frame, x, y, w, h)
        if crop.size == 0:
            return False
        self.template = crop
        self.box = (x, y, w, h)
        return True

    def update(self, frame: np.ndarray) -> tuple[bool, tuple[float, float, float, float]]:
        if self.template is None or self.box is None:
            return False, (0.0, 0.0, 0.0, 0.0)
        x, y, w, h = self.box
        pad_x = int(w * SEARCH_PAD)
        pad_y = int(h * SEARCH_PAD)
        x0 = max(0, x - pad_x)
        y0 = max(0, y - pad_y)
        x1 = min(frame.shape[1], x + w + pad_x)
        y1 = min(frame.shape[0], y + h + pad_y)
        region = frame[y0:y1, x0:x1]
        if region.shape[0] < h or region.shape[1] < w:
            return False, (float(x), float(y), float(w), float(h))
        gray_r = _gray(region)
        gray_t = _gray(self.template)
        result = cv2.matchTemplate(gray_r, gray_t, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val < 0.35:
            return False, (float(x), float(y), float(w), float(h))
        nx = x0 + int(max_loc[0])
        ny = y0 + int(max_loc[1])
        self.box = (nx, ny, w, h)
        return True, (float(nx), float(ny), float(w), float(h))


def _gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _crop(frame: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(frame.shape[1], x + w)
    y1 = min(frame.shape[0], y + h)
    return frame[y0:y1, x0:x1]


def _csrt_tracker() -> TrackerLike | None:
    factory: Callable[[], TrackerLike] | None = None
    if hasattr(cv2, "TrackerCSRT_create"):
        factory = cv2.TrackerCSRT_create  # type: ignore[attr-defined]
    elif hasattr(cv2, "legacy") and hasattr(cv2.legacy, "TrackerCSRT_create"):
        factory = cv2.legacy.TrackerCSRT_create
    if factory is None:
        return None
    try:
        return factory()
    except Exception:
        return None


def create_tracker() -> TrackerLike:
    tracker = _csrt_tracker()
    return tracker if tracker is not None else TemplateTracker()


def tracker_init_ok(
    tracker: TrackerLike,
    frame: np.ndarray,
    bbox: tuple[int, int, int, int],
) -> bool:
    """OpenCV 4.5+/5 Tracker.init is void and returns None on success."""
    try:
        result = tracker.init(frame, bbox)
    except Exception:
        return False
    return result is not False


def create_initialized_tracker(
    frame: np.ndarray,
    bbox: tuple[int, int, int, int],
) -> TrackerLike:
    tracker = create_tracker()
    if tracker_init_ok(tracker, frame, bbox):
        return tracker
    fallback = TemplateTracker()
    if tracker_init_ok(fallback, frame, bbox):
        return fallback
    raise ValueError("Could not initialize tracker on the drawn box")


def padded_crop_xywh(
    box: tuple[float, float, float, float],
    width: int,
    height: int,
    pad_frac: float = POSE_CROP_PAD,
) -> tuple[int, int, int, int]:
    x, y, w, h = box
    px = w * pad_frac
    py = h * pad_frac
    x0 = max(0, int(x - px))
    y0 = max(0, int(y - py))
    x1 = min(width, int(x + w + px))
    y1 = min(height, int(y + h + py))
    return x0, y0, max(x1 - x0, 1), max(y1 - y0, 1)


def masked_player_crop(
    frame: np.ndarray,
    box: tuple[float, float, float, float],
    *,
    crop_pad: float = POSE_CROP_PAD,
    keep_pad: float = POSE_KEEP_PAD,
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Crop around the track box and black out pixels that belong to nearby players."""
    height, width = frame.shape[:2]
    cx, cy, cw, ch = padded_crop_xywh(box, width, height, crop_pad)
    crop = frame[cy : cy + ch, cx : cx + cw].copy()
    kx, ky, kw, kh = padded_crop_xywh(box, width, height, keep_pad)
    x0 = max(0, kx - cx)
    y0 = max(0, ky - cy)
    x1 = min(cw, kx + kw - cx)
    y1 = min(ch, ky + kh - cy)
    if x1 <= x0 or y1 <= y0:
        return crop, (cx, cy, cw, ch)
    masked = np.zeros_like(crop)
    masked[y0:y1, x0:x1] = crop[y0:y1, x0:x1]
    return masked, (cx, cy, cw, ch)


def box_jumped(
    prev: tuple[float, float, float, float],
    new: tuple[float, float, float, float],
    *,
    max_center_shift: float = MAX_CENTER_SHIFT_FRAC,
    max_scale: float = MAX_BOX_SCALE_CHANGE,
) -> bool:
    """True when the tracker likely hopped onto a different person."""
    px, py, pw, ph = prev
    nx, ny, nw, nh = new
    prev_diag = float(np.hypot(pw, ph)) or 1.0
    shift = float(np.hypot((nx + nw / 2) - (px + pw / 2), (ny + nh / 2) - (py + ph / 2)))
    if shift > max_center_shift * prev_diag:
        return True
    if pw > 0 and ph > 0:
        if nw > pw * max_scale or nh > ph * max_scale:
            return True
        if nw < pw / max_scale or nh < ph / max_scale:
            return True
    return False


def core_in_box_fraction(
    payload: dict,
    box: tuple[float, float, float, float],
    frame_wh: tuple[int, int],
    *,
    margin: float = 0.2,
    min_vis: float = 0.4,
) -> float:
    """Fraction of torso/head landmarks that fall inside the track box."""
    fw, fh = frame_wh
    x, y, w, h = box
    mx, my = w * margin, h * margin
    x0, y0, x1, y1 = x - mx, y - my, x + w + mx, y + h + my
    by_name = {p.get("name"): p for p in payload.get("landmarks") or []}
    considered = 0
    inside = 0
    for name in BOX_CORE_LANDMARKS:
        point = by_name.get(name)
        if point is None:
            continue
        if float(point.get("visibility") or 0.0) < min_vis:
            continue
        considered += 1
        px = float(point["x"]) * fw
        py = float(point["y"]) * fh
        if x0 <= px <= x1 and y0 <= py <= y1:
            inside += 1
    if considered == 0:
        return 0.0
    return inside / considered


def pick_pose_in_box(
    payloads: list[dict],
    box: tuple[float, float, float, float],
    frame_wh: tuple[int, int],
    *,
    min_frac: float = MIN_CORE_IN_BOX,
) -> dict | None:
    """Keep the pose whose torso sits in the drawn/tracked box; never a neighbor."""
    best: tuple[float, dict] | None = None
    for payload in payloads:
        score = core_in_box_fraction(payload, box, frame_wh)
        if best is None or score > best[0]:
            best = (score, payload)
    if best is None or best[0] < min_frac:
        return None
    return best[1]


def square_letterbox(image: np.ndarray) -> tuple[np.ndarray, tuple[int, int, int]]:
    """Pad a crop to a square so MediaPipe landmark projection stays aligned."""
    height, width = image.shape[:2]
    side = max(height, width, 1)
    canvas = np.zeros((side, side, image.shape[2]), dtype=image.dtype) if image.ndim == 3 else np.zeros((side, side), dtype=image.dtype)
    ox = (side - width) // 2
    oy = (side - height) // 2
    canvas[oy : oy + height, ox : ox + width] = image
    return canvas, (ox, oy, side)


def remap_landmarks_to_full_frame(
    payload: dict,
    crop_xywh: tuple[int, int, int, int],
    frame_wh: tuple[int, int],
    *,
    letterbox: tuple[int, int, int] | None = None,
) -> dict:
    cx, cy, cw, ch = crop_xywh
    fw, fh = frame_wh
    points = []
    for point in payload.get("landmarks") or []:
        mapped = dict(point)
        x = float(point["x"])
        y = float(point["y"])
        if letterbox is not None:
            ox, oy, side = letterbox
            x = (x * side - ox) / max(cw, 1)
            y = (y * side - oy) / max(ch, 1)
        mapped["x"] = (cx + x * cw) / fw
        mapped["y"] = (cy + y * ch) / fh
        points.append(mapped)
    vis = [float(p.get("visibility") or 0.0) for p in points]
    confidence = float(sum(vis) / len(vis)) if vis else 0.0
    return {
        **payload,
        "landmarks": points,
        "landmark_count": len(points),
        "confidence": confidence,
        "crop": {"x": cx, "y": cy, "w": cw, "h": ch},
    }


def should_skip_pose(consecutive_lost: int, *, lost_skip: int = LOST_SKIP_FRAMES) -> bool:
    return consecutive_lost >= lost_skip
