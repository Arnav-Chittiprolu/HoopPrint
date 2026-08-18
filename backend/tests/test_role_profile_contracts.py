"""Phase 10.1 data contract tests."""

from datetime import date
from uuid import uuid4

import pytest

from app.models.role_profile import (
    ClipEventRecord,
    RoleDimension,
    RoleDimensionState,
    RoleDimensionStatus,
    UserRoleProfileRecord,
    UserRoleVector,
    validate_role_vector_payload,
)
from app.services.role_profile.constants import BANNED_MECHANICS_KEYS, ROLE_PROFILE_VERSION
from app.services.role_profile.db import clip_event_to_row, user_role_profile_from_row, user_role_profile_to_row
from app.services.role_profile.validate import assert_no_mechanics_keys, build_user_role_vector


def test_validate_role_vector_rejects_mechanics_keys():
    with pytest.raises(ValueError, match="Mechanics keys"):
        validate_role_vector_payload({"release_angle": 0.5, "catch_readiness": 0.3})
    with pytest.raises(ValueError, match="Mechanics keys"):
        validate_role_vector_payload({"shot_arc": 0.1})


def test_validate_role_vector_rejects_unknown_keys():
    with pytest.raises(ValueError, match="Unknown role vector"):
        validate_role_vector_payload({"catch_readiness": 0.3, "perimeter_vs_rim": 0.8})


def test_build_user_role_vector_accepts_valid_keys():
    vec = build_user_role_vector(
        {
            "catch_readiness": 0.42,
            "rim_pressure_tendency": 0.55,
            "playmaking_orientation": None,
        }
    )
    assert vec.catch_readiness == 0.42
    assert vec.rim_pressure_tendency == 0.55
    assert vec.playmaking_orientation is None


def test_banned_mechanics_keys_cover_legacy_style_slots():
    assert "release_angle" in BANNED_MECHANICS_KEYS
    assert "shot_arc" in BANNED_MECHANICS_KEYS
    assert "first_step_burst" in BANNED_MECHANICS_KEYS


def test_assert_no_mechanics_keys():
    assert_no_mechanics_keys({"catch_readiness": 0.5})
    with pytest.raises(ValueError):
        assert_no_mechanics_keys({"elbow_angle_at_release": 90.0})


def test_clip_event_to_row():
    clip_id = uuid4()
    user_id = uuid4()
    event = ClipEventRecord(
        clip_id=clip_id,
        user_id=user_id,
        role_dimension=RoleDimension.rim_pressure,
        event_index=0,
        gate_passed=True,
        signal_values={"burst_body_lengths": 1.2},
        quality={"track_confidence": 0.88},
        fps=30.0,
        burst_window_ms=175,
        event_confidence=0.82,
        session_date=date(2026, 8, 17),
    )
    row = clip_event_to_row(event)
    assert row["clip_id"] == str(clip_id)
    assert row["role_dimension"] == "rim_pressure"
    assert row["gate_passed"] is True
    assert row["burst_window_ms"] == 175
    assert row["session_date"] == "2026-08-17"


def test_user_role_profile_round_trip():
    user_id = uuid4()
    profile = UserRoleProfileRecord(
        user_id=user_id,
        profile_version=ROLE_PROFILE_VERSION,
        catch_readiness=RoleDimensionState(
            value=0.38,
            event_count=4,
            session_count=2,
            confidence=0.74,
            status=RoleDimensionStatus.emerging,
        ),
        role_vector=UserRoleVector(catch_readiness=0.38),
        active_dimensions=[RoleDimension.catch_readiness],
    )
    row = user_role_profile_to_row(profile)
    assert row["profile_version"] == ROLE_PROFILE_VERSION
    assert row["catch_readiness_event_count"] == 4
    assert row["catch_readiness_status"] == "emerging"
    assert row["role_vector"] == {"catch_readiness": 0.38}

    row["id"] = uuid4()
    parsed = user_role_profile_from_row(row)
    assert parsed.user_id == user_id
    assert parsed.catch_readiness.event_count == 4
    assert parsed.role_vector.catch_readiness == 0.38
