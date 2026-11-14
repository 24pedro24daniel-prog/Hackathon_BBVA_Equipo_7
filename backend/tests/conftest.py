"""Fixtures comunes.

- BD: usa SIEMPRE la BD de pruebas (POSTGRES_TEST_DB). Se recrea y siembra una vez por sesión; cada test corre
  dentro de una transacción que se revierte al final. Si Postgres no está accesible, los tests que piden `db`
  se saltan con un mensaje claro (los demás corren igual).
- Credenciales: los tests nunca usan las de .env; la API key es fija y la de OpenRouter va vacía.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.reset import resetear
from app.db.session import crear_engine, get_db
from app.main import app

API_KEY_PRUEBAS = "clave-de-pruebas-cajaclara"


@pytest.fixture(autouse=True)
def _credenciales_de_prueba(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", SecretStr(""))
    monkeypatch.setattr(settings, "API_KEY", SecretStr(API_KEY_PRUEBAS))


# ── BD de pruebas ───────────────────────────────────────────────────────────────────────────────


def _url_pruebas() -> str:
    url = settings.test_database_url
    if make_url(url).database == settings.POSTGRES_DB:
        raise RuntimeError("La BD de pruebas no puede ser la BD principal")
    return url


@pytest.fixture(scope="session")
def engine_pruebas() -> Iterator[Engine]:
    url = _url_pruebas()
    engine = crear_engine(url, connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        engine.dispose()
        destino = make_url(url).render_as_string(hide_password=True)
        pytest.skip(f"Postgres no accesible en {destino} ({type(exc).__name__}). "
                    "Levanta la BD con `docker compose up -d db` para correr los tests de BD.")  # fmt: skip
    resetear(engine, con_seed=True)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine_pruebas: Engine) -> Iterator[Session]:
    """Sesión dentro de una transacción que se revierte: cada test ve el seed intacto."""
    conexion = engine_pruebas.connect()
    transaccion = conexion.begin()
    sesion = Session(bind=conexion, join_transaction_mode="create_savepoint", autoflush=False,
                     expire_on_commit=False)  # fmt: skip
    try:
        yield sesion
    finally:
        sesion.close()
        transaccion.rollback()
        conexion.close()


# ── Cliente HTTP ────────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def _sesiones_sin_conexion():
    """Fábrica de sesiones a la BD de pruebas que no conecta hasta usarse (los stubs no tocan la BD)."""
    engine = crear_engine(_url_pruebas(), connect_args={"connect_timeout": 2})
    yield sessionmaker(bind=engine)
    engine.dispose()


def _cliente(fabrica, headers: dict) -> Iterator[TestClient]:
    def _get_db():
        sesion = fabrica()
        try:
            yield sesion
        finally:
            sesion.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app, headers=headers) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client(_sesiones_sin_conexion) -> Iterator[TestClient]:
    """Cliente con X-API-Key. get_db apunta a la BD de pruebas (no requiere que esté levantada)."""
    yield from _cliente(_sesiones_sin_conexion, {"X-API-Key": API_KEY_PRUEBAS})


@pytest.fixture
def client_sin_key(_sesiones_sin_conexion) -> Iterator[TestClient]:
    yield from _cliente(_sesiones_sin_conexion, {})


@pytest.fixture
def client_db(db: Session) -> Iterator[TestClient]:
    """Cliente cuyo get_db usa la sesión transaccional `db` (los cambios se revierten al final)."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, headers={"X-API-Key": API_KEY_PRUEBAS}) as c:
        yield c
    app.dependency_overrides.clear()
