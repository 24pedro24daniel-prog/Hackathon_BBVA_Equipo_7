"""db/models.py: las 25 tablas del DBML, sus CHECK, únicos e índice parcial del sueldo."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DataError, IntegrityError

from app.db import models as m
from app.db.base import Base
from app.schemas.common import Canal, Frecuencia, MetodoPago, TipoDeuda, TipoFlujo, TipoMovimiento

AHORA = datetime.fromisoformat("2026-11-14T10:42:00-05:00")


def test_metadata_tiene_las_25_tablas_mas_idempotencia():
    assert set(Base.metadata.tables) == set(m.TABLAS_DBML) | {"idempotency_keys"}
    assert len(m.TABLAS_DBML) == 25


def test_dinero_es_numeric_12_2():
    col = m.Transaccion.__table__.c.monto
    assert (col.type.precision, col.type.scale) == (12, 2)
    assert m.Transaccion.__table__.c.fecha_hora.type.timezone is True
    assert m.Transaccion.__table__.c.confianza_extraccion.type.scale == 3



def _tx(**cambios) -> m.Transaccion:
    base = dict(transaccion_id="MOV-900001", empresa_id="EMP-0001", fecha_hora=AHORA, tipo=TipoMovimiento.venta,
                categoria_id="CAT-01", monto=Decimal("13.00"), metodo_pago=MetodoPago.efectivo, afecta_caja=True,
                canal=Canal.voz, creado_en=AHORA)  # fmt: skip
    base.update(cambios)
    return m.Transaccion(**base)


def _falla(db, *objs, error=(IntegrityError, DataError)):
    with pytest.raises(error):
        with db.begin_nested():
            db.add_all(objs)
            db.flush()


@pytest.mark.db
def test_bd_tiene_todas_las_tablas(db):
    tablas = set(inspect(db.connection()).get_table_names())
    assert set(m.TABLAS_DBML) | {"idempotency_keys"} <= tablas


@pytest.mark.db
def test_transaccion_valida_se_guarda_con_decimal(db):
    db.add(_tx())
    db.flush()
    db.expire_all()
    guardada = db.get(m.Transaccion, "MOV-900001")
    assert guardada.monto == Decimal("13.00") and isinstance(guardada.monto, Decimal)
    assert guardada.moneda == "PEN" and guardada.anulada is False


@pytest.mark.db
@pytest.mark.parametrize(
    "cambios",
    [
        pytest.param({"monto": Decimal("0")}, id="monto_cero"),
        pytest.param({"monto": Decimal("-5")}, id="monto_negativo"),
        pytest.param({"metodo_pago": MetodoPago.credito, "afecta_caja": True, "fiado_id": "FIA-0045"},
                     id="credito_que_afecta_caja"),
        pytest.param({"afecta_caja": False}, id="efectivo_que_no_afecta_caja"),
        pytest.param({"metodo_pago": MetodoPago.credito, "afecta_caja": False}, id="venta_fiada_sin_fiado"),
        pytest.param({"tipo": TipoMovimiento.compra, "categoria_id": "CAT-10", "metodo_pago": MetodoPago.credito,
                      "afecta_caja": False}, id="compra_credito_sin_deuda"),
        pytest.param({"tipo": TipoMovimiento.cobro_fiado, "categoria_id": "CAT-07"}, id="cobro_sin_fiado"),
        pytest.param({"tipo": TipoMovimiento.pago_proveedor, "categoria_id": "CAT-10"}, id="pago_proveedor_sin_deuda"),
        pytest.param({"tipo": TipoMovimiento.prestamo_recibido, "categoria_id": "CAT-08"}, id="prestamo_sin_deuda"),
        pytest.param({"tipo": TipoMovimiento.pago_impuesto, "categoria_id": "CAT-14"}, id="impuesto_sin_impuesto"),
        pytest.param({"tipo": TipoMovimiento.cobro_fiado, "categoria_id": "CAT-07", "fiado_id": "FIA-0045",
                      "deuda_id": "PED-0012"}, id="dos_vinculos"),
        pytest.param({"moneda": "USD"}, id="moneda_no_pen"),
        pytest.param({"confianza_extraccion": Decimal("1.500")}, id="confianza_mayor_a_1"),
        pytest.param({"categoria_id": "CAT-99"}, id="fk_categoria_inexistente"),
    ],
)  # fmt: skip
def test_check_de_transacciones_rechaza(db, cambios):
    _falla(db, _tx(**cambios))


@pytest.mark.db
def test_casos_validos_del_diccionario(db):
    db.add_all([
        _tx(transaccion_id="MOV-900002", metodo_pago=MetodoPago.credito, afecta_caja=False, fiado_id="FIA-0045"),
        _tx(transaccion_id="MOV-900003", tipo=TipoMovimiento.cobro_fiado, categoria_id="CAT-07", fiado_id="FIA-0045"),
        _tx(transaccion_id="MOV-900004", tipo=TipoMovimiento.pago_proveedor, categoria_id="CAT-10",
            deuda_id="PED-0012"),
        _tx(transaccion_id="MOV-900005", tipo=TipoMovimiento.retiro_personal, categoria_id="CAT-15",
            programado_id="PRG-0002"),
    ])  # fmt: skip
    db.flush()


@pytest.mark.db
def test_enum_invalido_se_rechaza(db):
    with pytest.raises(DataError):
        with db.begin_nested():
            db.execute(text(
                "INSERT INTO transacciones (transaccion_id, empresa_id, fecha_hora, tipo, categoria_id, monto, "
                "metodo_pago, afecta_caja, canal, creado_en) VALUES ('MOV-900009', 'EMP-0001', now(), 'venta', "
                "'CAT-01', 10, 'bitcoin', true, 'voz', now())"
            ))  # fmt: skip


def _deuda(**cambios) -> m.Deuda:
    base = dict(deuda_id="DEU-0901", empresa_id="EMP-0001", tipo=TipoDeuda.proveedor, proveedor_id="PRV-0001",
                monto_recibido=Decimal("100"), monto_total_a_pagar=Decimal("100"), fecha_inicio=date(2026, 11, 1),
                fecha_vencimiento=date(2026, 11, 30), canal=Canal.voz)  # fmt: skip
    base.update(cambios)
    return m.Deuda(**base)


@pytest.mark.db
def test_deuda_proveedor_segun_tipo(db):
    _falla(db, _deuda(proveedor_id=None))
    _falla(db, _deuda(tipo=TipoDeuda.prestamo_informal))
    _falla(db, _deuda(fecha_vencimiento=date(2026, 10, 1)))
    db.add(_deuda(deuda_id="DEU-0902", tipo=TipoDeuda.prestamo_informal, proveedor_id=None,
                  acreedor_nombre="prestamista", monto_total_a_pagar=Decimal("1200"),
                  frecuencia_cuota=Frecuencia.diaria, monto_cuota=Decimal("40")))  # fmt: skip
    db.flush()


def _sueldo(pid: str, activo: bool = True, es_sueldo: bool = True) -> m.MovimientoProgramado:
    return m.MovimientoProgramado(programado_id=pid, empresa_id="EMP-0001", categoria_id="CAT-15",
                                  tipo=TipoFlujo.egreso, descripcion="Sueldo", monto=Decimal("500"),
                                  frecuencia=Frecuencia.semanal, dia_semana=6, es_sueldo=es_sueldo,
                                  fecha_inicio=date(2026, 11, 14), activo=activo)  # fmt: skip


@pytest.mark.db
def test_indice_parcial_un_solo_sueldo_activo(db):
    _falla(db, _sueldo("PRG-0901"), error=IntegrityError)  # el seed ya tiene PRG-0002 activo
    db.add_all([_sueldo("PRG-0902", activo=False), _sueldo("PRG-0903", es_sueldo=False)])
    db.flush()


@pytest.mark.db
def test_cambiar_sueldo_cerrando_el_anterior(db):
    anterior = db.get(m.MovimientoProgramado, "PRG-0002")
    anterior.activo = False
    anterior.fecha_fin = date(2026, 11, 14)
    db.flush()
    db.add(_sueldo("PRG-0904"))
    db.flush()


@pytest.mark.db
def test_unicos_impuestos_y_billeteras(db):
    _falla(db, m.Impuesto(impuesto_id="IMP-0901", empresa_id="EMP-0001", regimen="nuevo_rus", periodo="2026-10",
                          monto=Decimal("20"), fecha_vencimiento=date(2026, 11, 15), canal=Canal.texto))  # fmt: skip
    _falla(db, m.Impuesto(impuesto_id="IMP-0902", empresa_id="EMP-0001", regimen="nuevo_rus", periodo="2026-13",
                          monto=Decimal("20"), fecha_vencimiento=date(2026, 11, 15), canal=Canal.texto))  # fmt: skip
    billetera = dict(empresa_id="EMP-0001", proveedor_billetera="billetera_a", operacion_id="OP-1",
                     tipo=TipoFlujo.ingreso, monto=Decimal("18.50"), fecha_hora=AHORA, origen="api")  # fmt: skip
    _falla(db, m.BilleteraDigital(billetera_mov_id="BIL-0001", **billetera),
           m.BilleteraDigital(billetera_mov_id="BIL-0002", **billetera))


@pytest.mark.db
def test_otros_check(db):
    _falla(db, m.Alerta(alerta_id="ALR-0901", empresa_id="EMP-0001", tipo="faltante_caja", prioridad=9,
                        fecha_evento=date(2026, 11, 30), canal="app", creada_en=AHORA))  # fmt: skip
    _falla(db, m.ScoreSalud(empresa_id="EMP-0001", mes="2026-11", score=101, subindicadores={},
                            version_formula="v"))  # fmt: skip
    _falla(db, m.CuadernoFiado(fiado_id="FIA-0901", empresa_id="EMP-0001", cliente_id="CLI-0102", monto=Decimal("0"),
                               fecha_fiado=date(2026, 11, 14), canal=Canal.voz))  # fmt: skip
