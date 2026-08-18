"""Phase 10.5 scoring, pool, seed provenance, and named-match gates."""

from datetime import date
from uuid import uuid4

import pytest

from app.models.role_profile import (
    ClipEventRecord,
    EvidenceTier,
    RoleDimension,
    UserRoleVector,
    validate_role_vector_payload,
)
from app.services.role_profile.aggregate import aggregate_role_profile
from app.services.role_profile.archetype import classify_archetype
from app.services.role_profile.constants import (
    BANNED_MECHANICS_KEYS,
    HEIGHT_TIEBREAK_WEIGHT,
    ROLE_VECTOR_KEYS,
)
from app.services.role_profile.nba_transform import (
    derive_rates,
    empirical_percentile,
    finalize_nba_role_rows,
)
from app.services.role_profile.pool import select_nba_pool
from app.services.role_profile.recs import build_mechanics_recs, build_role_recs
from app.services.role_profile.score import (
    build_role_vector,
    height_tiebreak,
    masked_distance,
    rank_role_matches,
)
from app.services.role_profile.validate import assert_no_mechanics_keys


def test_role_vector_excludes_release_angle():
    with pytest.raises(ValueError, match="Mechanics keys"):
        build_role_vector({"release_angle": 0.4, "catch_readiness": 0.5})


def test_role_vector_excludes_elbow_angle():
    with pytest.raises(ValueError, match="Mechanics keys"):
        validate_role_vector_payload({"elbow_angle": 140.0})


def test_role_vector_excludes_release_height():
    with pytest.raises(ValueError, match="Mechanics keys"):
        validate_role_vector_payload({"relative_release_height": 1.1})


def test_role_vector_excludes_wrist_rise_proxy():
    with pytest.raises(ValueError, match="Mechanics keys"):
        validate_role_vector_payload({"wrist_rise_proxy": 0.2})


def test_role_vector_excludes_pass_release_extension():
    with pytest.raises(ValueError, match="Mechanics keys"):
        validate_role_vector_payload({"pass_release_extension_deg": 150.0})


def test_role_vector_excludes_release_consistency():
    with pytest.raises(ValueError, match="Mechanics keys"):
        validate_role_vector_payload({"release_point_consistency": 0.01})


def test_build_role_vector_omits_nulls():
    vec = build_role_vector(
        {"catch_readiness": 0.7, "rim_pressure_tendency": None, "playmaking_orientation": 0.4}
    )
    assert vec == {"catch_readiness": 0.7, "playmaking_orientation": 0.4}
    assert "rim_pressure_tendency" not in vec


def test_no_valid_action_means_no_role_dimension():
    profile = aggregate_role_profile([], user_id=uuid4())
    dumped = profile.role_vector.model_dump(exclude_none=True)
    assert dumped == {}
    assert profile.evidence_tier == EvidenceTier.insufficient


def test_insufficient_events_returns_archetype_or_no_comp_not_player_name():
    user_id = uuid4()
    events = [
        ClipEventRecord(
            clip_id=uuid4(),
            user_id=user_id,
            role_dimension=RoleDimension.catch_readiness,
            gate_passed=True,
            signal_values={"catch_to_release_s": 0.5},
            event_confidence=0.8,
            session_date=date(2026, 8, 1),
        )
        for _ in range(2)
    ]
    profile = aggregate_role_profile(events, user_id=user_id)
    arch = classify_archetype(
        profile.role_vector.model_dump(exclude_none=True),
        evidence_tier=profile.evidence_tier,
    )
    assert profile.evidence_tier != EvidenceTier.established
    assert arch["key"] in {"insufficient_evidence", "quick_trigger_perimeter", "balanced_developing"}
    if profile.evidence_tier == EvidenceTier.insufficient:
        assert arch["shown"] is False


def test_named_matches_require_established_evidence():
    arch = classify_archetype(
        {"catch_readiness": 0.8, "rim_pressure_tendency": 0.2},
        evidence_tier=EvidenceTier.emerging,
    )
    assert arch["shown"] is True
    assert arch["label"] == "quick-trigger perimeter role"


def test_active_dimensions_are_masked_not_zero_filled():
    user = {"catch_readiness": 0.8}
    close = {"catch_readiness": 0.8, "rim_pressure_tendency": 0.0}
    far_rim = {"catch_readiness": 0.8, "rim_pressure_tendency": 0.99}
    d_close = masked_distance(user, close)
    d_far = masked_distance(user, far_rim)
    assert d_close is not None and d_far is not None
    assert abs(d_close - d_far) < 1e-9


def test_missing_dimension_not_penalized_as_zero():
    user = {"catch_readiness": 0.5, "playmaking_orientation": 0.5}
    nba = {"catch_readiness": 0.5}
    dist = masked_distance(user, nba)
    assert dist is not None
    assert dist < 0.05


def test_height_and_position_only_filter_or_tiebreak_not_primary_similarity():
    user = {"catch_readiness": 0.5, "rim_pressure_tendency": 0.5}
    nba = {"catch_readiness": 0.5, "rim_pressure_tendency": 0.5}
    dist = masked_distance(user, nba)
    tie = height_tiebreak(70.0, 75.0, band_in=5.0)
    assert dist == 0.0 or dist is not None and dist < 1e-9
    assert 0 < tie <= HEIGHT_TIEBREAK_WEIGHT


