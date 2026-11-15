"""Fixtures de la suite sobre el CSV (marcador `csv`).

BD dedicada `cajaclara_csv` (POSTGRES_CSV_DB): se crea y se carga con `app.db.cargar_csv` una vez por sesión, desde
DATA_CSV_DIR (`data/csv`). Cada test corre dentro de una transacción que se revierte. Si no hay CSV o Postgres no está
accesible, los tests se saltan con un mensaje claro (la suite normal sigue).
"""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.cargar_csv import asegurar_bd, cargar
from app.db.session import crear_engine, get_db
from app.main import app
from tests.conftest import API_KEY_PRUEBAS

BD_CSV = os.environ.get("POSTGRES_CSV_DB", "cajaclara_csv")
EMPRESAS = [f"EMP-{n:04d}" for n in range(1, 31)]


@pytest.fixture(scope="session")
def engine_csv() -> Iterator[Engine]:
    carpeta = settings.data_csv_dir
    if not carpeta.is_dir() or not list(carpeta.glob("*.csv")):
        pytest.skip(f"No hay CSV en {carpeta} (monta ../data/csv o define DATA_CSV_DIR): suite CSV omitida.")
    if BD_CSV in (settings.POSTGRES_DB, settings.POSTGRES_TEST_DB) or settings.es_produccion:
        pytest.skip(f"La BD de la suite CSV ({BD_CSV}) no puede ser la principal, la de pruebas ni producción.")
    try:
        asegurar_bd(BD_CSV)
        engine = crear_engine(settings._url(BD_CSV), connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Postgres no accesible para crear {BD_CSV} ({type(exc).__name__}). "
                    "Levanta la BD con `docker compose up -d db`: suite CSV omitida.")  # fmt: skip
    cargar(engine, carpeta)
    yield engine
    engine.dispose()


@pytest.fixture
def db_csv(engine_csv: Engine) -> Iterator[Session]:
    conexion = engine_csv.connect()
    transaccion = conexion.begin()
    sesion = Session(bind=conexion, join_transaction_mode="create_savepoint", autoflush=False, expire_on_commit=False)
    try:
        yield sesion
    finally:
        sesion.close()
        transaccion.rollback()
        conexion.close()


@pytest.fixture
def client_csv(db_csv: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db_csv
    with TestClient(app, headers={"X-API-Key": API_KEY_PRUEBAS}) as c:
        yield c
    app.dependency_overrides.clear()


def destino(engine: Engine) -> str:
    return make_url(engine.url).render_as_string(hide_password=True)
