from fastapi import APIRouter, Depends

from app.auth import CurrentUser, get_current_user
from app.config import Settings, get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
        "supabase_configured": bool(settings.supabase_url and settings.supabase_anon_key),
    }


@router.get("/me")
def me(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Protected smoke endpoint — requires a valid Supabase JWT."""
    return {"id": user.id, "email": user.email}
