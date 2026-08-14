from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.services.aggregate import compute_height_z


class PlayerPosition(str, Enum):
    guard = "guard"
    wing = "wing"
    forward = "forward"
    center = "center"


class DominantHand(str, Enum):
    left = "left"
    right = "right"


class PrimarySkill(str, Enum):
    shot = "shot"
    pass_skill = "pass"
    drive = "drive"


class AggregatedFeature(BaseModel):
    feature_name: str
    value: float
    clip_count: int
    updated_at: datetime | None = None


class ProfileQuestionnaire(BaseModel):
    display_name: str | None = None
    height_in: float | None = None
    height_z: float | None = None
    position: PlayerPosition | None = None
    dominant_hand: DominantHand | None = None
    primary_skill: PrimarySkill | None = None


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = None
    height_in: float | None = Field(default=None, ge=48, le=96)
    position: PlayerPosition | None = None
    dominant_hand: DominantHand | None = None
    primary_skill: PrimarySkill | None = None

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    def to_db_patch(self) -> dict:
        patch: dict = {}
        data = self.model_dump(exclude_unset=True)
        for key, value in data.items():
            if hasattr(value, "value"):
                patch[key] = value.value
            else:
                patch[key] = value
        if "height_in" in data:
            patch["height_z"] = compute_height_z(data.get("height_in"))
        return patch


class ProfileResponse(BaseModel):
    id: UUID
    email: str | None = None
    questionnaire: ProfileQuestionnaire
    aggregated_features: list[AggregatedFeature] = []


class HistoryPoint(BaseModel):
    clip_id: UUID
    clip_type: str
    feature_name: str
    value: float
    created_at: datetime
