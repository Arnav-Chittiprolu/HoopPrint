"""Split mechanics_recs vs role_recs. Never cite NBA players in mechanics recs."""

from __future__ import annotations

from typing import Any, Iterable

from app.models.role_profile import EvidenceTier, UserRoleProfileRecord
from app.services.role_profile.constants import ROLE_VECTOR_KEYS

# Pose bands used only as rec *targets* for this user's mechanics — not NBA %.
POSE_TARGETS: dict[str, dict[str, Any]] = {
    "shot_arc": {
        "category": "shot",
        "low": 0.05,
        "target": 0.20,
        "action": (
            "Film a side-view stationary shooting drill and hold the follow-through "
            "so the wrist keeps rising after release (wrist-rise proxy)."
        ),
    },
    "release_angle": {
        "category": "shot",
        "low": 32.0,
        "high": 62.0,
        "target": 48.0,
        "action": (
            "On the next shot clip, release with a higher forearm elevation "
            "(release posture toward ~48° from horizontal)."
        ),
    },
    "elbow_angle_at_release": {
        "category": "shot",
        "low": 125.0,
        "target": 155.0,
        "action": (
            "At release, extend the shooting elbow further "
            "(elbow configuration toward ~155°)."
        ),
    },
    "first_step_burst": {
        "category": "drive",
        "low": 0.35,
        "target": 0.70,
        "action": (
            "On the next drive clip, cover more ground in the first two steps "
            "(body-relative burst)."
        ),
    },
    "arm_extension_at_release": {
        "category": "pass",
        "low": 130.0,
        "target": 160.0,
        "action": (
            "On the next pass clip, finish with a more extended passing arm "
            "(pass-motion descriptor toward ~160°)."
        ),
    },
}

DIM_UPLOAD_HINTS = {
    "catch_readiness": "Upload catch-and-shoot or pull-up / gather clips. Form shooting is mechanics only.",
    "rim_pressure_tendency": "Upload gameplay or drive clips with a clear first step toward the rim.",
    "playmaking_orientation": "Upload pass clips with a visible gather and release.",
}


def _clip_counts(agg: Iterable[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in agg:
        name = row.get("feature_name")
        if not isinstance(name, str):
            continue
        try:
            counts[name] = int(row.get("clip_count") or 1)
        except (TypeError, ValueError):
            counts[name] = 1
    return counts


def build_mechanics_recs(
    mechanics: dict[str, float],
    *,
    agg: Iterable[dict] | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    counts = _clip_counts(agg or [])
    recs: list[dict[str, Any]] = []
    for feature, spec in POSE_TARGETS.items():
        if feature not in mechanics:
            continue
        current = float(mechanics[feature])
        low = spec.get("low")
        high = spec.get("high")
        target = float(spec["target"])
        below = low is not None and current < float(low)
        above = high is not None and current > float(high)
        if not below and not above:
            continue
        n = counts.get(feature, 1)
        recs.append(
            {
                "target": feature,
                "category": spec["category"],
                "current_value": round(current, 4),
                "reference": target,
                "reference_kind": "pose_range",
                "clip_count": n,
                "gap": round(abs(current - target), 4),
                "action": spec["action"],
                "because": (
                    f"Across {n} valid clip{'s' if n != 1 else ''}, {feature}={current:.3f} "
                    f"vs personal target {target:g}. Video limits apply; this is not an NBA form match."
                ),
            }
        )
    recs.sort(key=lambda row: -float(row.get("gap") or 0))
    return recs[:limit]


def build_role_recs(
    profile: UserRoleProfileRecord,
    *,
    archetype: dict[str, Any] | None = None,
    named_match_name: str | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    vector = profile.role_vector.model_dump(exclude_none=True)
    active = {d.value for d in profile.active_dimensions}
    missing = [k for k in ROLE_VECTOR_KEYS if k not in vector]

    if profile.evidence_tier in {EvidenceTier.insufficient, EvidenceTier.emerging}:
        recs.append(
            {
                "target": "evidence_tier",
                "category": "role",
                "current_value": None,
                "reference": None,
                "reference_kind": "evidence",
                "action": "Keep building your profile with more quality-checked events.",
                "because": (
                    f"Evidence strength is {profile.evidence_tier.value}. "
                    "Named NBA examples need about 5 quality-checked clips (Established)."
                ),
            }
        )

    for key in missing:
        recs.append(
            {
                "target": key,
                "category": "role",
                "current_value": None,
                "reference": None,
                "reference_kind": "missing_dimension",
                "action": DIM_UPLOAD_HINTS[key],
                "because": (
                    f"{key} is not in the comparison mask yet. "
                    "Uploads are sampled evidence, not game-frequency rates."
                ),
            }
        )

    if archetype and archetype.get("shown") and archetype.get("label"):
        recs.append(
            {
                "target": "archetype",
                "category": "role",
                "current_value": None,
                "reference": None,
                "reference_kind": "archetype",
                "action": (
                    f"Your evidence is most consistent with a {archetype['label']}."
                ),
                "because": (
                    "That describes role-stat orientation in the comparison pool, "
                    "not skill, outcomes, or identical mechanics."
                    + (
                        f" Closest named example (role resemblance only): {named_match_name}."
                        if named_match_name
                        else ""
                    )
                    + (
                        f" Active dimensions: {', '.join(sorted(active))}."
                        if active
                        else ""
                    )
                ),
            }
        )

    picked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rec in recs:
        if rec["target"] in seen:
            continue
        seen.add(rec["target"])
        picked.append(rec)
        if len(picked) >= limit:
            break
    return picked
