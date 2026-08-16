"""Deterministic why-this-match + personalized rec candidates (Phase 6).

No LLM here. Gemini only narrates these JSON blobs later.
Never map pose joints onto FG%/3P%/FT%.
"""

from __future__ import annotations

from typing import Any, Iterable

from app.services.style import (
    CATEGORY_DIMS,
    STYLE_DIMS,
    cosine_similarity,
    height_band_inches,
    primary_skill_bonus,
    size_similarity,
)

# Pose bands used only as rec *targets* for this user's mechanics — not NBA %.
POSE_TARGETS: dict[str, dict[str, Any]] = {
    "shot_arc": {
        "category": "shot",
        "low": 0.05,
        "target": 0.20,
        "action": (
            "Record another jumper and hold the follow-through so the wrist keeps "
            "rising after release (raise shot_arc)."
        ),
    },
    "release_angle": {
        "category": "shot",
        "low": 32.0,
        "high": 62.0,
        "target": 48.0,
        "action": (
            "On the next shot clip, release with a higher forearm elevation "
            "(release_angle toward ~48° from horizontal)."
        ),
    },
    "elbow_angle_at_release": {
        "category": "shot",
        "low": 125.0,
        "target": 155.0,
        "action": (
            "At release, extend the shooting elbow further (elbow_angle_at_release "
            "toward ~155°)."
        ),
    },
    "first_step_burst": {
        "category": "drive",
        "low": 0.35,
        "target": 0.70,
        "action": (
            "On the next drive clip, cover more ground in the first two steps "
            "(raise first_step_burst in body-lengths)."
        ),
    },
    "arm_extension_at_release": {
        "category": "pass",
        "low": 130.0,
        "target": 160.0,
        "action": (
            "On the next pass clip, finish with a more extended passing arm "
            "(arm_extension_at_release toward ~160°)."
        ),
    },
}

SLOT_ACTIONS: dict[str, str] = {
    "perimeter_vs_rim": (
        "On the next shot clip, increase release elevation and follow-through arc "
        "so your perimeter_vs_rim slot moves toward this match."
    ),
    "creation": (
        "On the next pass clip, shorten catch-to-release time (decision_speed) "
        "so your creation slot moves toward this match."
    ),
    "drive_burst": (
        "On the next drive clip, explode into the first step and change direction "
        "so your drive_burst slot moves toward this match."
    ),
    "passing": (
        "On the next pass clip, repeat the same release point with a fuller arm "
        "extension so your passing slot moves toward this match."
    ),
}

SLOT_CATEGORY = {
    "perimeter_vs_rim": "shot",
    "creation": "pass",
    "passing": "pass",
    "drive_burst": "drive",
}

MISSING_CLIP_ACTIONS = {
    "drive": "Upload a drive clip so drive_burst can be scored — no drive advice until then.",
    "pass": "Upload a pass clip so creation/passing can be scored — no passing advice until then.",
    "shot": "Upload a shot clip so perimeter_vs_rim can be scored — no jumper advice until then.",
}


def _numeric_style(style: Any) -> dict[str, float]:
    if not isinstance(style, dict):
        return {}
    out: dict[str, float] = {}
    for key in STYLE_DIMS:
        value = style.get(key)
        if isinstance(value, (int, float)):
            out[key] = float(value)
    return out


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


def _percentile(value: float, population: list[float]) -> float | None:
    if not population:
        return None
    below = sum(1 for item in population if item < value)
    return below / len(population)


