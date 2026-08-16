from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "HoopPrint API"
    environment: str = "development"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwt_secret: str = ""
    supabase_service_role_key: str = ""

    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


def get_settings() -> Settings:
    return Settings()
