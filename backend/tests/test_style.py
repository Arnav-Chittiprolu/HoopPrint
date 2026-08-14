from app.services.aggregate import compute_height_z, compute_height_z_nba
from app.services.nba_seed import build_nba_style_vector
from app.services.style import (
    build_user_style_vector,
    cosine_similarity,
    evidence_from_agg,
    filter_nba_pool,
    height_band_inches,
    map_nba_position,
    rank_matches,
    score_player,
    size_from_height_in,
)


def test_map_nba_position():
    assert map_nba_position("G") == "guard"
    assert map_nba_position("G-F") == "wing"
    assert map_nba_position("F") == "forward"
    assert map_nba_position("C") == "center"
    assert map_nba_position("C-F") == "center"


def test_us_male_and_nba_height_z_are_different():
    # 71" is slightly tall vs US men, but short vs NBA / NBA guards
    assert abs(compute_height_z(71.0) - (2.0 / 3.0)) < 1e-9
    assert compute_height_z_nba(71.0) is not None
    assert compute_height_z_nba(71.0) < 0  # below league ~78"
    assert compute_height_z_nba(71.0, "guard") < 0  # below guard ~75"
    assert compute_height_z_nba(75.0, "guard") == 0.0
    assert compute_height_z_nba(78.0) == 0.0


def test_size_uses_nba_scale_not_us_male():
    # League-average NBA height → mid size slot
    assert size_from_height_in(78.0) == 0.5
    assert size_from_height_in(75.0, "guard") == 0.5
    # Same inches: US-male z would be positive, NBA size is below mid for a guard
    assert size_from_height_in(71.0, "guard") < 0.5


def test_size_and_band():
    assert height_band_inches(0.0) == 4.0
    assert height_band_inches(-1.5) == 5.0
    assert height_band_inches(2.5) == 6.0


def test_user_style_skips_missing_categories():
    agg = [
        {"feature_name": "release_angle", "value": 45.0},
        {"feature_name": "shot_arc", "value": 0.2},
    ]
    evidence = evidence_from_agg(agg)
    assert evidence == {"shot": True, "pass": False, "drive": False}

    style = build_user_style_vector(
        height_in=71.0, aggregated_features=agg, position="guard"
    )
    assert "size" in style
    assert "perimeter_vs_rim" in style
    assert "creation" not in style
    assert "drive_burst" not in style
    assert "passing" not in style


def test_cosine_identical_vectors():
    a = {"size": 0.5, "perimeter_vs_rim": 0.8}
    assert abs(cosine_similarity(a, a) - 1.0) < 1e-9


def test_filter_excludes_wrong_position_and_height():
    players = [
        {"name": "Short Guard", "position": "guard", "height_in": 73.0, "style_vector": {"size": 0.4}},
        {"name": "Tall Center", "position": "center", "height_in": 83.0, "style_vector": {"size": 0.9}},
        {"name": "Far Guard", "position": "guard", "height_in": 80.0, "style_vector": {"size": 0.7}},
    ]
    eligible = filter_nba_pool(
        players, position="guard", height_in=72.0, height_z_nba=compute_height_z_nba(72.0, "guard")
    )
    names = {p["name"] for p in eligible}
    assert names == {"Short Guard"}


def test_short_guard_does_not_rank_tall_center():
    user_style = {"size": 0.35, "perimeter_vs_rim": 0.7}
    players = [
        {
            "player_id": 1,
            "name": "Short Guard",
            "season": "2025-26",
            "position": "guard",
            "height_in": 73.0,
            "style_vector": {"size": 0.4, "perimeter_vs_rim": 0.75},
        },
        {
            "player_id": 2,
            "name": "Tall Center",
            "season": "2025-26",
            "position": "center",
            "height_in": 84.0,
            "style_vector": {"size": 0.95, "perimeter_vs_rim": 0.1},
        },
    ]
    hz = compute_height_z_nba(72.0, "guard")
    eligible = filter_nba_pool(players, position="guard", height_in=72.0, height_z_nba=hz)
    ranked = rank_matches(
        eligible,
        user_style=user_style,
        user_height_in=72.0,
        height_z_nba=hz,
        primary_skill="shot",
        evidence={"shot": True, "pass": False, "drive": False},
        top_k=3,
    )
    assert ranked["overall"]
    assert ranked["overall"][0]["name"] == "Short Guard"
    assert "Tall Center" not in {m["name"] for m in ranked["overall"]}
    assert "shot" in ranked["by_category"]


def test_score_changes_with_height():
    user = {"size": 0.5, "perimeter_vs_rim": 0.6}
    nba = {"size": 0.5, "perimeter_vs_rim": 0.6}
    hz = compute_height_z_nba(74.0, "guard")
    close = score_player(
        user,
        nba,
        user_height_in=74.0,
        nba_height_in=74.0,
        height_z_nba=hz,
        primary_skill=None,
    )
    far = score_player(
        user,
        nba,
        user_height_in=74.0,
        nba_height_in=78.0,
        height_z_nba=hz,
        primary_skill=None,
    )
    assert close is not None and far is not None
    assert close > far


def test_nba_style_vector_from_raw():
    raw = {
        "height_in": 78.0,
        "position": "wing",
        "pct_fga_3pt": 0.4,
        "pct_pts_paint": 0.3,
        "pct_uast_fgm": 0.5,
        "pull_up_fga": 3.0,
        "catch_shoot_fga": 1.0,
        "drives_norm": 0.8,
        "speed_off_norm": 0.7,
        "ast_pct": 0.25,
        "potential_ast": 5.0,
        "passes_made": 40.0,
    }
    style = build_nba_style_vector(raw)
    assert set(style) >= {"size", "perimeter_vs_rim", "creation", "drive_burst", "passing"}
    assert 0.0 <= style["perimeter_vs_rim"] <= 1.0
