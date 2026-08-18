"""Version constants for Phase 10 role-profile pipeline."""

ROLE_PROFILE_VERSION = "role_profile_v1"
NBA_TRANSFORM_VERSION = "role_profile_v1"
DISCLOSURE_VERSION = "2026-08-18"
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
PULL_UP_LATENT = 0.18
PULL_UP_MAX_GATHER_S = 3.5
MIN_HIP_TRAVEL_FOR_PULL_UP = 0.05
MIN_TRACK_CONFIDENCE = 0.5
MIN_EVENT_CONFIDENCE_FOR_EMERGING = 0.70
MIN_PRE_POSE_SAMPLES = 2
MIN_POST_POSE_SAMPLES = 2
MIN_POSE_SAMPLES_FOR_PASS = 5
MIN_HIP_BURST_BODY_LENGTHS = 0.04
MIN_WRIST_SEPARATION_FOR_CATCH = 0.02
MAX_WRIST_SEPARATION_FOR_CATCH = 0.22

# Aggregation / evidence (§5.7, Phase 10.3)
MIN_EVENTS_DIMENSION_EMERGING = 2
MIN_EVENTS_DIMENSION_ESTABLISHED = 5
MIN_EVENTS_OVERALL_EMERGING = 3
MIN_EVENTS_OVERALL_ESTABLISHED = 5
MIN_EVENTS_OVERALL_STRONG = 10
MIN_ACTIVE_DIMS_FOR_NAMED = 1
MIN_EVENT_CONFIDENCE_FOR_ESTABLISHED = 0.75
BOOTSTRAP_ITERATIONS = 300
BOOTSTRAP_SD_MAX = 0.12
RIM_BURST_LATENT_SCALE = 0.25  # body-lengths → ~[0, 1] latent
PLAYMAKING_EXTENSION_FLOOR_DEG = 80.0
PLAYMAKING_EXTENSION_SPAN_DEG = 80.0

# Scoring (§5.6.2, §5.8) — equal role-dim weights; blend is role-first
ROLE_DIM_WEIGHTS: dict[str, float] = {
    "catch_readiness": 1.0,
    "rim_pressure_tendency": 1.0,
    "playmaking_orientation": 1.0,
}
RANK_ROLE_WEIGHT = 0.72
RANK_BODY_WEIGHT = 0.16
RANK_CONFIDENCE_WEIGHT = 0.07
RANK_LISTED_ROLE_WEIGHT = 0.05
# Deprecated alias: body term is RANK_BODY_WEIGHT, not a role dimension
HEIGHT_TIEBREAK_WEIGHT = RANK_BODY_WEIGHT
Z_CLIP = 3.0
MIN_NAMED_MATCH_POOL = 8  # confidence label only; do not hide names below this
MIN_NBA_GP = 15
MIN_NBA_MINUTES = 200.0
MIN_CATCH_ATTEMPT_SHARE_DENOM = 1.0  # C&S FGA + pull-up FGA (per game)
MIN_TOUCHES_FOR_RATE = 1.0
BODY_NO_PENALTY_IN = 3.0
BODY_SMALL_PENALTY_IN = 5.0
BODY_EXCEPTIONAL_IN = 7.0
BODY_EXCLUDE_IN = 9.0  # never a named comparison beyond this
BODY_PRIMARY_MAX_IN = 5.0
EXCEPTIONAL_ROLE_DISTANCE = 0.75  # High resemblance; needed for 5–7" primary
NBA_POSITION_FIT_IN = 5.0  # typical NBA role size for physical-context copy only
ALL_POSITION_GROUPS = frozenset({"guard", "wing", "forward", "center"})
# Legacy names used by older tests / leftover imports
POOL_HEIGHT_BAND_STAGE1 = BODY_NO_PENALTY_IN
POOL_HEIGHT_BAND_STAGE2 = BODY_SMALL_PENALTY_IN
POOL_HEIGHT_BAND_MAX = BODY_EXCLUDE_IN
TOP3_OVERLAP_MIN = 0.60
BOOTSTRAP_RANK_ITERATIONS = 80
SEASON_TYPE_DEFAULT = "Regular Season"

