"""Phase 10.2 gate and event extraction tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.role_profile import RoleDimension
from app.services.features.geometry import parse_frames
from app.services.pose_job import FrameKeypoints
from app.services.pose_landmarks import POSE_LANDMARK_NAMES
from app.services.role_profile.extract_events import extract_clip_events
from app.services.role_profile.gates import (
    gate_catch_readiness,
    gate_pass_event,
    gate_rim_pressure,
)
from app.services.role_profile.quality import mean_track_confidence


def _landmarks(**overrides: tuple[float, float, float]) -> dict:
    points = []
    for index, name in enumerate(POSE_LANDMARK_NAMES):
        x, y, vis = overrides.get(name, (0.5, 0.5, 1.0))
        points.append(
            {
                "index": index,
                "name": name,
                "x": x,
                "y": y,
                "z": 0.0,
                "visibility": vis,
            }
        )
    return {"landmarks": points, "landmark_count": 33, "confidence": 1.0}


def _standing(**arm: tuple[float, ...]) -> dict:
    base: dict[str, tuple[float, ...]] = {
        "nose": (0.50, 0.20, 1.0),
        "left_shoulder": (0.44, 0.38, 1.0),
        "right_shoulder": (0.56, 0.38, 1.0),
        "left_hip": (0.46, 0.58, 1.0),
        "right_hip": (0.54, 0.58, 1.0),
        "left_knee": (0.46, 0.74, 1.0),
        "right_knee": (0.54, 0.74, 1.0),
        "left_ankle": (0.46, 0.90, 1.0),
        "right_ankle": (0.54, 0.90, 1.0),
        "left_elbow": (0.40, 0.48, 1.0),
        "right_elbow": (0.60, 0.48, 1.0),
        "left_wrist": (0.38, 0.58, 1.0),
        "right_wrist": (0.62, 0.58, 1.0),
    }
    for key, value in arm.items():
        if len(value) == 2:
            base[key] = (value[0], value[1], 1.0)
        else:
            base[key] = value
    return _landmarks(**base)


def _fk(frame_index: int, keypoints: dict, *, track: float = 0.95) -> FrameKeypoints:
    return FrameKeypoints(
        frame_index=frame_index,
        keypoints=keypoints,
        track_confidence=track,
    )


def _shot_catch_sequence() -> list[FrameKeypoints]:
    frames: list[FrameKeypoints] = []
    for fi in range(0, 6):
        frames.append(
            _fk(
                fi,
                _standing(
                    left_wrist=(0.40, 0.55),
                    right_wrist=(0.64, 0.55),
                ),
            )
        )
    for fi in range(6, 12):
        frames.append(
            _fk(
                fi,
                _standing(
                    left_wrist=(0.49, 0.50),
                    right_wrist=(0.51, 0.50),
                ),
            )
        )
    wrist_ys = [0.48, 0.40, 0.32, 0.24, 0.18, 0.14, 0.12]
    for offset, wy in enumerate(wrist_ys):
        fi = 12 + offset * 2
        frames.append(
            _fk(
                fi,
                _standing(
                    right_elbow=(0.60, 0.42),
                    right_wrist=(0.62, wy),
                    left_wrist=(0.48, 0.52),
                ),
            )
        )
    for fi in range(26, 32):
        frames.append(
            _fk(
                fi,
                _standing(
                    right_elbow=(0.60, 0.44),
                    right_wrist=(0.62, 0.14),
                    left_wrist=(0.48, 0.52),
                ),
            )
        )
    return frames


def test_gate_catch_readiness_valid():
    parsed = parse_frames(_shot_catch_sequence())
    result = gate_catch_readiness(parsed, dominant_hand="right", video_fps=30.0, mean_track_conf=0.9)
    assert result.gate_passed is True
    assert result.rejection_reason is None
    assert 0.3 <= result.signal_values["catch_to_release_s"] <= 1.2
    assert result.event_confidence is not None
    assert result.event_confidence >= 0.5
    assert result.signal_values.get("shot_origin") == "catch_and_shoot"


def test_gate_catch_readiness_missing_fps():
    parsed = parse_frames(_shot_catch_sequence())
    result = gate_catch_readiness(parsed, dominant_hand="right", video_fps=None, mean_track_conf=0.9)
    assert result.gate_passed is False
    assert result.rejection_reason == "missing_fps"


def test_gate_catch_readiness_low_track():
    parsed = parse_frames(_shot_catch_sequence())
    result = gate_catch_readiness(parsed, dominant_hand="right", video_fps=30.0, mean_track_conf=0.2)
    assert result.gate_passed is False
    assert result.rejection_reason == "low_track_confidence"


def test_gate_catch_readiness_low_visibility():
    low_vis = _standing(
        right_elbow=(0.60, 0.42, 0.05),
        right_wrist=(0.62, 0.18, 0.05),
        right_shoulder=(0.56, 0.38, 0.05),
    )
    frames = [_fk(i, low_vis) for i in range(8)]
    parsed = parse_frames(frames)
    result = gate_catch_readiness(parsed, dominant_hand="right", video_fps=30.0, mean_track_conf=0.9)
    assert result.gate_passed is False
    assert result.rejection_reason in {"low_pose_visibility", "no_release_frame", "insufficient_pre_post_window"}


def test_missing_fps_suppresses_time_based_catch_readiness():
    test_gate_catch_readiness_missing_fps()


def test_low_pose_visibility_suppresses_event():
    test_gate_catch_readiness_low_visibility()


def test_gate_rim_pressure_valid():
    frames: list[FrameKeypoints] = []
    xs = [0.40, 0.44, 0.50, 0.58, 0.66, 0.74, 0.80, 0.84]
    for index, hip_x in enumerate(xs):
        frames.append(
            _fk(
                index * 2,
                _standing(
                    left_hip=(hip_x - 0.04, 0.58),
                    right_hip=(hip_x + 0.04, 0.58),
                    left_ankle=(hip_x - 0.04, 0.90),
                    right_ankle=(hip_x + 0.04, 0.90),
                    nose=(hip_x, 0.20),
                ),
            )
        )
    parsed = parse_frames(frames)
    result = gate_rim_pressure(parsed, video_fps=30.0, mean_track_conf=0.9)
    assert result.gate_passed is True
    assert result.signal_values["burst_body_lengths"] >= 0.04
    assert result.burst_window_ms == 175


def test_gate_rim_pressure_insufficient_displacement():
    frames = [
        _fk(0, _standing()),
        _fk(2, _standing(left_hip=(0.461, 0.58), right_hip=(0.541, 0.58))),
    ]
    parsed = parse_frames(frames)
    result = gate_rim_pressure(parsed, video_fps=30.0, mean_track_conf=0.9)
    assert result.gate_passed is False
    assert result.rejection_reason in {
        "insufficient_hip_displacement",
        "insufficient_pre_post_window",
        "no_drive_onset",
    }


def test_gate_pass_event_valid():
    frames = []
    poses = [
        {"right_elbow": (0.60, 0.48), "right_wrist": (0.52, 0.50), "left_wrist": (0.48, 0.50)},
        {"right_elbow": (0.60, 0.48), "right_wrist": (0.58, 0.48), "left_wrist": (0.46, 0.50)},
        {"right_elbow": (0.62, 0.46), "right_wrist": (0.78, 0.40), "left_wrist": (0.44, 0.50)},
        {"right_elbow": (0.60, 0.48), "right_wrist": (0.58, 0.48), "left_wrist": (0.46, 0.50)},
    ]
    for index, arm in enumerate(poses):
        frames.append(_fk(index * 3, _standing(**arm)))
    frames.append(_fk(12, _standing(right_elbow=(0.60, 0.48), right_wrist=(0.58, 0.48))))
    frames.append(_fk(15, _standing(right_elbow=(0.60, 0.48), right_wrist=(0.58, 0.48))))
    parsed = parse_frames(frames)
    result = gate_pass_event(parsed, peak_list_index=2, dominant_hand="right", mean_track_conf=0.9, video_fps=30.0)
    assert result.gate_passed is True
    assert result.signal_values["arm_extension_deg"] > 100.0


def test_sparse_track_pass_is_rejected():
    frames = [
        _fk(0, _standing(right_elbow=(0.62, 0.46), right_wrist=(0.78, 0.40))),
        _fk(8, _standing(right_elbow=(0.62, 0.44), right_wrist=(0.80, 0.38))),
    ]
    events = extract_clip_events(
        frames,
        clip_id=uuid4(),
        user_id=uuid4(),
        clip_type="pass",
        video_fps=30.0,
    )
    assert len(events) == 1
    assert events[0].gate_passed is False
    assert events[0].rejection_reason == "sparse_track"


def test_extract_clip_events_shot():
    events = extract_clip_events(
        _shot_catch_sequence(),
        clip_id=uuid4(),
        user_id=uuid4(),
        clip_type="shot",
        video_fps=30.0,
    )
    assert len(events) == 1
    assert events[0].role_dimension == RoleDimension.catch_readiness
    assert events[0].gate_passed is True


def test_extract_clip_events_pass_multi_peak():
    frames = []
    for index, elbow_y in enumerate([0.48, 0.44, 0.48, 0.42, 0.48, 0.40]):
        frames.append(
            _fk(
                index * 4,
                _standing(
                    right_elbow=(0.60, elbow_y),
                    right_wrist=(0.62, elbow_y + 0.06),
                    left_wrist=(0.48, 0.50),
                ),
            )
        )
    events = extract_clip_events(
        frames,
        clip_id=uuid4(),
        user_id=uuid4(),
        clip_type="pass",
        video_fps=30.0,
    )
    assert len(events) >= 1
    assert all(e.role_dimension == RoleDimension.playmaking for e in events)


def test_extract_clip_events_drive():
    frames: list[FrameKeypoints] = []
    for index, hip_x in enumerate([0.40, 0.50, 0.62, 0.74, 0.86]):
        frames.append(
            _fk(
                index * 3,
                _standing(
                    left_hip=(hip_x - 0.04, 0.58),
                    right_hip=(hip_x + 0.04, 0.58),
                ),
            )
        )
    events = extract_clip_events(
        frames,
        clip_id=uuid4(),
        user_id=uuid4(),
        clip_type="drive",
        video_fps=30.0,
    )
    assert len(events) == 1
    assert events[0].role_dimension == RoleDimension.rim_pressure


def test_mean_track_confidence():
    frames = [_fk(0, _standing(), track=0.8), _fk(1, _standing(), track=1.0)]
    assert mean_track_confidence(frames) == pytest.approx(0.9)


def test_quick_catch_counts_as_catch_and_shoot():
    parsed = parse_frames(_shot_catch_sequence())
    result = gate_catch_readiness(
        parsed, dominant_hand="right", video_fps=240.0, mean_track_conf=0.9
    )
    assert result.gate_passed is True
    assert result.signal_values.get("shot_origin") == "catch_and_shoot"


def test_slow_gather_counts_as_pull_up():
    frames: list[FrameKeypoints] = []
    for fi in range(0, 6):
        frames.append(
            _fk(fi, _standing(left_wrist=(0.40, 0.55), right_wrist=(0.64, 0.55)))
        )
    for fi in range(6, 50):
        frames.append(
            _fk(fi, _standing(left_wrist=(0.49, 0.50), right_wrist=(0.51, 0.50)))
        )
    wrist_ys = [0.48, 0.40, 0.32, 0.24, 0.18, 0.14, 0.12]
    for offset, wy in enumerate(wrist_ys):
        fi = 50 + offset * 2
        frames.append(
            _fk(
                fi,
                _standing(
                    right_elbow=(0.60, 0.42),
                    right_wrist=(0.62, wy),
                    left_wrist=(0.48, 0.52),
                ),
            )
        )
    for fi in range(64, 70):
        frames.append(
            _fk(
                fi,
                _standing(
                    right_elbow=(0.60, 0.44),
                    right_wrist=(0.62, 0.14),
                    left_wrist=(0.48, 0.52),
                ),
            )
        )
    parsed = parse_frames(frames)
    result = gate_catch_readiness(
        parsed, dominant_hand="right", video_fps=30.0, mean_track_conf=0.9
    )
    assert result.gate_passed is True
    assert result.signal_values.get("shot_origin") == "pull_up"


def test_pull_up_without_catch_uses_hip_travel():
    frames: list[FrameKeypoints] = []
    for index, hip_x in enumerate([0.40, 0.46, 0.52, 0.58, 0.64, 0.70, 0.74]):
        wy = 0.55 - index * 0.05
        frames.append(
            _fk(
                index * 2,
                _standing(
                    left_hip=(hip_x - 0.04, 0.58),
                    right_hip=(hip_x + 0.04, 0.58),
                    left_wrist=(0.20, 0.55),
                    right_wrist=(0.80, wy),
                    right_elbow=(0.70, 0.38),
                    nose=(hip_x, 0.20),
                ),
            )
        )
    parsed = parse_frames(frames)
    result = gate_catch_readiness(
        parsed, dominant_hand="right", video_fps=30.0, mean_track_conf=0.9
    )
    assert result.gate_passed is True
    assert result.signal_values.get("shot_origin") == "pull_up"


def test_form_shot_without_catch_or_travel_is_rejected():
    frames = [
        _fk(
            i,
            _standing(
                left_wrist=(0.20, 0.55),
                right_wrist=(0.80, 0.20),
                right_elbow=(0.70, 0.38),
            ),
        )
        for i in range(16)
    ]
    parsed = parse_frames(frames)
    result = gate_catch_readiness(
        parsed, dominant_hand="right", video_fps=30.0, mean_track_conf=0.9
    )
    assert result.gate_passed is False
    assert result.rejection_reason == "form_shot"


def test_low_fps_suppresses_time_based_catch_readiness():
    parsed = parse_frames(_shot_catch_sequence())
    result = gate_catch_readiness(
        parsed, dominant_hand="right", video_fps=15.0, mean_track_conf=0.9
    )
    assert result.gate_passed is False
    assert result.rejection_reason == "missing_fps"


def test_pull_up_jumper_boxed_at_release_counts():
    """Tracking started at the apex: wrist already high, then they land."""
    frames: list[FrameKeypoints] = []
    for index in range(12):
        t = index / 11.0
        hip_y = 0.48 + t * 0.10
        wrist_y = 0.12 + t * 0.28
        frames.append(
            _fk(
                index,
                _standing(
                    left_hip=(0.46, hip_y),
                    right_hip=(0.54, hip_y),
                    left_wrist=(0.20, 0.55),
                    right_wrist=(0.80, wrist_y),
                    right_elbow=(0.70, 0.30 + t * 0.12),
                ),
            )
        )
    parsed = parse_frames(frames)
    result = gate_catch_readiness(
        parsed, dominant_hand="right", video_fps=30.0, mean_track_conf=0.9
    )
    assert result.gate_passed is True
    assert result.signal_values.get("shot_origin") == "pull_up"


def test_no_catch_proxy_suppresses_event():
    frames = [
        _fk(
            i,
            _standing(
                left_wrist=(0.20, 0.55),
                right_wrist=(0.80, 0.20),
                right_elbow=(0.70, 0.38),
            ),
        )
        for i in range(16)
    ]
    parsed = parse_frames(frames)
    result = gate_catch_readiness(
        parsed, dominant_hand="right", video_fps=30.0, mean_track_conf=0.9
    )
    assert result.gate_passed is False
    assert result.rejection_reason == "form_shot"
