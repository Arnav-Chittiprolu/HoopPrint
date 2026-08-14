from app.services.aggregate import (
    average_features_by_name,
    compute_height_z,
    compute_height_z_nba,
)


def test_compute_height_z_average_man():
    assert compute_height_z(69.0) == 0.0


def test_compute_height_z_taller_and_shorter():
    assert compute_height_z(72.0) == 1.0
    assert compute_height_z(66.0) == -1.0
    assert compute_height_z(None) is None


def test_compute_height_z_nba_league_and_position():
    assert compute_height_z_nba(78.0) == 0.0
    assert compute_height_z_nba(75.0, "guard") == 0.0
    assert compute_height_z_nba(71.0, "guard") < 0
    # Same person: US-male z and NBA z must not use the same baseline
    assert compute_height_z(71.0) != compute_height_z_nba(71.0, "guard")


def test_average_features_by_name_means_and_clip_counts():
    rows = [
        {"clip_id": "a", "feature_name": "release_angle", "value": 40.0},
        {"clip_id": "b", "feature_name": "release_angle", "value": 60.0},
        {"clip_id": "a", "feature_name": "elbow_angle_at_release", "value": 120.0},
        {"clip_id": "b", "feature_name": "elbow_angle_at_release", "value": 140.0},
    ]
    agg = {row["feature_name"]: row for row in average_features_by_name(rows)}
    assert agg["release_angle"]["value"] == 50.0
    assert agg["release_angle"]["clip_count"] == 2
    assert agg["elbow_angle_at_release"]["value"] == 130.0
    assert agg["elbow_angle_at_release"]["clip_count"] == 2


def test_average_features_ignores_bad_rows():
    rows = [
        {"clip_id": "a", "feature_name": "shot_arc", "value": 0.1},
        {"clip_id": "b", "feature_name": "", "value": 1.0},
        {"clip_id": "c", "feature_name": "shot_arc", "value": "nope"},
    ]
    agg = average_features_by_name(rows)
    assert len(agg) == 1
    assert agg[0]["feature_name"] == "shot_arc"
    assert agg[0]["value"] == 0.1
    assert agg[0]["clip_count"] == 1
