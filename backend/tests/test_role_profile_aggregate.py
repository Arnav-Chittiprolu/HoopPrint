"""Phase 10.3 aggregation, stability, and evidence-tier tests."""

from __future__ import annotations

import random
from datetime import date
from uuid import uuid4

from app.models.role_profile import (
    ClipEventRecord,
    EvidenceTier,
    RoleDimension,
    RoleDimensionStatus,
)
from app.services.role_profile.aggregate import (
    aggregate_role_profile,
    bootstrap_stability,
    dimension_status,
    event_latent_score,
    iqr,
    mad,
    median,
)
from app.services.role_profile.constants import BANNED_MECHANICS_KEYS, ROLE_VECTOR_KEYS
from app.services.role_profile.validate import assert_no_mechanics_keys, build_user_role_vector


def _event(
    dim: RoleDimension,
    *,
    raw: float,
    confidence: float = 0.8,
    session: date | None = None,
    passed: bool = True,
    extra: dict | None = None,
) -> ClipEventRecord:
    key = {
        RoleDimension.catch_readiness: "catch_to_release_s",
        RoleDimension.rim_pressure: "burst_body_lengths",
        RoleDimension.playmaking: "arm_extension_deg",
    }[dim]
    return ClipEventRecord(
        clip_id=uuid4(),
        user_id=uuid4(),
        role_dimension=dim,
        gate_passed=passed,
        signal_values={key: raw, **(extra or {})},
        event_confidence=confidence,
        session_date=session,
    )


def test_median_ignores_outlier():
    assert median([0.4, 0.42, 0.41, 9.0]) == 0.415


def test_iqr_and_mad():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert iqr(values) == 2.0
    assert mad(values, 3.0) == 1.0


def test_failed_events_are_excluded():
    user = uuid4()
    events = [
        ClipEventRecord(
            **{
                **_event(
                    RoleDimension.catch_readiness,
                    raw=0.4,
                    session=date(2026, 8, 1),
                ).model_dump(),
                "user_id": user,
            }
        ),
        ClipEventRecord(
            **{
                **_event(
                    RoleDimension.catch_readiness,
                    raw=0.45,
                    passed=False,
                    session=date(2026, 8, 1),
                ).model_dump(),
                "user_id": user,
            }
        ),
    ]
    profile = aggregate_role_profile(events, user_id=user, rng=random.Random(0), n_iter=50)
    assert profile.catch_readiness.event_count == 1
    assert profile.catch_readiness.status == RoleDimensionStatus.insufficient
    assert profile.role_vector.catch_readiness is None
    assert profile.evidence_tier == EvidenceTier.insufficient


def test_faster_catch_is_higher_latent():
    fast = _event(RoleDimension.catch_readiness, raw=0.35)
    slow = _event(RoleDimension.catch_readiness, raw=1.1)
    assert event_latent_score(fast) > event_latent_score(slow)  # type: ignore[operator]


def test_emerging_after_three_events():
    user = uuid4()
    events = [
        ClipEventRecord(
            **{
                **_event(
                    RoleDimension.catch_readiness,
                    raw=0.45,
                    session=date(2026, 8, 1),
                ).model_dump(),
                "user_id": user,
            }
        )
        for _ in range(3)
    ]
    profile = aggregate_role_profile(events, user_id=user, rng=random.Random(1), n_iter=80)
    assert profile.catch_readiness.status == RoleDimensionStatus.emerging
    assert profile.catch_readiness.event_count == 3
    assert profile.role_vector.catch_readiness is not None
    assert profile.evidence_tier == EvidenceTier.emerging
    assert RoleDimension.catch_readiness in profile.active_dimensions
    assert_no_mechanics_keys(profile.role_vector.model_dump(exclude_none=True))
    assert set(profile.role_vector.model_dump(exclude_none=True)) <= ROLE_VECTOR_KEYS


