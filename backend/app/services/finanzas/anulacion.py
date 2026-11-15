"""POST /empresas/{id}/cuentas/anular — anula un fiado, un pedido (deuda) o un impuesto registrado por error.

Nada se borra (PLAN §8):
- fiado / pedido: se marcan `anulada = true` las transacciones que lo originaron (venta fiada, compra a crédito o
  préstamo recibido). `consultas.cuentas_fiado/cuentas_deuda` ya excluyen la cuenta cuyo origen está anulado, así que
  deja de aparecer en /fiados, /pedidos, el forecast, el simulador, el resumen y las alertas. Los cobros o pagos que
  ya tuviera se conservan (son plata que sí entró o salió de la caja).
- impuesto: no tiene columna `anulada`; se marca el régimen con el prefijo `anulado_` (y `fecha_pago` para que la
  ingesta no lo tome como impuesto pendiente). Si ya tiene un pago registrado → 409 (primero se anula el pago).
- Las alertas activas de esa cuenta se descartan y los faltantes activos se recalculan (o se cierran si ya no hay).
Repetir la anulación de algo ya anulado responde lo mismo (idempotente).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import reloj
from app.core.categorias import buscar_categoria
from app.core.errors import Conflicto, NoEncontrado
from app.core.ids import nuevo_id
from app.db import models as m
from app.schemas.common import TipoDeuda, TipoMovimiento
from app.services.finanzas import consultas as q

T = TipoMovimiento
Tx = m.Transaccion
ORIGEN_DEUDA = (T.compra, T.prestamo_recibido)


def _fiado(db: Session, empresa_id: str, fiado_id: str) -> None:
    fiado = db.get(m.CuadernoFiado, fiado_id)
    if fiado is None or fiado.empresa_id != empresa_id:
        raise NoEncontrado("No encontré ese fiado.")
    filas = db.scalars(select(Tx).where(Tx.empresa_id == empresa_id, Tx.fiado_id == fiado_id, Tx.tipo == T.venta)).all()
    if not filas:
        # Fiado sin venta de origen (no lo crea la app): se deja una venta fiada ya anulada que lo marca como anulado.
        db.add(Tx(transaccion_id=_nuevo_mov(db), empresa_id=empresa_id, fecha_hora=reloj.inicio_del_dia(fiado.fecha_fiado),
                  tipo=T.venta, categoria_id=_categoria(db, "otros_ingresos"), descripcion="Fiado anulado",
                  monto=fiado.monto, metodo_pago="credito", afecta_caja=False, canal=fiado.canal, fiado_id=fiado_id,
                  anulada=True, creado_en=reloj.ahora()))  # fmt: skip
        return
    for t in filas:
        t.anulada = True


def _pedido(db: Session, empresa_id: str, deuda_id: str) -> None:
    deuda = db.get(m.Deuda, deuda_id)
    if deuda is None or deuda.empresa_id != empresa_id:
        raise NoEncontrado("No encontré ese pedido.")
    filas = db.scalars(select(Tx).where(Tx.empresa_id == empresa_id, Tx.deuda_id == deuda_id,
                                        Tx.tipo.in_(list(ORIGEN_DEUDA)))).all()  # fmt: skip
    if not filas:
        es_proveedor = deuda.tipo == TipoDeuda.proveedor
        db.add(Tx(transaccion_id=_nuevo_mov(db), empresa_id=empresa_id,
                  fecha_hora=reloj.inicio_del_dia(deuda.fecha_inicio), tipo=T.compra if es_proveedor else T.prestamo_recibido,
                  categoria_id=_categoria(db, "mercaderia" if es_proveedor else "prestamos_recibidos"),
                  descripcion="Pedido anulado", monto=deuda.monto_recibido,
                  metodo_pago="credito" if es_proveedor else "efectivo", afecta_caja=not es_proveedor, canal=deuda.canal,
                  deuda_id=deuda_id, anulada=True, creado_en=reloj.ahora()))  # fmt: skip
        return
    for t in filas:
        t.anulada = True


def _impuesto(db: Session, empresa_id: str, impuesto_id: str) -> None:
    imp = db.get(m.Impuesto, impuesto_id)
    if imp is None or imp.empresa_id != empresa_id:
        raise NoEncontrado("No encontré ese impuesto.")
    if q.impuesto_anulado(imp):
        return
    pago = db.scalar(select(Tx.transaccion_id).where(Tx.impuesto_id == impuesto_id, ~Tx.anulada))
    if pago is not None:
        raise Conflicto("Ese impuesto ya tiene un pago anotado. Si fue un error, borra primero ese pago.")
    regimen = (q.PREFIJO_ANULADO + imp.regimen)[:20]
    ya = db.scalar(select(m.Impuesto.impuesto_id).where(m.Impuesto.empresa_id == empresa_id,
                                                        m.Impuesto.regimen == regimen,
                                                        m.Impuesto.periodo == imp.periodo))  # fmt: skip
    if ya is not None:
        regimen = (q.PREFIJO_ANULADO + impuesto_id)[:20]
    imp.regimen = regimen
    imp.fecha_pago = imp.fecha_pago or reloj.hoy()


def _nuevo_mov(db: Session) -> str:
    return nuevo_id(db, m.Transaccion, "MOV")


def _categoria(db: Session, nombre: str) -> str:
    cat = buscar_categoria(db, nombre)
    return cat.categoria_id if cat else db.scalar(select(m.Categoria.categoria_id).order_by(m.Categoria.categoria_id))


ANULADORES = {"fiado": _fiado, "pedido": _pedido, "impuesto": _impuesto}


def anular_cuenta(db: Session, empresa_id: str, tipo: str, cuenta_id: str) -> dict:
    from app.services.alertas.motor import refrescar_tras_anulacion

    q.empresa_o_404(db, empresa_id)
    ANULADORES[tipo](db, empresa_id, cuenta_id)
    db.flush()
    refrescar_tras_anulacion(db, empresa_id, cuenta_id)
    db.commit()
    return {"id": cuenta_id, "anulada": True}
