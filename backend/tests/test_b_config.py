"""core/config.py: DATABASE_URL compuesto y separación parámetros (parametros.env) vs credenciales (.env)."""

from datetime import date

import pytest

from app.core.config import BACKEND_DIR, Settings

CREDENCIALES = {"POSTGRES_USER", "POSTGRES_PASSWORD", "API_KEY", "OPENROUTER_API_KEY", "R2_ACCESS_KEY_ID",
               "R2_SECRET_ACCESS_KEY"}
SECRETOS = CREDENCIALES - {"POSTGRES_USER"}


def _claves(ruta) -> dict[str, str]:
    pares = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            clave, valor = linea.split("=", 1)
            pares[clave.strip()] = valor.strip()
    return pares


@pytest.fixture
def sin_entorno(monkeypatch):
    """Quita del entorno las variables que podrían venir de docker compose."""
    for var in ["POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_TEST_DB", "POSTGRES_USER",
                "POSTGRES_PASSWORD", "DATABASE_URL", "TEST_DATABASE_URL", "FECHA_DEMO", "CORS_ORIGINS"]:  # fmt: skip
        monkeypatch.delenv(var, raising=False)


def test_database_url_se_compone_de_las_partes(sin_entorno):
    s = Settings(_env_file=None, POSTGRES_USER="pedro", POSTGRES_PASSWORD="p@ss/word:1", POSTGRES_HOST="db",
                 POSTGRES_PORT=5433, POSTGRES_DB="cajaclara", POSTGRES_TEST_DB="cajaclara_test")  # fmt: skip
    assert s.database_url == "postgresql+psycopg://pedro:p%40ss%2Fword%3A1@db:5433/cajaclara"
    assert s.test_database_url == "postgresql+psycopg://pedro:p%40ss%2Fword%3A1@db:5433/cajaclara_test"


def test_database_url_override_explicito(sin_entorno):
    s = Settings(_env_file=None, DATABASE_URL="postgresql+psycopg://x:y@remoto:5432/otra", POSTGRES_PASSWORD="z")
    assert s.database_url == "postgresql+psycopg://x:y@remoto:5432/otra"
    assert "remoto" not in s.test_database_url


def test_override_vacio_se_ignora(sin_entorno):
    s = Settings(_env_file=None, DATABASE_URL="  ", FECHA_DEMO="", POSTGRES_PASSWORD="z")
    assert s.DATABASE_URL is None and s.FECHA_DEMO is None
    assert s.database_url.startswith("postgresql+psycopg://")


def test_variables_de_entorno_tienen_prioridad_sobre_archivos(sin_entorno, monkeypatch, tmp_path):
    parametros = tmp_path / "parametros.env"
    parametros.write_text("POSTGRES_HOST=localhost\nPOSTGRES_DB=desde_archivo\n", encoding="utf-8")
    credenciales = tmp_path / ".env"
    credenciales.write_text("POSTGRES_USER=u\nPOSTGRES_PASSWORD=secreta\n", encoding="utf-8")
    monkeypatch.setenv("POSTGRES_HOST", "db")
    s = Settings(_env_file=(parametros, credenciales))
    assert s.POSTGRES_HOST == "db"
    assert s.POSTGRES_DB == "desde_archivo"
    assert s.POSTGRES_PASSWORD.get_secret_value() == "secreta"
    assert s.database_url == "postgresql+psycopg://u:secreta@db:5432/desde_archivo"


def test_dotenv_sobreescribe_a_parametros(sin_entorno, tmp_path):
    parametros = tmp_path / "parametros.env"
    parametros.write_text("POSTGRES_USER=del_parametro\n", encoding="utf-8")
    credenciales = tmp_path / ".env"
    credenciales.write_text("POSTGRES_USER=del_env\n", encoding="utf-8")
    assert Settings(_env_file=(parametros, credenciales)).POSTGRES_USER == "del_env"


def test_secretos_no_aparecen_en_repr(sin_entorno):
    s = Settings(_env_file=None, POSTGRES_PASSWORD="supersecreta", API_KEY="clave-api", OPENROUTER_API_KEY="sk-or-x")
    texto = repr(s) + str(s.model_dump())
    for secreto in ("supersecreta", "clave-api", "sk-or-x"):
        assert secreto not in texto


def test_parametros_env_no_tiene_credenciales():
    claves = _claves(BACKEND_DIR / "parametros.env")
    assert not (claves.keys() & CREDENCIALES)
    assert {"POSTGRES_HOST", "POSTGRES_DB", "POSTGRES_TEST_DB", "FECHA_DEMO", "LLM_BASE_URL", "WHISPER_MODEL"} <= claves.keys()


def test_parametros_env_valores_de_la_demo(sin_entorno):
    s = Settings(_env_file=BACKEND_DIR / "parametros.env")
    assert s.FECHA_DEMO == date(2026, 11, 14)
    assert s.TZ == "America/Lima"
    assert s.API_PREFIX == "/api/v1"
    assert s.cors_origins == ["http://localhost:5173"]
    assert s.POSTGRES_DB == "cajaclara" and s.POSTGRES_TEST_DB == "cajaclara_test"
    assert s.LLM_BASE_URL == "https://openrouter.ai/api/v1"
    assert (s.WHISPER_MODEL, s.WHISPER_DEVICE, s.WHISPER_COMPUTE_TYPE) == ("small", "cpu", "int8")
    assert s.UMBRAL_CONFIANZA == 0.75


def test_example_env_tiene_solo_credenciales_vacias():
    claves = _claves(BACKEND_DIR / "example.env")
    assert set(claves) == CREDENCIALES
    assert all(claves[k] == "" for k in SECRETOS)


def test_dotenv_local_solo_tiene_credenciales():
    ruta = BACKEND_DIR / ".env"
    if not ruta.exists():
        pytest.skip(".env no existe en este entorno (en docker entra por env_file, no se copia a la imagen)")
    assert set(_claves(ruta)) <= CREDENCIALES


def test_cors_varios_origenes(sin_entorno):
    s = Settings(_env_file=None, CORS_ORIGINS="http://localhost:5173, http://127.0.0.1:5173 ,")
    assert s.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]
