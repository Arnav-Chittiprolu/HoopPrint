"""Version constants for Phase 10 role-profile pipeline."""

ROLE_PROFILE_VERSION = "role_profile_v1"
NBA_TRANSFORM_VERSION = "role_profile_v1"
DISCLOSURE_VERSION = "2026-08-17"
COMPARISON_MODE_LEGACY = "legacy_style"
COMPARISON_MODE_ROLE = "role_profile_v1"

# Mechanics keys that must never appear in role-vector inputs (§5.6.1).
BANNED_MECHANICS_KEYS = frozenset(
    {
        "release_angle",
        "release_angle_deg",
        "elbow_angle",
        "elbow_angle_deg",
        "elbow_angle_at_release",
        "release_height_ratio",
        "relative_release_height",
        "approx_release_height_in",
        "shot_arc",
        "wrist_rise_proxy",
        "first_step_burst",
        "first_step_burst_body_lengths",
        "change_of_direction_angle",
        "arm_extension_at_release",
        "pass_release_extension_deg",
        "release_point_consistency",
        "decision_speed",
    }
)

ROLE_VECTOR_KEYS = frozenset(
    {
        "catch_readiness",
        "rim_pressure_tendency",
        "playmaking_orientation",
    }
)

# Gate thresholds (§5.6, Phase 10.2)
MIN_VIDEO_FPS = 24.0
BURST_WINDOW_MS_MIN = 150
BURST_WINDOW_MS_MAX = 200
BURST_WINDOW_MS_DEFAULT = 175
CATCH_RELEASE_MIN_S = 0.3
CATCH_RELEASE_MAX_S = 1.2
MIN_TRACK_CONFIDENCE = 0.5
MIN_EVENT_CONFIDENCE_FOR_EMERGING = 0.70
MIN_PRE_POSE_SAMPLES = 2
MIN_POST_POSE_SAMPLES = 2
MIN_HIP_BURST_BODY_LENGTHS = 0.04
MIN_WRIST_SEPARATION_FOR_CATCH = 0.02
MAX_WRIST_SEPARATION_FOR_CATCH = 0.22

# Aggregation / evidence (§5.7, Phase 10.3)
MIN_EVENT_CONFIDENCE_FOR_ESTABLISHED = 0.75
BOOTSTRAP_ITERATIONS = 300
BOOTSTRAP_SD_MAX = 0.12
RIM_BURST_LATENT_SCALE = 0.25  # body-lengths → ~[0, 1] latent
PLAYMAKING_EXTENSION_FLOOR_DEG = 100.0
PLAYMAKING_EXTENSION_SPAN_DEG = 80.0

# Scoring (§5.6.2, §5.8, Phase 10.5) — predeclared equal weights
ROLE_DIM_WEIGHTS: dict[str, float] = {
    "catch_readiness": 1.0,
    "rim_pressure_tendency": 1.0,
    "playmaking_orientation": 1.0,
}
HEIGHT_TIEBREAK_WEIGHT = 0.08  # ≤10% of ranking; never a role dimension
Z_CLIP = 3.0
MIN_NAMED_MATCH_POOL = 8
MIN_NBA_GP = 15
MIN_NBA_MINUTES = 200.0
MIN_CATCH_ATTEMPT_SHARE_DENOM = 1.0  # C&S FGA + pull-up FGA (per game)
MIN_TOUCHES_FOR_RATE = 1.0
POOL_HEIGHT_BAND_STAGE1 = 3.0
POOL_HEIGHT_BAND_STAGE2 = 5.0
POOL_HEIGHT_BAND_STAGE3 = 5.0
TOP3_OVERLAP_MIN = 0.60
BOOTSTRAP_RANK_ITERATIONS = 80
SEASON_TYPE_DEFAULT = "Regular Season"

