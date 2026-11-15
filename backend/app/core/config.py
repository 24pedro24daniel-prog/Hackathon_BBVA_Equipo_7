"""Configuración del backend.

Se lee de `parametros.env` (no secretos, versionado) y luego de `.env` (solo credenciales).
Las variables de entorno reales tienen prioridad sobre ambos archivos.
"""

from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

BACKEND_DIR = Path(__file__).resolve().parents[2]


def es_misma_bd(a: str | None, b: str | None) -> bool:
    """Mismo host, puerto y base (ignora driver, usuario y parámetros)."""
    if not a or not b:
        return False
    ua, ub = make_url(a), make_url(b)
    return (ua.host, ua.port or 5432, ua.database) == (ub.host, ub.port or 5432, ub.database)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / "parametros.env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # Aplicación
    APP_ENV: str = "local"
    TZ: str = "America/Lima"
    FECHA_DEMO: date | None = None
    API_PREFIX: str = "/api/v1"
    API_VERSION: str = "1.0.0"
    CORS_ORIGINS: str = "http://localhost:5173"
    LOG_LEVEL: str = "INFO"

    # Base de datos: partes no secretas en parametros.env, usuario y contraseña en .env
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "cajaclara"
    POSTGRES_TEST_DB: str = "cajaclara_test"
    POSTGRES_USER: str = "cajaclara"
    POSTGRES_PASSWORD: SecretStr = SecretStr("")
    # Override completo opcional (p. ej. una BD remota). Si viene, se ignoran las partes.
    DATABASE_URL: str | None = None
    TEST_DATABASE_URL: str | None = None
    # BD de producción (Render). Vive en .env y solo se usa con APP_ENV=produccion; local, docker y tests nunca la tocan.
    DATABASE_URL_PRODUCCION: SecretStr = SecretStr("")

    # Credenciales de la API
    API_KEY: SecretStr = SecretStr("")
    OPENROUTER_API_KEY: SecretStr = SecretStr("")
    R2_ACCESS_KEY_ID: SecretStr = SecretStr("")
    R2_SECRET_ACCESS_KEY: SecretStr = SecretStr("")

    # LLM (OpenRouter)
    LLM_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_MODEL: str = "openai/gpt-4o-mini"
    LLM_TIMEOUT_S: float = 20.0
    LLM_TEMPERATURE: float = 0.0
    LLM_MAX_TOKENS: int = 800
    LLM_APP_URL: str = "http://localhost:5173"
    LLM_APP_NAME: str = "CajaClara"
    # Trazabilidad de cada llamada al LLM/VLM (tabla llm_llamadas). Sin contenido: solo metadatos, tokens y costo.
    LLM_TRAZA_ACTIVA: bool = True
    LLM_TRAZA_GUARDAR_CONTENIDO: bool = True
    # Visión (foto del cuaderno de fiados): mismo OpenRouter y misma OPENROUTER_API_KEY, otro modelo con imágenes.
    VLM_MODEL: str = "openai/gpt-4o-mini"
    VLM_TIMEOUT_S: float = Field(default=30.0, gt=0)
    VLM_MAX_TOKENS: int = Field(default=1500, gt=0)

    # Whisper (faster-whisper local)
    WHISPER_MODEL: str = "small"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    WHISPER_LANGUAGE: str = "es"
    WHISPER_CACHE_DIR: str | None = None

    # Ingesta
    UMBRAL_CONFIANZA: float = Field(default=0.75, ge=0, le=1)
    # Carpeta (relativa a backend/) de audios y fotos que se pueden leer por media_url.
    MEDIA_DIR: str = "data"
    # Media en Cloudflare R2 (S3-compatible): subida directa con URL prefirmada. Las claves viven en .env.
    R2_ACCOUNT_ID: str = ""
    R2_BUCKET: str = "cajaclara-media"
    R2_PRESIGN_TTL_S: int = Field(default=600, ge=30, le=3600)
    MEDIA_MAX_AUDIO_BYTES: int = Field(default=10 * 1024 * 1024, gt=0)
    MEDIA_MAX_IMAGEN_BYTES: int = Field(default=8 * 1024 * 1024, gt=0)
    MEDIA_TIPOS_AUDIO: str = "audio/ogg,audio/webm,audio/mpeg,audio/mp4,audio/wav"
    MEDIA_TIPOS_IMAGEN: str = "image/jpeg,image/png,image/webp"
    # Asistente: el LLM solo redacta con las cifras de las herramientas; desactivable para responder con plantillas.
    ASISTENTE_USAR_LLM: bool = True

    @field_validator("FECHA_DEMO", "DATABASE_URL", "TEST_DATABASE_URL", "WHISPER_CACHE_DIR", mode="before")
    @classmethod
    def _vacio_es_none(cls, v):
        return None if isinstance(v, str) and not v.strip() else v

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def _url(self, base_datos: str) -> str:
        return URL.create(
            "postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD.get_secret_value() or None,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=base_datos,
        ).render_as_string(hide_password=False)

    @property
    def es_produccion(self) -> bool:
        return self.APP_ENV.strip().lower() in ("produccion", "production", "prod")

    @property
    def url_produccion(self) -> str | None:
        """DATABASE_URL_PRODUCCION normalizada: driver psycopg y SSL obligatorio (Render lo exige desde fuera)."""
        crudo = self.DATABASE_URL_PRODUCCION.get_secret_value().strip()
        if not crudo:
            return None
        url = make_url(crudo).set(drivername="postgresql+psycopg")
        if "sslmode" not in url.query:
            url = url.update_query_dict({"sslmode": "require"})
        return url.render_as_string(hide_password=False)

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        if self.es_produccion:
            if not self.url_produccion:
                raise RuntimeError("APP_ENV=produccion pero DATABASE_URL_PRODUCCION está vacía en .env")
            return self.url_produccion
        return self._url(self.POSTGRES_DB)

    @property
    def test_database_url(self) -> str:
        url = self.TEST_DATABASE_URL or self._url(self.POSTGRES_TEST_DB)
        if self.es_produccion or es_misma_bd(url, self.url_produccion):
            raise RuntimeError("Los tests nunca corren contra la BD de producción")
        return url

    @property
    def r2_configurado(self) -> bool:
        return all([
            self.R2_ACCOUNT_ID.strip(), self.R2_BUCKET.strip(),
            self.R2_ACCESS_KEY_ID.get_secret_value().strip(), self.R2_SECRET_ACCESS_KEY.get_secret_value().strip(),
        ])  # fmt: skip

    @property
    def media_tipos_audio(self) -> list[str]:
        return [t.strip().lower() for t in self.MEDIA_TIPOS_AUDIO.split(",") if t.strip()]

    @property
    def media_tipos_imagen(self) -> list[str]:
        return [t.strip().lower() for t in self.MEDIA_TIPOS_IMAGEN.split(",") if t.strip()]

    @property
    def llm_configurado(self) -> bool:
        return bool(self.OPENROUTER_API_KEY.get_secret_value().strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
