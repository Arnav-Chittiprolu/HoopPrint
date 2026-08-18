from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.auth import CurrentUser, get_current_user
from app.config import Settings, get_settings
from app.models.clip import ClipCreateResponse, ClipResponse, ClipStatus, ClipType, SourceType
from app.models.keypoint import ClipFeatureResponse, ClipProcessResponse, KeypointFrameResponse
from app.services.aggregate import average_features_by_name
from app.services.clip_processor import (
    ClipProcessingError,
    process_clip as run_clip_pipeline,
    remember_bbox_start_s,
)
from app.services.clip_validation import validate_clip_upload
from app.services.pose_extraction import extract_frame_jpeg
from app.services.pose_overlay import overlay_storage_path
from app.services.rate_limit import inflight_clips, process_limiter, upload_limiter
from app.services.role_profile.aggregate import aggregate_role_profile
from app.services.role_profile.db import user_role_profile_to_row
from app.services.supabase_client import SupabaseService
from app.services.track import validate_norm_box

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clips", tags=["clips"])
_process_jobs: set[asyncio.Task] = set()


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
        result = await run_clip_pipeline(clip_id, user_id)
        logger.info(
            "clip_process_done",
            extra={
                "event": "clip_process_done",
                "clip_id": clip_id,
                "user_id": user_id,
                "frames": result["frame_count"],
                "features": result.get("feature_count", 0),
            },
        )
    except ClipProcessingError as exc:
        logger.warning(
            "clip_process_failed",
            extra={
                "event": "clip_process_failed",
                "clip_id": clip_id,
                "user_id": user_id,
                "reason": str(exc),
            },
        )
    except Exception:
        logger.exception(
            "clip_process_crash",
            extra={"event": "clip_process_crash", "clip_id": clip_id, "user_id": user_id},
        )
    finally:
        inflight_clips.release(clip_id)


def _spawn_process_clip(clip_id: str, user_id: str) -> bool:
    """Start pose off-request. Returns False if this clip is already running."""
    if not inflight_clips.acquire(clip_id):
        logger.info(
            "clip_process_idempotent_skip",
            extra={"event": "clip_process_idempotent_skip", "clip_id": clip_id, "user_id": user_id},
        )
        return False
    task = asyncio.create_task(_run_process_clip(clip_id, user_id))
    _process_jobs.add(task)
    task.add_done_callback(_process_jobs.discard)
    return True


def _enforce_process_rate(user_id: str) -> None:
    allowed, retry_after = process_limiter.allow(user_id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many process requests. Try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )


@router.post("", response_model=ClipCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_clip(
    file: UploadFile = File(...),
    source_type: SourceType = Form(...),
    clip_type: ClipType = Form(...),
    user: CurrentUser = Depends(get_current_user),
    supabase: SupabaseService = Depends(get_supabase),
) -> ClipCreateResponse:
    allowed, retry_after = upload_limiter.allow(user.id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many uploads. Try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )
    if source_type == SourceType.individual:
        _enforce_process_rate(user.id)

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
        _spawn_process_clip(str(clip_id), user.id)

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


class ClipDeleteAllResponse(BaseModel):
    deleted: int


@router.delete("", response_model=ClipDeleteAllResponse)
async def delete_all_clips(
    user: CurrentUser = Depends(get_current_user),
    supabase: SupabaseService = Depends(get_supabase),
) -> ClipDeleteAllResponse:
    try:
        rows = await supabase.list_clips(user.id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to list clips: {exc}",
        ) from exc

    storage_paths: list[str] = []
    for row in rows:
        path = row.get("storage_path")
        if isinstance(path, str) and path:
            storage_paths.append(path)
            storage_paths.append(overlay_storage_path(path))

    try:
        await supabase.delete_storage_objects(storage_paths)
        await supabase.delete_clips_for_user(user.id)
        await supabase.replace_user_profile_agg(user.id, [])
        empty_profile = aggregate_role_profile([], user_id=user.id)
        await supabase.upsert_user_role_profile(user_role_profile_to_row(empty_profile))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to delete clips: {exc}",
        ) from exc

    return ClipDeleteAllResponse(deleted=len(rows))


