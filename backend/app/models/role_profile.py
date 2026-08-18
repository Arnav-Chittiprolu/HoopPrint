"""Phase 10 role-profile data contracts (§4.4–4.6, §5.6.1)."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.services.role_profile.constants import BANNED_MECHANICS_KEYS, ROLE_VECTOR_KEYS


class RoleDimension(str, Enum):
    catch_readiness = "catch_readiness"
    rim_pressure = "rim_pressure"
    playmaking = "playmaking"


class RoleDimensionStatus(str, Enum):
    not_observed = "not_observed"
    insufficient = "insufficient"
    emerging = "emerging"
    established = "established"
    suppressed_low_quality = "suppressed_low_quality"


class EvidenceTier(str, Enum):
    insufficient = "insufficient"
    emerging = "emerging"
    established = "established"
    strong = "strong"


class ComparisonMode(str, Enum):
    legacy_style = "legacy_style"
    role_profile_v1 = "role_profile_v1"


class SummaryStat(BaseModel):
    value: float | None = None
    n: int = 0
    std: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None


class MechanicsSummary(BaseModel):
    """Pose mechanics only — must not feed role scoring."""

    release_angle_deg: SummaryStat | None = None
    elbow_angle_deg: SummaryStat | None = None
    relative_release_height: SummaryStat | None = None
    wrist_rise_proxy: SummaryStat | None = None
    first_step_burst_body_lengths: SummaryStat | None = None
    pass_release_extension_deg: SummaryStat | None = None
    release_point_consistency: SummaryStat | None = None


class UserRoleVector(BaseModel):
    """Role-dimension evidence only."""

    catch_readiness: float | None = None
    rim_pressure_tendency: float | None = None
    playmaking_orientation: float | None = None


class NbaRoleVector(BaseModel):
    catch_readiness: float
    rim_pressure_tendency: float
    playmaking_orientation: float


class NbaFieldProvenance(BaseModel):
    raw_value: float | None = None
    raw_numerator: float | None = None
    raw_denominator: float | None = None
    season: str
    season_type: str = "Regular Season"
    endpoint_name: str
    endpoint_params: dict[str, Any] = Field(default_factory=dict)
    field_name: str
    transformation_version: str
    cohort_definition: str
    percentile: float | None = None
    sample_reliability: float | None = None
    fetched_at: datetime


class RoleDimensionState(BaseModel):
    value: float | None = None
    percentile: float | None = None
    event_count: int = 0
    session_count: int = 0
    confidence: float | None = None
    stability: float | None = None
    status: RoleDimensionStatus = RoleDimensionStatus.not_observed


class ClipEventRecord(BaseModel):
    id: UUID | None = None
    clip_id: UUID
    user_id: UUID
    role_dimension: RoleDimension
    event_index: int = 0
    gate_passed: bool = False
    rejection_reason: str | None = None
    signal_values: dict[str, Any] = Field(default_factory=dict)
    quality: dict[str, Any] = Field(default_factory=dict)
    fps: float | None = None
    burst_window_ms: int | None = None
    event_confidence: float | None = None
    session_date: date | None = None
    created_at: datetime | None = None


class UserRoleProfileRecord(BaseModel):
    id: UUID | None = None
    user_id: UUID
    profile_version: str
    reference_population_version: str | None = None
    catch_readiness: RoleDimensionState = Field(default_factory=RoleDimensionState)
    rim_pressure: RoleDimensionState = Field(default_factory=RoleDimensionState)
    playmaking: RoleDimensionState = Field(default_factory=RoleDimensionState)
    role_vector: UserRoleVector = Field(default_factory=UserRoleVector)
    active_dimensions: list[RoleDimension] = Field(default_factory=list)
    quality_summary: dict[str, Any] = Field(default_factory=dict)
    evidence_tier: EvidenceTier = EvidenceTier.insufficient
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CompAuditSnapshot(BaseModel):
    """Immutable comp_result fields for role_profile_v1."""

    user_role_profile_id: UUID | None = None
    profile_version: str | None = None
    nba_seed_version: str | None = None
    comparison_mode: ComparisonMode = ComparisonMode.legacy_style
    cohort_definition: dict[str, Any] = Field(default_factory=dict)
    active_dimensions: list[str] = Field(default_factory=list)
    excluded_dimensions: list[str] = Field(default_factory=list)
    dimension_contributions: dict[str, Any] = Field(default_factory=dict)
    candidate_results: list[dict[str, Any]] = Field(default_factory=list)
    archetype_result: dict[str, Any] = Field(default_factory=dict)
    evidence_tier: EvidenceTier | None = None
    stability_metrics: dict[str, Any] = Field(default_factory=dict)
    disclosure_version: str | None = None
    mechanics_recs: list[dict[str, Any]] = Field(default_factory=list)
    role_recs: list[dict[str, Any]] = Field(default_factory=list)


def validate_role_vector_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Reject mechanics keys and unknown slots before role scoring (§5.6.1)."""
    banned = set(data) & BANNED_MECHANICS_KEYS
    if banned:
        raise ValueError(f"Mechanics keys not allowed in role vector: {sorted(banned)}")
    extra = set(data) - ROLE_VECTOR_KEYS
    if extra:
        raise ValueError(f"Unknown role vector keys: {sorted(extra)}")
    return data
