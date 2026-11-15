"""B8 — Chequeo antes de confirmar un pedido a crédito (contract.md §4.5, context.md F4).

1. Se proyecta la caja con todo lo que ya debes y se agrega este pedido como un pago el día del vencimiento.
   Si ya hay registrada una deuda igual (mismo proveedor, monto y vencimiento, aún impaga) se toma como este mismo
   pedido y no se cuenta dos veces: pasa al confirmar (A registra la deuda y luego pide el chequeo) y en la demo, donde
   PED-0012 ya existe. Se usa la más reciente (`pedido_coincidente_id`).
2. `venta_esperada_periodo`: lo que sueles vender (a precio de venta, al contado o fiado) de los productos que te
   trae ese proveedor, desde mañana hasta el vencimiento = tasa diaria de las últimas 4 semanas × días. Es la plata
   que esa mercadería devuelve antes de tener que pagarla. Proveedor sin historial de productos → todas tus ventas.
   Es una estimación con error de más de S/ 100, por eso se redondea (centenas desde S/ 1 000; decenas debajo).
3. `exceso_vs_ventas` = monto − venta esperada (si es positivo).
4. Sugerencias (solo si no te alcanza holgado): `reducir_pedido` a ~90 % de la venta esperada (redondeado hacia abajo;
   si eso no aplica, lo justo para no quedar en negativo), `pagar_en_partes` (2 partes: vencimiento y +15 días) y
   `combinar`. `saldo_resultante` = saldo más bajo hasta el vencimiento (o hasta la última parte si cae en el horizonte).
"""

from datetime import date, timedelta
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.core import reloj
from app.schemas.common import Confianza, redondear
from app.schemas.cuentas import ChequeoResponse, Sugerencia
from app.services.finanzas import consultas as q
from app.services.finanzas import proyeccion as fc
from app.services.finanzas import simulador as sim
from app.services.finanzas.modelo_ml import meta_b, motivo_fallback_forecast
from app.services.ingesta.texto import fecha_corta, soles

PEDIDO_NUEVO = "PEDIDO-NUEVO"
FRACCION_SUGERIDA = Decimal("0.9")
DIAS_TASA = 28


def _paso(x: Decimal) -> Decimal:
    return Decimal(100) if abs(x) >= 1000 else Decimal(10) if abs(x) >= 100 else Decimal(1)


def redondear_estimacion(x: Decimal) -> Decimal:
    paso = _paso(x)
    return redondear((x / paso).quantize(Decimal(1), rounding=ROUND_HALF_UP) * paso)


def redondear_abajo(x: Decimal) -> Decimal:
    paso = _paso(x)
    return redondear((x / paso).quantize(Decimal(1), rounding=ROUND_FLOOR) * paso)


def venta_esperada(db: Session, empresa_id: str, proveedor_id: str | None, corte: date, vencimiento: date
                   ) -> tuple[Decimal, bool]:  # fmt: skip
    """(venta esperada hasta el vencimiento, ¿se usaron los productos del proveedor?)."""
    productos = q.productos_de_proveedor(db, empresa_id, proveedor_id, corte) if proveedor_id else set()
    primer = q.primer_dia_con_datos(db, empresa_id, corte)
    dias_hist = min(DIAS_TASA, (corte - primer).days) if primer else 0
    dias = max(1, (vencimiento - corte).days)
    if dias_hist <= 0:
        return q.CERO, bool(productos)
    desde = corte - timedelta(days=dias_hist)
    vendido = q.ventas_de_productos(db, empresa_id, productos or None, desde, corte - timedelta(days=1), corte)
    return redondear_estimacion(vendido / dias_hist * dias), bool(productos)


def pedido_coincidente(deudas: list[q.DeudaCalc], proveedor_id: str | None, monto: Decimal, vence: date):
    iguales = [d for d in deudas if d.es_proveedor and d.pendiente > 0 and d.deuda.proveedor_id == proveedor_id
               and d.deuda.monto_total_a_pagar == monto and d.deuda.fecha_vencimiento == vence]  # fmt: skip
    return max(iguales, key=lambda d: (d.creado_en or reloj.inicio_del_dia(d.deuda.fecha_inicio), d.deuda.deuda_id),
               default=None)  # fmt: skip


def _confianza(proy: fc.Proyeccion, saldo: Decimal, h: int) -> Confianza:
    s = proy.sigma * max(h, 1) ** 0.5
    if proy.semanas < 2 or s <= 0:
        return Confianza.baja
    z = abs(float(saldo)) / s
    return Confianza.alta if z >= 2 else Confianza.media if z >= 1 else Confianza.baja


