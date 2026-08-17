from __future__ import annotations

import logging
import os
import ssl
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import certifi
import cv2
import numpy as np
from mediapipe.tasks.python.core import base_options as base_options_module
from mediapipe.tasks.python.vision import pose_landmarker
from mediapipe.tasks.python.vision.core import image as image_module

from app.services.pose_landmarks import POSE_LANDMARK_NAMES
from app.services.pose_quality import is_plausible_person
from app.services.track import (
    LOST_SKIP_FRAMES,
    NormBox,
    box_is_valid,
    box_jumped,
    create_initialized_tracker,
    masked_player_crop,
    pick_pose_in_box,
    remap_landmarks_to_full_frame,
    should_skip_pose,
    square_letterbox,
)

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
MODELS_DIR = BACKEND_DIR / "models"
MODEL_PATH = MODELS_DIR / "pose_landmarker_lite.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)
FRAME_STEP = 2
# 4K gameplay frames are ~25MB each; work at 640px so 8GB machines survive.
WORK_MAX_SIDE = 640
POSE_INPUT_MAX_SIDE = 256


def scale_to_max_side(frame: np.ndarray, max_side: int = WORK_MAX_SIDE) -> np.ndarray:
    """Downscale so the long edge is at most max_side. Normalized coords stay valid."""
    height, width = frame.shape[:2]
    longest = max(height, width)
    if longest <= max_side:
        return frame
    scale = max_side / float(longest)
    new_w = max(2, int(round(width * scale)) & ~1)
    new_h = max(2, int(round(height * scale)) & ~1)
    return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _pose_image(frame_bgr: np.ndarray) -> np.ndarray:
    """BGR frame → RGB, capped for MediaPipe."""
    small = scale_to_max_side(frame_bgr, POSE_INPUT_MAX_SIDE)
    frame_rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    if not frame_rgb.flags["C_CONTIGUOUS"]:
        frame_rgb = np.ascontiguousarray(frame_rgb)
    return frame_rgb


@dataclass(frozen=True)
class FrameKeypoints:
    frame_index: int
    keypoints: dict
    track_confidence: float


def ensure_pose_model() -> Path:
    if MODEL_PATH.is_file():
        return MODEL_PATH

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = MODEL_PATH.with_suffix(".task.download")
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(MODEL_URL, context=ssl_context, timeout=120) as response:
        tmp_path.write_bytes(response.read())
    tmp_path.replace(MODEL_PATH)
    return MODEL_PATH


def _landmarks_to_dict(landmarks) -> dict:
    points = []
    for index, landmark in enumerate(landmarks):
        points.append(
            {
                "index": index,
                "name": POSE_LANDMARK_NAMES[index]
                if index < len(POSE_LANDMARK_NAMES)
                else f"landmark_{index}",
                "x": float(landmark.x),
                "y": float(landmark.y),
                "z": float(landmark.z),
                "visibility": float(getattr(landmark, "visibility", 0.0) or 0.0),
            }
        )
    visibilities = [point["visibility"] for point in points]
    confidence = float(sum(visibilities) / len(visibilities)) if visibilities else 0.0
    return {"landmarks": points, "landmark_count": len(points), "confidence": confidence}


def _create_landmarker(*, num_poses: int = 1) -> pose_landmarker.PoseLandmarker:
    os.environ.setdefault("MEDIAPIPE_DISABLE_GPU", "1")
    model_path = ensure_pose_model()
    options = pose_landmarker.PoseLandmarkerOptions(
        base_options=base_options_module.BaseOptions(
            model_asset_path=str(model_path),
            delegate=base_options_module.BaseOptions.Delegate.CPU,
        ),
        output_segmentation_masks=False,
        num_poses=num_poses,
    )
    return pose_landmarker.PoseLandmarker.create_from_options(options)


def extract_pose_keypoints(
    video_bytes: bytes,
    *,
    frame_step: int = FRAME_STEP,
    suffix: str = ".mp4",
) -> list[FrameKeypoints]:
    """Sample every Nth frame and run MediaPipe Pose on the full frame."""
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(video_bytes)
            tmp.flush()
            tmp_path = tmp.name
        return extract_pose_keypoints_from_path(tmp_path, frame_step=frame_step)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def extract_pose_keypoints_from_path(
    video_path: str,
    *,
    frame_step: int = FRAME_STEP,
) -> list[FrameKeypoints]:
    """Sample every Nth frame from an on-disk video (no extra RAM copy)."""
    if frame_step < 1:
        raise ValueError("frame_step must be >= 1")

    results: list[FrameKeypoints] = []
    landmarker = _create_landmarker()
    frame_index = 0

    try:
        capture = cv2.VideoCapture(video_path)
        if not capture.isOpened():
            raise ValueError("Could not open video for pose extraction")

        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        logger.info(
            "Pose extraction started (frames=%s, step=%s)",
            total_frames or "unknown",
            frame_step,
        )

        try:
            while True:
                ok, frame_bgr = capture.read()
                if not ok:
                    break

                if frame_index % frame_step == 0:
                    frame_bgr = scale_to_max_side(frame_bgr)
                    mp_image = image_module.Image(
                        image_format=image_module.ImageFormat.SRGB,
                        data=_pose_image(frame_bgr),
                    )
                    detection = landmarker.detect(mp_image)
                    if detection.pose_landmarks:
                        payload = _landmarks_to_dict(detection.pose_landmarks[0])
                        if is_plausible_person(payload):
                            results.append(
                                FrameKeypoints(
                                    frame_index=frame_index,
                                    keypoints=payload,
                                    track_confidence=payload["confidence"],
                                )
                            )

                    if frame_index > 0 and frame_index % (frame_step * 15) == 0:
                        logger.info(
                            "Pose extraction progress: frame %s/%s (%s poses)",
                            frame_index,
                            total_frames or "?",
                            len(results),
                        )

                frame_index += 1
        finally:
            capture.release()
    finally:
        landmarker.close()

    logger.info("Pose extraction finished: %s pose frames from %s video frames", len(results), frame_index)
    return results


