"""Configuración desde backend/.env (pydantic-settings). Nunca hardcodear secretos."""
from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/cajaclara"
    API_KEY: str = ""
    OLLAMA_URL: str = "http://localhost:11434"
    WHISPER_MODEL: str = "small"
    TZ: str = "America/Lima"
    FECHA_DEMO: date | None = None
    CORS_ORIGINS: str = "http://localhost:5173"
    VERSION_API: str = "1.0.0"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
