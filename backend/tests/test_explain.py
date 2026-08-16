from app.services.explain import (
    annotate_matches_with_why,
    build_llm_prompt,
    build_recommendations,
    build_why,
)
from app.services.style import build_user_style_vector, evidence_from_agg, rank_matches
from app.services.aggregate import compute_height_z_nba


def _shot_agg():
    return [
        {"feature_name": "release_angle", "value": 43.6, "clip_count": 1},
        {"feature_name": "shot_arc", "value": 0.0, "clip_count": 1},
        {"feature_name": "elbow_angle_at_release", "value": 129.2, "clip_count": 1},
    ]


def _guard_match(**overrides):
    base = {
        "player_id": 1,
        "name": "Isaiah Stevens",
        "season": "2025-26",
        "position": "guard",
        "height_in": 71.0,
        "score": 0.96,
        "style_vector": {
            "size": 0.32,
            "perimeter_vs_rim": 0.27,
            "creation": 0.3,
            "drive_burst": 0.28,
            "passing": 0.27,
        },
        "kind": "style",
    }
    base.update(overrides)
    return base


def test_why_includes_filter_and_slots_not_shooting_pct():
    user_style = {"size": 0.32, "perimeter_vs_rim": 0.24}
    why = build_why(
        match=_guard_match(),
        user_style=user_style,
        user_height_in=71.0,
        height_z_nba=compute_height_z_nba(71.0, "guard"),
        primary_skill="shot",
        evidence={"shot": True, "pass": False, "drive": False},
    )
    assert why["label"] == "style"
    assert why["filter"]["position"] == "guard"
    assert why["filter"]["band_in"] >= 4.0
    dims = {row["dim"] for row in why["slots"]}
    assert dims == {"size", "perimeter_vs_rim"}
    assert "creation" in why["omitted_slots"]
    blob = str(why)
    assert "3P" not in blob
    assert "FG%" not in blob
    assert "release_angle" not in blob  # pose stays on mechanics, not why slots


def test_why_is_deterministic():
    kwargs = dict(
        match=_guard_match(),
        user_style={"size": 0.32, "perimeter_vs_rim": 0.24},
        user_height_in=71.0,
        height_z_nba=-1.45,
        primary_skill="shot",
        evidence={"shot": True, "pass": False, "drive": False},
    )
    assert build_why(**kwargs) == build_why(**kwargs)


def test_shot_only_never_gets_drive_mechanics_rec():
    agg = _shot_agg()
    evidence = evidence_from_agg(agg)
    user_style = build_user_style_vector(
        height_in=71.0, aggregated_features=agg, position="guard"
    )
    recs = build_recommendations(
        mechanics={r["feature_name"]: r["value"] for r in agg},
        user_style=user_style,
        evidence=evidence,
        overall_matches=[_guard_match()],
        eligible=[_guard_match(), _guard_match(player_id=2, name="Other", style_vector={"size": 0.4, "perimeter_vs_rim": 0.8})],
        agg=agg,
    )
    assert recs
    drive_mech = [
        r
        for r in recs
        if r["category"] == "drive" and r["reference_kind"] != "missing_evidence"
    ]
    assert drive_mech == []
    assert any(r["target"] == "shot_arc" for r in recs)
    # Hard rule: no first_step_burst / drive_burst drill without drive clips.
    assert all(r["target"] not in {"first_step_burst", "drive_burst"} for r in recs)


def test_changing_shot_arc_changes_recs():
    low = _shot_agg()
    high = [
        {"feature_name": "release_angle", "value": 43.6, "clip_count": 1},
        {"feature_name": "shot_arc", "value": 0.25, "clip_count": 1},
        {"feature_name": "elbow_angle_at_release", "value": 155.0, "clip_count": 1},
    ]
    match = _guard_match(style_vector={"size": 0.32, "perimeter_vs_rim": 0.24})
    recs_low = build_recommendations(
        mechanics={r["feature_name"]: r["value"] for r in low},
        user_style=build_user_style_vector(height_in=71.0, aggregated_features=low, position="guard"),
        evidence=evidence_from_agg(low),
        overall_matches=[match],
        eligible=[match],
        agg=low,
    )
    recs_high = build_recommendations(
        mechanics={r["feature_name"]: r["value"] for r in high},
        user_style=build_user_style_vector(height_in=71.0, aggregated_features=high, position="guard"),
        evidence=evidence_from_agg(high),
        overall_matches=[match],
        eligible=[match],
        agg=high,
    )
    assert any(r["target"] == "shot_arc" for r in recs_low)
    assert not any(r["target"] == "shot_arc" for r in recs_high)


def test_prompt_contains_why_and_rec_candidates():
    why = build_why(
        match=_guard_match(),
        user_style={"size": 0.32, "perimeter_vs_rim": 0.24},
        user_height_in=71.0,
        height_z_nba=-1.45,
        primary_skill="shot",
        evidence={"shot": True, "pass": False, "drive": False},
    )
    recs = [
        {
            "target": "shot_arc",
            "category": "shot",
            "current_value": 0.0,
            "reference": 0.2,
            "reference_kind": "pose_range",
            "action": "hold follow-through",
            "because": "shot_arc=0.000 vs target 0.2",
            "gap": 0.2,
        }
    ]
    prompt = build_llm_prompt(
        questionnaire={"height_in": 71, "position": "guard"},
        mechanics={"shot_arc": 0.0, "release_angle": 43.6},
        user_style={"size": 0.32, "perimeter_vs_rim": 0.24},
        top_match=_guard_match(),
        why=why,
        recommendations=recs,
    )
    assert "WHY_THIS_MATCH" in prompt
    assert "REC_CANDIDATES" in prompt
    assert "shot_arc" in prompt
    assert "Isaiah Stevens" in prompt
    assert "Do not pick a different NBA player" in prompt


def test_annotate_attaches_why_to_ranked_matches():
    players = [
        _guard_match(),
        {
            "player_id": 2,
            "name": "Tall Center",
            "season": "2025-26",
            "position": "center",
            "height_in": 84.0,
            "style_vector": {"size": 0.95, "perimeter_vs_rim": 0.1},
        },
    ]
    user_style = {"size": 0.32, "perimeter_vs_rim": 0.24}
    ranked = rank_matches(
        [players[0]],
        user_style=user_style,
        user_height_in=71.0,
        height_z_nba=-1.45,
        primary_skill="shot",
        evidence={"shot": True, "pass": False, "drive": False},
    )
    annotated = annotate_matches_with_why(
        ranked,
        user_style=user_style,
        user_height_in=71.0,
        height_z_nba=-1.45,
        primary_skill="shot",
        evidence={"shot": True, "pass": False, "drive": False},
    )
    assert annotated["overall"]
    assert annotated["overall"][0]["why"]["filter"]["position"] == "guard"
    assert "shot" in annotated["by_category"]
    assert annotated["by_category"]["shot"][0]["why"]["slots"]
