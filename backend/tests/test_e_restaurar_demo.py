"""app.db.restaurar_demo: vuelve UNA empresa al estado de data/csv sin tocar las demás ni llm_llamadas.

Corre contra la BD de pruebas dentro de la transacción del fixture `db` (todo se revierte al final): primero deja la
BD con los catálogos y dos empresas cargadas desde data/csv, simula una demo en vivo y restaura una.
"""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import delete, func, insert, select, update

from app.core.config import settings
from app.db import models as m
from app.db import restaurar_demo as rd
from app.db.base import Base
from app.db.cargar_csv import _insertar, _leer
from app.db.reset import ResetProhibido

LIMA = ZoneInfo("America/Lima")


def _csv_disponible() -> bool:
    return (settings.data_csv_dir / "empresas.csv").exists()


pytestmark = pytest.mark.skipif(not _csv_disponible(), reason="data/csv no está montado (DATA_CSV_DIR)")


def _contar(conn, tabla, empresa_id):
    alcance = rd._alcance()
    return conn.scalar(select(func.count()).select_from(tabla).where(rd._de_la_empresa(tabla, alcance, empresa_id)))


@pytest.fixture
def conn_csv(db):
    """Conexión de la transacción de pruebas con catálogos de data/csv, EMP-0001 y EMP-0002 restauradas desde el CSV."""
    conn = db.connection()
    for tabla in reversed(Base.metadata.sorted_tables):
        conn.execute(delete(tabla))
    for nombre in ("rubros", "categorias"):
        columnas, filas = _leer(settings.data_csv_dir / f"{nombre}.csv")
        _insertar(conn, Base.metadata.tables[nombre], columnas, filas)
    for emp in ("EMP-0001", "EMP-0002"):
        rd.restaurar(conn, emp)
    return conn


@pytest.mark.db
def test_restaurar_vuelve_al_csv_y_no_toca_otras_empresas_ni_llm(conn_csv):
    conn = conn_csv
    tx, emp, idem, alerta = (Base.metadata.tables[n] for n in ("transacciones", "empresas", "idempotency_keys", "alertas"))
    esperado = {t.name: _contar(conn, t, "EMP-0001") for t in Base.metadata.sorted_tables if t.name in rd._alcance()}
    assert esperado["transacciones"] > 0
    otra_antes = {t.name: _contar(conn, t, "EMP-0002") for t in Base.metadata.sorted_tables if t.name in rd._alcance()}
    tx_1 = conn.scalar(select(tx.c.transaccion_id).where(tx.c.empresa_id == "EMP-0001").order_by(tx.c.transaccion_id))
    tx_2 = conn.scalar(select(tx.c.transaccion_id).where(tx.c.empresa_id == "EMP-0002").order_by(tx.c.transaccion_id))
    monto_1 = conn.scalar(select(tx.c.monto).where(tx.c.transaccion_id == tx_1))
    nombre_1 = conn.scalar(select(emp.c.nombre_ficticio).where(emp.c.empresa_id == "EMP-0001"))

    # "Demo en vivo": cambia cifras de las dos empresas, borra alertas, deja una idempotency key y una traza de IA
    ahora = datetime(2026, 11, 14, 10, 0, tzinfo=LIMA)
    conn.execute(update(tx).where(tx.c.transaccion_id.in_([tx_1, tx_2])).values(monto=Decimal("9999.00")))
    conn.execute(update(emp).where(emp.c.empresa_id == "EMP-0001").values(nombre_ficticio="Cambiado en la demo"))
    conn.execute(delete(alerta).where(alerta.c.empresa_id == "EMP-0001"))
    conn.execute(insert(idem).values(clave="k-demo", endpoint="POST /ingesta/confirmar", empresa_id="EMP-0001",
                                     payload_hash="0" * 64, status_code=201, respuesta={}, creado_en=ahora))  # fmt: skip
    conn.execute(insert(Base.metadata.tables["llm_llamadas"]).values(
        llamada_id="LLM-9001", empresa_id="EMP-0001", origen="asistente", estado="ok", creado_en=ahora))

    informe = rd.restaurar(conn, "EMP-0001")

    assert {t: _contar(conn, Base.metadata.tables[t], "EMP-0001") for t in esperado} == esperado
    assert conn.scalar(select(tx.c.monto).where(tx.c.transaccion_id == tx_1)) == monto_1
    assert conn.scalar(select(emp.c.nombre_ficticio).where(emp.c.empresa_id == "EMP-0001")) == nombre_1
    assert conn.scalar(select(func.count()).select_from(idem).where(idem.c.empresa_id == "EMP-0001")) == 0
    # La traza de IA se conserva (y su llave a empresas sigue válida)
    assert conn.scalar(select(func.count()).select_from(Base.metadata.tables["llm_llamadas"])) == 1
    # La otra empresa queda con su cambio (no se restauró)
    assert conn.scalar(select(tx.c.monto).where(tx.c.transaccion_id == tx_2)) == Decimal("9999.00")
    assert {t.name: _contar(conn, t, "EMP-0002") for t in Base.metadata.sorted_tables if t.name in rd._alcance()} == otra_antes
    assert informe.tablas["transacciones"] == (esperado["transacciones"], esperado["transacciones"])
    assert informe.insertadas == sum(esperado.values()) + 1  # + la fila de empresas


@pytest.mark.db
def test_tablas_hijas_sin_empresa_id_se_filtran_por_su_padre(conn_csv):
    detalle = Base.metadata.tables["detalle_transaccion"]
    tx = Base.metadata.tables["transacciones"]
    # Todos los detalles cargados cuelgan de transacciones de EMP-0001 o EMP-0002
    huerfanos = conn_csv.scalar(select(func.count()).select_from(detalle).where(
        ~detalle.c.transaccion_id.in_(select(tx.c.transaccion_id))))
    assert huerfanos == 0
    assert rd._alcance()["detalle_transaccion"] and rd._alcance()["predicciones_fiado"]
    assert {"rubros", "categorias", "llm_llamadas", "empresas"}.isdisjoint(rd._alcance())


@pytest.mark.db
def test_empresa_que_no_esta_en_el_csv_falla_sin_tocar_nada(conn_csv):
    antes = _contar(conn_csv, Base.metadata.tables["transacciones"], "EMP-0001")
    with pytest.raises(rd.CargaInvalida):
        rd.restaurar(conn_csv, "EMP-9999")
    with pytest.raises(ValueError):
        rd.restaurar(conn_csv, "'; DROP TABLE empresas; --")
    assert _contar(conn_csv, Base.metadata.tables["transacciones"], "EMP-0001") == antes


def test_bloqueado_en_produccion_salvo_confirmacion(monkeypatch, capsys):
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "DATABASE_URL_PRODUCCION", SecretStr("postgresql://u:p@prod.ejemplo.com:5432/bdprod"))
    with pytest.raises(ResetProhibido):
        rd.url_destino(None, True, None)
    with pytest.raises(ResetProhibido):
        rd.url_destino(None, True, "otra")
    assert "prod.ejemplo.com" in rd.url_destino(None, True, "bdprod")
    assert rd.main(["--empresa", "EMP-0001", "--produccion", "--confirmar", "otra"]) == 2
    assert "BLOQUEADO" in capsys.readouterr().err
    # Sin --produccion, con APP_ENV=produccion tampoco corre
    monkeypatch.setattr(settings, "APP_ENV", "produccion")

    class _Conn:
        engine = type("E", (), {"url": type("U", (), {"render_as_string": lambda self: "postgresql://x@h/db"})()})()

    with pytest.raises(ResetProhibido):
        rd.restaurar(_Conn(), "EMP-0001")
