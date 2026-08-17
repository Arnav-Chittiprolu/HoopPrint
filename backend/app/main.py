from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.clips import router as clips_router
from app.api.comp import router as comp_router
from app.api.health import router as health_router
from app.api.profile import router as profile_router
from app.config import get_settings
from app.logging_config import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.environment)
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
    app.include_router(comp_router)
    return app


app = create_app()
