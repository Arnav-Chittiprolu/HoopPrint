from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class KeypointFrameResponse(BaseModel):
    id: UUID
    clip_id: UUID
    frame_index: int
    keypoints: dict
    track_confidence: float | None = None
    created_at: datetime


class ClipProcessResponse(BaseModel):
    clip_id: UUID
    status: str
    frame_count: int