async def _rebuild_user_aggregates(supabase: SupabaseService, user_id: str) -> None:
    features = await supabase.list_done_clip_features_for_user(user_id)
    await supabase.replace_user_profile_agg(user_id, average_features_by_name(features))
    events = await supabase.list_clip_events(user_id=user_id, gate_passed=True)
    profile = aggregate_role_profile(events, user_id=user_id)
    await supabase.upsert_user_role_profile(user_role_profile_to_row(profile))


class ClipDeleteResponse(BaseModel):
    deleted: str


@router.delete("/{clip_id}", response_model=ClipDeleteResponse)
async def delete_clip(
    clip_id: str,
    user: CurrentUser = Depends(get_current_user),
    supabase: SupabaseService = Depends(get_supabase),
) -> ClipDeleteResponse:
    try:
        clip = await supabase.get_clip(clip_id, user.id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch clip: {exc}",
        ) from exc

    if clip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    storage_paths: list[str] = []
    path = clip.get("storage_path")
    if isinstance(path, str) and path:
        storage_paths.append(path)
        storage_paths.append(overlay_storage_path(path))

    try:
        await supabase.delete_storage_objects(storage_paths)
        removed = await supabase.delete_clip_for_user(clip_id, user.id)
        if not removed:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")
        await _rebuild_user_aggregates(supabase, user.id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to delete clip: {exc}",
        ) from exc

    return ClipDeleteResponse(deleted=clip_id)


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


class ClipPatchRequest(BaseModel):
    clip_type: ClipType


@router.patch("/{clip_id}", response_model=ClipResponse)
async def patch_clip(
    clip_id: str,
    body: ClipPatchRequest,
    user: CurrentUser = Depends(get_current_user),
    supabase: SupabaseService = Depends(get_supabase),
) -> ClipResponse:
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
        row = await supabase.update_clip(clip_id, {"clip_type": body.clip_type.value})
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to update clip: {exc}",
        ) from exc

    return ClipResponse.model_validate(row)


@router.post("/{clip_id}/process", response_model=ClipProcessResponse)
async def kick_process_clip(
    clip_id: str,
    user: CurrentUser = Depends(get_current_user),
    supabase: SupabaseService = Depends(get_supabase),
) -> ClipProcessResponse:
    try:
        clip = await supabase.get_clip(clip_id, user.id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch clip: {exc}",
        ) from exc

    if clip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    if inflight_clips.contains(clip_id):
        return ClipProcessResponse(
            clip_id=clip_id, status=ClipStatus.processing.value, frame_count=0
        )

    if clip["source_type"] == SourceType.gameplay.value:
        box = await supabase.get_player_box(clip_id)
        if box is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Draw a player box on the first frame before processing",
            )
    elif clip["source_type"] != SourceType.individual.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported clip source type",
        )

    _enforce_process_rate(user.id)

    try:
        await supabase.update_clip(
            clip_id,
            {"status": ClipStatus.processing.value, "error_message": None},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to update clip: {exc}",
        ) from exc

    _spawn_process_clip(clip_id, user.id)
    return ClipProcessResponse(clip_id=clip_id, status=ClipStatus.processing.value, frame_count=0)


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


@router.get("/{clip_id}/features", response_model=list[ClipFeatureResponse])
async def list_clip_features(
    clip_id: str,
    user: CurrentUser = Depends(get_current_user),
    supabase: SupabaseService = Depends(get_supabase),
) -> list[ClipFeatureResponse]:
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
        rows = await supabase.list_clip_features(clip_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to list features: {exc}",
        ) from exc

    return [ClipFeatureResponse.model_validate(row) for row in rows]


class ClipEventResponse(BaseModel):
    clip_id: str
    role_dimension: str
    gate_passed: bool
    rejection_reason: str | None = None
    event_confidence: float | None = None


