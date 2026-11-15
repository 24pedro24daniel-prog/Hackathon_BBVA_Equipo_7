"""db/seed_demo.py: el dataset cuadra con la historia de Pedro (context.md §9).

Los tests sin marca `db` revisan el generador en memoria (corren siempre); los `db` revisan lo que quedó en Postgres.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import models as m
from app.db import seed_demo as seed

CORTE_SQL = "2026-11-15 00:00:00-05:00"  # todo lo registrado hasta el final del 14/11 en Lima


# ── generador en memoria ──


def test_generador_es_deterministico():
    a, b = seed.resumen_calibracion(), seed.resumen_calibracion()
    assert a == b


def test_generador_cuadra_la_historia():
    r = seed.resumen_calibracion()
    assert r["retiros_nov_1_13"] == Decimal("1900.00")
    assert r["retiros_sep_1_13"] == r["retiros_oct_1_13"] == Decimal("1200.00")  # +700 este mes
    assert r["fiados_pendientes"] == Decimal("310.00")
    assert abs(r["proyeccion_30_11"] - Decimal("-650")) <= Decimal("1")
    assert r["saldo_inicial"] > 0 and r["saldo_minimo_historico"] > seed.MINIMO_OPERATIVO


def test_sin_esas_tres_causas_cerraria_con_760():
    # context.md §9: −650 + 700 (retiros) + 400 (pedido sobre ventas) + 310 (fiados) = 760
    assert seed.SALDO_OBJETIVO_30_11 + 700 + 400 + 310 == 760


# ── en la BD ──


def _escalar(db, sql: str, **params):
    return db.execute(text(sql), params).scalar_one()


@pytest.mark.db
def test_empresa_de_pedro(db):
    emp = db.get(m.Empresa, "EMP-0001")
    assert emp.nombre_ficticio == "Bodega Don Pedro"
    assert db.get(m.Rubro, emp.rubro_id).nombre == "bodega"
    assert emp.tiene_ruc and emp.regimen_tributario == "nuevo_rus"
    assert emp.fecha_saldo_inicial == date(2026, 8, 15)
    assert emp.minimo_operativo == Decimal("800.00")


@pytest.mark.db
def test_saldo_de_caja_al_14_11_es_2340(db):
    saldo = _escalar(db, """
        SELECT e.saldo_inicial + COALESCE(SUM(CASE WHEN t.tipo IN ('venta','cobro_fiado','prestamo_recibido','otro_ingreso')
                                              THEN t.monto ELSE -t.monto END), 0)
        FROM empresas e LEFT JOIN transacciones t
          ON t.empresa_id = e.empresa_id AND t.afecta_caja AND NOT t.anulada AND t.fecha_hora < CAST(:corte AS timestamptz)
        WHERE e.empresa_id = 'EMP-0001' GROUP BY e.saldo_inicial""", corte=CORTE_SQL)  # fmt: skip
    assert saldo == Decimal("2340.00")
    assert db.get(m.SaldoDiario, ("EMP-0001", date(2026, 11, 13))).saldo_cierre == Decimal("2340.00")


@pytest.mark.db
def test_no_hay_movimientos_desde_el_14_11(db):
    n = _escalar(db, "SELECT count(*) FROM transacciones WHERE empresa_id = 'EMP-0001' "
                     "AND fecha_hora >= '2026-11-14 00:00:00-05:00'")
    assert n == 0


@pytest.mark.db
def test_90_dias_de_ventas_todos_los_dias(db):
    dias = db.execute(text("""SELECT DISTINCT (fecha_hora AT TIME ZONE 'America/Lima')::date FROM transacciones
                              WHERE tipo = 'venta' AND afecta_caja AND empresa_id = 'EMP-0001'""")).scalars().all()  # fmt: skip
    esperado = {date(2026, 8, 15) + timedelta(days=i) for i in range(91)}
    assert set(dias) == esperado


@pytest.mark.db
def test_pedido_andina_2400_vence_30_11(db):
    pedido = db.get(m.Deuda, "PED-0012")
    assert pedido.tipo == "proveedor"
    assert db.get(m.Proveedor, pedido.proveedor_id).nombre_ficticio == "Distribuidora Andina"
    assert pedido.monto_total_a_pagar == Decimal("2400.00") == pedido.monto_recibido
    assert (pedido.fecha_inicio, pedido.fecha_vencimiento) == (date(2026, 11, 13), date(2026, 11, 30))
    assert pedido.fecha_pago_total is None
    movs = db.query(m.Transaccion).filter_by(deuda_id="PED-0012").all()
    assert [(t.tipo, t.metodo_pago, t.afecta_caja) for t in movs] == [("compra", "credito", False)]
    detalle = db.query(m.DetalleTransaccion).filter_by(transaccion_id=movs[0].transaccion_id).all()
    assert sum(d.subtotal for d in detalle) == Decimal("2400.00")
    pendientes = db.query(m.Deuda).filter(m.Deuda.fecha_pago_total.is_(None)).all()
    assert [d.deuda_id for d in pendientes] == ["PED-0012"]


@pytest.mark.db
def test_pedidos_anteriores_pagados_en_su_totalidad(db):
    pagos = dict(db.execute(text("""SELECT d.deuda_id, d.monto_total_a_pagar - COALESCE(SUM(t.monto), 0)
                                    FROM deudas d LEFT JOIN transacciones t ON t.deuda_id = d.deuda_id
                                     AND t.tipo = 'pago_proveedor'
                                    WHERE d.deuda_id <> 'PED-0012' GROUP BY d.deuda_id""")).all())  # fmt: skip
    assert len(pagos) == 11 and all(v == 0 for v in pagos.values())


@pytest.mark.db
def test_fiados_pendientes_310(db):
    filas = db.execute(text("""
        SELECT f.fiado_id, c.nombre_ficticio, f.monto - COALESCE(SUM(t.monto), 0) AS pendiente
        FROM cuaderno_fiado f JOIN clientes c USING (cliente_id)
        LEFT JOIN transacciones t ON t.fiado_id = f.fiado_id AND t.tipo = 'cobro_fiado'
        GROUP BY f.fiado_id, c.nombre_ficticio, f.monto HAVING f.monto - COALESCE(SUM(t.monto), 0) > 0
        ORDER BY f.fiado_id""")).all()  # fmt: skip
    assert [(f, c, p) for f, c, p in filas] == [
        ("FIA-0045", "Sra. Carmen", Decimal("120.00")),
        ("FIA-0046", "Don Luis", Decimal("95.00")),
        ("FIA-0047", "Vecina Rosa", Decimal("95.00")),
    ]
    assert db.query(m.CuadernoFiado).filter(m.CuadernoFiado.fecha_pago_total.is_(None)).count() == 3


@pytest.mark.db
def test_cada_fiado_tiene_su_venta_a_credito(db):
    sin_venta = _escalar(db, """SELECT count(*) FROM cuaderno_fiado f WHERE NOT EXISTS (
        SELECT 1 FROM transacciones t WHERE t.fiado_id = f.fiado_id AND t.tipo = 'venta' AND t.metodo_pago = 'credito'
        AND t.monto = f.monto)""")  # fmt: skip
    assert sin_venta == 0


@pytest.mark.db
def test_catalogo_clientes_y_proveedor(db):
    productos = db.query(m.Producto).filter_by(empresa_id="EMP-0001").all()
    assert len(productos) == 20 and all(p.alias for p in productos)
    cerveza = db.get(m.Producto, "PRD-0031")
    assert cerveza.nombre == "Cerveza 620 ml" and cerveza.precio_venta == Decimal("6.50") and "chela" in cerveza.alias
    assert any(p.costo_unitario is None for p in productos)  # ganancia como rango
    assert {c.nombre_ficticio for c in db.query(m.Cliente)} == {"Sra. Carmen", "Don Luis", "Vecina Rosa"}
    assert [p.nombre_ficticio for p in db.query(m.Proveedor)] == ["Distribuidora Andina"]


@pytest.mark.db
def test_sueldo_programado_y_retiros(db):
    sueldos = db.query(m.MovimientoProgramado).filter_by(es_sueldo=True, activo=True).all()
    assert len(sueldos) == 1
    s = sueldos[0]
    assert (s.monto, s.frecuencia, s.dia_semana, s.categoria_id) == (Decimal("400.00"), "semanal", 6, "CAT-15")

    def retiros(desde, hasta):
        return _escalar(db, """SELECT COALESCE(SUM(monto), 0) FROM transacciones WHERE tipo = 'retiro_personal'
                               AND (fecha_hora AT TIME ZONE 'America/Lima')::date BETWEEN :d AND :h""", d=desde, h=hasta)  # fmt: skip

    nov = retiros(date(2026, 11, 1), date(2026, 11, 13))
    usual = (retiros(date(2026, 9, 1), date(2026, 9, 13)) + retiros(date(2026, 10, 1), date(2026, 10, 13))) / 2
    assert (nov, usual, nov - usual) == (Decimal("1900.00"), Decimal("1200.00"), Decimal("700.00"))


@pytest.mark.db
def test_rus_al_dia_y_proximo_vencimiento(db):
    imp = {i.periodo: i for i in db.query(m.Impuesto).filter_by(regimen="nuevo_rus", empresa_id="EMP-0001")}
    assert set(imp) == {"2026-08", "2026-09", "2026-10", "2026-11"}
    assert all(imp[p].fecha_pago is not None for p in ("2026-08", "2026-09", "2026-10"))
    assert imp["2026-11"].fecha_pago is None and imp["2026-11"].fecha_vencimiento == date(2026, 12, 15)
    assert all(i.monto == Decimal("20.00") for i in imp.values())


@pytest.mark.db
def test_proyeccion_de_referencia_da_faltante_650_el_30_11(db):
    """Implementación independiente (SQL) de la proyección documentada en seed_demo."""
    filas = db.execute(text("""
        SELECT (fecha_hora AT TIME ZONE 'America/Lima')::date AS dia,
               SUM(CASE WHEN tipo IN ('venta','cobro_fiado','prestamo_recibido','otro_ingreso') THEN monto ELSE -monto END)
        FROM transacciones
        WHERE empresa_id = 'EMP-0001' AND afecta_caja AND NOT anulada AND fiado_id IS NULL AND deuda_id IS NULL AND impuesto_id IS NULL
          AND programado_id IS NULL
          AND (fecha_hora AT TIME ZONE 'America/Lima')::date BETWEEN '2026-10-17' AND '2026-11-13'
        GROUP BY 1""")).all()  # fmt: skip
    por_dia_semana = {wd: Decimal("0") for wd in range(7)}
    for dia, neto in filas:
        por_dia_semana[dia.weekday()] += neto
    proyeccion = sum((por_dia_semana[(date(2026, 11, 15) + timedelta(days=i)).weekday()] / 4 for i in range(16)),
                     Decimal("0"))  # fmt: skip
    deudas = _escalar(db, """SELECT SUM(monto_total_a_pagar) FROM deudas WHERE fecha_pago_total IS NULL
                             AND fecha_vencimiento <= '2026-11-30'""")  # fmt: skip
    luz = db.get(m.MovimientoProgramado, "PRG-0001").monto  # día 16
    sueldo = db.get(m.MovimientoProgramado, "PRG-0002").monto * 2  # sábados 21 y 28
    saldo_30 = Decimal("2340.00") + proyeccion - deudas - luz - sueldo
    assert abs(saldo_30 - Decimal("-650")) <= Decimal("1"), saldo_30


@pytest.mark.db
def test_etiquetas_y_resultados(db):
    assert db.query(m.SaldoDiario).filter_by(empresa_id="EMP-0001").count() == 91
    assert db.query(m.ScoreSalud).count() == 3  # solo EMP-0001 tiene historial
    assert db.query(m.Evento).count() == 2
    assert db.get(m.PreferenciasAlertas, "EMP-0001").max_por_dia == 2
    assert db.query(m.Alerta).count() == 0  # las escribe el motor de B


# ── EMP-0002: Pedro · día 3 ──


@pytest.mark.db
def test_pedro_dia_3_tiene_solo_tres_dias(db):
    emp = db.get(m.Empresa, "EMP-0002")
    assert emp.nombre_ficticio == "Pedro · día 3" and db.get(m.Rubro, emp.rubro_id).nombre == "bodega"
    assert emp.telefono_whatsapp != db.get(m.Empresa, "EMP-0001").telefono_whatsapp
    dias = db.execute(text("""SELECT DISTINCT (fecha_hora AT TIME ZONE 'America/Lima')::date FROM transacciones
                              WHERE empresa_id = 'EMP-0002'""")).scalars().all()  # fmt: skip
    assert sorted(dias) == [date(2026, 11, 12), date(2026, 11, 13), date(2026, 11, 14)]
    assert db.query(m.Transaccion).filter_by(empresa_id="EMP-0002").count() == 13
    assert db.query(m.Producto).filter_by(empresa_id="EMP-0002").count() == 20
    assert db.query(m.CuadernoFiado).filter_by(empresa_id="EMP-0002").count() == 0


@pytest.mark.db
def test_pedro_dia_3_resumen_y_forecast(client_db):
    base = "/api/v1/empresas/EMP-0002"
    r = client_db.get(f"{base}/resumen?periodo=2026-11").json()
    assert r["dias_con_datos"] == 3 and r["dias_con_datos"] < r["dias_requeridos_forecast"]
    ind = r["indicadores"]
    assert (ind["saldo_caja_negocio"]["valor"], ind["ingresos_mes"]["valor"], ind["egresos_mes"]["valor"]) == (
        1120.0, 1870.0, 1600.0)
    f = client_db.get(f"{base}/forecast").json()
    assert f["disponible"] is False and f["dias_con_datos"] == 3 and f["saldo_actual"] == 1120.0
