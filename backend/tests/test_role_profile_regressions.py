"""Phase 10.7 remaining regressions: why, LLM, stability, seed round-trip, API cutover."""

from __future__ import annotations

import inspect
from datetime import date
from uuid import uuid4

from app.models.role_profile import EvidenceTier, RoleDimension
from app.services.comp import comp_from_stored_row
from app.services.role_profile.aggregate import aggregate_role_profile, bootstrap_stability
from app.services.role_profile.constants import ROLE_VECTOR_KEYS
from app.services.role_profile.named import bootstrap_top3_overlap, decide_named_matches
from app.services.role_profile.nba_transform import finalize_nba_role_rows
from app.services.role_profile.pool import PoolSelection
from app.services.role_profile.why import build_role_llm_prompt, build_role_why


def _pool() -> PoolSelection:
    return PoolSelection(
        players=[],
        stage=1,
        position_groups=["forward"],
        height_band_in=3.0,
        pool_sentence="Height does not determine how you play. Named comparisons start from clip role resemblance.",
        named_matches_allowed=True,
        cohort_definition={"season": "2025-26"},
    )


def test_role_why_never_maps_mechanics_to_box_score():
    why = build_role_why(
        match={
            "name": "Example",
            "height_in": 78.0,
            "distance": 0.2,
            "height_tiebreak": 0.01,
            "ranking_distance": 0.21,
            "resemblance_band": "High",
            "score": 0.83,
            "role_vector": {
                "catch_readiness": 0.7,
                "rim_pressure_tendency": 0.4,
            },
        },
        user_vector={"catch_readiness": 0.65, "rim_pressure_tendency": 0.42},
        user_height_in=76.0,
        pool=_pool(),
        evidence_tier="established",
    )
    blob = str(why)
    assert why["label"] == "role_profile"
    assert {row["dim"] for row in why["slots"]} <= ROLE_VECTOR_KEYS
    for banned in (
        "release_angle",
        "elbow_angle",
        "wrist_rise_proxy",
        "shot_arc",
        "FG%",
        "3P",
        "FT%",
    ):
        assert banned not in blob
    assert "mechanics" not in (why.get("note") or "").lower() or "not shared mechanics" in why["note"].lower()


def test_role_why_is_traceable_to_pool_and_scales():
    why = build_role_why(
        match={
            "name": "Example",
            "height_in": 78.0,
            "distance": 0.4,
            "role_vector": {"catch_readiness": 0.5},
        },
        user_vector={"catch_readiness": 0.5},
        user_height_in=76.0,
        pool=_pool(),
        evidence_tier="established",
    )
    assert why["pool_sentence"].startswith("Height does not determine")
    assert why["score_terms"]["user_scale"] == "latent_0_1"
    assert why["score_terms"]["nba_scale"] == "cohort_percentile"
    assert why["evidence_tier"] == "established"


def test_role_llm_prompt_separates_mechanics_and_role_and_forbids_claims():
    prompt = build_role_llm_prompt(
        questionnaire={"height_in": 70, "position": "forward"},
        mechanics={"release_angle": 44.0},
        user_role_vector={"catch_readiness": 0.6},
        archetype={"key": "quick_trigger_perimeter", "label": "quick-trigger perimeter role"},
        top_match={"name": "Example"},
        why={"note": "role resemblance"},
        mechanics_recs=[{"action": "Film a side-view drill.", "target": "release_angle"}],
        role_recs=[{"action": "Upload more catch clips.", "target": "catch_readiness"}],
        evidence_tier="emerging",
        named_matches_suppressed=True,
    )
    assert "MECHANICS_RECS" in prompt
    assert "ROLE_RECS" in prompt
    assert "Do not pick a different NBA player" in prompt
    assert "Do not claim outcome prediction" in prompt
    assert "do not use for the NBA comparison" in prompt
    assert "no NBA player names" in prompt
    assert "NAMED_MATCHES_SUPPRESSED: True" in prompt
    assert "PRIMARY_MATCH:" in prompt
    assert "STYLE_ONLY_REFERENCES:" in prompt


