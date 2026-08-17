from __future__ import annotations

import tempfile

import cv2
import numpy as np
import pytest

from app.services.pose_extraction import extract_first_frame_jpeg
from app.services.track import (
    NormBox,
    TemplateTracker,
    box_jumped,
    create_initialized_tracker,
    masked_player_crop,
    pick_pose_in_box,
    remap_landmarks_to_full_frame,
    should_skip_pose,
    square_letterbox,
    tracker_init_ok,
    validate_norm_box,
)


def test_validate_norm_box_accepts_in_frame():
    box = validate_norm_box(0.2, 0.1, 0.3, 0.5)
    assert 0 <= box.x < 1
    assert box.w > 0 and box.h > 0


def test_validate_norm_box_rejects_tiny_or_outside():
    with pytest.raises(ValueError):
        validate_norm_box(0.1, 0.1, 0.01, 0.5)
    with pytest.raises(ValueError):
        validate_norm_box(0.8, 0.8, 0.4, 0.4)


def test_remap_landmarks_to_full_frame():
    payload = {
        "landmarks": [
            {"index": 0, "name": "nose", "x": 0.5, "y": 0.5, "z": 0.0, "visibility": 1.0}
        ]
    }
    mapped = remap_landmarks_to_full_frame(payload, (100, 50, 200, 100), (400, 200))
    # crop origin 100,50 size 200x100; 0.5,0.5 in crop → 200,100 in pixels → 0.5, 0.5 full
    assert mapped["landmarks"][0]["x"] == pytest.approx(0.5)
    assert mapped["landmarks"][0]["y"] == pytest.approx(0.5)


def test_remap_landmarks_from_letterboxed_crop():
    crop = np.zeros((50, 100, 3), dtype=np.uint8)
    square, letterbox = square_letterbox(crop)
    assert square.shape[0] == square.shape[1] == 100
    payload = {
        "landmarks": [
            {"index": 0, "name": "nose", "x": 0.5, "y": 0.5, "z": 0.0, "visibility": 1.0}
        ]
    }
    mapped = remap_landmarks_to_full_frame(
        payload, (100, 50, 100, 50), (400, 200), letterbox=letterbox
    )
    # Square center is crop center → full-frame (150/400, 75/200)
    assert mapped["landmarks"][0]["x"] == pytest.approx(0.375)
    assert mapped["landmarks"][0]["y"] == pytest.approx(0.375)


def test_should_skip_pose_after_consecutive_losses():
    assert should_skip_pose(0) is False
    assert should_skip_pose(4) is False
    assert should_skip_pose(5) is True


class _VoidInitTracker:
    """Mimics OpenCV 5 CSRT: init() returns None, update() still works."""

    def __init__(self) -> None:
        self.box: tuple[int, int, int, int] | None = None

    def init(self, frame: np.ndarray, bbox: tuple[int, int, int, int]) -> None:
        self.box = bbox

    def update(self, frame: np.ndarray) -> tuple[bool, tuple[float, float, float, float]]:
        assert self.box is not None
        x, y, w, h = self.box
        return True, (float(x), float(y), float(w), float(h))


def test_tracker_init_ok_treats_none_as_success():
    frame = np.zeros((80, 80, 3), dtype=np.uint8)
    tracker = _VoidInitTracker()
    assert tracker_init_ok(tracker, frame, (10, 10, 20, 20)) is True


def test_create_initialized_tracker_accepts_opencv_void_init():
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    frame[40:80, 20:56] = (40, 180, 40)
    tracker = create_initialized_tracker(frame, (20, 40, 36, 40))
    ok, box = tracker.update(frame)
    assert ok
    assert box[2] > 0 and box[3] > 0


def test_template_tracker_follows_moving_square():
    frames = []
    for i in range(8):
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        x = 20 + i * 8
        patch = np.zeros((40, 36, 3), dtype=np.uint8)
        patch[:, 0:12] = (255, 255, 255)
        patch[:, 12:24] = (180, 40, 40)
        patch[:, 24:36] = (40, 180, 40)
        frame[40:80, x : x + 36] = patch
        frames.append(frame)

    tracker = TemplateTracker()
    assert tracker.init(frames[0], (20, 40, 36, 40))
    xs = []
    for frame in frames[1:]:
        ok, box = tracker.update(frame)
        assert ok
        xs.append(box[0])
    assert xs[-1] > xs[0]
    assert xs[-1] == pytest.approx(20 + 7 * 8, abs=4)


def test_extract_first_frame_jpeg():
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=True) as tmp:
        writer = cv2.VideoWriter(
            tmp.name,
            cv2.VideoWriter_fourcc(*"mp4v"),
            8.0,
            (80, 60),
        )
        frame = np.full((60, 80, 3), 40, dtype=np.uint8)
        frame[:] = (0, 0, 200)
        for _ in range(4):
            writer.write(frame)
        writer.release()
        tmp.flush()
        with open(tmp.name, "rb") as handle:
            video = handle.read()
    jpeg = extract_first_frame_jpeg(video)
    assert jpeg[:2] == b"\xff\xd8"
    decoded = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape[0] == 60
    assert decoded.shape[1] == 80


def test_norm_box_to_pixels():
    x, y, w, h = NormBox(0.25, 0.5, 0.5, 0.25).to_pixels(200, 100)
    assert (x, y, w, h) == (50, 50, 100, 25)


def _core_payload(cx: float, cy: float) -> dict:
    offsets = {
        "nose": (0.0, -0.18),
        "left_shoulder": (-0.04, -0.08),
        "right_shoulder": (0.04, -0.08),
        "left_hip": (-0.03, 0.08),
        "right_hip": (0.03, 0.08),
    }
    return {
        "landmarks": [
            {
                "index": i,
                "name": name,
                "x": cx + dx,
                "y": cy + dy,
                "z": 0.0,
                "visibility": 1.0,
            }
            for i, (name, (dx, dy)) in enumerate(offsets.items())
        ]
    }


def test_pick_pose_in_box_ignores_neighbor():
    box = (20.0, 20.0, 80.0, 160.0)
    frame_wh = (400, 200)
    boxed = _core_payload(0.15, 0.5)
    neighbor = _core_payload(0.75, 0.5)
    chosen = pick_pose_in_box([neighbor, boxed], box, frame_wh)
    assert chosen is boxed
    assert pick_pose_in_box([neighbor], box, frame_wh) is None


def test_box_jumped_detects_hop_to_other_person():
    prev = (20.0, 40.0, 40.0, 80.0)
    assert box_jumped(prev, (22.0, 42.0, 40.0, 80.0)) is False
    assert box_jumped(prev, (200.0, 40.0, 40.0, 80.0)) is True
    assert box_jumped(prev, (20.0, 40.0, 120.0, 200.0)) is True


def test_masked_player_crop_blacks_out_neighbor():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    frame[:, 0:80] = (0, 180, 40)
    frame[:, 120:200] = (0, 0, 255)
    crop, xywh = masked_player_crop(frame, (10.0, 10.0, 50.0, 80.0))
    assert crop.size > 0
    cx, cy, cw, ch = xywh
    assert cw > 0 and ch > 0
    # Right-side neighbor should not appear in the masked crop.
    assert not np.any(crop[:, :, 2] > 200)
