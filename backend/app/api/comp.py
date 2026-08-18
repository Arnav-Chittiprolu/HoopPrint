from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import CurrentUser, get_current_user
from app.config import Settings, get_settings
from app.models.comp import CompResultResponse
from app.services.comp import CompError, comp_from_stored_row, run_role_comp
from app.services.supabase_client import SupabaseService

router = APIRouter(prefix="/me", tags=["comp"])


def get_supabase(settings: Settings = Depends(get_settings)) -> SupabaseService:
    try:
        return SupabaseService(settings)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.post("/comp", response_model=CompResultResponse)
async def create_comp(
    user: CurrentUser = Depends(get_current_user),
    supabase: SupabaseService = Depends(get_supabase),
) -> CompResultResponse:
    try:
        result = await run_role_comp(supabase, user.id)
    except CompError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to run comp: {exc}",
        ) from exc
    return CompResultResponse.model_validate(result)


@router.get("/comp", response_model=CompResultResponse)
async def get_comp(
    user: CurrentUser = Depends(get_current_user),
    supabase: SupabaseService = Depends(get_supabase),
) -> CompResultResponse:
    try:
        row = await supabase.get_latest_comp_result(user.id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to load comp: {exc}",
        ) from exc

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No comp yet")

    return CompResultResponse.model_validate(comp_from_stored_row(row))
