from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status

from app.auth import CurrentUser, get_current_user
from app.config import Settings, get_settings
from app.models.clip import ClipCreateResponse, ClipResponse, ClipStatus, ClipType, SourceType
from app.models.keypoint import ClipProcessResponse, KeypointFrameResponse
from app.services.clip_processor import ClipProcessingError, process_individual_clip
from app.services.clip_validation import validate_clip_upload
from app.services.supabase_client import SupabaseService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clips", tags=["clips"])


def get_supabase(settings: Settings = Depends(get_settings)) -> SupabaseService:
    try:
        return SupabaseService(settings)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


async def _run_process_clip(clip_id: str, user_id: str) -> None:
    try:
        result = await process_individual_clip(clip_id, user_id)
        logger.info("Processed clip %s (%s frames)", clip_id, result["frame_count"])
    except ClipProcessingError as exc:
        logger.warning("Background processing failed for clip %s: %s", clip_id, exc)


@router.post("", response_model=ClipCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_clip(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source_type: SourceType = Form(...),
    clip_type: ClipType = Form(...),
    user: CurrentUser = Depends(get_current_user),
    supabase: SupabaseService = Depends(get_supabase),
) -> ClipCreateResponse:
    content, content_type = await validate_clip_upload(file)

    clip_id = uuid4()
    extension = ".mp4" if content_type == "video/mp4" else ".mov"
    storage_path = f"{user.id}/{clip_id}{extension}"
    initial_status = (
        ClipStatus.awaiting_bbox.value
        if source_type == SourceType.gameplay
        else ClipStatus.uploaded.value
    )

    try:
        await supabase.upload_clip_file(storage_path, content, content_type)
        row = await supabase.insert_clip(
            {
                "id": str(clip_id),
                "user_id": user.id,
                "source_type": source_type.value,
                "clip_type": clip_type.value,
                "storage_path": storage_path,
                "status": initial_status,
            }
        )
    except Exception as exc:
        try:
            await supabase.delete_clip_file(storage_path)
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to store clip: {exc}",
        ) from exc

    if source_type == SourceType.individual:
        background_tasks.add_task(_run_process_clip, str(clip_id), user.id)

    return ClipCreateResponse.model_validate(row)


@router.get("", response_model=list[ClipResponse])
async def list_clips(
    user: CurrentUser = Depends(get_current_user),
    supabase: SupabaseService = Depends(get_supabase),
) -> list[ClipResponse]:
    try:
        rows = await supabase.list_clips(user.id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to list clips: {exc}",
        ) from exc
    return [ClipResponse.model_validate(row) for row in rows]


@router.get("/{clip_id}", response_model=ClipResponse)
async def get_clip(
    clip_id: str,
    user: CurrentUser = Depends(get_current_user),
    supabase: SupabaseService = Depends(get_supabase),
) -> ClipResponse:
    try:
        row = await supabase.get_clip(clip_id, user.id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch clip: {exc}",
        ) from exc

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    return ClipResponse.model_validate(row)


@router.post("/{clip_id}/process", response_model=ClipProcessResponse)
async def process_clip(
    clip_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> ClipProcessResponse:
    try:
        result = await process_individual_clip(clip_id, user.id)
    except ClipProcessingError as exc:
        message = str(exc)
        if message == "Clip not found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc

    clip = result["clip"]
    return ClipProcessResponse(
        clip_id=clip["id"],
        status=clip["status"],
        frame_count=result["frame_count"],
    )


@router.get("/{clip_id}/keypoints", response_model=list[KeypointFrameResponse])
async def list_clip_keypoints(
    clip_id: str,
    user: CurrentUser = Depends(get_current_user),
    supabase: SupabaseService = Depends(get_supabase),
) -> list[KeypointFrameResponse]:
    try:
        clip = await supabase.get_clip(clip_id, user.id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch clip: {exc}",
        ) from exc

    if clip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    try:
        rows = await supabase.list_keypoints(clip_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to list keypoints: {exc}",
        ) from exc

    return [KeypointFrameResponse.model_validate(row) for row in rows]
