"""B2/B13 — resumen F2 (variación vs mes anterior al mismo día de corte, ganancia como rango) y análisis F5."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import models as m
from app.services import finanzas
from tests._b_util import EMP, HOY, E, dt, reloj_fijo, tx  # noqa: F401

pytestmark = pytest.mark.db

INGRESOS_CAJA = "('venta','cobro_fiado','otro_ingreso')"


def _suma_sql(db, desde: str, hasta: str, condicion: str) -> Decimal:
    return db.execute(text(f"""SELECT COALESCE(SUM(monto), 0) FROM transacciones WHERE empresa_id = 'EMP-0001'
        AND NOT anulada AND (fecha_hora AT TIME ZONE 'America/Lima')::date BETWEEN :d AND :h AND {condicion}"""),
                      {"d": desde, "h": hasta}).scalar_one()  # fmt: skip


def test_resumen_de_noviembre(db, reloj_fijo):
    r = finanzas.resumen(db, E, "2026-11")
    i = r.indicadores
    assert (r.corte, r.dias_con_datos, r.variacion_vs) == (HOY, 91, "2026-10 al mismo día de corte")
    assert i.saldo_caja_negocio.valor == Decimal("2340.00")
    assert (i.retiros_personales.valor, i.retiros_personales.promedio_historico) == (Decimal("1900.00"), Decimal("1200.00"))
    assert i.retiros_personales.sueldo_fijo_definido == Decimal("400.00") and i.retiros_personales.sueldo_frecuencia == "semanal"
    assert i.retiros_personales.exceso_vs_promedio == Decimal("700.00")
    assert (i.pendiente_cobro.valor, i.pendiente_cobro.n_fiados) == (Decimal("310.00"), 3)
    assert (i.pagos_pendientes.valor, i.pagos_pendientes.n_obligaciones) == (Decimal("2420.00"), 2)
    assert i.pagos_pendientes.detalle == "Distribuidora Andina + RUS"
    ingresos = _suma_sql(db, "2026-11-01", "2026-11-14", f"afecta_caja AND tipo IN {INGRESOS_CAJA}")
    ingresos_oct = _suma_sql(db, "2026-10-01", "2026-10-14", f"afecta_caja AND tipo IN {INGRESOS_CAJA}")
    egresos = _suma_sql(db, "2026-11-01", "2026-11-14", "afecta_caja AND tipo NOT IN "
                                                       "('venta','cobro_fiado','otro_ingreso','prestamo_recibido','retiro_personal')")  # fmt: skip
    assert i.ingresos_mes.valor == ingresos and i.egresos_mes.valor == egresos
    assert i.ingresos_mes.variacion_pct == round(float((ingresos - ingresos_oct) / ingresos_oct * 100), 1)
    g = i.ganancia_neta
    assert g.es_aproximada is True and g.rango[0] <= g.valor <= g.rango[1]  # hay productos sin costo


def test_resumen_cambia_con_una_venta_de_hoy(db, reloj_fijo):
    antes = finanzas.resumen(db, E, "2026-11").indicadores
    tx(db, "venta", 13, HOY)
    despues = finanzas.resumen(db, E, "2026-11").indicadores
    assert despues.saldo_caja_negocio.valor - antes.saldo_caja_negocio.valor == 13
    assert despues.ingresos_mes.valor - antes.ingresos_mes.valor == 13


def test_resumen_de_un_mes_cerrado_y_uno_futuro(db, reloj_fijo):
    octubre = finanzas.resumen(db, E, "2026-10")
    assert octubre.corte == date(2026, 10, 31)
    assert octubre.indicadores.saldo_caja_negocio.valor == db.get(m.SaldoDiario, (E, date(2026, 10, 31))).saldo_cierre
    assert octubre.indicadores.retiros_personales.valor == _suma_sql(db, "2026-10-01", "2026-10-31", "tipo = 'retiro_personal'")
    agosto = finanzas.resumen(db, E, "2026-08")
    assert agosto.variacion_vs is None and agosto.indicadores.ingresos_mes.variacion_pct is None
    futuro = finanzas.resumen(db, E, "2026-12")
    assert futuro.indicadores.ingresos_mes.valor == 0 and futuro.corte == HOY


def test_resumen_endpoint_y_404(client_db, reloj_fijo):
    j = client_db.get(f"{EMP}/resumen").json()
    assert j["periodo"] == "2026-11" and j["indicadores"]["saldo_caja_negocio"]["valor"] == 2340.0
    assert isinstance(j["indicadores"]["ganancia_neta"]["rango"], list)
    assert client_db.get("/api/v1/empresas/EMP-9999/resumen").status_code == 404


# ── B13 análisis ──


def test_analisis_por_categoria(db, reloj_fijo):
    a = finanzas.analisis(db, E, "categoria", "egreso")
    assert (a.periodo.desde, a.periodo.hasta) == (date(2026, 11, 1), HOY)
    montos = [g.monto for g in a.grupos]
    assert montos == sorted(montos, reverse=True) and a.grupos[0].clave == "mercaderia"
    retiro = next(g for g in a.grupos if g.clave == "retiro_personal")
    assert retiro.monto == Decimal("1900.00") and retiro.variacion_pct == round((1900 - 1200) / 1200 * 100, 1)
    assert sum(g.participacion_pct for g in a.grupos) == pytest.approx(100, abs=0.5)
    assert a.total == sum(montos)
    # base caja: la compra a crédito de PED-0012 no está; su pago sí estaría (cuando ocurra)
    assert a.total == _suma_sql(db, "2026-11-01", "2026-11-14", "afecta_caja AND tipo NOT IN "
                                                                "('venta','cobro_fiado','prestamo_recibido','otro_ingreso')")  # fmt: skip


def test_analisis_por_metodo_de_pago_y_otros(db, reloj_fijo):
    ing = finanzas.analisis(db, E, "metodo_pago", "ingreso")
    assert {g.clave for g in ing.grupos} == {"efectivo", "billetera_digital", "credito"}
    credito = next(g for g in ing.grupos if g.clave == "credito")
    assert credito.monto == _suma_sql(db, "2026-11-01", "2026-11-14", "tipo = 'venta' AND metodo_pago = 'credito'")
    assert finanzas.analisis(db, E, "proveedor", "egreso").grupos[0].clave == "Distribuidora Andina"
    clientes = {g.clave for g in finanzas.analisis(db, E, "cliente_fiado", "ingreso").grupos}
    assert {"Sra. Carmen", "Don Luis", "Vecina Rosa"} >= clientes and clientes
    assert finanzas.analisis(db, E, "producto", "ingreso").grupos
    meses = finanzas.analisis(db, E, "mes", "ingreso", desde=date(2026, 9, 1), hasta=date(2026, 10, 31))
    assert [g.clave for g in sorted(meses.grupos, key=lambda g: g.clave)] == ["2026-09", "2026-10"]


def test_comparacion_con_pares_necesita_datos(db, reloj_fijo):
    a = finanzas.analisis(db, E, "categoria", "egreso")
    assert a.comparacion_pares is None and "pendiente de datos" in a.comparacion_pares_motivo
    for k in range(5):  # bodegas pares sintéticas (mismo rubro)
        eid = f"EMP-01{k:02d}"
        db.add(m.Empresa(empresa_id=eid, rubro_id="RUB-01", nombre_ficticio=f"Bodega par {k}",
                         telefono_whatsapp=f"+5190000099{k}", zona="SJL", saldo_inicial=Decimal("500"),
                         fecha_saldo_inicial=date(2026, 10, 1), minimo_operativo=Decimal("300"),
                         fecha_alta=dt(date(2026, 10, 1))))  # fmt: skip
        db.flush()
        tx(db, "venta", 1000, date(2026, 11, 5), empresa_id=eid)
        tx(db, "retiro_personal", 100 + 50 * k, date(2026, 11, 6), empresa_id=eid)
    pares = finanzas.analisis(db, E, "categoria", "egreso").comparacion_pares
    # 6 pares: las 5 sintéticas + EMP-0002 ("Pedro · día 3", sin retiros: 0).
    assert pares.n_pares == 6 and pares.mediana_pares == 0.17 and pares.metrica == "retiros_personales_sobre_ventas"
    assert 0 < pares.valor_empresa < 1


def test_analisis_validaciones(client_db, reloj_fijo):
    assert client_db.get(f"{EMP}/analisis?agrupar_por=metodo_pago&tipo=ingreso").status_code == 200
    assert client_db.get(f"{EMP}/analisis?agrupar_por=color").status_code == 400
    assert client_db.get(f"{EMP}/analisis?desde=2026-11-10&hasta=2026-11-01").status_code == 400
