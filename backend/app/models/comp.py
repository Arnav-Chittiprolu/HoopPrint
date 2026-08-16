from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CompMatch(BaseModel):
    player_id: int | None = None
    name: str
    season: str | None = None
    position: str | None = None
    height_in: float | None = None
    score: float
    style_vector: dict[str, float] = Field(default_factory=dict)
    kind: str = "style"
    why: dict[str, Any] | None = None


class Recommendation(BaseModel):
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
    id: UUID | None = None
    user_id: UUID
    created_at: datetime | None = None
    season: str | None = None
    label: str = "style"
    user_style: dict[str, float]
    evidence: dict[str, bool]
    mechanics: dict[str, float] = Field(default_factory=dict)
    overall: list[CompMatch]
    by_category: dict[str, list[CompMatch]] = Field(default_factory=dict)
    pool_size: int = 0
    recommendations: list[Recommendation] = Field(default_factory=list)
    height_z_us: float | None = None
    height_z_nba: float | None = None
    summary: str | None = None


class CompRunResponse(CompResultResponse):
    """POST /me/comp response — same shape as latest GET."""
