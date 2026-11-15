"""B10 — Reglas de alerta por prioridad (context.md F6): 1 faltante_caja · 2 pedido_excesivo · 3 retiro_excesivo ·
4 obligacion_proxima. Cada regla recibe el contexto de evaluación y devuelve candidatas con monto, fecha, nivel de
riesgo y causas cuantificadas. Solo usan datos a la fecha de corte; nunca etiquetas (`deficit_14d`, `eventos`…).

- faltante_caja: el forecast tiene un día con saldo esperado < 0. Causas (cada una es lo que mejoraría ese día):
  retiros del mes por encima de lo usual al mismo día, exceso del pedido que vence ese día sobre lo que vendes de esa
  mercadería hasta su vencimiento (chequeo B8) y fiados sin cobrar (la proyección no los cuenta).
- pedido_excesivo: un pedido a crédito supera lo que sueles vender de lo que te trae ese proveedor hasta que vence.
- retiro_excesivo: retiros del mes por encima del sueldo fijo esperado a la fecha (o, sin sueldo, del promedio usual).
- obligacion_proxima: una deuda o impuesto impago vence dentro de 3 días.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from functools import cached_property

from sqlalchemy.orm import Session

from app.db import models as m
from app.schemas.common import NivelRiesgo, TipoAlerta, redondear
from app.services.finanzas import chequeo as chq
from app.services.finanzas import consultas as q
from app.services.finanzas import proyeccion as fc

DIAS_OBLIGACION = 3
DIAS_PEDIDO_RECIENTE = 7
CAUSA_RETIROS = "Sacaste más de la caja de lo usual"
CAUSA_PEDIDO = "Pediste más de lo que vendes"
CAUSA_FIADOS = "Fiados sin cobrar"


@dataclass
class Candidata:
    tipo: TipoAlerta
    fecha_evento: date
    monto: Decimal | None
    nivel: NivelRiesgo | None
    entidad_tipo: str | None
    entidad_id: str | None
    accion: str
    probabilidad: float | None = None
    causas: list[dict] = field(default_factory=list)


@dataclass
class Contexto:
    db: Session
    empresa_id: str
    corte: date
    disparador: str | None = None
    entidad_id: str | None = None

    @cached_property
    def empresa(self) -> m.Empresa:
        return q.empresa_o_404(self.db, self.empresa_id)

    @cached_property
    def proy(self) -> fc.Proyeccion:
        return fc.proyectar(self.db, self.empresa_id, self.corte, 30)

    @cached_property
    def puntos(self) -> list[fc.Punto]:
        return self.proy.puntos()

    @cached_property
    def critico(self):
        return fc.dia_critico(self.proy, self.puntos)

    def exceso_pedido(self, dc: q.DeudaCalc) -> tuple[Decimal, Decimal]:
        """(venta esperada hasta el vencimiento, exceso del pedido sobre ella)."""
        venta, _ = chq.venta_esperada(self.db, self.empresa_id, dc.deuda.proveedor_id, self.corte,
                                      max(dc.deuda.fecha_vencimiento, self.corte + timedelta(days=1)))  # fmt: skip
        return venta, max(q.CERO, redondear(dc.deuda.monto_total_a_pagar - venta))


def nivel_por_probabilidad(p: float) -> NivelRiesgo:
    return NivelRiesgo.alto if p >= 0.6 else NivelRiesgo.medio if p >= 0.3 else NivelRiesgo.bajo


def nivel_por_proporcion(parte: Decimal, total: Decimal) -> NivelRiesgo:
    r = float(parte / total) if total else 0.0
    return NivelRiesgo.alto if r >= 0.25 else NivelRiesgo.medio if r >= 0.10 else NivelRiesgo.bajo


def faltante_caja(ctx: Contexto) -> list[Candidata]:
    critico = ctx.critico
    if critico is None or critico.saldo_p50 >= 0:
        return []
    deudas_dia = {e.deuda_id for e in ctx.proy.eventos if e.deuda_id and e.fecha <= critico.fecha}
    if ctx.disparador == "compra_credito" and ctx.entidad_id in deudas_dia:
        entidad = ctx.entidad_id
    else:
        entidad = critico.obligacion_asociada.id if critico.obligacion_asociada else None
    causas = []
    exceso_ret = q.retiros_del_mes(ctx.db, ctx.empresa, ctx.corte).exceso
    if exceso_ret > 0:
        causas.append({"descripcion": CAUSA_RETIROS, "monto": float(exceso_ret)})
    dc = next((d for d in ctx.proy.deudas if d.deuda.deuda_id == entidad and d.es_proveedor), None)
    if dc is not None:
        _, exceso = ctx.exceso_pedido(dc)
        if exceso > 0:
            causas.append({"descripcion": CAUSA_PEDIDO, "monto": float(exceso)})
    fiados = sum((f.pendiente for f in ctx.proy.fiados if f.pendiente > 0), q.CERO)
    if fiados > 0:
        causas.append({"descripcion": CAUSA_FIADOS, "monto": float(fiados)})
    return [Candidata(TipoAlerta.faltante_caja, critico.fecha, -critico.saldo_p50,
                      nivel_por_probabilidad(critico.probabilidad_deficit), "deuda" if entidad else None, entidad,
                      "abrir_simulador", probabilidad=critico.probabilidad_deficit, causas=causas)]  # fmt: skip


def pedido_excesivo(ctx: Contexto) -> list[Candidata]:
    if ctx.disparador == "compra_credito":
        candidatos = [d for d in ctx.proy.deudas if d.deuda.deuda_id == ctx.entidad_id]
    else:
        desde = ctx.corte - timedelta(days=DIAS_PEDIDO_RECIENTE)
        candidatos = [d for d in ctx.proy.deudas if d.deuda.fecha_inicio >= desde]
    salida = []
    for dc in candidatos:
        if not dc.es_proveedor or dc.pendiente <= 0:
            continue
        venta, exceso = ctx.exceso_pedido(dc)
        if exceso <= 0:
            continue
        salida.append(Candidata(TipoAlerta.pedido_excesivo, dc.deuda.fecha_vencimiento, exceso,
                                nivel_por_proporcion(exceso, dc.deuda.monto_total_a_pagar), "deuda", dc.deuda.deuda_id,
                                "abrir_simulador",
                                causas=[{"descripcion": "Lo que pediste", "monto": float(dc.deuda.monto_total_a_pagar)},
                                        {"descripcion": f"Lo que sueles vender de eso hasta el "
                                                        f"{dc.deuda.fecha_vencimiento.strftime('%d/%m')}",
                                         "monto": float(venta)}]))  # fmt: skip
    return salida


def retiro_excesivo(ctx: Contexto) -> list[Candidata]:
    ret = q.retiros_del_mes(ctx.db, ctx.empresa, ctx.corte)
    sueldo = q.sueldo_esperado(ctx.db, ctx.empresa_id, ctx.corte.replace(day=1), ctx.corte)
    if sueldo is not None:
        referencia, etiqueta = sueldo, "Tu sueldo fijo hasta hoy"
    elif ret.promedio_historico is not None:
        referencia, etiqueta = ret.promedio_historico, "Lo que sueles sacar a esta altura del mes"
    else:
        return []
    exceso = redondear(ret.mes - referencia)
    if exceso <= 0:
        return []
    return [Candidata(TipoAlerta.retiro_excesivo, ctx.corte, exceso, nivel_por_proporcion(exceso, ret.mes), "mes",
                      ctx.corte.strftime("%Y-%m"), "ver_retiros",
                      causas=[{"descripcion": "Lo que sacaste de la caja este mes", "monto": float(ret.mes)},
                              {"descripcion": etiqueta, "monto": float(referencia)}])]  # fmt: skip


def obligacion_proxima(ctx: Contexto) -> list[Candidata]:
    limite = ctx.corte + timedelta(days=DIAS_OBLIGACION)
    saldos = {p.fecha: p.p50 for p in ctx.puntos}
    salida = []

    def nivel(d: date) -> NivelRiesgo:
        s = saldos.get(d, ctx.proy.saldo_actual)
        return NivelRiesgo.alto if s < 0 else NivelRiesgo.medio if s < ctx.proy.minimo else NivelRiesgo.bajo

    for dc in ctx.proy.deudas:
        if dc.pendiente > 0 and ctx.corte <= dc.deuda.fecha_vencimiento <= limite:
            salida.append(Candidata(TipoAlerta.obligacion_proxima, dc.deuda.fecha_vencimiento, dc.pendiente,
                                    nivel(dc.deuda.fecha_vencimiento), "deuda", dc.deuda.deuda_id, "ver_cuentas",
                                    causas=[{"descripcion": f"Pago a {dc.nombre}", "monto": float(dc.pendiente)}]))  # fmt: skip
    for ic in ctx.proy.impuestos:
        imp = ic.impuesto
        if not ic.pagado and ctx.corte <= imp.fecha_vencimiento <= limite:
            salida.append(Candidata(TipoAlerta.obligacion_proxima, imp.fecha_vencimiento, Decimal(imp.monto),
                                    nivel(imp.fecha_vencimiento), "impuesto", imp.impuesto_id, "ver_cuentas",
                                    causas=[{"descripcion": ic.nombre, "monto": float(imp.monto)}]))  # fmt: skip
    return salida


REGLAS = {
    TipoAlerta.faltante_caja: faltante_caja,
    TipoAlerta.pedido_excesivo: pedido_excesivo,
    TipoAlerta.retiro_excesivo: retiro_excesivo,
    TipoAlerta.obligacion_proxima: obligacion_proxima,
}
