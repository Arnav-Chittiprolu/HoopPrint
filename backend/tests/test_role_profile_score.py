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
    RANK_BODY_WEIGHT,
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
    body_plausibility,
    build_role_vector,
    classify_comp_bucket,
    height_tiebreak,
    masked_distance,
    rank_role_matches,
    split_role_matches,
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
    from app.services.role_profile.named import decide_named_matches, visible_named_matches

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
    allowed, reason = decide_named_matches(
        evidence_tier=profile.evidence_tier,
        active_dimension_count=len(profile.active_dimensions),
        overall_stable=bool((profile.quality_summary or {}).get("overall_stable")),
        top3_overlap_rate=1.0,
        pool_named_allowed=True,
        vector_dim_count=len(profile.role_vector.model_dump(exclude_none=True)),
    )
    overall = visible_named_matches(
        [{"name": "Should Not Appear", "score": 0.99}],
        allowed=allowed,
    )
    assert profile.evidence_tier != EvidenceTier.established
    assert allowed is False
    assert reason == "evidence_tier"
    assert overall == []
    assert all(row.get("name") != "Should Not Appear" for row in overall)
    if profile.evidence_tier == EvidenceTier.insufficient:
        assert arch["shown"] is False


def test_named_matches_require_established_evidence():
    from app.services.role_profile.named import decide_named_matches, visible_named_matches

    arch = classify_archetype(
        {"catch_readiness": 0.8, "rim_pressure_tendency": 0.2},
        evidence_tier=EvidenceTier.emerging,
    )
    assert arch["shown"] is True
    allowed, reason = decide_named_matches(
        evidence_tier=EvidenceTier.emerging,
        active_dimension_count=2,
        overall_stable=True,
        top3_overlap_rate=1.0,
        pool_named_allowed=True,
        vector_dim_count=2,
    )
    assert allowed is False
    assert reason == "evidence_tier"
    assert visible_named_matches([{"name": "Named Player"}], allowed=allowed) == []

    allowed_ok, reason_ok = decide_named_matches(
        evidence_tier=EvidenceTier.established,
        active_dimension_count=1,
        overall_stable=False,
        top3_overlap_rate=0.1,
        pool_named_allowed=True,
        vector_dim_count=1,
    )
    assert allowed_ok is True
    assert reason_ok is None
    names = visible_named_matches([{"name": "Named Player"}], allowed=allowed_ok)
    assert names[0]["name"] == "Named Player"


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


def test_named_rank_skips_players_missing_a_user_dimension():
    user = {"catch_readiness": 0.18, "playmaking_orientation": 1.0}
    players = [
        {
            "name": "Subset Only",
            "player_id": 1,
            "position": "forward",
            "position_group": "forward",
            "height_in": 79.0,
            "role_vector": {"playmaking_orientation": 0.997},
            "meets_min_sample": True,
            "raw_source": {},
        },
        {
            "name": "Full Coverage",
            "player_id": 2,
            "position": "guard",
            "position_group": "guard",
            "height_in": 78.0,
            "role_vector": {"catch_readiness": 0.2, "playmaking_orientation": 0.95},
            "meets_min_sample": True,
            "raw_source": {},
        },
    ]
    ranked = rank_role_matches(
        players,
        user_vector=user,
        user_height_in=78.0,
        listed_position="guard",
        top_k=None,
    )
    names = [row["name"] for row in ranked]
    assert "Subset Only" not in names
    assert names[0] == "Full Coverage"


def test_height_and_position_only_filter_or_tiebreak_not_primary_similarity():
    user = {"catch_readiness": 0.5, "rim_pressure_tendency": 0.5}
    nba = {"catch_readiness": 0.5, "rim_pressure_tendency": 0.5}
    dist = masked_distance(user, nba)
    tie = height_tiebreak(70.0, 75.0, band_in=5.0)
    assert dist == 0.0 or dist is not None and dist < 1e-9
    assert 0 < tie <= RANK_BODY_WEIGHT
    assert body_plausibility(2.0) == 1.0
    assert body_plausibility(5.0) < body_plausibility(3.0)
    assert body_plausibility(10.0) == 0.0
    assert classify_comp_bucket(4.0, 1.2) == "primary"
    assert classify_comp_bucket(6.0, 0.4) == "primary"
    assert classify_comp_bucket(6.0, 1.2) == "style_only"
    assert classify_comp_bucket(8.0, 0.2) == "style_only"
    assert classify_comp_bucket(10.0, 0.1) is None


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


