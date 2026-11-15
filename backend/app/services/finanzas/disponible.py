"""B4 — "Disponible para gastar" (contract.md §4.1, context.md F3).

    valor = saldo_actual + cobros_esperados − pagos_comprometidos_hasta_proximo_vencimiento − minimo_operativo
            − reserva_impuestos                                                           (se acota en 0)

- Ventana: hasta el día crítico si hay uno; si no, hasta el próximo vencimiento de una deuda; si no, el horizonte.
- `pagos_comprometidos`: todo egreso con fecha en la ventana (deudas, programados incluido el sueldo, impuestos y
  ajustes). No se descuenta el flujo ordinario: la fórmula del contrato es deliberadamente conservadora.
- `cobros_esperados`: fiados pendientes ponderados por la probabilidad de pagar a tiempo, esperados en la ventana.
- `reserva_impuestos`: impuestos impagos que vencen después de la ventana (se apartan desde ya).
"""

from app.schemas.forecast import ComponentesDisponible, DiaCritico, DisponibleParaGastar
from app.services.finanzas import consultas as q
from app.services.ingesta.texto import fecha_corta, soles

FORMULA = ("saldo_actual + cobros_esperados − pagos_comprometidos_hasta_proximo_vencimiento − minimo_operativo − "
           "reserva_impuestos")  # fmt: skip


def ventana_fin(proy, critico: DiaCritico | None):
    if critico is not None:
        return critico.fecha
    vencimientos = [e.fecha for e in proy.eventos if e.deuda_id]
    return min(vencimientos) if vencimientos else proy.fin


def calcular_disponible(proy, critico: DiaCritico | None) -> DisponibleParaGastar:
    fin = ventana_fin(proy, critico)
    pagos = sum((-e.monto for e in proy.eventos if e.monto < 0 and e.fecha <= fin), q.CERO)
    cobros = sum((e.monto for e in proy.cobros_fiado if e.fecha <= fin), q.CERO)
    reserva = sum((ic.impuesto.monto for ic in proy.impuestos
                   if not ic.pagado and ic.impuesto.fecha_vencimiento > fin), q.CERO)  # fmt: skip
    bruto = proy.saldo_actual + cobros - pagos - proy.minimo - reserva
    valor = max(q.CERO, bruto)
    if valor > 0:
        mensaje = f"Hoy puedes sacar hasta {soles(valor)} para la casa sin arriesgar tus pagos hasta el {fecha_corta(fin)}."
    elif critico is not None and critico.saldo_p50 < 0:
        mensaje = f"Hoy no conviene sacar plata para la casa: comprometería el pago del {fecha_corta(critico.fecha)}."
    else:
        mensaje = "Hoy no conviene sacar plata para la casa: tu caja quedaría por debajo de tu mínimo para operar."
    return DisponibleParaGastar(
        valor=valor, formula=FORMULA,
        componentes=ComponentesDisponible(saldo_actual=proy.saldo_actual, cobros_esperados=cobros,
                                          pagos_comprometidos=pagos, minimo_operativo=proy.minimo,
                                          reserva_impuestos=reserva),
        mensaje=mensaje,
    )  # fmt: skip