def build_why(
    *,
    match: dict,
    user_style: dict[str, float],
    user_height_in: float,
    height_z_nba: float | None,
    primary_skill: str | None,
    evidence: dict[str, bool],
    dims: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    nba_style = _numeric_style(match.get("style_vector"))
    if dims is not None:
        a = {k: user_style[k] for k in dims if k in user_style}
        b = {k: nba_style[k] for k in dims if k in nba_style}
    else:
        a, b = user_style, nba_style

    shared = [k for k in STYLE_DIMS if k in a and k in b]
    cosine = cosine_similarity(a, b)
    try:
        nba_h = float(match["height_in"])
    except (KeyError, TypeError, ValueError):
        nba_h = None

    band = height_band_inches(height_z_nba)
    size_term = (
        size_similarity(user_height_in, nba_h, band) if nba_h is not None else None
    )
    skill = primary_skill_bonus(primary_skill, nba_style)

    slots = []
    for dim in shared:
        gap = abs(a[dim] - b[dim])
        slots.append(
            {
                "dim": dim,
                "user": round(a[dim], 4),
                "nba": round(b[dim], 4),
                "gap": round(gap, 4),
            }
        )
    slots.sort(key=lambda row: row["gap"])
    for index, row in enumerate(slots):
        row["contribution_rank"] = index + 1  # 1 = closest overlap

    omitted = [d for d in STYLE_DIMS if d not in shared]
    height_delta = None if nba_h is None else round(abs(float(user_height_in) - nba_h), 2)

    return {
        "label": "style",
        "filter": {
            "position": match.get("position"),
            "user_height_in": user_height_in,
            "nba_height_in": nba_h,
            "height_z_nba": None if height_z_nba is None else round(float(height_z_nba), 4),
            "band_in": band,
            "height_delta_in": height_delta,
        },
        "score_terms": {
            "cosine": None if cosine is None else round(cosine, 4),
            "size_similarity": None if size_term is None else round(size_term, 4),
            "primary_skill_bonus": round(skill, 4),
            "weights": {"style": 0.75, "size": 0.20, "skill": 0.05},
            "total": match.get("score"),
        },
        "slots": slots,
        "omitted_slots": omitted,
        "evidence": dict(evidence),
        "note": "Style similarity, not identical motion and not a joint-angle match.",
    }


def annotate_matches_with_why(
    ranked: dict[str, Any],
    *,
    user_style: dict[str, float],
    user_height_in: float,
    height_z_nba: float | None,
    primary_skill: str | None,
    evidence: dict[str, bool],
) -> dict[str, Any]:
    overall = []
    for match in ranked.get("overall") or []:
        item = dict(match)
        item["why"] = build_why(
            match=item,
            user_style=user_style,
            user_height_in=user_height_in,
            height_z_nba=height_z_nba,
            primary_skill=primary_skill,
            evidence=evidence,
        )
        overall.append(item)

    by_category: dict[str, list[dict]] = {}
    for category, matches in (ranked.get("by_category") or {}).items():
        dims = CATEGORY_DIMS.get(category)
        annotated = []
        for match in matches:
            item = dict(match)
            item["why"] = build_why(
                match=item,
                user_style=user_style,
                user_height_in=user_height_in,
                height_z_nba=height_z_nba,
                primary_skill=primary_skill,
                evidence=evidence,
                dims=dims,
            )
            annotated.append(item)
        by_category[category] = annotated

    return {**ranked, "overall": overall, "by_category": by_category}


def _pose_recs(mechanics: dict[str, float], evidence: dict[str, bool], counts: dict[str, int]) -> list[dict]:
    recs: list[dict] = []
    for feature, spec in POSE_TARGETS.items():
        category = spec["category"]
        if not evidence.get(category):
            continue
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
        recs.append(
            {
                "target": feature,
                "category": category,
                "current_value": round(current, 4),
                "reference": target,
                "reference_kind": "pose_range",
                "clip_count": counts.get(feature, 1),
                "gap": round(abs(current - target), 4),
                "action": spec["action"],
                "because": (
                    f"{feature}={current:.3f} (n={counts.get(feature, 1)} clips) "
                    f"vs target {target:g}."
                ),
            }
        )
    return recs


def _match_slot_recs(
    user_style: dict[str, float],
    match: dict,
    evidence: dict[str, bool],
) -> list[dict]:
    recs: list[dict] = []
    nba_style = _numeric_style(match.get("style_vector"))
    name = match.get("name") or "this match"
    for dim, action in SLOT_ACTIONS.items():
        category = SLOT_CATEGORY[dim]
        if not evidence.get(category):
            continue
        if dim not in user_style or dim not in nba_style:
            continue
        user_v = user_style[dim]
        nba_v = nba_style[dim]
        gap = abs(user_v - nba_v)
        if gap < 0.08:
            continue
        recs.append(
            {
                "target": dim,
                "category": category,
                "current_value": round(user_v, 4),
                "reference": round(nba_v, 4),
                "reference_kind": "match_slot",
                "match_name": name,
                "gap": round(gap, 4),
                "action": action,
                "because": (
                    f"{dim} user={user_v:.3f} vs {name}={nba_v:.3f} (gap {gap:.3f})."
                ),
            }
        )
    return recs


def _cohort_recs(
    user_style: dict[str, float],
    eligible: list[dict],
    evidence: dict[str, bool],
) -> list[dict]:
    recs: list[dict] = []
    for dim, category in SLOT_CATEGORY.items():
        if not evidence.get(category):
            continue
        if dim not in user_style:
            continue
        population = []
        for player in eligible:
            style = _numeric_style(player.get("style_vector"))
            if dim in style:
                population.append(style[dim])
        pct = _percentile(user_style[dim], population)
        if pct is None or not population:
            continue
        # Rec only if the user is in a tail vs the same-position height-band pool.
        if 0.25 <= pct <= 0.75:
            continue
        target = sorted(population)[len(population) // 2]
        recs.append(
            {
                "target": dim,
                "category": category,
                "current_value": round(user_style[dim], 4),
                "reference": round(pct, 4),
                "reference_kind": "cohort_percentile",
                "cohort_median": round(target, 4),
                "cohort_n": len(population),
                "gap": round(abs(user_style[dim] - target), 4),
                "action": SLOT_ACTIONS[dim],
                "because": (
                    f"{dim}={user_style[dim]:.3f} is percentile {pct:.2f} "
                    f"among {len(population)} same-position NBA players in the height band "
                    f"(median {target:.3f})."
                ),
            }
        )
    return recs


def _missing_evidence_recs(evidence: dict[str, bool]) -> list[dict]:
    recs: list[dict] = []
    for category, action in MISSING_CLIP_ACTIONS.items():
        if evidence.get(category):
            continue
        recs.append(
            {
                "target": f"missing_{category}_clip",
                "category": category,
                "current_value": 0.0,
                "reference": 1.0,
                "reference_kind": "missing_evidence",
                "gap": 0.15,
                "action": action,
                "because": f"No {category} clips in the aggregated profile.",
            }
        )
    return recs


def build_recommendations(
    *,
    mechanics: dict[str, float],
    user_style: dict[str, float],
    evidence: dict[str, bool],
    overall_matches: list[dict],
    eligible: list[dict],
    agg: Iterable[dict] | None = None,
    limit: int = 3,
) -> list[dict]:
    counts = _clip_counts(agg or [])
    top = overall_matches[0] if overall_matches else {}
    candidates = [
        *_pose_recs(mechanics, evidence, counts),
        *_match_slot_recs(user_style, top, evidence),
        *_cohort_recs(user_style, eligible, evidence),
        *_missing_evidence_recs(evidence),
    ]
    # Prefer numeric gaps from evidence we have; missing-clip recs sort last.
    candidates.sort(
        key=lambda row: (
            1 if row["reference_kind"] == "missing_evidence" else 0,
            -float(row.get("gap") or 0),
        )
    )
    picked: list[dict] = []
    seen: set[str] = set()
    for rec in candidates:
        key = rec["target"]
        if key in seen:
            continue
        seen.add(key)
        picked.append(rec)
        if len(picked) >= limit:
            break
    return picked


def build_llm_prompt(
    *,
    questionnaire: dict[str, Any],
    mechanics: dict[str, float],
    user_style: dict[str, float],
    top_match: dict | None,
    why: dict | None,
    recommendations: list[dict],
) -> str:
    import json

    return (
        "You explain a basketball STYLE similarity result that was already computed. "
        "Do not pick a different NBA player. Do not invent statistics, game history, "
        "or drills. Do not say a joint angle equals a shooting percentage. "
        "Do not give generic advice unless a rec candidate supports it with numbers.\n\n"
        f"QUESTIONNAIRE:\n{json.dumps(questionnaire, indent=2)}\n\n"
        f"USER_STYLE:\n{json.dumps(user_style, indent=2)}\n\n"
        f"MECHANICS (pose, with clip evidence only):\n{json.dumps(mechanics, indent=2)}\n\n"
        f"TOP_MATCH:\n{json.dumps(top_match or {}, indent=2, default=str)}\n\n"
        f"WHY_THIS_MATCH:\n{json.dumps(why or {}, indent=2, default=str)}\n\n"
        f"REC_CANDIDATES:\n{json.dumps(recommendations, indent=2)}\n\n"
        "Write exactly two sections:\n"
        "## Why this match\n"
        "1–2 short paragraphs walking through the filter and the closest / largest "
        "style-slot gaps. State that this is play-style, not identical motion.\n\n"
        "## Personalized next steps\n"
        "2–3 bullets. Each bullet must cite a candidate's current_value and reference. "
        "Do not add a drill that is not in REC_CANDIDATES.\n"
    )
