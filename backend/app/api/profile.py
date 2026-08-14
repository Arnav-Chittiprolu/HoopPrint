from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import CurrentUser, get_current_user
from app.config import Settings, get_settings
from app.models.profile import (
    AggregatedFeature,
    HistoryPoint,
    ProfileQuestionnaire,
    ProfileResponse,
    ProfileUpdateRequest,
)
from app.services.supabase_client import SupabaseService

router = APIRouter(prefix="/me", tags=["profile"])


def get_supabase(settings: Settings = Depends(get_settings)) -> SupabaseService:
    try:
        return SupabaseService(settings)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


def _questionnaire_from_row(row: dict) -> ProfileQuestionnaire:
    return ProfileQuestionnaire(
        display_name=row.get("display_name"),
        height_in=row.get("height_in"),
        height_z=row.get("height_z"),
        position=row.get("position"),
        dominant_hand=row.get("dominant_hand"),
        primary_skill=row.get("primary_skill"),
    )


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    user: CurrentUser = Depends(get_current_user),
    supabase: SupabaseService = Depends(get_supabase),
) -> ProfileResponse:
    try:
        row = await supabase.get_profile(user.id)
        agg = await supabase.list_user_profile_agg(user.id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to load profile: {exc}",
        ) from exc

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    return ProfileResponse(
        id=row["id"],
        email=user.email,
        questionnaire=_questionnaire_from_row(row),
        aggregated_features=[AggregatedFeature.model_validate(item) for item in agg],
    )


@router.patch("/profile", response_model=ProfileResponse)
async def patch_profile(
    body: ProfileUpdateRequest,
    user: CurrentUser = Depends(get_current_user),
    supabase: SupabaseService = Depends(get_supabase),
) -> ProfileResponse:
    patch = body.to_db_patch()
    if not patch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No profile fields to update",
        )

    try:
        row = await supabase.update_profile(user.id, patch)
        agg = await supabase.list_user_profile_agg(user.id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to update profile: {exc}",
        ) from exc

    return ProfileResponse(
        id=row["id"],
        email=user.email,
        questionnaire=_questionnaire_from_row(row),
        aggregated_features=[AggregatedFeature.model_validate(item) for item in agg],
    )


@router.get("/history", response_model=list[HistoryPoint])
async def get_history(
    user: CurrentUser = Depends(get_current_user),
    supabase: SupabaseService = Depends(get_supabase),
) -> list[HistoryPoint]:
    try:
        rows = await supabase.list_feature_history_for_user(user.id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to load history: {exc}",
        ) from exc
    return [HistoryPoint.model_validate(row) for row in rows]
