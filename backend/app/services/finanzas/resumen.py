"""B2 — Resumen F2 (contract.md §3). Determinístico, sin bloque `meta` de modelo.

- Periodo `AAAA-MM`, del día 1 al día de corte (o al fin de mes si el periodo ya pasó). La variación es contra el mes
  anterior del día 1 al mismo día de corte.
- `ingresos_mes`: lo que entró a la caja (ventas al contado, cobros de fiado, otros ingresos; sin préstamos recibidos).
- `egresos_mes`: lo que salió de la caja por el negocio (todo egreso salvo el retiro personal, que va aparte).
- `ganancia_neta`: ventas (incluidas las fiadas) − costo de lo vendido − gastos del negocio − impuestos. El costo sale
  de `detalle_transaccion.costo_unitario`; si falta (producto sin costo o venta sin detalle) se estima con el margen
  de los productos con costo y se informa `rango` [margen mínimo, margen máximo] con `es_aproximada = true`.
- `retiros_personales`: retiros del mes vs el promedio de los meses anteriores al mismo día de corte.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import reloj
from app.db import models as m
from app.schemas.common import TipoMovimiento, redondear
from app.schemas.resumen import (
    IndGanancia,
    Indicadores,
    IndPagosPendientes,
    IndPendienteCobro,
    IndRetiros,
    IndSaldo,
    ResumenResponse,
)
from app.services.finanzas import consultas as q
from app.services.finanzas.proyeccion import DIAS_REQUERIDOS

T = TipoMovimiento
Tx = m.Transaccion
INGRESOS_CAJA = [T.venta, T.cobro_fiado, T.otro_ingreso]


def _variacion(actual: Decimal, previo: Decimal | None) -> float | None:
    if previo is None or previo == 0:
        return None
    return round(float((actual - previo) / abs(previo) * 100), 1)


def _rango_periodo(periodo: str, corte: date) -> tuple[date, date] | None:
    anio, mes = map(int, periodo.split("-"))
    inicio = date(anio, mes, 1)
    if inicio > corte:
        return None
    fin = min(corte, date(anio, mes, q.ultimo_dia_mes(anio, mes)))
    return inicio, fin


def _ganancia(db: Session, empresa_id: str, desde: date, hasta: date, corte: date) -> tuple[Decimal, Decimal, Decimal, bool]:
    """(estimada, mínima, máxima, ¿aproximada?)."""
    filas = db.execute(
        select(Tx.transaccion_id, Tx.monto, m.DetalleTransaccion.subtotal, m.DetalleTransaccion.cantidad,
               m.DetalleTransaccion.costo_unitario)
        .outerjoin(m.DetalleTransaccion, m.DetalleTransaccion.transaccion_id == Tx.transaccion_id)
        .where(*q.vigentes(empresa_id, corte), Tx.tipo == T.venta, Tx.fecha_hora >= reloj.inicio_del_dia(desde),
               Tx.fecha_hora < q.fin_del_dia(hasta))).all()  # fmt: skip
    ventas, costo, sin_costo = q.CERO, q.CERO, q.CERO
    vistas: dict[str, Decimal] = {}
    con_detalle: dict[str, Decimal] = {}
    ratios = []
    for tid, monto, subtotal, cantidad, costo_u in filas:
        vistas[tid] = Decimal(monto)
        if subtotal is None:
            continue
        con_detalle[tid] = con_detalle.get(tid, q.CERO) + Decimal(subtotal)
        if costo_u is None:
            sin_costo += Decimal(subtotal)
        else:
            c = Decimal(costo_u) * Decimal(cantidad)
            costo += c
            if subtotal:
                ratios.append(c / Decimal(subtotal))
    ventas = sum(vistas.values(), q.CERO)
    sin_costo += sum((mo - con_detalle.get(tid, q.CERO) for tid, mo in vistas.items() if mo > con_detalle.get(tid, q.CERO)),
                     q.CERO)  # fmt: skip
    gastos = q.suma(db, empresa_id, desde, hasta, corte, Tx.tipo.in_([T.gasto_negocio, T.pago_impuesto]))
    if sin_costo <= 0 or not ratios:
        valor = redondear(ventas - costo - gastos)
        return valor, valor, valor, False
    media = sum(ratios, Decimal(0)) / len(ratios)
    bajo, alto = min(ratios), max(ratios)

    def g(r):
        return redondear(ventas - costo - sin_costo * r - gastos)

    return g(media), g(alto), g(bajo), True


def _indicadores_flujo(db: Session, empresa_id: str, desde: date, hasta: date, corte: date) -> tuple[Decimal, Decimal]:
    ingresos = q.suma(db, empresa_id, desde, hasta, corte, Tx.afecta_caja, Tx.tipo.in_(INGRESOS_CAJA))
    egresos = q.suma(db, empresa_id, desde, hasta, corte, Tx.afecta_caja,
                     Tx.tipo.in_([t for t in T if t not in (*INGRESOS_CAJA, T.prestamo_recibido, T.retiro_personal)]))  # fmt: skip
    return ingresos, egresos


def resumen(db: Session, empresa_id: str, periodo: str, fecha_corte: date | None = None) -> ResumenResponse:
    hoy = q.corte_de(fecha_corte)
    empresa = q.empresa_o_404(db, empresa_id)
    rango = _rango_periodo(periodo, hoy)
    desde, corte = rango if rango else (date.fromisoformat(f"{periodo}-01"), hoy)
    previo_ini = q.sumar_meses(desde, -1)
    previo_fin = previo_ini.replace(day=min(corte.day, q.ultimo_dia_mes(previo_ini.year, previo_ini.month)))
    hay_previo = previo_ini >= empresa.fecha_saldo_inicial

    saldo = q._saldo(db, empresa, corte)
    saldo_previo = q._saldo(db, empresa, previo_fin) if previo_fin >= empresa.fecha_saldo_inicial else None
    if rango:
        ingresos, egresos = _indicadores_flujo(db, empresa_id, desde, corte, corte)
        ganancia, g_min, g_max, aprox = _ganancia(db, empresa_id, desde, corte, corte)
    else:
        ingresos = egresos = ganancia = g_min = g_max = q.CERO
        aprox = False
    ing_p = egr_p = gan_p = None
    if hay_previo:
        ing_p, egr_p = _indicadores_flujo(db, empresa_id, previo_ini, previo_fin, corte)
        gan_p = _ganancia(db, empresa_id, previo_ini, previo_fin, corte)[0]

    ret = q.retiros_del_mes(db, empresa, corte) if rango else q.Retiros(q.CERO, None, 0)
    sueldo = q.sueldo_vigente(db, empresa_id, corte)
    fiados = q.fiados_pendientes(db, empresa_id, corte)
    deudas = [d for d in q.cuentas_deuda(db, empresa_id, corte) if d.pendiente > 0]
    impuestos = [i for i in q.cuentas_impuesto(db, empresa_id, corte) if not i.pagado]
    nombres = list(dict.fromkeys([d.nombre for d in deudas] + ["RUS" if "rus" in i.impuesto.regimen else
                                                                i.impuesto.regimen for i in impuestos]))  # fmt: skip
    dias = q.dias_con_datos(db, empresa_id, corte)
    return ResumenResponse(
        empresa_id=empresa_id, periodo=periodo, corte=corte, dias_con_datos=dias, dias_requeridos_forecast=DIAS_REQUERIDOS,
        indicadores=Indicadores(
            saldo_caja_negocio=IndSaldo(valor=saldo, variacion_pct=_variacion(saldo, saldo_previo)),
            ingresos_mes=IndSaldo(valor=ingresos, variacion_pct=_variacion(ingresos, ing_p)),
            egresos_mes=IndSaldo(valor=egresos, variacion_pct=_variacion(egresos, egr_p)),
            ganancia_neta=IndGanancia(valor=ganancia, variacion_pct=_variacion(ganancia, gan_p), es_aproximada=aprox,
                                      rango=[g_min, g_max] if aprox else None),
            retiros_personales=IndRetiros(valor=ret.mes, sueldo_fijo_definido=sueldo.monto if sueldo else None,
                                          promedio_historico=ret.promedio_historico,
                                          sueldo_frecuencia=sueldo.frecuencia if sueldo else None,
                                          exceso_vs_promedio=ret.exceso if ret.promedio_historico is not None else None),
            pendiente_cobro=IndPendienteCobro(valor=sum((f.pendiente for f in fiados), q.CERO), n_fiados=len(fiados)),
            pagos_pendientes=IndPagosPendientes(
                valor=sum((d.pendiente for d in deudas), q.CERO) + sum((i.impuesto.monto for i in impuestos), q.CERO),
                n_obligaciones=len(deudas) + len(impuestos), detalle=" + ".join(nombres) or None),
        ),
        variacion_vs=f"{previo_ini.strftime('%Y-%m')} al mismo día de corte" if hay_previo else None,
    )  # fmt: skip

