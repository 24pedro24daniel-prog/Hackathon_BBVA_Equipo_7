"""Impuestos por menú de botones (A9, F1.4): "¿Pagaste tu RUS de octubre?" → impuestos (+ pago_impuesto).

Si se marca pagado y hay monto, se registra la transacción `pago_impuesto` (sale de la caja) con el registrador.
Repetir el mismo periodo ya pagado no duplica nada: responde lo que ya estaba (`ya_registrado = true`).
"""

from datetime import datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import nuevo_id
from app.core.reloj import ahora, hoy, zona
from app.db import models as m
from app.schemas.common import Canal, MetodoPago, TipoMovimiento
from app.schemas.ingesta import ImpuestoRequest, MovimientoPropuesto
from app.services.ingesta import registrador
from app.services.ingesta.registrador import vencimiento_impuesto
from app.services.ingesta.servicio import empresa_o_404


def _pagado(db: Session, imp: m.Impuesto) -> bool:
    tx = db.scalar(select(m.Transaccion.transaccion_id).where(m.Transaccion.impuesto_id == imp.impuesto_id,
                                                              ~m.Transaccion.anulada))  # fmt: skip
    return imp.fecha_pago is not None or tx is not None


def proximo_vencimiento(db: Session, empresa_id: str):
    impuestos = db.scalars(select(m.Impuesto).where(m.Impuesto.empresa_id == empresa_id).order_by(m.Impuesto.periodo)).all()
    pendientes = [i.fecha_vencimiento for i in impuestos if i.fecha_pago is None]
    if pendientes:
        return min(pendientes)
    if not impuestos:
        return vencimiento_impuesto(hoy().strftime("%Y-%m"))
    ultimo = impuestos[-1].periodo
    anio, mes = map(int, ultimo.split("-"))
    return vencimiento_impuesto(f"{anio + mes // 12}-{mes % 12 + 1:02d}")


def estado_de(db: Session, imp: m.Impuesto, empresa_id: str) -> str:
    if imp.fecha_pago is None:
        return "vencido" if imp.fecha_vencimiento < hoy() else "pendiente"
    vencidos = db.scalar(select(m.Impuesto.impuesto_id).where(
        m.Impuesto.empresa_id == empresa_id, m.Impuesto.fecha_pago.is_(None), m.Impuesto.fecha_vencimiento < hoy()))  # fmt: skip
    return "vencido" if vencidos else "al_dia"


def registrar(db: Session, empresa_id: str, body: ImpuestoRequest) -> dict:
    empresa_o_404(db, empresa_id)
    imp = db.scalars(select(m.Impuesto).where(m.Impuesto.empresa_id == empresa_id, m.Impuesto.regimen == body.regimen,
                                              m.Impuesto.periodo == body.periodo)).first()  # fmt: skip
    if imp is None:
        imp = m.Impuesto(impuesto_id=nuevo_id(db, m.Impuesto, "IMP"), empresa_id=empresa_id, regimen=body.regimen,
                         periodo=body.periodo, monto=body.monto, fecha_vencimiento=vencimiento_impuesto(body.periodo),
                         canal=Canal.texto)  # fmt: skip
        db.add(imp)
        db.flush()
    ya_registrado = _pagado(db, imp) if body.pagado else False
    movimiento_id = None
    if body.pagado and not ya_registrado:
        fecha = body.fecha_pago or hoy()
        if body.monto > 0:
            imp.monto = body.monto
            cuando = ahora().replace(microsecond=0) if fecha == hoy() else datetime.combine(fecha, time(12, 0), zona())
            mov = MovimientoPropuesto(tipo=TipoMovimiento.pago_impuesto, monto=body.monto, metodo_pago=MetodoPago.efectivo,
                                      impuesto_id=imp.impuesto_id, fecha_hora=cuando,
                                      descripcion=f"{body.regimen.replace('_', ' ').title()} {body.periodo}")  # fmt: skip
            movimiento_id = registrador.registrar_movimiento(db, empresa_id, mov, canal=Canal.texto,
                                                             commit=False).movimiento_id  # fmt: skip
        else:
            imp.fecha_pago = fecha
    elif not body.pagado and imp.fecha_pago is None and body.monto > 0:
        imp.monto = body.monto
    db.commit()
    respuesta = {"impuesto_id": imp.impuesto_id, "estado": estado_de(db, imp, empresa_id),
                 "proximo_vencimiento": proximo_vencimiento(db, empresa_id), "ya_registrado": ya_registrado}  # fmt: skip
    if movimiento_id:
        respuesta["movimiento_id"] = movimiento_id
    return respuesta
