"""Aggregate gated clip_events into user_role_profile (Phase 10.3).

Percentile fields stay null until a documented amateur reference population exists.
Latent role-vector scores are 0–1 transforms of gated event signals — not NBA percentiles
and not mechanics features.
"""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Iterable
from uuid import UUID

from app.models.role_profile import (
    ClipEventRecord,
    EvidenceTier,
    RoleDimension,
    RoleDimensionState,
    RoleDimensionStatus,
    UserRoleProfileRecord,
    UserRoleVector,
    validate_role_vector_payload,
)
from app.services.role_profile.constants import (
    BOOTSTRAP_ITERATIONS,
    BOOTSTRAP_SD_MAX,
    CATCH_RELEASE_MAX_S,
    CATCH_RELEASE_MIN_S,
    MIN_EVENT_CONFIDENCE_FOR_EMERGING,
    MIN_EVENT_CONFIDENCE_FOR_ESTABLISHED,
    MIN_EVENTS_DIMENSION_EMERGING,
    MIN_EVENTS_DIMENSION_ESTABLISHED,
    MIN_EVENTS_OVERALL_ESTABLISHED,
    MIN_EVENTS_OVERALL_STRONG,
    PLAYMAKING_EXTENSION_FLOOR_DEG,
    PLAYMAKING_EXTENSION_SPAN_DEG,
    PULL_UP_LATENT,
    RIM_BURST_LATENT_SCALE,
    ROLE_PROFILE_VERSION,
    ROLE_VECTOR_KEYS,
)


SIGNAL_KEYS: dict[RoleDimension, str] = {
    RoleDimension.catch_readiness: "catch_to_release_s",
    RoleDimension.rim_pressure: "burst_body_lengths",
    RoleDimension.playmaking: "arm_extension_deg",
}

VECTOR_KEY: dict[RoleDimension, str] = {
    RoleDimension.catch_readiness: "catch_readiness",
    RoleDimension.rim_pressure: "rim_pressure_tendency",
    RoleDimension.playmaking: "playmaking_orientation",
}

_STATUS_RANK = {
    RoleDimensionStatus.not_observed: 0,
    RoleDimensionStatus.suppressed_low_quality: 1,
    RoleDimensionStatus.insufficient: 2,
    RoleDimensionStatus.emerging: 3,
    RoleDimensionStatus.established: 4,
}