@router.get("/{clip_id}/events", response_model=list[ClipEventResponse])
async def list_clip_role_events(
    clip_id: str,
    user: CurrentUser = Depends(get_current_user),
    supabase: SupabaseService = Depends(get_supabase),
) -> list[ClipEventResponse]:
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
        rows = await supabase.list_clip_events(clip_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to list clip events: {exc}",
        ) from exc
    return [ClipEventResponse.model_validate(row) for row in rows]


class OverlayUrlResponse(BaseModel):
    url: str
    expires_in: int = 3600


@router.get("/{clip_id}/overlay-url", response_model=OverlayUrlResponse)
async def get_overlay_url(
    clip_id: str,
    user: CurrentUser = Depends(get_current_user),
    supabase: SupabaseService = Depends(get_supabase),
) -> OverlayUrlResponse:
    try:
        clip = await supabase.get_clip(clip_id, user.id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch clip: {exc}",
        ) from exc

    if clip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    path = overlay_storage_path(clip["storage_path"])
    try:
        exists = await supabase.storage_object_exists(path)
    except Exception:
        exists = False

    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pose overlay not ready for this clip",
        )

    try:
        url = await supabase.create_signed_url(path, expires_in=3600)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to sign overlay URL: {exc}",
        ) from exc

    return OverlayUrlResponse(url=url, expires_in=3600)


class BboxRequest(BaseModel):
    x: float = Field(..., ge=0, le=1)
    y: float = Field(..., ge=0, le=1)
    w: float = Field(..., gt=0, le=1)
    h: float = Field(..., gt=0, le=1)
    start_s: float = Field(0, ge=0)


class BboxResponse(BaseModel):
    clip_id: str
    x: float
    y: float
    w: float
    h: float
    start_s: float = 0
    status: str


@router.get("/{clip_id}/first-frame")
async def get_first_frame(
    clip_id: str,
    user: CurrentUser = Depends(get_current_user),
    supabase: SupabaseService = Depends(get_supabase),
    t: float = Query(0, ge=0, description="Seconds into the clip"),
) -> Response:
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
        video_bytes = await supabase.download_clip_file(clip["storage_path"])
        jpeg, duration = await asyncio.to_thread(
            extract_frame_jpeg,
            video_bytes,
            at_s=t,
            suffix=".mov" if str(clip["storage_path"]).lower().endswith(".mov") else ".mp4",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to extract frame: {exc}",
        ) from exc

    return Response(
        content=jpeg,
        media_type="image/jpeg",
        headers={"X-Video-Duration": f"{duration:.3f}"},
    )


@router.post("/{clip_id}/bbox", response_model=BboxResponse)
async def save_bbox(
    clip_id: str,
    body: BboxRequest,
    user: CurrentUser = Depends(get_current_user),
    supabase: SupabaseService = Depends(get_supabase),
) -> BboxResponse:
    try:
        clip = await supabase.get_clip(clip_id, user.id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch clip: {exc}",
        ) from exc

    if clip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")
    if clip["source_type"] != SourceType.gameplay.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Player box is only used for gameplay clips",
        )

    try:
        box = validate_norm_box(body.x, body.y, body.w, body.h)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if inflight_clips.contains(clip_id):
        return BboxResponse(
            clip_id=clip_id,
            x=box.x,
            y=box.y,
            w=box.w,
            h=box.h,
            start_s=body.start_s,
            status=ClipStatus.processing.value,
        )

    _enforce_process_rate(user.id)

    try:
        remember_bbox_start_s(clip_id, body.start_s)
        await supabase.upsert_player_box(
            clip_id, box.x, box.y, box.w, box.h, start_s=body.start_s
        )
        await supabase.update_clip(
            clip_id,
            {"status": ClipStatus.processing.value, "error_message": None},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to save player box: {exc}",
        ) from exc

    _spawn_process_clip(clip_id, user.id)
    return BboxResponse(
        clip_id=clip_id,
        x=box.x,
        y=box.y,
        w=box.w,
        h=box.h,
        start_s=body.start_s,
        status=ClipStatus.processing.value,
    )