def extract_first_frame_jpeg(video_bytes: bytes, *, suffix: str = ".mp4", quality: int = 85) -> bytes:
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(video_bytes)
            tmp.flush()
            tmp_path = tmp.name
        capture = cv2.VideoCapture(tmp_path)
        if not capture.isOpened():
            raise ValueError("Could not open video for first frame")
        try:
            ok, frame = capture.read()
        finally:
            capture.release()
        if not ok or frame is None:
            raise ValueError("Could not read the first video frame")
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not ok:
            raise ValueError("Could not encode first frame as JPEG")
        return encoded.tobytes()
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def extract_pose_keypoints_tracked(
    video_bytes: bytes,
    bbox: NormBox,
    *,
    frame_step: int = FRAME_STEP,
    suffix: str = ".mp4",
    lost_skip: int = LOST_SKIP_FRAMES,
) -> list[FrameKeypoints]:
    """Track one bbox with CSRT (or template fallback), pose only on that crop."""
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(video_bytes)
            tmp.flush()
            tmp_path = tmp.name
        return extract_pose_keypoints_tracked_from_path(
            tmp_path,
            bbox,
            frame_step=frame_step,
            lost_skip=lost_skip,
        )
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def extract_pose_keypoints_tracked_from_path(
    video_path: str,
    bbox: NormBox,
    *,
    frame_step: int = FRAME_STEP,
    lost_skip: int = LOST_SKIP_FRAMES,
) -> list[FrameKeypoints]:
    """Track one bbox from an on-disk video (no extra RAM copy)."""
    if frame_step < 1:
        raise ValueError("frame_step must be >= 1")

    results: list[FrameKeypoints] = []
    landmarker = _create_landmarker(num_poses=3)
    frame_index = 0
    consecutive_lost = 0

    try:
        capture = cv2.VideoCapture(video_path)
        if not capture.isOpened():
            raise ValueError("Could not open video for tracked pose extraction")

        ok, first = capture.read()
        if not ok or first is None:
            raise ValueError("Could not read the first video frame")
        first = scale_to_max_side(first)

        height, width = first.shape[:2]
        pixel_box = bbox.to_pixels(width, height)
        tracker = create_initialized_tracker(first, pixel_box)
        logger.info("Gameplay tracker ready: %s box=%s", type(tracker).__name__, pixel_box)
        current_box: tuple[float, float, float, float] = tuple(float(v) for v in pixel_box)

        def _maybe_pose(frame_bgr: np.ndarray, box: tuple[float, float, float, float], index: int) -> None:
            if index % frame_step != 0:
                return
            if should_skip_pose(consecutive_lost, lost_skip=lost_skip):
                return
            if not box_is_valid(box, width, height):
                return
            crop, crop_xywh = masked_player_crop(frame_bgr, box)
            if crop.size == 0:
                return
            square, letterbox = square_letterbox(crop)
            mp_image = image_module.Image(
                image_format=image_module.ImageFormat.SRGB,
                data=_pose_image(square),
            )
            detection = landmarker.detect(mp_image)
            if not detection.pose_landmarks:
                return
            mapped: list[dict] = []
            for pose in detection.pose_landmarks:
                crop_payload = _landmarks_to_dict(pose)
                if not is_plausible_person(crop_payload):
                    continue
                mapped.append(
                    remap_landmarks_to_full_frame(
                        crop_payload,
                        crop_xywh,
                        (width, height),
                        letterbox=letterbox,
                    )
                )
            chosen = pick_pose_in_box(mapped, box, (width, height))
            if chosen is None:
                return
            results.append(
                FrameKeypoints(
                    frame_index=index,
                    keypoints=chosen,
                    track_confidence=chosen["confidence"],
                )
            )

        try:
            _maybe_pose(first, current_box, 0)
            frame_index = 1
            while True:
                ok, frame_bgr = capture.read()
                if not ok:
                    break
                frame_bgr = scale_to_max_side(frame_bgr)
                tracked_ok, new_box = False, current_box
                try:
                    tracked_ok, new_box = tracker.update(frame_bgr)
                except Exception:
                    tracked_ok = False
                if (
                    tracked_ok
                    and box_is_valid(new_box, width, height)
                    and not box_jumped(current_box, new_box)
                ):
                    consecutive_lost = 0
                    current_box = new_box
                else:
                    consecutive_lost += 1
                    if consecutive_lost == lost_skip:
                        logger.warning(
                            "tracker_lost",
                            extra={
                                "event": "tracker_lost",
                                "frame_index": frame_index,
                                "reason": "box lost for consecutive frames; skipping pose",
                            },
                        )
                _maybe_pose(frame_bgr, current_box, frame_index)
                if frame_index % 60 == 0:
                    logger.info(
                        "Tracked pose progress: frame %s (%s poses)",
                        frame_index,
                        len(results),
                    )
                frame_index += 1
        finally:
            capture.release()
    finally:
        landmarker.close()

    logger.info(
        "Tracked pose finished: %s pose frames from %s video frames",
        len(results),
        frame_index,
    )
    return results
