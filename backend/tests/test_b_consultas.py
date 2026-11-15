"""B1 — consultas a fecha de corte: saldo, fiados, deudas (pedidos) e impuestos, con el seed de Pedro."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.errors import NoEncontrado
from app.db import models as m
from app.services import finanzas
from app.services.finanzas import consultas as q
from tests._b_util import EMP, HOY, E, deuda_proveedor, dt, fiado, reloj_fijo, tx  # noqa: F401

pytestmark = pytest.mark.db


# ── saldo de caja ──


def test_saldo_del_seed_es_2340(db, reloj_fijo):
    assert finanzas.saldo_caja(db, E) == Decimal("2340.00")
    assert finanzas.saldo_caja(db, E, HOY) == Decimal("2340.00")


def test_saldo_en_un_corte_pasado_coincide_con_el_cierre_del_dia(db):
    for d in (date(2026, 8, 15), date(2026, 9, 30), date(2026, 10, 31)):
        assert finanzas.saldo_caja(db, E, d) == db.get(m.SaldoDiario, (E, d)).saldo_cierre


def test_saldo_respeta_creado_en_anuladas_y_credito(db, reloj_fijo):
    tx(db, "venta", 13, HOY)                                            # cuenta
    tx(db, "venta", 100, HOY, creado=dt(HOY + timedelta(days=1), 9))    # anotado después del corte: no cuenta hoy
    tx(db, "gasto_negocio", 50, HOY, anulada=True)                      # anulado: nunca cuenta
    fiado(db, "CLI-0110", 40)                                           # venta fiada: crédito, no mueve caja
    tx(db, "venta", 7, HOY + timedelta(days=1))                         # ocurre después del corte
    assert finanzas.saldo_caja(db, E, HOY) == Decimal("2353.00")
    assert finanzas.saldo_caja(db, E, HOY + timedelta(days=1)) == Decimal("2460.00")


def test_saldo_empresa_inexistente_404(db):
    with pytest.raises(NoEncontrado):
        finanzas.saldo_caja(db, "EMP-9999")


# ── fiados ──


def test_fiados_pendientes_del_seed(db, reloj_fijo):
    r = finanzas.fiados(db, E)
    assert r.total_pendiente == Decimal("310.00") and r.total_vencido == Decimal("120.00")
    por_id = {i.fiado_id: i for i in r.items}
    assert set(por_id) == {"FIA-0045", "FIA-0046", "FIA-0047"}
    carmen, luis, rosa = por_id["FIA-0045"], por_id["FIA-0046"], por_id["FIA-0047"]
    assert (carmen.cliente, carmen.monto, carmen.dias_transcurridos, carmen.estado) == ("Sra. Carmen", 120, 18, "vencido")
    assert (luis.estado, rosa.estado) == ("por_vencer", "pendiente")  # compromiso 16/11 (2 días) y 19/11 (5 días)
    assert r.items[0].fiado_id == "FIA-0045"  # lo vencido primero


def test_fiados_a_fecha_de_corte_y_cobros(db, reloj_fijo):
    antes = finanzas.fiados(db, E, fecha_corte=date(2026, 11, 1))
    carmen = next(i for i in antes.items if i.fiado_id == "FIA-0045")
    assert {i.fiado_id for i in antes.items} >= {"FIA-0045"} and "FIA-0046" not in {i.fiado_id for i in antes.items}
    assert (carmen.estado, carmen.dias_transcurridos) == ("pendiente", 5)
    tx(db, "cobro_fiado", 50, HOY, fiado_id="FIA-0045")
    tx(db, "cobro_fiado", 70, HOY, fiado_id="FIA-0045", creado=dt(HOY + timedelta(days=1)))  # aún no se sabe
    r = finanzas.fiados(db, E)
    assert next(i for i in r.items if i.fiado_id == "FIA-0045").monto == Decimal("70.00")
    assert r.total_pendiente == Decimal("260.00")
    manana = finanzas.fiados(db, E, fecha_corte=HOY + timedelta(days=1))
    assert "FIA-0045" not in {i.fiado_id for i in manana.items}
    pagados = finanzas.fiados(db, E, estado="pagado", fecha_corte=HOY + timedelta(days=1))
    assert "FIA-0045" in {i.fiado_id for i in pagados.items}


def test_filtro_de_estado_de_fiados(client_db, reloj_fijo):
    assert [i["fiado_id"] for i in client_db.get(f"{EMP}/fiados?estado=vencido").json()["items"]] == ["FIA-0045"]
    assert [i["fiado_id"] for i in client_db.get(f"{EMP}/fiados?estado=por_vencer").json()["items"]] == ["FIA-0046"]
    pagados = client_db.get(f"{EMP}/fiados?estado=pagado").json()
    assert len(pagados["items"]) == 44 and pagados["total_pendiente"] == 0


# ── deudas (pedidos) ──


def test_pedido_andina_a_fecha_de_corte(db, reloj_fijo):
    r = finanzas.pedidos(db, E)
    assert r.total_pendiente == Decimal("2400.00") and [i.pedido_id for i in r.items] == ["PED-0012"]
    ped = r.items[0]
    assert (ped.proveedor, ped.monto_pendiente, ped.estado, ped.dias_para_vencer) == (
        "Distribuidora Andina", Decimal("2400.00"), "pendiente", 16)
    assert finanzas.pedidos(db, E, fecha_corte=date(2026, 11, 27)).items[0].estado == "por_vencer"  # ≤ 3 días
    assert finanzas.pedidos(db, E, fecha_corte=date(2026, 12, 1)).items[0].estado == "vencido"
    assert finanzas.pedidos(db, E, fecha_corte=date(2026, 11, 12)).items == []  # aún no se había pedido
    assert len(finanzas.pedidos(db, E, estado="pagado").items) == 11


def test_pago_parcial_anulada_y_posterior_al_corte(db, reloj_fijo):
    tx(db, "pago_proveedor", 400, HOY, deuda_id="PED-0012")
    tx(db, "pago_proveedor", 100, HOY, deuda_id="PED-0012", anulada=True)
    tx(db, "pago_proveedor", 200, HOY, deuda_id="PED-0012", creado=dt(HOY + timedelta(days=2)))
    assert finanzas.pedidos(db, E).items[0].monto_pendiente == Decimal("2000.00")
    assert finanzas.saldo_caja(db, E) == Decimal("1940.00")


def test_deuda_con_origen_anulado_no_existe(db, reloj_fijo):
    d = deuda_proveedor(db, 500, date(2026, 11, 25), anulada=True)
    assert d.deuda_id not in {i.pedido_id for i in finanzas.pedidos(db, E).items}


def test_cronograma_de_prestamo_con_cuotas(db):
    deuda = m.Deuda(deuda_id="DEU-0001", empresa_id=E, tipo="prestamo_informal", acreedor_nombre="Don Pepe",
                    monto_recibido=Decimal("1000"), monto_total_a_pagar=Decimal("1200"), frecuencia_cuota="diaria",
                    monto_cuota=Decimal("40"), fecha_inicio=date(2026, 11, 10), fecha_vencimiento=date(2026, 12, 10),
                    canal="voz")  # fmt: skip
    db.add(deuda)
    db.flush()
    tx(db, "prestamo_recibido", 1000, date(2026, 11, 10), deuda_id="DEU-0001")
    tx(db, "pago_prestamo", 80, date(2026, 11, 12), deuda_id="DEU-0001")
    dc = next(d for d in q.cuentas_deuda(db, E, HOY) if d.deuda.deuda_id == "DEU-0001")
    assert dc.pendiente == Decimal("1120.00")
    pagos = q.cronograma_pagos(dc, HOY, HOY + timedelta(days=30))
    assert pagos[0] == (HOY + timedelta(days=1), Decimal("80.00"))  # cuotas del 13 y 14 atrasadas → mañana
    assert all(mo == Decimal("40.00") for _, mo in pagos[1:])
    assert sum(mo for _, mo in pagos) == Decimal("1120.00")


# ── impuestos ──


def test_estado_impuestos(db, reloj_fijo):
    e = finanzas.estado_impuestos(db, E)
    assert (e.estado, e.proximo_vencimiento, e.monto_estimado, e.nombre) == (
        "al_dia", date(2026, 12, 15), Decimal("20.00"), "RUS de noviembre")
    assert finanzas.estado_impuestos(db, E, date(2026, 12, 16)).estado == "vencido"
    antes = finanzas.estado_impuestos(db, E, date(2026, 10, 12))  # RUS de septiembre aún sin pagar, vence 15/10
    assert (antes.estado, antes.proximo_vencimiento) == ("al_dia", date(2026, 10, 15))
    assert finanzas.estado_impuestos(db, E, date(2026, 10, 16)).estado == "al_dia"  # se pagó el 13/10
    assert finanzas.pedidos(db, E).impuestos.estado == "al_dia"


def test_impuesto_pagado_con_transaccion(db, reloj_fijo):
    tx(db, "pago_impuesto", 20, HOY, impuesto_id="IMP-0004")
    e = finanzas.estado_impuestos(db, E, date(2026, 12, 20))
    assert e.estado == "al_dia" and e.proximo_vencimiento == date(2027, 1, 15)