def test_small_pool_still_allows_named_with_limited_confidence():
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
    assert pool.named_matches_allowed is True
    assert pool.pool_confidence == "limited"
    assert len(pool.players) == 3


def test_undersized_forward_still_gets_similar_height_guards():
    players = [
        {
            "name": f"G{i}",
            "position": "guard",
            "position_group": "guard",
            "height_in": 70.0,
            "role_vector": {"catch_readiness": 0.5, "rim_pressure_tendency": 0.5},
            "meets_min_sample": True,
        }
        for i in range(10)
    ] + [
        {
            "name": "Tall Forward",
            "position": "forward",
            "position_group": "forward",
            "height_in": 81.0,
            "role_vector": {"catch_readiness": 0.5, "rim_pressure_tendency": 0.5},
            "meets_min_sample": True,
        }
    ]
    pool = select_nba_pool(players, position="forward", height_in=70.0, min_pool=8)
    assert pool.named_matches_allowed is True
    names = {p["name"] for p in pool.players}
    assert "Tall Forward" not in names
    assert len(pool.players) == 10


def test_six_six_user_never_matches_wemby_height():
    players = [
        {
            "name": f"W{i}",
            "position": "wing",
            "position_group": "wing",
            "height_in": 78.0,
            "role_vector": {"catch_readiness": 0.5},
            "meets_min_sample": True,
        }
        for i in range(10)
    ] + [
        {
            "name": "Victor Wembanyama",
            "position": "forward",
            "position_group": "forward",
            "height_in": 88.0,
            "role_vector": {"catch_readiness": 0.5, "rim_pressure_tendency": 0.9},
            "meets_min_sample": True,
        }
    ]
    for listed in ("wing", "forward", "center"):
        pool = select_nba_pool(players, position=listed, height_in=78.0, min_pool=8)
        assert all(abs(float(p["height_in"]) - 78.0) <= 9.0 for p in pool.players)
        assert all(p["name"] != "Victor Wembanyama" for p in pool.players)


def test_role_outranks_height_and_splits_style_only():
    user = {"catch_readiness": 0.9, "rim_pressure_tendency": 0.9}
    players = [
        {
            "name": "SameStyleTaller",
            "player_id": 1,
            "position": "forward",
            "position_group": "forward",
            "height_in": 86.0,
            "role_vector": {"catch_readiness": 0.9, "rim_pressure_tendency": 0.9},
            "meets_min_sample": True,
            "raw_source": {},
        },
        {
            "name": "DifferentStyleSameHeight",
            "player_id": 2,
            "position": "guard",
            "position_group": "guard",
            "height_in": 78.0,
            "role_vector": {"catch_readiness": 0.05, "rim_pressure_tendency": 0.05},
            "meets_min_sample": True,
            "raw_source": {},
        },
        {
            "name": "SameStyleClose",
            "player_id": 3,
            "position": "wing",
            "position_group": "wing",
            "height_in": 79.0,
            "role_vector": {"catch_readiness": 0.9, "rim_pressure_tendency": 0.9},
            "meets_min_sample": True,
            "raw_source": {},
        },
    ]
    ranked = rank_role_matches(
        players,
        user_vector=user,
        user_height_in=78.0,
        listed_position="wing",
        top_k=None,
    )
    names = [row["name"] for row in ranked]
    assert names[0] == "SameStyleClose"
    by_name = {row["name"]: row for row in ranked}
    assert by_name["SameStyleTaller"]["comp_bucket"] == "style_only"
    assert by_name["SameStyleClose"]["comp_bucket"] == "primary"
    assert by_name["SameStyleTaller"]["ranking_distance"] < by_name["DifferentStyleSameHeight"]["ranking_distance"]
    primary, style_only = split_role_matches(ranked)
    assert primary[0]["name"] == "SameStyleClose"
    assert "DifferentStyleSameHeight" in [row["name"] for row in primary]
    assert [row["name"] for row in style_only] == ["SameStyleTaller"]


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
    import inspect

    from app.services.role_profile.constants import NBA_TRANSFORM_VERSION
    from app.services.supabase_client import SupabaseService

    src = inspect.getsource(SupabaseService.insert_comp_result)
    assert "client.post" in src
    assert "client.patch" not in src
    assert "client.put" not in src
    first = {"nba_seed_version": "role_profile_v1", "comparison_mode": "role_profile_v1"}
    second = dict(first)
    second["nba_seed_version"] = NBA_TRANSFORM_VERSION + "_next"
    assert first["nba_seed_version"] != second["nba_seed_version"]
    assert first["comparison_mode"] == second["comparison_mode"]


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