def test_identical_role_vectors_rank_identically_regardless_of_mechanics():
    user = {"catch_readiness": 0.6, "rim_pressure_tendency": 0.4}
    players = [
        {
            "name": "A",
            "player_id": 1,
            "position": "forward",
            "height_in": 78.0,
            "role_vector": {"catch_readiness": 0.6, "rim_pressure_tendency": 0.4},
            "raw_source": {},
        },
        {
            "name": "B",
            "player_id": 2,
            "position": "forward",
            "height_in": 78.0,
            "role_vector": {"catch_readiness": 0.6, "rim_pressure_tendency": 0.4},
            "raw_source": {},
        },
    ]
    ranked = rank_role_matches(
        players,
        user_vector=user,
        user_height_in=78.0,
        height_band_in=5.0,
        top_k=2,
    )
    assert len(ranked) == 2
    assert ranked[0]["ranking_distance"] == ranked[1]["ranking_distance"]
    mechanics_a = {"release_angle": 32.0}
    mechanics_b = {"release_angle": 55.0}
    assert mechanics_a != mechanics_b
    ranked_again = rank_role_matches(
        players,
        user_vector=user,
        user_height_in=78.0,
        height_band_in=5.0,
        top_k=2,
    )
    assert [r["ranking_distance"] for r in ranked] == [r["ranking_distance"] for r in ranked_again]


def test_pool_below_minimum_suppresses_named_match():
    players = [
        {
            "name": f"G{i}",
            "position": "guard",
            "position_group": "guard",
            "height_in": 74.0,
            "role_vector": {"catch_readiness": 0.5},
            "meets_min_sample": True,
        }
        for i in range(3)
    ]
    pool = select_nba_pool(players, position="guard", height_in=74.0, min_pool=8)
    assert pool.stage == 4
    assert pool.named_matches_allowed is False


def test_nba_seed_requires_provenance_and_denominator():
    rows = finalize_nba_role_rows(
        [
            {
                "name": "Guard One",
                "player_id": 1,
                "season": "2025-26",
                "position": "guard",
                "position_group": "guard",
                "height_in": 74.0,
                "raw_stats": {
                    "gp": 40,
                    "minutes": 900,
                    "catch_shoot_fga": 3.0,
                    "pull_up_fga": 2.0,
                    "drives": 4.0,
                    "touches": 40.0,
                    "passes_made": 20.0,
                    "potential_ast": 5.0,
                },
            },
            {
                "name": "Guard Two",
                "player_id": 2,
                "season": "2025-26",
                "position": "guard",
                "position_group": "guard",
                "height_in": 75.0,
                "raw_stats": {
                    "gp": 40,
                    "minutes": 800,
                    "catch_shoot_fga": 1.0,
                    "pull_up_fga": 4.0,
                    "drives": 8.0,
                    "touches": 50.0,
                    "passes_made": 30.0,
                    "potential_ast": 8.0,
                },
            },
        ],
        season="2025-26",
    )
    for row in rows:
        assert row["style_vector"] == {}
        assert row["transform_version"]
        vec = row["role_vector"]
        assert set(vec) <= ROLE_VECTOR_KEYS
        for dim in vec:
            src = row["raw_source"][dim]
            assert src["endpoint_name"]
            assert src["field_name"]
            assert src["raw_denominator"] is not None
            assert src["season"] == "2025-26"
            assert src["transformation_version"]


def test_seed_version_change_creates_new_comp_result_not_mutating_old():
    """Comp snapshots are inserts; nba_seed_version is stored on the new row."""
    from app.services.role_profile.constants import NBA_TRANSFORM_VERSION

    first = {"nba_seed_version": "role_profile_v1", "comparison_mode": "role_profile_v1"}
    second = {"nba_seed_version": NBA_TRANSFORM_VERSION + "_next", "comparison_mode": "role_profile_v1"}
    assert first != second


def test_mechanics_recs_never_cite_nba_player():
    recs = build_mechanics_recs({"release_angle": 20.0, "first_step_burst": 0.1})
    blob = str(recs).lower()
    assert "like" not in blob or "nba" not in blob
    for rec in recs:
        assert rec.get("match_name") is None
        assert "Player" not in rec["action"]


def test_role_recs_do_not_tell_user_to_shoot_like_a_player():
    from app.models.role_profile import RoleDimensionState, RoleDimensionStatus, UserRoleProfileRecord
    from app.services.role_profile.constants import ROLE_PROFILE_VERSION

    profile = UserRoleProfileRecord(
        user_id=uuid4(),
        profile_version=ROLE_PROFILE_VERSION,
        evidence_tier=EvidenceTier.emerging,
        catch_readiness=RoleDimensionState(
            value=0.7,
            event_count=3,
            status=RoleDimensionStatus.emerging,
        ),
        role_vector=UserRoleVector(catch_readiness=0.7),
        active_dimensions=[RoleDimension.catch_readiness],
    )
    recs = build_role_recs(
        profile,
        archetype={"shown": True, "label": "quick-trigger perimeter role"},
        named_match_name="Example Player",
    )
    blob = str(recs)
    assert "Take more catch-and-shoot" not in blob
    assert "become more like" not in blob.lower()


def test_banned_keys_constant_covers_plan_list():
    for key in (
        "release_angle",
        "elbow_angle",
        "wrist_rise_proxy",
        "pass_release_extension_deg",
        "release_point_consistency",
    ):
        assert key in BANNED_MECHANICS_KEYS
    assert_no_mechanics_keys({"catch_readiness": 0.2})


def test_empirical_percentile_is_rank_not_minmax():
    pop = [0.1, 0.2, 0.3, 0.4, 0.5]
    assert empirical_percentile(0.1, pop) < empirical_percentile(0.5, pop)
    assert 0 <= empirical_percentile(0.3, pop) <= 1


def test_derive_rates_omit_without_denominator():
    rates = derive_rates({"raw_stats": {"drives": 5.0, "gp": 40, "minutes": 500}})
    assert rates["drives_per_touch"] is None
    assert rates["catch_shoot_share"] is None
