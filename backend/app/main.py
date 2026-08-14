from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.clips import router as clips_router
from app.api.health import router as health_router
from app.api.profile import router as profile_router
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(clips_router)
    app.include_router(profile_router)
    return app


app = create_app()
