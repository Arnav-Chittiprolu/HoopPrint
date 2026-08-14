from __future__ import annotations

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

BACKEND_DIR = Path(__file__).resolve().parents[2]
MODELS_DIR = BACKEND_DIR / "models"
MODEL_PATH = MODELS_DIR / "pose_landmarker_lite.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)
FRAME_STEP = 2


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
    visibilities = [point["visibility"] for point in points if point["visibility"] > 0]
    confidence = float(sum(visibilities) / len(visibilities)) if visibilities else 0.0
    return {"landmarks": points, "landmark_count": len(points), "confidence": confidence}


def _create_landmarker() -> pose_landmarker.PoseLandmarker:
    model_path = ensure_pose_model()
    options = pose_landmarker.PoseLandmarkerOptions(
        base_options=base_options_module.BaseOptions(model_asset_path=str(model_path)),
        output_segmentation_masks=False,
        num_poses=1,
    )
    return pose_landmarker.PoseLandmarker.create_from_options(options)


def extract_pose_keypoints(
    video_bytes: bytes,
    *,
    frame_step: int = FRAME_STEP,
    suffix: str = ".mp4",
) -> list[FrameKeypoints]:
    """Sample every Nth frame and run MediaPipe Pose on the full frame."""
    if frame_step < 1:
        raise ValueError("frame_step must be >= 1")

    results: list[FrameKeypoints] = []
    landmarker = _create_landmarker()

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(video_bytes)
        tmp.flush()

        capture = cv2.VideoCapture(tmp.name)
        if not capture.isOpened():
            raise ValueError("Could not open video for pose extraction")

        frame_index = 0
        try:
            while True:
                ok, frame_bgr = capture.read()
                if not ok:
                    break

                if frame_index % frame_step == 0:
                    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    if not frame_rgb.flags["C_CONTIGUOUS"]:
                        frame_rgb = np.ascontiguousarray(frame_rgb)

                    mp_image = image_module.Image(
                        image_format=image_module.ImageFormat.SRGB,
                        data=frame_rgb,
                    )
                    detection = landmarker.detect(mp_image)
                    if detection.pose_landmarks:
                        payload = _landmarks_to_dict(detection.pose_landmarks[0])
                        results.append(
                            FrameKeypoints(
                                frame_index=frame_index,
                                keypoints=payload,
                                track_confidence=payload["confidence"],
                            )
                        )

                frame_index += 1
        finally:
            capture.release()
            landmarker.close()

    return results
