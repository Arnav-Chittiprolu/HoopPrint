from __future__ import annotations

import pytest

from app.services.features.drive import extract_drive_features
from app.services.features.extract import extract_clip_features
from app.services.features.geometry import (
    LandmarkLookup,
    angle_at,
    distance,
    parse_frames,
    standing_height_proxy,
    vector_elevation_deg,
)
from app.services.features.passing import extract_pass_features
from app.services.features.shot import extract_shot_features
from app.services.pose_landmarks import POSE_LANDMARK_NAMES


def _landmarks(**overrides: tuple[float, float]) -> dict:
    points = []
    for index, name in enumerate(POSE_LANDMARK_NAMES):
        x, y = overrides.get(name, (0.5, 0.5))
        points.append(
            {
                "index": index,
                "name": name,
                "x": x,
                "y": y,
                "z": 0.0,
                "visibility": 1.0,
            }
        )
    return {"landmarks": points, "landmark_count": 33, "confidence": 1.0}


def _standing(**arm: tuple[float, float]) -> dict:
    """Upright figure, y-down image coords (feet near 0.9, head near 0.2)."""
    base = {
        "nose": (0.50, 0.20),
        "left_shoulder": (0.44, 0.38),
        "right_shoulder": (0.56, 0.38),
        "left_hip": (0.46, 0.58),
        "right_hip": (0.54, 0.58),
        "left_knee": (0.46, 0.74),
        "right_knee": (0.54, 0.74),
        "left_ankle": (0.46, 0.90),
        "right_ankle": (0.54, 0.90),
        "left_elbow": (0.40, 0.48),
        "right_elbow": (0.60, 0.48),
        "left_wrist": (0.38, 0.58),
        "right_wrist": (0.62, 0.58),
    }
    base.update(arm)
    return _landmarks(**base)


def test_angle_at_right_angle():
    vertex = __import__("numpy").array([0.0, 0.0])
    arm_a = __import__("numpy").array([0.0, 1.0])
    arm_b = __import__("numpy").array([1.0, 0.0])
    assert angle_at(vertex, arm_a, arm_b) == pytest.approx(90.0, abs=1e-6)


def test_vector_elevation_straight_up():
    vec = __import__("numpy").array([0.0, 1.0])
    assert vector_elevation_deg(vec) == pytest.approx(90.0, abs=1e-6)


def test_standing_height_proxy_positive():
    lookup = LandmarkLookup(_standing())
    height = standing_height_proxy(lookup)
    assert height is not None
    assert height == pytest.approx(distance(lookup.xy("nose"), lookup.xy("left_ankle")) or 0, abs=0.05)


def test_shot_features_known_range():
    frames = []
    # Wrist rises (y-down decreases) toward a high release, then a little extra rise.
    wrist_ys = [0.55, 0.48, 0.40, 0.28, 0.22, 0.18]
    for index, wrist_y in enumerate(wrist_ys):
        frames.append(
            {
                "frame_index": index * 2,
                "keypoints": _standing(
                    right_elbow=(0.60, 0.42),
                    right_wrist=(0.62, wrist_y),
                    right_shoulder=(0.56, 0.38),
                ),
            }
        )

    parsed = parse_frames(frames)
    features = {row["feature_name"]: row for row in extract_shot_features(parsed, height_in=74.0)}

    assert 20.0 <= features["release_angle"]["value"] <= 160.0
    assert 20.0 <= features["elbow_angle_at_release"]["value"] <= 180.0
    assert 0.3 <= features["release_height_ratio"]["value"] <= 1.4
    assert features["shot_arc"]["value"] >= 0.0
    assert features["release_height_ratio"]["meta"]["approx_release_height_in"] == pytest.approx(
        74.0 * features["release_height_ratio"]["value"]
    )


def test_pass_features_extension_and_decision():
    frames = []
    # Hands together (catch), then right arm extends (release).
    poses = [
        {"right_elbow": (0.60, 0.48), "right_wrist": (0.52, 0.50), "left_wrist": (0.48, 0.50)},
        {"right_elbow": (0.60, 0.48), "right_wrist": (0.58, 0.48), "left_wrist": (0.46, 0.50)},
        {"right_elbow": (0.62, 0.46), "right_wrist": (0.78, 0.40), "left_wrist": (0.44, 0.50)},
    ]
    for index, arm in enumerate(poses):
        frames.append({"frame_index": index * 3, "keypoints": _standing(**arm)})

    parsed = parse_frames(frames)
    features = {row["feature_name"]: row for row in extract_pass_features(parsed)}

    assert features["arm_extension_at_release"]["value"] > 90.0
    assert features["release_point_consistency"]["value"] >= 0.0
    assert features["decision_speed"]["value"] >= 0.0


def test_drive_features_body_lengths():
    frames = []
    # Whole body translates right (drive), slight heading change at the end.
    xs = [0.40, 0.44, 0.50, 0.58, 0.66, 0.70, 0.71]
    for index, hip_x in enumerate(xs):
        frames.append(
            {
                "frame_index": index,
                "keypoints": _standing(
                    left_hip=(hip_x - 0.04, 0.58),
                    right_hip=(hip_x + 0.04, 0.58),
                    left_ankle=(hip_x - 0.04, 0.90),
                    right_ankle=(hip_x + 0.04, 0.90),
                    nose=(hip_x, 0.20),
                ),
            }
        )

    parsed = parse_frames(frames)
    features = {row["feature_name"]: row for row in extract_drive_features(parsed)}

    assert features["first_step_burst"]["value"] > 0.1
    assert features["change_of_direction_angle"]["value"] >= 0.0


def test_extract_clip_features_dispatches_shot():
    frames = [
        {"frame_index": 0, "keypoints": _standing(right_wrist=(0.62, 0.50))},
        {"frame_index": 2, "keypoints": _standing(right_wrist=(0.62, 0.22))},
    ]
    rows = extract_clip_features(frames, "shot")
    names = {row["feature_name"] for row in rows}
    assert names == {
        "release_angle",
        "elbow_angle_at_release",
        "release_height_ratio",
        "shot_arc",
    }


def test_extract_clip_features_rejects_unknown_type():
    frames = [{"frame_index": 0, "keypoints": _standing()}]
    with pytest.raises(ValueError, match="Unknown clip_type"):
        extract_clip_features(frames, "dunk")