def test_production_comp_endpoint_uses_role_engine_not_legacy():
    from app.api import comp as api_comp

    src = inspect.getsource(api_comp)
    assert "run_role_comp" in src
    assert "run_style_comp" not in src


def test_comp_from_stored_row_preserves_role_profile_mode():
    row = {
        "id": uuid4(),
        "user_id": uuid4(),
        "comparison_mode": "role_profile_v1",
        "evidence_tier": "established",
        "matches": {
            "label": "role_profile",
            "user_role_vector": {"catch_readiness": 0.5},
            "overall": [],
            "named_matches_suppressed": True,
        },
        "mechanics_recs": [{"target": "release_angle", "action": "drill", "because": "x", "reference_kind": "pose_range"}],
        "role_recs": [{"target": "evidence_tier", "action": "upload", "because": "y", "reference_kind": "evidence"}],
    }
    parsed = comp_from_stored_row(row)
    assert parsed["comparison_mode"] == "role_profile_v1"
    assert parsed["named_matches_suppressed"] is True
    assert parsed["mechanics_recs"]
    assert parsed["role_recs"]


def test_comp_stale_when_height_or_clips_change():
    from app.services.comp import apply_stale_flag, make_inputs_snapshot

    result = {
        "inputs_snapshot": make_inputs_snapshot(height_in=70, position="guard", valid_event_count=8)
    }
    apply_stale_flag(result, height_in=70, position="guard", valid_event_count=8)
    assert result["stale"] is False
    apply_stale_flag(result, height_in=74, position="guard", valid_event_count=8)
    assert result["stale"] is True
    assert "height" in result["stale_reasons"]
    apply_stale_flag(result, height_in=70, position="wing", valid_event_count=8)
    assert "position" in result["stale_reasons"]
    apply_stale_flag(result, height_in=70, position="guard", valid_event_count=12)
    assert "clips" in result["stale_reasons"]
    old = apply_stale_flag({}, height_in=70, position="guard", valid_event_count=8)
    assert old["stale"] is True


def test_nba_seed_raw_payload_round_trip():
    raw = {
        "gp": 50,
        "minutes": 1200,
        "catch_shoot_fga": 2.5,
        "pull_up_fga": 1.5,
        "drives": 6.0,
        "touches": 40.0,
        "passes_made": 22.0,
        "potential_ast": 6.0,
    }
    rows = finalize_nba_role_rows(
        [
            {
                "name": "Round Trip",
                "player_id": 99,
                "season": "2025-26",
                "position": "guard",
                "position_group": "guard",
                "height_in": 74.0,
                "raw_stats": raw,
            },
            {
                "name": "Peer",
                "player_id": 100,
                "season": "2025-26",
                "position": "guard",
                "position_group": "guard",
                "height_in": 75.0,
                "raw_stats": {**raw, "drives": 3.0, "catch_shoot_fga": 1.0},
            },
        ],
        season="2025-26",
    )
    row = next(r for r in rows if r["name"] == "Round Trip")
    assert row["raw_stats"]["touches"] == 40.0
    src = row["raw_source"]["rim_pressure_tendency"]
    assert src["raw_numerator"] == 6.0
    assert src["raw_denominator"] == 40.0
    assert src["field_name"] == "DRIVES / TOUCHES"
    assert row["raw_source"]["catch_readiness"]["raw_numerator"] == 2.5


def test_stability_and_overlap_gates_suppress_names():
    allowed, reason = decide_named_matches(
        evidence_tier=EvidenceTier.strong,
        active_dimension_count=2,
        overall_stable=False,
        top3_overlap_rate=0.9,
        pool_named_allowed=True,
        vector_dim_count=2,
    )
    assert allowed is False
    assert reason == "stability"

    allowed, reason = decide_named_matches(
        evidence_tier=EvidenceTier.strong,
        active_dimension_count=2,
        overall_stable=True,
        top3_overlap_rate=0.2,
        pool_named_allowed=True,
        vector_dim_count=2,
    )
    assert allowed is False
    assert reason == "top3_overlap"

    allowed, reason = decide_named_matches(
        evidence_tier=EvidenceTier.established,
        active_dimension_count=1,
        overall_stable=False,
        top3_overlap_rate=0.2,
        pool_named_allowed=True,
        vector_dim_count=1,
    )
    assert allowed is True
    assert reason is None


