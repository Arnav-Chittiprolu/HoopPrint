from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompMatch(BaseModel):
    model_config = ConfigDict(extra="allow")

    player_id: int | None = None
    name: str
    season: str | None = None
    position: str | None = None
    height_in: float | None = None
    score: float
    style_vector: dict[str, float] = Field(default_factory=dict)
    role_vector: dict[str, float] = Field(default_factory=dict)
    kind: str = "role_profile"
    resemblance_band: str | None = None
    match_confidence: int | None = None
    comp_bucket: str | None = None
    body_mismatch: bool | None = None
    body_plausibility: float | None = None
    height_delta_in: float | None = None
    why: dict[str, Any] | None = None


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="allow")

    target: str
    category: str | None = None
    current_value: float | None = None
    reference: float | None = None
    reference_kind: str
    action: str
    because: str
    gap: float | None = None
    clip_count: int | None = None
    match_name: str | None = None
    cohort_median: float | None = None
    cohort_n: int | None = None


class CompResultResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: UUID | None = None
    user_id: UUID
    created_at: datetime | None = None
    season: str | None = None
    label: str = "role_profile"
    comparison_mode: str | None = None
    user_style: dict[str, float] = Field(default_factory=dict)
    user_role_vector: dict[str, float] = Field(default_factory=dict)
    evidence: dict[str, bool] = Field(default_factory=dict)
    evidence_tier: str | None = None
    mechanics: dict[str, float] = Field(default_factory=dict)
    overall: list[CompMatch] = Field(default_factory=list)
    style_only: list[CompMatch] = Field(default_factory=list)
    by_category: dict[str, list[CompMatch]] = Field(default_factory=dict)
    pool_size: int = 0
    pool_sentence: str | None = None
    physical_context: str | None = None
    pool_confidence: str | None = None
    recommendations: list[Recommendation] = Field(default_factory=list)
    mechanics_recs: list[Recommendation] = Field(default_factory=list)
    role_recs: list[Recommendation] = Field(default_factory=list)
    archetype_result: dict[str, Any] = Field(default_factory=dict)
    named_matches_suppressed: bool | None = None
    suppression_reason: str | None = None
    active_dimensions: list[str] = Field(default_factory=list)
    excluded_dimensions: list[str] = Field(default_factory=list)
    height_z_us: float | None = None
    height_z_nba: float | None = None
    valid_event_count: int | None = None
    inputs_snapshot: dict[str, Any] = Field(default_factory=dict)
    stale: bool = False
    stale_reasons: list[str] = Field(default_factory=list)
    summary: str | None = None


class CompRunResponse(CompResultResponse):
    """POST /me/comp response — same shape as latest GET."""
