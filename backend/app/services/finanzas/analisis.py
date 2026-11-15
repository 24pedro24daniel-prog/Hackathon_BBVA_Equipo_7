"""B13 — Análisis F5 (contract.md §5): agrupaciones y comparación con pares.

- Base caja (lo que entró o salió de la caja) para `categoria`, `producto` y `mes`; así una compra a crédito no se
  cuenta dos veces (la compra y su pago). `metodo_pago` usa todos los movimientos (muestra cuánto se fió o pidió a
  crédito). `proveedor` = pedidos a crédito por proveedor; `cliente_fiado` = ventas fiadas por cliente.
- Variación contra el periodo anterior de igual largo (por defecto) o el mismo periodo del año anterior.
- Comparación con pares: mediana de `retiros_personales / ventas` de las otras empresas del mismo rubro en la BD. Con
  menos de MIN_PARES no se publica (`comparacion_pares = null` y el motivo): la BD de la demo solo tiene a Pedro.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import reloj
from app.core.errors import Validacion
from app.db import models as m
from app.schemas.analisis import AnalisisResponse, ComparacionPares, Grupo, PeriodoAnalisis
from app.schemas.common import TIPOS_INGRESO, TipoMovimiento, redondear
from app.services.finanzas import consultas as q

T = TipoMovimiento
Tx = m.Transaccion
MIN_PARES = 5
METRICA_PARES = "retiros_personales_sobre_ventas"


def _clave(texto: str) -> str:
    return texto.strip().lower().replace(" ", "_")


def _filtro_tipo(tipo: str):
    ingresos = list(TIPOS_INGRESO)
    return Tx.tipo.in_(ingresos) if tipo == "ingreso" else Tx.tipo.not_in(ingresos)


def _agrupar(db: Session, empresa_id: str, agrupar_por: str, tipo: str, desde: date, hasta: date, corte: date
             ) -> dict[str, Decimal]:  # fmt: skip
    rango = [Tx.fecha_hora >= reloj.inicio_del_dia(desde), Tx.fecha_hora < q.fin_del_dia(hasta)]
    base = [*q.vigentes(empresa_id, corte), *rango]
    grupos: dict[str, Decimal] = defaultdict(Decimal)
    if agrupar_por == "categoria":
        filas = db.execute(select(m.Categoria.nombre, Tx.monto).join(m.Categoria, m.Categoria.categoria_id == Tx.categoria_id)
                           .where(*base, Tx.afecta_caja, _filtro_tipo(tipo))).all()  # fmt: skip
        for nombre, monto in filas:
            grupos[_clave(nombre)] += Decimal(monto)
    elif agrupar_por == "metodo_pago":
        for metodo, monto in db.execute(select(Tx.metodo_pago, Tx.monto).where(*base, _filtro_tipo(tipo))).all():
            grupos[str(getattr(metodo, "value", metodo))] += Decimal(monto)
    elif agrupar_por == "mes":
        for fh, monto in db.execute(select(Tx.fecha_hora, Tx.monto).where(*base, Tx.afecta_caja, _filtro_tipo(tipo))).all():
            grupos[q.dia_lima(fh).strftime("%Y-%m")] += Decimal(monto)
    elif agrupar_por == "producto":
        tipos = [T.venta] if tipo == "ingreso" else [T.compra]
        filas = db.execute(select(m.Producto.nombre, m.DetalleTransaccion.descripcion, m.DetalleTransaccion.subtotal)
                           .join(Tx, Tx.transaccion_id == m.DetalleTransaccion.transaccion_id)
                           .outerjoin(m.Producto, m.Producto.producto_id == m.DetalleTransaccion.producto_id)
                           .where(*base, Tx.tipo.in_(tipos))).all()  # fmt: skip
        for producto, descripcion, subtotal in filas:
            grupos[producto or descripcion or "sin_producto"] += Decimal(subtotal)
    elif agrupar_por == "proveedor":
        if tipo == "egreso":
            filas = db.execute(select(m.Proveedor.nombre_ficticio, Tx.monto)
                               .join(m.Deuda, m.Deuda.deuda_id == Tx.deuda_id)
                               .join(m.Proveedor, m.Proveedor.proveedor_id == m.Deuda.proveedor_id)
                               .where(*base, Tx.tipo == T.compra)).all()  # fmt: skip
            for nombre, monto in filas:
                grupos[nombre] += Decimal(monto)
    elif agrupar_por == "cliente_fiado":
        if tipo == "ingreso":
            filas = db.execute(select(m.Cliente.nombre_ficticio, Tx.monto)
                               .join(m.CuadernoFiado, m.CuadernoFiado.fiado_id == Tx.fiado_id)
                               .join(m.Cliente, m.Cliente.cliente_id == m.CuadernoFiado.cliente_id)
                               .where(*base, Tx.tipo == T.venta)).all()  # fmt: skip
            for nombre, monto in filas:
                grupos[nombre] += Decimal(monto)
    else:
        raise Validacion(f"No sé agrupar por '{agrupar_por}'.", [{"campo": "agrupar_por", "problema": "no soportado"}])
    return {k: redondear(v) for k, v in grupos.items()}


def _comparacion_pares(db: Session, empresa: m.Empresa, desde: date, hasta: date, corte: date
                       ) -> tuple[ComparacionPares | None, str | None]:  # fmt: skip
    def ratio(empresa_id: str) -> float | None:
        ventas = q.suma(db, empresa_id, desde, hasta, corte, Tx.tipo == T.venta)
        if ventas <= 0:
            return None
        return float(q.retiros(db, empresa_id, desde, hasta, corte) / ventas)

    propio = ratio(empresa.empresa_id)
    if propio is None:
        return None, "Todavía no hay ventas en el periodo para comparar."
    pares = db.scalars(select(m.Empresa.empresa_id).where(m.Empresa.rubro_id == empresa.rubro_id,
                                                          m.Empresa.empresa_id != empresa.empresa_id)).all()  # fmt: skip
    valores = [r for r in (ratio(p) for p in pares) if r is not None]
    if len(valores) < MIN_PARES:
        return None, (f"Comparación con pares pendiente de datos: hay {len(valores)} bodegas del mismo rubro con datos "
                      f"en la BD y se necesitan al menos {MIN_PARES}. Tus retiros son {round(propio * 100)} % de tus "
                      "ventas.")  # fmt: skip
    rubro = db.get(m.Rubro, empresa.rubro_id)
    return ComparacionPares(metrica=METRICA_PARES, valor_empresa=round(propio, 2), mediana_pares=round(median(valores), 2),
                            grupo_pares=f"{rubro.nombre if rubro else 'mismo rubro'} · {empresa.zona}",
                            n_pares=len(valores), nota="Comparación anónima con datos sintéticos."), None  # fmt: skip


def analisis(db: Session, empresa_id: str, agrupar_por: str = "categoria", tipo: str = "egreso", *,
             desde: date | None = None, hasta: date | None = None, comparar_con: str | None = None,
             fecha_corte: date | None = None) -> AnalisisResponse:  # fmt: skip
    corte = q.corte_de(fecha_corte)
    empresa = q.empresa_o_404(db, empresa_id)
    hasta = min(hasta or corte, corte)
    desde = desde or hasta.replace(day=1)
    if desde > hasta:
        raise Validacion("`desde` no puede ser posterior a `hasta`.", [{"campo": "desde", "problema": "posterior a hasta"}])
    if comparar_con == "mismo_periodo_anio_anterior":
        prev_desde, prev_hasta = q.sumar_meses(desde, -12), q.sumar_meses(hasta, -12)
    elif desde.day == 1 and hasta.month == desde.month:  # mes en curso: mes anterior al mismo día
        prev_desde = q.sumar_meses(desde, -1)
        prev_hasta = prev_desde.replace(day=min(hasta.day, q.ultimo_dia_mes(prev_desde.year, prev_desde.month)))
    else:
        largo = (hasta - desde).days + 1
        prev_hasta = desde - timedelta(days=1)
        prev_desde = prev_hasta - timedelta(days=largo - 1)
    actual = _agrupar(db, empresa_id, agrupar_por, tipo, desde, hasta, corte)
    previo = _agrupar(db, empresa_id, agrupar_por, tipo, prev_desde, prev_hasta, corte) \
        if prev_desde >= empresa.fecha_saldo_inicial else {}  # fmt: skip
    total = sum(actual.values(), Decimal(0))
    grupos = [Grupo(clave=k, monto=v, participacion_pct=round(float(v / total * 100), 1) if total else 0.0,
                    variacion_pct=round(float((v - previo[k]) / previo[k] * 100), 1) if previo.get(k) else None)
              for k, v in sorted(actual.items(), key=lambda kv: (-kv[1], kv[0]))]  # fmt: skip
    pares, motivo = _comparacion_pares(db, empresa, desde, hasta, corte)
    return AnalisisResponse(agrupar_por=agrupar_por, tipo=tipo, periodo=PeriodoAnalisis(desde=desde, hasta=hasta),
                            grupos=grupos, comparacion_pares=pares, comparacion_pares_motivo=motivo,
                            total=redondear(total))  # fmt: skip
