"""Map role-profile Pydantic records ↔ Postgres row shapes."""

from __future__ import annotations

from typing import Any

from app.models.role_profile import (
    ClipEventRecord,
    EvidenceTier,
    RoleDimension,
    RoleDimensionState,
    RoleDimensionStatus,
    UserRoleProfileRecord,
    UserRoleVector,
)


def _dimension_prefix(dimension: RoleDimension) -> str:
    if dimension == RoleDimension.catch_readiness:
        return "catch_readiness"
    if dimension == RoleDimension.rim_pressure:
        return "rim_pressure"
    return "playmaking"


def clip_event_to_row(event: ClipEventRecord) -> dict[str, Any]:
    row: dict[str, Any] = {
        "clip_id": str(event.clip_id),
        "user_id": str(event.user_id),
        "role_dimension": event.role_dimension.value,
        "event_index": event.event_index,
        "gate_passed": event.gate_passed,
        "rejection_reason": event.rejection_reason,
        "signal_values": event.signal_values,
        "quality": event.quality,
        "fps": event.fps,
        "burst_window_ms": event.burst_window_ms,
        "event_confidence": event.event_confidence,
    }
    if event.session_date is not None:
        row["session_date"] = event.session_date.isoformat()
    return row


def _state_to_columns(prefix: str, state: RoleDimensionState) -> dict[str, Any]:
    return {
        f"{prefix}_value": state.value,
        f"{prefix}_percentile": state.percentile,
        f"{prefix}_event_count": state.event_count,
        f"{prefix}_session_count": state.session_count,
        f"{prefix}_confidence": state.confidence,
        f"{prefix}_stability": state.stability,
        f"{prefix}_status": state.status.value,
    }


def user_role_profile_to_row(profile: UserRoleProfileRecord) -> dict[str, Any]:
    row: dict[str, Any] = {
        "user_id": str(profile.user_id),
        "profile_version": profile.profile_version,
        "reference_population_version": profile.reference_population_version,
        "role_vector": profile.role_vector.model_dump(exclude_none=True),
        "active_dimensions": [d.value for d in profile.active_dimensions],
        "quality_summary": profile.quality_summary,
        "evidence_tier": profile.evidence_tier.value,
    }
    row.update(_state_to_columns("catch_readiness", profile.catch_readiness))
    row.update(_state_to_columns("rim_pressure", profile.rim_pressure))
    row.update(_state_to_columns("playmaking", profile.playmaking))
    return row


def user_role_profile_from_row(row: dict[str, Any]) -> UserRoleProfileRecord:
    rv = row.get("role_vector") or {}
    return UserRoleProfileRecord(
        id=row.get("id"),
        user_id=row["user_id"],
        profile_version=row["profile_version"],
        reference_population_version=row.get("reference_population_version"),
        catch_readiness=RoleDimensionState(
            value=row.get("catch_readiness_value"),
            percentile=row.get("catch_readiness_percentile"),
            event_count=row.get("catch_readiness_event_count") or 0,
            session_count=row.get("catch_readiness_session_count") or 0,
            confidence=row.get("catch_readiness_confidence"),
            stability=row.get("catch_readiness_stability"),
            status=RoleDimensionStatus(row.get("catch_readiness_status", "not_observed")),
        ),
        rim_pressure=RoleDimensionState(
            value=row.get("rim_pressure_value"),
            percentile=row.get("rim_pressure_percentile"),
            event_count=row.get("rim_pressure_event_count") or 0,
            session_count=row.get("rim_pressure_session_count") or 0,
            confidence=row.get("rim_pressure_confidence"),
            stability=row.get("rim_pressure_stability"),
            status=RoleDimensionStatus(row.get("rim_pressure_status", "not_observed")),
        ),
        playmaking=RoleDimensionState(
            value=row.get("playmaking_value"),
            percentile=row.get("playmaking_percentile"),
            event_count=row.get("playmaking_event_count") or 0,
            session_count=row.get("playmaking_session_count") or 0,
            confidence=row.get("playmaking_confidence"),
            stability=row.get("playmaking_stability"),
            status=RoleDimensionStatus(row.get("playmaking_status", "not_observed")),
        ),
        role_vector=UserRoleVector(
            catch_readiness=rv.get("catch_readiness"),
            rim_pressure_tendency=rv.get("rim_pressure_tendency"),
            playmaking_orientation=rv.get("playmaking_orientation"),
        ),
        active_dimensions=[RoleDimension(v) for v in (row.get("active_dimensions") or [])],
        quality_summary=row.get("quality_summary") or {},
        evidence_tier=EvidenceTier(row.get("evidence_tier", "insufficient")),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )
