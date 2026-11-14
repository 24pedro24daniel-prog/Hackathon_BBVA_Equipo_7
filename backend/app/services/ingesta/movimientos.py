"""Listado de movimientos (A2): filtros, paginación por cursor (más reciente primero) y `saldo_post`.

`saldo_post` = saldo de la caja del negocio justo después del movimiento: saldo_inicial + Σ (con signo) de los
movimientos que afectan caja y no están anulados, en orden (fecha_hora, transaccion_id). Se calcula al leer;
nunca se guarda. Las anuladas no se listan.
"""

from datetime import date, datetime, timedelta

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.errors import Validacion
from app.core.paginacion import Pagina, recortar
from app.core.reloj import a_lima, inicio_del_dia
from app.db import models as m
from app.schemas.common import TIPOS_INGRESO

Tx = m.Transaccion


def listar(db: Session, empresa_id: str, pagina: Pagina, *, desde: date | None = None, hasta: date | None = None,
           tipo: str | None = None, categoria: str | None = None, canal: str | None = None) -> dict:  # fmt: skip
    empresa = db.get(m.Empresa, empresa_id)
    con_signo = case((Tx.tipo.in_(list(TIPOS_INGRESO)), Tx.monto), else_=-Tx.monto)
    efecto = case((and_(Tx.afecta_caja, ~Tx.anulada), con_signo), else_=0)
    acumulado = func.sum(efecto).over(order_by=(Tx.fecha_hora, Tx.transaccion_id))

    cliente = aliased(m.Cliente)
    proveedor = aliased(m.Proveedor)
    base = (
        select(
            Tx.transaccion_id, Tx.fecha_hora, Tx.tipo, Tx.monto, Tx.moneda, Tx.metodo_pago, Tx.canal,
            Tx.confianza_extraccion, Tx.afecta_caja, Tx.anulada, Tx.categoria_id,
            m.Categoria.nombre.label("categoria"),
            func.coalesce(cliente.nombre_ficticio, proveedor.nombre_ficticio, m.Deuda.acreedor_nombre).label("contraparte"),
            acumulado.label("acumulado"),
        )  # fmt: skip
        .join(m.Categoria, m.Categoria.categoria_id == Tx.categoria_id)
        .outerjoin(m.CuadernoFiado, m.CuadernoFiado.fiado_id == Tx.fiado_id)
        .outerjoin(cliente, cliente.cliente_id == m.CuadernoFiado.cliente_id)
        .outerjoin(m.Deuda, m.Deuda.deuda_id == Tx.deuda_id)
        .outerjoin(proveedor, proveedor.proveedor_id == m.Deuda.proveedor_id)
        .where(Tx.empresa_id == empresa_id)
        .subquery()
    )
    q = select(base).where(~base.c.anulada)
    if desde:
        q = q.where(base.c.fecha_hora >= inicio_del_dia(desde))
    if hasta:
        q = q.where(base.c.fecha_hora < inicio_del_dia(hasta + timedelta(days=1)))
    if tipo:
        q = q.where(base.c.tipo == tipo)
    if canal:
        q = q.where(base.c.canal == canal)
    if categoria:
        clave = categoria.replace("_", " ").lower()
        q = q.where(or_(base.c.categoria_id == categoria, func.lower(base.c.categoria) == clave))
    if pagina.cursor:
        try:
            f_cursor = datetime.fromisoformat(pagina.cursor["f"])
            id_cursor = str(pagina.cursor["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise Validacion("El cursor no es válido.", [{"campo": "cursor", "problema": "formato inválido"}]) from exc
        q = q.where(or_(base.c.fecha_hora < f_cursor,
                        and_(base.c.fecha_hora == f_cursor, base.c.transaccion_id < id_cursor)))  # fmt: skip
    filas = db.execute(q.order_by(base.c.fecha_hora.desc(), base.c.transaccion_id.desc()).limit(pagina.limit + 1)).all()
    pagina_filas, siguiente = recortar(filas, pagina.limit,
                                       lambda f: {"f": f.fecha_hora.isoformat(), "id": f.transaccion_id})  # fmt: skip
    saldo_inicial = empresa.saldo_inicial if empresa else 0
    items = [
        {
            "movimiento_id": f.transaccion_id,
            "fecha_hora": a_lima(f.fecha_hora),
            "tipo": f.tipo,
            "categoria": f.categoria,
            "monto": f.monto,
            "moneda": f.moneda,
            "metodo_pago": f.metodo_pago,
            "contraparte": f.contraparte,
            "canal": f.canal,
            "confianza_extraccion": float(f.confianza_extraccion) if f.confianza_extraccion is not None else None,
            "afecta_caja": f.afecta_caja,
            "saldo_post": saldo_inicial + f.acumulado,
        }
        for f in pagina_filas
    ]
    return {"items": items, "next_cursor": siguiente}
