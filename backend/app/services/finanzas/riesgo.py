"""B6 — Riesgo de atraso de los fiados (baseline) y recordatorio.

Baseline (context.md F4): tasa histórica de atraso del cliente, calculada a la fecha de corte con lo que se sabía ese
día: fiados ya pagados (¿se pagaron después del compromiso?) y fiados impagos con el compromiso vencido (atraso ya
conocido). El fiado que se evalúa no entra en su propia tasa. Se suaviza hacia la tasa global de la bodega
(pseudo-conteo m = 2) para que un cliente con 1–2 fiados no quede en 0 % o 100 %.

Prohibido (PLAN §8): `cuaderno_fiado.pago_tardio`, `clientes.perfil_pago` y `eventos`. No hay clasificador de ML
entregado en modelo/artifacts/, así que siempre se usa este baseline (`meta.fallback_usado = true`).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import NoEncontrado
from app.db import models as m
from app.schemas.common import EstadoCuenta, NivelRiesgo
from app.schemas.cuentas import AccionSugerida, FiadoItem, FiadosResponse, RecordatorioResponse, RiesgoAtraso
from app.services.finanzas import consultas as q
from app.services.finanzas.modelo_ml import meta_b
from app.services.ingesta.texto import soles

MODELO = "riesgo-atraso-baseline"
VERSION = "0.1.0"
PSEUDO_CONTEO = 2
UMBRAL_ALTO = 0.6
UMBRAL_MEDIO = 0.3
MOTIVO_SIN_MODELO = "No hay clasificador de riesgo de atraso en modelo/artifacts/: se usa la tasa histórica del cliente."


@dataclass
class Riesgo:
    probabilidad: float
    nivel: NivelRiesgo
    baseline: float
    n_historial: int


def nivel_de(p: float) -> NivelRiesgo:
    if p >= UMBRAL_ALTO:
        return NivelRiesgo.alto
    if p >= UMBRAL_MEDIO:
        return NivelRiesgo.medio
    return NivelRiesgo.bajo


def riesgos(calc: list[q.FiadoCalc]) -> dict[str, Riesgo]:
    conocidos = [(f.fiado.fiado_id, f.fiado.cliente_id, f.atrasado) for f in calc if f.atrasado is not None]
    k_total = sum(1 for *_, a in conocidos if a)
    global_ = (k_total + 1) / (len(conocidos) + 2)  # Laplace: sin historial, 50 %
    salida = {}
    for f in calc:
        propios = [a for fid, cid, a in conocidos if cid == f.fiado.cliente_id and fid != f.fiado.fiado_id]
        p = (sum(1 for a in propios if a) + PSEUDO_CONTEO * global_) / (len(propios) + PSEUDO_CONTEO)
        salida[f.fiado.fiado_id] = Riesgo(round(p, 2), nivel_de(p), round(global_, 2), len(propios))
    return salida


def probabilidad_cobro(r: Riesgo) -> Decimal:
    """Peso con el que un fiado entra a los cobros esperados: probabilidad de que pague a tiempo."""
    return Decimal(str(round(1 - r.probabilidad, 2)))


def _accion(f: q.FiadoCalc, r: Riesgo) -> AccionSugerida | None:
    if f.estado in (EstadoCuenta.vencido, EstadoCuenta.por_vencer) or r.nivel == NivelRiesgo.alto:
        return AccionSugerida(tipo="recordatorio", texto_boton=f"Recordar a {f.cliente}")
    return None


def respuesta_fiados(db: Session, empresa_id: str, estado: str, corte: date) -> FiadosResponse:
    q.empresa_o_404(db, empresa_id)
    calc = q.cuentas_fiado(db, empresa_id, corte)
    r = riesgos(calc)
    items = [FiadoItem(fiado_id=f.fiado.fiado_id, cliente_id=f.fiado.cliente_id, cliente=f.cliente,
                       detalle=f.fiado.detalle, monto=f.pendiente if f.pendiente > 0 else f.fiado.monto,
                       fecha=f.fiado.fecha_fiado, dias_transcurridos=f.dias_transcurridos, estado=f.estado,
                       riesgo_atraso=RiesgoAtraso(probabilidad=r[f.fiado.fiado_id].probabilidad,
                                                  nivel=r[f.fiado.fiado_id].nivel,
                                                  baseline_probabilidad=r[f.fiado.fiado_id].baseline),
                       accion_sugerida=_accion(f, r[f.fiado.fiado_id]) if f.pendiente > 0 else None)
             for f in calc if q.coincide_estado(f.estado, estado)]  # fmt: skip
    items.sort(key=lambda i: (i.estado != EstadoCuenta.vencido.value, i.fecha, i.fiado_id))
    pendientes = [i for i in items if i.estado != EstadoCuenta.pagado.value]
    meta = meta_b(MODELO, VERSION, fallback=True, motivo=MOTIVO_SIN_MODELO)
    return FiadosResponse(
        total_pendiente=sum((i.monto for i in pendientes), q.CERO),
        total_vencido=sum((i.monto for i in pendientes if i.estado == EstadoCuenta.vencido.value), q.CERO),
        items=items,
        fundamento="Cada riesgo sale de cuántas veces esa persona pagó después de lo acordado en sus fiados anteriores.",
        limites="Es una estimación con pocos fiados por cliente; no sabe si el vecino tuvo un imprevisto.",
        meta=meta,
    )


def recordatorio(db: Session, fiado_id: str, fecha_corte: date | None = None) -> RecordatorioResponse:
    fiado = db.get(m.CuadernoFiado, fiado_id) if db is not None else None
    if fiado is None:
        raise NoEncontrado("No encontré ese fiado.")
    corte = q.corte_de(fecha_corte)
    calc = next((f for f in q.cuentas_fiado(db, fiado.empresa_id, corte) if f.fiado.fiado_id == fiado_id), None)
    if calc is None:
        raise NoEncontrado("No encontré ese fiado.")
    if calc.pendiente <= 0:
        return RecordatorioResponse(mensaje=f"{calc.cliente} ya pagó este fiado. No hace falta recordarle nada.")
    return RecordatorioResponse(
        mensaje=f"Hola, {calc.cliente} 😊 Le recuerdo amablemente los {soles(calc.pendiente)} pendientes en la bodega. "
                "¡Gracias!"  # fmt: skip
    )
