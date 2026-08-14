from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    individual = "individual"
    gameplay = "gameplay"


class ClipType(str, Enum):
    shot = "shot"
    pass_clip = "pass"
    drive = "drive"


class ClipStatus(str, Enum):
    uploaded = "uploaded"
    awaiting_bbox = "awaiting_bbox"
    processing = "processing"
    done = "done"
    failed = "failed"


class ClipResponse(BaseModel):
    id: UUID
    user_id: UUID
    source_type: SourceType
    clip_type: ClipType
    storage_path: str
    status: ClipStatus
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class ClipCreateResponse(ClipResponse):
    pass
