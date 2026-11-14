"""A1 — registrador: cada caso del diccionario §4 crea la transacción y la fila satélite correcta."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.core.errors import Conflicto, Validacion
from app.db import models as m
from app.schemas.ingesta import MovimientoPropuesto
from app.services.ingesta.registrador import anular_movimiento, registrar_movimiento

pytestmark = pytest.mark.db
EMP = "EMP-0001"
HOY = datetime.fromisoformat("2026-11-14T10:42:00-05:00")


def _mov(**kw) -> MovimientoPropuesto:
    kw.setdefault("fecha_hora", HOY)
    return MovimientoPropuesto(**kw)


def _registrar(db, canal="texto", **kw):
    return registrar_movimiento(db, EMP, _mov(**kw), canal=canal, confianza=Decimal("0.9"))


def _tx(db, res) -> m.Transaccion:
    return db.get(m.Transaccion, res.movimiento_id)


def _tablas(res) -> list[str]:
    return [r.tabla for r in res.registros_creados]


def test_venta_efectivo_con_detalle(db):
    res = _registrar(db, canal="voz", tipo="venta", monto=13, metodo_pago="efectivo",
                     items=[{"producto_id": "PRD-0031", "producto": "Cerveza 620 ml", "cantidad": 2,
                             "precio_unitario": 6.5, "subtotal": 13}])  # fmt: skip
    tx = _tx(db, res)
    assert _tablas(res) == ["transacciones"]
    assert (tx.tipo, tx.metodo_pago, tx.afecta_caja, tx.monto, tx.categoria_id) == ("venta", "efectivo", True,
                                                                                    Decimal("13.00"), "CAT-01")
    assert tx.confianza_extraccion == Decimal("0.900") and tx.canal == "voz" and tx.moneda == "PEN"
    detalle = db.query(m.DetalleTransaccion).filter_by(transaccion_id=tx.transaccion_id).one()
    assert (detalle.producto_id, detalle.cantidad, detalle.costo_unitario) == ("PRD-0031", Decimal("2"), Decimal("4.80"))
    assert res.movimiento_id.startswith("MOV-") and len(res.movimiento_id) == 10


def test_venta_fiada_crea_cuaderno_fiado_y_no_mueve_caja(db):
    res = _registrar(db, tipo="venta", monto=20, metodo_pago="credito", contraparte="Rosa")
    tx = _tx(db, res)
    assert _tablas(res) == ["transacciones", "cuaderno_fiado"]
    assert tx.metodo_pago == "credito" and tx.afecta_caja is False
    fiado = db.get(m.CuadernoFiado, tx.fiado_id)
    assert (fiado.cliente_id, fiado.monto, fiado.fecha_fiado, fiado.fecha_pago_total) == (
        "CLI-0110", Decimal("20.00"), date(2026, 11, 14), None)


def test_venta_fiada_a_cliente_nuevo_lo_crea(db):
    res = _registrar(db, tipo="venta", monto=12, metodo_pago="credito", contraparte="Juana")
    assert _tablas(res) == ["transacciones", "clientes", "cuaderno_fiado"]
    cliente = db.get(m.Cliente, next(r.id for r in res.registros_creados if r.tabla == "clientes"))
    assert cliente.nombre_ficticio == "Juana" and cliente.perfil_pago is None


def test_venta_fiada_sin_cliente_es_400(db):
    with pytest.raises(Validacion, match="fiaste"):
        _registrar(db, tipo="venta", monto=12, metodo_pago="credito")


def test_cobro_de_fiado_completo_cierra_el_fiado(db):
    res = _registrar(db, tipo="cobro_fiado", monto=95, contraparte="Vecina Rosa")
    tx = _tx(db, res)
    assert tx.fiado_id == "FIA-0047" and tx.afecta_caja is True
    fiado = db.get(m.CuadernoFiado, "FIA-0047")
    assert fiado.fecha_pago_total == date(2026, 11, 14) and fiado.pago_tardio is False


def test_cobro_parcial_no_cierra_y_excedente_es_400(db):
    _registrar(db, tipo="cobro_fiado", monto=50, contraparte="la señora Carmen")
    assert db.get(m.CuadernoFiado, "FIA-0045").fecha_pago_total is None
    with pytest.raises(Validacion, match="Solo te debe"):
        _registrar(db, tipo="cobro_fiado", monto=500, contraparte="Carmen")


def test_cobro_de_cliente_sin_fiados_es_400(db):
    with pytest.raises(Validacion):
        _registrar(db, tipo="cobro_fiado", monto=10, contraparte="Nadie Conocido")


def test_compra_a_credito_crea_deuda_proveedor(db):
    res = _registrar(db, canal="voz", tipo="compra", monto=2400, metodo_pago="credito",
                     contraparte="Distribuidora Andina", fecha_vencimiento="2026-11-30")  # fmt: skip
    tx = _tx(db, res)
    assert _tablas(res) == ["transacciones", "deudas"]
    assert tx.afecta_caja is False and tx.deuda_id == "PED-0013"
    deuda = db.get(m.Deuda, "PED-0013")
    assert (deuda.tipo, deuda.proveedor_id, deuda.monto_total_a_pagar, deuda.fecha_vencimiento) == (
        "proveedor", "PRV-0001", Decimal("2400.00"), date(2026, 11, 30))


def test_compra_a_credito_sin_fecha_usa_plazo_del_proveedor(db):
    res = _registrar(db, tipo="compra", monto=300, metodo_pago="credito", contraparte="Andina")
    assert db.get(m.Deuda, _tx(db, res).deuda_id).fecha_vencimiento == date(2026, 11, 29)


def test_pago_a_proveedor_y_pago_total(db):
    res = _registrar(db, tipo="pago_proveedor", monto=1200, contraparte="Andina")
    tx = _tx(db, res)
    assert tx.deuda_id == "PED-0012" and tx.afecta_caja is True
    assert db.get(m.Deuda, "PED-0012").fecha_pago_total is None
    _registrar(db, tipo="pago_proveedor", monto=1200, contraparte="Andina")
    assert db.get(m.Deuda, "PED-0012").fecha_pago_total == date(2026, 11, 14)


def test_prestamo_recibido_y_pago_de_cuota(db):
    res = _registrar(db, tipo="prestamo_recibido", monto=1000, monto_total_a_pagar=1200, frecuencia_cuota="diaria",
                     monto_cuota=40, contraparte="Prestamista (gota a gota)")  # fmt: skip
    tx = _tx(db, res)
    deuda = db.get(m.Deuda, tx.deuda_id)
    assert tx.afecta_caja is True and tx.categoria_id == "CAT-08"
    assert (deuda.tipo, deuda.proveedor_id, deuda.frecuencia_cuota, deuda.fecha_vencimiento) == (
        "prestamo_informal", None, "diaria", date(2026, 12, 14))
    pago = _registrar(db, tipo="pago_prestamo", monto=40)
    assert _tx(db, pago).deuda_id == deuda.deuda_id


def test_prestamo_familiar_por_acreedor(db):
    res = _registrar(db, tipo="prestamo_recibido", monto=500, contraparte="Mi hermano")
    assert db.get(m.Deuda, _tx(db, res).deuda_id).tipo == "familiar"


def test_retiro_del_sueldo_se_vincula_al_programado(db):
    sueldo = _registrar(db, tipo="retiro_personal", monto=400)
    assert _tx(db, sueldo).programado_id == "PRG-0002" and _tx(db, sueldo).categoria_id == "CAT-15"
    extra = _registrar(db, tipo="retiro_personal", monto=400)
    assert _tx(db, extra).programado_id is None  # ya se pagó el sueldo de esta semana
    otro = _registrar(db, tipo="retiro_personal", monto=50)
    assert _tx(db, otro).programado_id is None


def test_gasto_recurrente_se_vincula(db):
    res = _registrar(db, tipo="gasto_negocio", monto=180, categoria="servicios", descripcion="Pagué la luz")
    tx = _tx(db, res)
    assert tx.programado_id == "PRG-0001" and tx.categoria_id == "CAT-11"
    otro = _registrar(db, tipo="gasto_negocio", monto=8, descripcion="Mototaxi")
    assert _tx(db, otro).programado_id is None and _tx(db, otro).categoria_id == "CAT-17"


def test_pago_de_impuesto_marca_el_periodo(db):
    res = _registrar(db, tipo="pago_impuesto", monto=20)
    tx = _tx(db, res)
    imp = db.get(m.Impuesto, tx.impuesto_id)
    assert (imp.periodo, imp.fecha_pago) == ("2026-11", date(2026, 11, 14))
    with pytest.raises(Conflicto):
        _registrar(db, tipo="pago_impuesto", monto=20, impuesto_id=imp.impuesto_id)


def test_credito_solo_en_venta_o_compra(db):
    with pytest.raises(Validacion, match="crédito"):
        _registrar(db, tipo="retiro_personal", monto=50, metodo_pago="credito")


@pytest.mark.parametrize("tipo", ["venta", "compra", "gasto_negocio", "otro_ingreso", "retiro_personal"])
def test_metodo_credito_implica_no_afecta_caja(db, tipo):
    metodo = "credito" if tipo in ("venta", "compra") else "billetera_digital"
    extra = {"contraparte": "Rosa" if tipo == "venta" else "Andina"} if metodo == "credito" else {}
    tx = _tx(db, _registrar(db, tipo=tipo, monto=10, metodo_pago=metodo, **extra))
    assert tx.afecta_caja is (metodo != "credito")


def test_anular_no_borra_y_reabre_el_fiado(db):
    res = _registrar(db, tipo="cobro_fiado", monto=95, contraparte="Rosa")
    anular_movimiento(db, EMP, res.movimiento_id)
    tx = _tx(db, res)
    assert tx is not None and tx.anulada is True
    assert db.get(m.CuadernoFiado, "FIA-0047").fecha_pago_total is None
    with pytest.raises(Conflicto):
        anular_movimiento(db, EMP, res.movimiento_id)


def test_error_hace_rollback(db):
    antes = db.query(m.Transaccion).count()
    with pytest.raises(Validacion):
        _registrar(db, tipo="pago_proveedor", monto=99999, contraparte="Andina")
    assert db.query(m.Transaccion).count() == antes