def chequeo_pedido(db: Session, empresa_id: str, proveedor: str, monto, fecha_vencimiento: date) -> ChequeoResponse:
    corte = reloj.hoy()
    monto = redondear(monto)
    q.empresa_o_404(db, empresa_id)
    prov = q.buscar_proveedor(db, empresa_id, proveedor)
    nombre = prov.nombre_ficticio if prov else (proveedor or "tu proveedor")
    coincide = pedido_coincidente(q.cuentas_deuda(db, empresa_id, corte, solo_proveedor=True),
                                  prov.proveedor_id if prov else None, monto, fecha_vencimiento)  # fmt: skip
    vence = max(fecha_vencimiento, corte + timedelta(days=1))
    horizonte = max(30, (vence - corte).days)
    proy = fc.proyectar(db, empresa_id, corte, horizonte,
                        excluir_deudas={coincide.deuda.deuda_id} if coincide else frozenset())  # fmt: skip
    pago = fc.Evento(vence, f"Pago a {nombre}", -monto, "pago_proveedor", ref_id=PEDIDO_NUEVO, deuda_id=PEDIDO_NUEVO,
                     proveedor=nombre)  # fmt: skip
    base = sim.Escenario(proy, proy.eventos + [pago])

    def resultado(esc: sim.Escenario) -> tuple[Decimal, fc.Punto]:
        puntos = esc.puntos()
        fin = max([vence, *[d for d in esc.fechas_movidas if d <= proy.fin]])
        return next(p.p50 for p in puntos if p.fecha == vence), sim.minimo_hasta(puntos, fin)

    al_vencimiento, minimo = resultado(base)
    estado = proy.estado_caja(minimo.p50)
    venta, por_producto = venta_esperada(db, empresa_id, prov.proveedor_id if prov else None, corte, vence)
    exceso = max(q.CERO, monto - venta)

    sugerencias, notas = [], []
    if estado != "te_alcanza":
        sugerido = redondear_abajo(venta * FRACCION_SUGERIDA) if venta > 0 else q.CERO
        if not (0 < sugerido < monto) and minimo.p50 < 0:
            sugerido = redondear_abajo(monto + minimo.p50)
        partes = [vence, vence + timedelta(days=sim.DIAS_ENTRE_PARTES)]
        if 0 < sugerido < monto:
            esc = base.copia()
            sim.reducir(esc, PEDIDO_NUEVO, sugerido)
            sugerencias.append(Sugerencia(accion="reducir_pedido", monto_sugerido=sugerido, saldo_resultante=resultado(esc)[1].p50))
        esc = base.copia()
        sim.en_partes(esc, PEDIDO_NUEVO, 2, partes, vence)
        notas += esc.notas
        sugerencias.append(Sugerencia(accion="pagar_en_partes", partes=2, saldo_resultante=resultado(esc)[1].p50))
        if 0 < sugerido < monto:
            esc = base.copia()
            sim.reducir(esc, PEDIDO_NUEVO, sugerido)
            sim.en_partes(esc, PEDIDO_NUEVO, 2, partes, vence)
            sugerencias.append(Sugerencia(accion="combinar", monto_sugerido=sugerido, partes=2,
                                          detalle=f"pedir {soles(sugerido)} y pagar en 2 partes",
                                          saldo_resultante=resultado(esc)[1].p50))  # fmt: skip

    otros = sum((-e.monto for e in proy.eventos if e.monto < 0 and e.fecha <= vence), q.CERO)
    que = f"de lo que te trae {nombre}" if por_producto else "en total"
    fundamento = f"Hasta el {fecha_corta(vence)} sueles vender alrededor de {soles(venta)} {que}"
    fundamento += f"; este pedido es {soles(exceso)} más." if exceso > 0 else "; el pedido no pasa de eso."
    if otros > 0:
        fundamento += f" Hasta esa fecha también tienes otros pagos por {soles(otros)}."
    limites = ("Proyección con tus ventas y gastos de las últimas 4 semanas; no considera eventos que no hayas "
               "registrado.")  # fmt: skip
    if notas:
        limites += " " + " ".join(dict.fromkeys(notas))
    return ChequeoResponse(
        saldo_proyectado_al_vencimiento=al_vencimiento, estado_caja=estado, venta_esperada_periodo=venta,
        exceso_vs_ventas=exceso, sugerencias=sugerencias, fundamento=fundamento, limites=limites,
        confianza=_confianza(proy, al_vencimiento, (vence - corte).days),
        saldo_minimo_hasta_vencimiento=minimo.p50, fecha_saldo_minimo=minimo.fecha,
        pedido_coincidente_id=coincide.deuda.deuda_id if coincide else None,
        meta=meta_b(fc.MODELO, fc.VERSION, fallback=True, motivo=motivo_fallback_forecast()),
    )  # fmt: skip
