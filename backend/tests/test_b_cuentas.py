"""B6/B7/B8 — fiados con riesgo de atraso, recordatorio, pedidos y chequeo antes del pedido (cifras de la historia)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.db import models as m
from app.services import finanzas
from app.services.finanzas import chequeo as chq
from tests._b_util import EMP, HOY, P, E, deuda_proveedor, reloj_fijo, tx  # noqa: F401

pytestmark = pytest.mark.db


# ── B6 riesgo de atraso ──


def test_riesgo_de_atraso_por_historial_del_cliente(db, reloj_fijo):
    r = finanzas.fiados(db, E)
    riesgo = {i.fiado_id: i.riesgo_atraso for i in r.items}
    assert riesgo["FIA-0045"].nivel == "alto" and riesgo["FIA-0046"].nivel == "medio" and riesgo["FIA-0047"].nivel == "bajo"
    assert len({x.baseline_probabilidad for x in riesgo.values()}) == 1  # tasa global de la bodega
    assert r.meta.fallback_usado is True and r.meta.modelo == "riesgo-atraso-baseline"
    acciones = {i.fiado_id: i.accion_sugerida for i in r.items}
    assert acciones["FIA-0045"].texto_boton == "Recordar a Sra. Carmen" and acciones["FIA-0047"] is None


def test_riesgo_no_usa_etiquetas_ni_perfil_oculto(db, reloj_fijo):
    antes = {i.fiado_id: i.riesgo_atraso.probabilidad for i in finanzas.fiados(db, E).items}
    db.query(m.CuadernoFiado).update({"pago_tardio": False})
    db.query(m.Cliente).update({"perfil_pago": "puntual"})
    db.query(m.Evento).delete()
    db.flush()
    assert {i.fiado_id: i.riesgo_atraso.probabilidad for i in finanzas.fiados(db, E).items} == antes


def test_riesgo_usa_solo_lo_sabido_al_corte(db, reloj_fijo):
    """Un cobro tardío de Rosa registrado después del corte no cambia su riesgo hoy."""
    hoy = finanzas.fiados(db, E).items
    rosa = next(i for i in hoy if i.fiado_id == "FIA-0047").riesgo_atraso.probabilidad
    tx(db, "cobro_fiado", 95, HOY + timedelta(days=20), fiado_id="FIA-0047")  # pagaría tarde, en el futuro
    assert next(i for i in finanzas.fiados(db, E).items if i.fiado_id == "FIA-0047").riesgo_atraso.probabilidad == rosa


def test_recordatorio(client_db, db, reloj_fijo):
    r = client_db.post(f"{P}/fiados/FIA-0045/recordatorio")
    assert r.status_code == 200
    assert r.json()["mensaje"] == "Hola, Sra. Carmen 😊 Le recuerdo amablemente los S/ 120 pendientes en la bodega. ¡Gracias!"
    assert client_db.post(f"{P}/fiados/FIA-9999/recordatorio").status_code == 404
    assert "ya pagó" in client_db.post(f"{P}/fiados/FIA-0001/recordatorio").json()["mensaje"]
    tx(db, "cobro_fiado", 20, HOY, fiado_id="FIA-0045")
    assert "S/ 100 pendientes" in client_db.post(f"{P}/fiados/FIA-0045/recordatorio").json()["mensaje"]


# ── B7 pedidos ──


def test_pedidos_endpoint(client_db, reloj_fijo):
    j = client_db.get(f"{EMP}/pedidos").json()
    assert j["total_pendiente"] == 2400.0 and j["items"][0]["pedido_id"] == "PED-0012"
    assert j["items"][0]["fecha_pedido"] == "2026-11-13" and j["items"][0]["estado"] == "pendiente"
    assert j["impuestos"] == {"estado": "al_dia", "proximo_vencimiento": "2026-12-15", "monto_estimado": 20.0,
                              "nombre": "RUS de noviembre"}  # fmt: skip
    assert client_db.get(f"{P}/empresas/EMP-9999/pedidos").status_code == 404


# ── B8 chequeo antes del pedido ──


def test_chequeo_2400_cuadra_con_la_historia(client_db, reloj_fijo):
    j = client_db.post(f"{EMP}/pedidos/chequeo",
                       json={"proveedor": "Distribuidora Andina", "monto": 2400, "fecha_vencimiento": "2026-11-30"}).json()  # fmt: skip
    assert j["saldo_proyectado_al_vencimiento"] == -650.0 and j["estado_caja"] == "no_te_alcanza"
    assert (j["venta_esperada_periodo"], j["exceso_vs_ventas"]) == (2000.0, 400.0)
    assert [(s["accion"], s.get("monto_sugerido"), s["saldo_resultante"]) for s in j["sugerencias"]] == [
        ("reducir_pedido", 1800.0, -50.0), ("pagar_en_partes", None, 550.0), ("combinar", 1800.0, 850.0)]
    assert j["pedido_coincidente_id"] == "PED-0012"  # el pedido ya registrado no se cuenta dos veces
    assert "S/ 2 000" in j["fundamento"] and "S/ 400" in j["fundamento"]
    assert "15/12" in j["limites"]  # la 2.ª parte queda fuera del horizonte y se avisa
    assert j["confianza"] in ("baja", "media", "alta") and j["meta"]["fallback_usado"] is True


def test_chequeo_acepta_alias_del_proveedor(db, reloj_fijo):
    ch = finanzas.chequeo_pedido(db, E, "andina", Decimal("2400"), date(2026, 11, 30))
    assert ch.pedido_coincidente_id == "PED-0012" and ch.saldo_proyectado_al_vencimiento == Decimal("-650.00")


def test_chequeo_de_un_pedido_nuevo_suma_al_que_ya_existe(db, reloj_fijo):
    ch = finanzas.chequeo_pedido(db, E, "Distribuidora Andina", Decimal("500"), date(2026, 11, 30))
    assert ch.pedido_coincidente_id is None
    assert ch.saldo_proyectado_al_vencimiento == Decimal("-1150.00")
    assert ch.venta_esperada_periodo == Decimal("2000.00") and ch.exceso_vs_ventas == 0


def test_chequeo_al_confirmar_no_duplica_el_pedido_recien_registrado(db, reloj_fijo):
    nuevo = deuda_proveedor(db, 2400, date(2026, 11, 30))  # lo que hace A al confirmar
    ch = finanzas.chequeo_pedido(db, E, "Distribuidora Andina", Decimal("2400"), date(2026, 11, 30))
    assert ch.pedido_coincidente_id == nuevo.deuda_id
    assert ch.saldo_proyectado_al_vencimiento == Decimal("-3050.00")  # ahora sí hay dos pedidos de 2 400


def test_chequeo_que_alcanza_no_sugiere(db, reloj_fijo):
    tx(db, "otro_ingreso", 5000, HOY)
    ch = finanzas.chequeo_pedido(db, E, "Distribuidora Andina", Decimal("300"), date(2026, 11, 25))
    assert ch.estado_caja == "te_alcanza" and ch.sugerencias == [] and ch.exceso_vs_ventas == 0


def test_chequeo_proveedor_desconocido_usa_todas_las_ventas(db, reloj_fijo):
    ch = finanzas.chequeo_pedido(db, E, "Distribuidora Sol", Decimal("1000"), date(2026, 12, 10))
    assert ch.venta_esperada_periodo > 10000 and "en total" in ch.fundamento
    assert ch.saldo_proyectado_al_vencimiento < 0  # el pago del 30/11 sigue ahí


def test_redondeo_de_estimaciones():
    assert chq.redondear_estimacion(Decimal("1961.6")) == Decimal("2000.00")
    assert chq.redondear_estimacion(Decimal("1949.9")) == Decimal("1900.00")
    assert chq.redondear_estimacion(Decimal("456")) == Decimal("460.00")
    assert chq.redondear_abajo(Decimal("1800")) == Decimal("1800.00")
    assert chq.redondear_abajo(Decimal("1799")) == Decimal("1700.00")