def test_low_confidence_suppresses_dimension():
    user = uuid4()
    events = [
        ClipEventRecord(
            **{
                **_event(
                    RoleDimension.rim_pressure,
                    raw=0.2,
                    confidence=0.4,
                    session=date(2026, 8, 1),
                ).model_dump(),
                "user_id": user,
            }
        )
        for _ in range(3)
    ]
    profile = aggregate_role_profile(events, user_id=user, rng=random.Random(2), n_iter=40)
    assert profile.rim_pressure.status == RoleDimensionStatus.suppressed_low_quality
    assert profile.role_vector.rim_pressure_tendency is None


def test_established_needs_five_events_two_sessions_and_stability():
    user = uuid4()
    events = []
    for i in range(5):
        events.append(
            ClipEventRecord(
                **{
                    **_event(
                        RoleDimension.catch_readiness,
                        raw=0.5,
                        confidence=0.82,
                        session=date(2026, 8, 1 + i % 2),
                    ).model_dump(),
                    "user_id": user,
                }
            )
        )
        events.append(
            ClipEventRecord(
                **{
                    **_event(
                        RoleDimension.rim_pressure,
                        raw=0.18,
                        confidence=0.82,
                        session=date(2026, 8, 1 + i % 2),
                    ).model_dump(),
                    "user_id": user,
                }
            )
        )
    profile = aggregate_role_profile(events, user_id=user, rng=random.Random(3), n_iter=120)
    assert profile.catch_readiness.status == RoleDimensionStatus.established
    assert profile.rim_pressure.status == RoleDimensionStatus.established
    assert profile.catch_readiness.session_count == 2
    assert profile.evidence_tier in {EvidenceTier.established, EvidenceTier.strong}
    dumped = profile.role_vector.model_dump(exclude_none=True)
    assert "catch_readiness" in dumped
    assert "rim_pressure_tendency" in dumped
    assert not (set(dumped) & BANNED_MECHANICS_KEYS)


def test_one_dimension_established_is_not_named_match_tier():
    user = uuid4()
    events = [
        ClipEventRecord(
            **{
                **_event(
                    RoleDimension.catch_readiness,
                    raw=0.48,
                    confidence=0.85,
                    session=date(2026, 8, 1 + i % 2),
                ).model_dump(),
                "user_id": user,
            }
        )
        for i in range(5)
    ]
    profile = aggregate_role_profile(events, user_id=user, rng=random.Random(4), n_iter=80)
    assert profile.catch_readiness.status == RoleDimensionStatus.established
    assert profile.evidence_tier == EvidenceTier.emerging
    assert profile.playmaking.status == RoleDimensionStatus.not_observed


def test_bootstrap_high_variance_is_not_stable():
    latents = [0.05, 0.95, 0.1, 0.9, 0.0, 1.0]
    result = bootstrap_stability(latents, n_iter=200, rng=random.Random(5))
    assert result["bootstrap_sd"] > 0.12
    assert result["stable"] is False


def test_dimension_status_thresholds():
    assert dimension_status(event_count=0, session_count=0, median_confidence=None, stable=False) == RoleDimensionStatus.not_observed
    assert dimension_status(event_count=2, session_count=1, median_confidence=0.9, stable=False) == RoleDimensionStatus.insufficient
    assert dimension_status(event_count=3, session_count=1, median_confidence=0.72, stable=False) == RoleDimensionStatus.emerging
    assert dimension_status(event_count=5, session_count=2, median_confidence=0.8, stable=True) == RoleDimensionStatus.established


def test_build_user_role_vector_from_aggregate_output():
    user = uuid4()
    events = [
        ClipEventRecord(
            **{
                **_event(RoleDimension.playmaking, raw=150.0, session=date(2026, 8, 1)).model_dump(),
                "user_id": user,
            }
        )
        for _ in range(3)
    ]
    profile = aggregate_role_profile(events, user_id=user, rng=random.Random(6), n_iter=40)
    vec = build_user_role_vector(profile.role_vector.model_dump())
    assert vec.playmaking_orientation is not None
    assert vec.catch_readiness is None