_TIER_RANK = {
    EvidenceTier.insufficient: 0,
    EvidenceTier.emerging: 1,
    EvidenceTier.established: 2,
    EvidenceTier.strong: 3,
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return float(ordered[mid - 1] + ordered[mid]) / 2.0


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * p
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return float(ordered[lo] * (1.0 - frac) + ordered[hi] * frac)


def iqr(values: list[float]) -> float | None:
    lo = percentile(values, 0.25)
    hi = percentile(values, 0.75)
    if lo is None or hi is None:
        return None
    return float(hi - lo)


def mad(values: list[float], center: float | None = None) -> float | None:
    if not values:
        return None
    mid = center if center is not None else median(values)
    if mid is None:
        return None
    return median([abs(v - mid) for v in values])


def event_raw_signal(event: ClipEventRecord) -> float | None:
    key = SIGNAL_KEYS[event.role_dimension]
    raw = event.signal_values.get(key)
    if isinstance(raw, (int, float)):
        return float(raw)
    return None


def event_latent_score(event: ClipEventRecord) -> float | None:
    """Map a gated event onto ~[0, 1]. Higher = stronger tendency on that dimension."""
    if event.role_dimension == RoleDimension.catch_readiness:
        origin = (event.signal_values or {}).get("shot_origin")
        if origin == "pull_up":
            return PULL_UP_LATENT
        raw = event_raw_signal(event)
        if raw is None:
            return None
        span = CATCH_RELEASE_MAX_S - CATCH_RELEASE_MIN_S
        if span <= 0:
            return None
        timed = max(float(raw), CATCH_RELEASE_MIN_S)
        return _clamp01(1.0 - (timed - CATCH_RELEASE_MIN_S) / span)
    raw = event_raw_signal(event)
    if raw is None:
        return None
    if event.role_dimension == RoleDimension.rim_pressure:
        return _clamp01(raw / RIM_BURST_LATENT_SCALE)
    return _clamp01((raw - PLAYMAKING_EXTENSION_FLOOR_DEG) / PLAYMAKING_EXTENSION_SPAN_DEG)


def _session_key(event: ClipEventRecord) -> date | None:
    if event.session_date is not None:
        return event.session_date
    if event.created_at is not None:
        return event.created_at.date()
    return None


def _dimension_band(latent: float | None) -> str:
    if latent is None:
        return "unknown"
    if latent >= 0.66:
        return "high"
    if latent <= 0.33:
        return "low"
    return "mid"


def bootstrap_stability(
    latents: list[float],
    *,
    n_iter: int = BOOTSTRAP_ITERATIONS,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Resample event latents; return SD of medians and band-agreement rate."""
    source = rng or random.Random()
    n = len(latents)
    if n == 0:
        return {
            "bootstrap_n": 0,
            "bootstrap_sd": None,
            "ci80_low": None,
            "ci80_high": None,
            "band_agreement_rate": None,
            "stable": False,
        }
    if n == 1:
        return {
            "bootstrap_n": n_iter,
            "bootstrap_sd": 0.0,
            "ci80_low": latents[0],
            "ci80_high": latents[0],
            "band_agreement_rate": 1.0,
            "stable": False,
        }

    medians: list[float] = []
    bands: list[str] = []
    base_band = _dimension_band(median(latents))
    for _ in range(n_iter):
        sample = [latents[source.randrange(n)] for _ in range(n)]
        med = median(sample)
        assert med is not None
        medians.append(med)
        bands.append(_dimension_band(med))

    sd = (sum((m - sum(medians) / len(medians)) ** 2 for m in medians) / len(medians)) ** 0.5
    agreement = sum(1 for b in bands if b == base_band) / len(bands)
    return {
        "bootstrap_n": n_iter,
        "bootstrap_sd": float(sd),
        "ci80_low": percentile(medians, 0.10),
        "ci80_high": percentile(medians, 0.90),
        "band_agreement_rate": float(agreement),
        "stable": n >= 5 and sd <= BOOTSTRAP_SD_MAX,
    }


def dimension_status(
    *,
    event_count: int,
    session_count: int,
    median_confidence: float | None,
    stable: bool,
) -> RoleDimensionStatus:
    if event_count <= 0:
        return RoleDimensionStatus.not_observed
    if (
        event_count >= MIN_EVENTS_DIMENSION_EMERGING
        and median_confidence is not None
        and median_confidence < MIN_EVENT_CONFIDENCE_FOR_EMERGING
    ):
        return RoleDimensionStatus.suppressed_low_quality
    if event_count < MIN_EVENTS_DIMENSION_EMERGING:
        return RoleDimensionStatus.insufficient
    if (
        event_count >= MIN_EVENTS_DIMENSION_ESTABLISHED
        and (median_confidence is None or median_confidence >= MIN_EVENT_CONFIDENCE_FOR_ESTABLISHED)
    ):
        return RoleDimensionStatus.established
    if event_count >= MIN_EVENTS_DIMENSION_EMERGING and (
        median_confidence is None or median_confidence >= MIN_EVENT_CONFIDENCE_FOR_EMERGING
    ):
        return RoleDimensionStatus.emerging
    return RoleDimensionStatus.insufficient


def overall_evidence_tier(
    states: dict[RoleDimension, RoleDimensionState],
    *,
    overall_stable: bool,
) -> EvidenceTier:
    active = [
        dim
        for dim, state in states.items()
        if _STATUS_RANK[state.status] >= _STATUS_RANK[RoleDimensionStatus.emerging]
    ]
    if not active:
        return EvidenceTier.insufficient

    total_events = sum(state.event_count for state in states.values())

    if total_events >= MIN_EVENTS_OVERALL_STRONG and overall_stable:
        return EvidenceTier.strong
    if total_events >= MIN_EVENTS_OVERALL_ESTABLISHED:
        return EvidenceTier.established
    return EvidenceTier.emerging


def _parse_event_row(row: dict[str, Any]) -> ClipEventRecord | None:
    try:
        dim = RoleDimension(row["role_dimension"])
        session = row.get("session_date")
        session_date: date | None = None
        if isinstance(session, date) and not isinstance(session, datetime):
            session_date = session
        elif isinstance(session, str) and session:
            session_date = date.fromisoformat(session[:10])
        created = row.get("created_at")
        created_at: datetime | None = None
        if isinstance(created, datetime):
            created_at = created
        elif isinstance(created, str) and created:
            created_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
        return ClipEventRecord(
            id=row.get("id"),
            clip_id=row["clip_id"] if isinstance(row["clip_id"], UUID) else UUID(str(row["clip_id"])),
            user_id=row["user_id"] if isinstance(row["user_id"], UUID) else UUID(str(row["user_id"])),
            role_dimension=dim,
            event_index=int(row.get("event_index") or 0),
            gate_passed=bool(row.get("gate_passed")),
            rejection_reason=row.get("rejection_reason"),
            signal_values=row.get("signal_values") or {},
            quality=row.get("quality") or {},
            fps=row.get("fps"),
            burst_window_ms=row.get("burst_window_ms"),
            event_confidence=row.get("event_confidence"),
            session_date=session_date,
            created_at=created_at,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _aggregate_dimension(
    events: list[ClipEventRecord],
    *,
    rng: random.Random | None,
    n_iter: int,
) -> tuple[RoleDimensionState, dict[str, Any], float | None]:
    if not events:
        return RoleDimensionState(), {"event_count": 0}, None

    raws = [v for e in events if (v := event_raw_signal(e)) is not None]
    latents = [v for e in events if (v := event_latent_score(e)) is not None]
    confidences = [float(e.event_confidence) for e in events if e.event_confidence is not None]
    sessions = {s for e in events if (s := _session_key(e)) is not None}

    raw_med = median(raws)
    latent_med = median(latents)
    conf_med = median(confidences)
    boot = bootstrap_stability(latents, n_iter=n_iter, rng=rng) if latents else {
        "bootstrap_n": 0,
        "bootstrap_sd": None,
        "ci80_low": None,
        "ci80_high": None,
        "band_agreement_rate": None,
        "stable": False,
    }
    stable = bool(boot["stable"])
    status = dimension_status(
        event_count=len(events),
        session_count=len(sessions),
        median_confidence=conf_med,
        stable=stable,
    )
    stability_score = None
    sd = boot.get("bootstrap_sd")
    if isinstance(sd, (int, float)):
        stability_score = _clamp01(1.0 - float(sd) / BOOTSTRAP_SD_MAX)

    state = RoleDimensionState(
        value=raw_med,
        percentile=None,
        event_count=len(events),
        session_count=len(sessions),
        confidence=conf_med,
        stability=stability_score,
        status=status,
    )
    summary = {
        "event_count": len(events),
        "session_count": len(sessions),
        "raw_median": raw_med,
        "latent_median": latent_med,
        "iqr": iqr(raws) if raws else None,
        "mad": mad(raws, raw_med) if raws else None,
        "median_confidence": conf_med,
        "band": _dimension_band(latent_med),
        **boot,
    }
    vector_value = latent_med if status != RoleDimensionStatus.not_observed and status != RoleDimensionStatus.insufficient and status != RoleDimensionStatus.suppressed_low_quality else None
    if status == RoleDimensionStatus.insufficient:
        vector_value = None
    return state, summary, vector_value


def aggregate_role_profile(
    events: Iterable[ClipEventRecord | dict[str, Any]],
    *,
    user_id: UUID | str,
    rng: random.Random | None = None,
    n_iter: int = BOOTSTRAP_ITERATIONS,
) -> UserRoleProfileRecord:
    """Build user_role_profile from gated events only (no mechanics keys)."""
    parsed: list[ClipEventRecord] = []
    for item in events:
        if isinstance(item, ClipEventRecord):
            rec = item
        else:
            rec = _parse_event_row(item)
        if rec is None or not rec.gate_passed:
            continue
        parsed.append(rec)

    by_dim: dict[RoleDimension, list[ClipEventRecord]] = defaultdict(list)
    for rec in parsed:
        by_dim[rec.role_dimension].append(rec)

    source = rng or random.Random()
    states: dict[RoleDimension, RoleDimensionState] = {}
    summaries: dict[str, Any] = {}
    vector_parts: dict[str, float] = {}

    for dim in RoleDimension:
        state, summary, latent = _aggregate_dimension(
            by_dim.get(dim, []),
            rng=source,
            n_iter=n_iter,
        )
        states[dim] = state
        summaries[dim.value] = summary
        if latent is not None:
            vector_parts[VECTOR_KEY[dim]] = float(latent)

    validate_role_vector_payload(vector_parts)
    extra = set(vector_parts) - ROLE_VECTOR_KEYS
    if extra:
        raise ValueError(f"Unknown role vector keys: {sorted(extra)}")

    active = [
        dim
        for dim, state in states.items()
        if _STATUS_RANK[state.status] >= _STATUS_RANK[RoleDimensionStatus.emerging]
    ]
    dim_stable = [
        bool((summaries[d.value] or {}).get("stable"))
        for d in active
        if summaries.get(d.value)
    ]
    total_valid = sum(s.event_count for s in states.values())
    overall_stable = total_valid >= MIN_EVENTS_OVERALL_STRONG and (
        all(dim_stable) if dim_stable else False
    )
    tier = overall_evidence_tier(states, overall_stable=overall_stable)

    quality_summary = {
        "dimensions": summaries,
        "active_dimension_count": len(active),
        "total_valid_events": sum(s.event_count for s in states.values()),
        "overall_stable": overall_stable,
        "percentile_available": False,
        "reference_population": None,
    }

    return UserRoleProfileRecord(
        user_id=user_id if isinstance(user_id, UUID) else UUID(str(user_id)),
        profile_version=ROLE_PROFILE_VERSION,
        reference_population_version=None,
        catch_readiness=states[RoleDimension.catch_readiness],
        rim_pressure=states[RoleDimension.rim_pressure],
        playmaking=states[RoleDimension.playmaking],
        role_vector=UserRoleVector(
            catch_readiness=vector_parts.get("catch_readiness"),
            rim_pressure_tendency=vector_parts.get("rim_pressure_tendency"),
            playmaking_orientation=vector_parts.get("playmaking_orientation"),
        ),
        active_dimensions=active,
        quality_summary=quality_summary,
        evidence_tier=tier,
    )