def test_bootstrap_top3_overlap_is_high_when_events_are_stable():
    from app.models.role_profile import ClipEventRecord

    user_id = uuid4()
    events = []
    for day in (1, 2):
        for _ in range(5):
            events.append(
                ClipEventRecord(
                    clip_id=uuid4(),
                    user_id=user_id,
                    role_dimension=RoleDimension.catch_readiness,
                    gate_passed=True,
                    signal_values={"catch_to_release_s": 0.45},
                    event_confidence=0.85,
                    session_date=date(2026, 8, day),
                )
            )
            events.append(
                ClipEventRecord(
                    clip_id=uuid4(),
                    user_id=user_id,
                    role_dimension=RoleDimension.rim_pressure,
                    gate_passed=True,
                    signal_values={"burst_body_lengths": 0.18},
                    event_confidence=0.85,
                    session_date=date(2026, 8, day),
                )
            )
    players = [
        {
            "name": "Close",
            "player_id": 1,
            "position": "forward",
            "height_in": 78.0,
            "role_vector": {"catch_readiness": 0.8, "rim_pressure_tendency": 0.7},
            "raw_source": {},
        },
        {
            "name": "Far",
            "player_id": 2,
            "position": "forward",
            "height_in": 78.0,
            "role_vector": {"catch_readiness": 0.05, "rim_pressure_tendency": 0.05},
            "raw_source": {},
        },
        {
            "name": "AlsoFar",
            "player_id": 3,
            "position": "forward",
            "height_in": 78.0,
            "role_vector": {"catch_readiness": 0.1, "rim_pressure_tendency": 0.1},
            "raw_source": {},
        },
        {
            "name": "Farther",
            "player_id": 4,
            "position": "forward",
            "height_in": 78.0,
            "role_vector": {"catch_readiness": 0.02, "rim_pressure_tendency": 0.02},
            "raw_source": {},
        },
        {
            "name": "Farthest",
            "player_id": 5,
            "position": "forward",
            "height_in": 78.0,
            "role_vector": {"catch_readiness": 0.01, "rim_pressure_tendency": 0.99},
            "raw_source": {},
        },
    ]
    overlap = bootstrap_top3_overlap(
        events,
        user_id=str(user_id),
        players=players,
        user_height_in=78.0,
        height_band_in=5.0,
        base_names=["Close", "Far", "AlsoFar"],
        n_iter=12,
    )
    assert overlap is not None
    assert overlap >= 0.6


def test_archetype_band_agreement_on_stable_latents():
    tight = bootstrap_stability([0.7, 0.71, 0.69, 0.72, 0.70], n_iter=40)
    wide = bootstrap_stability([0.1, 0.9, 0.2, 0.85, 0.15], n_iter=40)
    assert tight["band_agreement_rate"] >= 0.9
    assert tight["stable"] is True
    assert wide["band_agreement_rate"] < tight["band_agreement_rate"]


def test_rejected_events_do_not_enter_role_profile():
    from app.models.role_profile import ClipEventRecord

    user_id = uuid4()
    events = [
        ClipEventRecord(
            clip_id=uuid4(),
            user_id=user_id,
            role_dimension=RoleDimension.catch_readiness,
            gate_passed=False,
            rejection_reason="low_pose_visibility",
            signal_values={"catch_to_release_s": 0.4},
            event_confidence=0.9,
            session_date=date(2026, 8, 1),
        ),
        ClipEventRecord(
            clip_id=uuid4(),
            user_id=user_id,
            role_dimension=RoleDimension.catch_readiness,
            gate_passed=True,
            signal_values={"catch_to_release_s": 0.5},
            event_confidence=0.8,
            session_date=date(2026, 8, 1),
        ),
    ]
    profile = aggregate_role_profile(events, user_id=user_id)
    assert profile.catch_readiness.event_count == 1
    assert profile.evidence_tier == EvidenceTier.insufficient
