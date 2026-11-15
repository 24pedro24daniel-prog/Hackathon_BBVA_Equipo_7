"""B3 — Motor de proyección de caja (lo usan forecast, disponible, chequeo, simulador y alertas).

Proyección central (p50) de la caja del negocio, día a día desde mañana:
    saldo(d) = saldo(d−1) + media_mismo_día_de_semana(flujo_ordinario, últimas 4 semanas) + eventos_con_fecha(d)
- `flujo_ordinario` = movimientos que afectan caja sin vínculo a fiado/deuda/impuesto/programado (consultas.py).
- `eventos_con_fecha` = pagos de deudas (pedidos a crédito y cuotas de préstamos), movimientos programados (luz,
  sueldo fijo…) que aún no se pagaron en su periodo, impuestos impagos y ajustes manuales (`forecast_ajustes`).
- Fiados ponderados: cada fiado pendiente vale pendiente × P(paga a tiempo) (riesgo.py). Por prudencia NO entran a la
  línea esperada (p50): cobrar a tiempo es incierto (hoy 1 de los 3 ya venció y 2 de 3 clientes se atrasan ≥ 50 % de
  las veces) y es justo la palanca "cobrar fiados" del simulador. Entran a los `cobros_esperados` del disponible, a la
  banda optimista (p90) y a "Lo que viene" con `ponderado = true`. Si entraran al p50, el 30/11 de Pedro pasaría de
  −650 a ≈ −485 (ver README).
- Banda p10/p90: ± z·σ·√h, con σ = error del baseline en las últimas 4 semanas (residuos dejando-uno-fuera) y
  z = 1.2816 (80 %). La p90 suma además los fiados ponderados ya esperados. Siempre p10 ≤ p50 ≤ p90.
- `dia_critico`: primer día con p50 < 0 (déficit); si no hay, el día más bajo si queda bajo el mínimo operativo.

Motores (`FORECAST_MOTOR`, ver modelo_ml.py / forecast_ml.py):
- `lightgbm` (por defecto): el ingreso y el egreso ORDINARIOS de cada día salen del LightGBM por cuantiles del equipo de datos
  (predicción recursiva) en lugar de la media del mismo día de la semana; los eventos con fecha, los fiados ponderados, los
  ajustes y el saldo se tratan igual (los pagos conocidos se suman encima del flujo ordinario, sin doble conteo: el modelo
  nunca ve los pagos de deudas/impuestos/programados en su historia). La banda p10/p90 sale de los cuantiles del modelo
  acumulados por √h, no de σ·√h del baseline. `meta.modelo = "forecast-lgbm-quantile"`.
- `baseline` (o fallback si el modelo no carga, la historia es corta o algo falla): lo descrito arriba, con
  `meta.fallback_usado = true` y `meta.fallback_motivo` concreto.
"""

import logging
import math
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from app.schemas.common import Confianza, redondear
from app.schemas.forecast import DiaCritico, ObligacionAsociada, PuntoSerie
from app.services.finanzas import consultas as q
from app.services.finanzas import forecast_ml as fml
from app.services.finanzas import riesgo as rsg
from app.services.finanzas.modelo_ml import (
    MODELO_FORECAST,
    MOTOR_BASELINE,
    Motor,
    motivo_fallback_forecast,
    motor_baseline,
    motor_configurado,
)
from app.services.ingesta.texto import normalizar

log = logging.getLogger("cajaclara.forecast")

MODELO = "forecast-naive-estacional"
VERSION = "0.1.0"
SEMANAS = 4
DIAS_REQUERIDOS = 28
HORIZONTE_MAX = 120
Z80 = 1.2816
CERO = q.CERO


@dataclass
class Evento:
    fecha: date
    concepto: str
    monto: Decimal  # con signo: + entra a la caja, − sale
    tipo: str
    ref_id: str | None = None
    deuda_id: str | None = None
    proveedor: str | None = None
    programado_id: str | None = None
    ponderado: bool = False


@dataclass
class Punto:
    fecha: date
    ingresos: Decimal
    egresos: Decimal
    p50: Decimal


@dataclass
class Proyeccion:
    empresa: m.Empresa
    corte: date
    horizonte: int
    saldo_actual: Decimal
    minimo: Decimal
    media_ing: dict[int, Decimal]
    media_egr: dict[int, Decimal]
    media_ret: dict[int, Decimal]
    eventos: list[Evento]
    cobros_fiado: list[Evento]
    sigma: float
    semanas: int
    dias_con_datos: int
    ajustes: list[dict] = field(default_factory=list)
    mae_baseline: float | None = None
    cobertura: float | None = None
    fiados: list[q.FiadoCalc] = field(default_factory=list)
    riesgos: dict[str, rsg.Riesgo] = field(default_factory=dict)
    deudas: list[q.DeudaCalc] = field(default_factory=list)
    impuestos: list[q.ImpuestoCalc] = field(default_factory=list)
    ml: fml.PrediccionML | None = None  # serie del LightGBM; None = flujo ordinario del baseline
    motor: Motor | None = None
    cobertura_ml: float | None = None
    mae_ml: float | None = None

    @property
    def fechas(self) -> list[date]:
        return [self.corte + timedelta(days=i) for i in range(1, self.horizonte + 1)]

    @property
    def fin(self) -> date:
        return self.corte + timedelta(days=self.horizonte)

    def puntos(self, eventos: list[Evento] | None = None, menos_egreso_diario: dict[int, Decimal] | None = None
               ) -> list[Punto]:  # fmt: skip
        eventos = self.eventos if eventos is None else eventos
        por_dia: dict[date, list[Evento]] = {}
        for ev in eventos:
            por_dia.setdefault(ev.fecha, []).append(ev)
        saldo, salida = self.saldo_actual, []
        for i, d in enumerate(self.fechas):
            wd = d.weekday()
            if self.ml is not None:  # flujo ordinario del día según el LightGBM
                ing, egr = self.ml.ingreso[i], max(CERO, self.ml.egreso[i] - (menos_egreso_diario or {}).get(wd, CERO))
            else:
                ing, egr = self.media_ing[wd], self.media_egr[wd] - (menos_egreso_diario or {}).get(wd, CERO)
            ing += sum((e.monto for e in por_dia.get(d, []) if e.monto > 0), CERO)
            egr += sum((-e.monto for e in por_dia.get(d, []) if e.monto < 0), CERO)
            saldo += ing - egr
            salida.append(Punto(d, redondear(ing), redondear(egr), redondear(saldo)))
        return salida

    def sigma_h(self, h: int) -> float:
        """σ del saldo a h días: la del LightGBM (cuantiles acumulados) o σ·√h del baseline."""
        return self.ml.sigma_h(h) if self.ml is not None else self.sigma * math.sqrt(h)

    def ancho_bajo(self, h: int) -> Decimal:
        return self.ml.ancho_bajo(h) if self.ml is not None else redondear(Z80 * self.sigma * math.sqrt(h))

    def ancho_alto(self, h: int) -> Decimal:
        return self.ml.ancho_alto(h) if self.ml is not None else redondear(Z80 * self.sigma * math.sqrt(h))

    def prob_deficit(self, p50: Decimal, h: int) -> float:
        s = self.sigma_h(h)
        if s <= 0:
            return 1.0 if p50 < 0 else 0.0
        return round(0.5 * (1 + math.erf((0 - float(p50)) / (s * math.sqrt(2)))), 2)

    def estado_caja(self, saldo: Decimal) -> str:
        if saldo < 0:
            return "no_te_alcanza"
        if saldo < self.minimo:
            return "justo"
        return "te_alcanza"


# ── construcción ────────────────────────────────────────────────────────────────────────────────


def _medias(flujos: dict[date, q.FlujoDia], corte: date, semanas: int):
    ventana = [corte - timedelta(days=k) for k in range(7 * semanas, 0, -1)]
    ing, egr, ret = ({wd: CERO for wd in range(7)} for _ in range(3))
    if semanas == 0:
        return ing, egr, ret, 0.0
    for d in ventana:
        f = flujos.get(d, q.FlujoDia())
        ing[d.weekday()] += f.ingreso / semanas
        egr[d.weekday()] += f.egreso / semanas
        ret[d.weekday()] += f.retiro / semanas
    return ing, egr, ret, _sigma(flujos, ventana, semanas)


def _sigma(flujos: dict[date, q.FlujoDia], ventana: list[date], semanas: int) -> float:
    """Error típico de un día del baseline (residuos dejando-uno-fuera, reescalados a una media de `semanas`)."""
    netos = {d: float(flujos.get(d, q.FlujoDia()).neto) for d in ventana}
    if semanas < 2:
        valores = list(netos.values())
        media = sum(valores) / len(valores) if valores else 0.0
        return math.sqrt(sum((v - media) ** 2 for v in valores) / max(len(valores), 1))
    residuos = []
    for d, v in netos.items():
        otros = [netos[x] for x in netos if x != d and x.weekday() == d.weekday()]
        residuos.append(v - sum(otros) / len(otros))
    mse = sum(r * r for r in residuos) / len(residuos)
    k = semanas
    return math.sqrt(mse * (1 + 1 / k) / (1 + 1 / (k - 1)))


def backtest_baseline(flujos: dict[date, q.FlujoDia], corte: date, dias: int = 28, semanas: int = SEMANAS,
                      sigma: float | None = None) -> tuple[float | None, float | None]:  # fmt: skip
    """MAE diario del naive estacional en los últimos `dias` (cada día predicho con las 4 semanas previas) y cobertura
    de la banda p10–p90 de un día. Usa solo flujos hasta el día anterior al corte."""
    errores, dentro = [], 0
    for k in range(dias, 0, -1):
        t = corte - timedelta(days=k)
        previos = [t - timedelta(days=7 * j) for j in range(1, semanas + 1)]
        if any(p not in flujos for p in previos):
            continue
        pred = sum(float(flujos[p].neto) for p in previos) / semanas
        real = float(flujos.get(t, q.FlujoDia()).neto)
        errores.append(abs(real - pred))
        if sigma is not None and abs(real - pred) <= Z80 * sigma:
            dentro += 1
    if not errores:
        return None, None
    return round(sum(errores) / len(errores), 2), (round(dentro / len(errores), 2) if sigma is not None else None)


def _eventos_deudas(deudas: list[q.DeudaCalc], corte: date, hasta: date, excluir: set[str]) -> list[Evento]:
    salida = []
    for dc in deudas:
        if dc.deuda.deuda_id in excluir:
            continue
        tipo = "pago_proveedor" if dc.es_proveedor else "pago_prestamo"
        for fecha, monto in q.cronograma_pagos(dc, corte, hasta):
            salida.append(Evento(fecha, f"Pago a {dc.nombre}", -monto, tipo, ref_id=dc.deuda.deuda_id,
                                 deuda_id=dc.deuda.deuda_id, proveedor=dc.nombre if dc.es_proveedor else None))  # fmt: skip
    return salida


def _eventos_programados(db: Session, empresa_id: str, corte: date, hasta: date) -> list[Evento]:
    pagados = q.dias_pagados_programado(db, empresa_id, corte)
    salida = []
    for p in q.programados(db, empresa_id):
        for d in q.ocurrencias(p, corte + timedelta(days=1), hasta):
            ini, fin = q.periodo_de(p, d)
            if any(ini <= x <= fin for x in pagados.get(p.programado_id, [])):
                continue  # ya se pagó en su periodo
            egreso = p.tipo == "egreso"
            tipo = "retiro_personal" if p.es_sueldo else ("gasto_negocio" if egreso else "otro_ingreso")
            monto = Decimal(p.monto)
            salida.append(Evento(d, p.descripcion, -monto if egreso else monto, tipo, ref_id=p.programado_id,
                                 programado_id=p.programado_id))  # fmt: skip
    return salida


def _eventos_impuestos(impuestos: list[q.ImpuestoCalc], corte: date, hasta: date) -> list[Evento]:
    manana = corte + timedelta(days=1)
    salida = []
    for ic in impuestos:
        if ic.pagado:
            continue
        fecha = max(ic.impuesto.fecha_vencimiento, manana)
        if fecha <= hasta:
            salida.append(Evento(fecha, ic.nombre, -Decimal(ic.impuesto.monto), "pago_impuesto",
                                 ref_id=ic.impuesto.impuesto_id))  # fmt: skip
    return salida


def _cobros_fiado(fiados: list[q.FiadoCalc], riesgos: dict[str, rsg.Riesgo], corte: date, hasta: date
                  ) -> list[Evento]:  # fmt: skip
    salida = []
    for f in fiados:
        if f.pendiente <= 0:
            continue
        fecha = max(f.compromiso, corte + timedelta(days=1))
        monto = redondear(f.pendiente * rsg.probabilidad_cobro(riesgos[f.fiado.fiado_id]))
        if fecha <= hasta and monto > 0:
            salida.append(Evento(fecha, f"Te pagaría {f.cliente}", monto, "cobro_fiado", ref_id=f.fiado.fiado_id,
                                 ponderado=True))  # fmt: skip
    return salida


def _textos_programado(db: Session, empresa_id: str) -> dict[str, list[str]]:
    filas = db.execute(select(m.MovimientoProgramado.programado_id, m.MovimientoProgramado.descripcion,
                              m.Categoria.nombre)
                       .join(m.Categoria, m.Categoria.categoria_id == m.MovimientoProgramado.categoria_id)
                       .where(m.MovimientoProgramado.empresa_id == empresa_id)).all()  # fmt: skip
    return {pid: [desc, cat] for pid, desc, cat in filas}


def _coincide(concepto: str, textos: list[str]) -> bool:
    c = normalizar(concepto)
    if not c:
        return False
    for t in textos:
        n = normalizar(t or "")
        if n and (c in n or n in c or set(c.split()) & {w for w in n.split() if len(w) >= 4}):
            return True
    return False


def _aplicar_ajustes(db: Session, empresa_id: str, corte: date, hasta: date, eventos: list[Evento]
                     ) -> tuple[list[Evento], list[dict]]:  # fmt: skip
    ajustes = db.scalars(select(m.ForecastAjuste).where(
        m.ForecastAjuste.empresa_id == empresa_id, m.ForecastAjuste.activo,
        m.ForecastAjuste.creado_en < q.fin_del_dia(corte), m.ForecastAjuste.fecha > corte,
        m.ForecastAjuste.fecha <= hasta).order_by(m.ForecastAjuste.creado_en, m.ForecastAjuste.ajuste_id)).all()  # fmt: skip
    if not ajustes:
        return eventos, []
    textos_prog = _textos_programado(db, empresa_id)
    eventos = list(eventos)
    aplicados = []
    for aj in ajustes:
        def candidato(ev: Evento) -> bool:
            if ev.ponderado or (ev.fecha.year, ev.fecha.month) != (aj.fecha.year, aj.fecha.month):  # noqa: B023
                return False
            if aj.programado_id:  # noqa: B023
                return ev.programado_id == aj.programado_id  # noqa: B023
            return _coincide(aj.concepto, [ev.concepto, *textos_prog.get(ev.programado_id or "", [])])  # noqa: B023

        opciones = sorted((i for i, ev in enumerate(eventos) if candidato(ev)),
                          key=lambda i: abs((eventos[i].fecha - aj.fecha).days))  # noqa: B023
        registro = {"ajuste_id": aj.ajuste_id, "fecha": aj.fecha.isoformat(), "concepto": aj.concepto,
                    "monto": float(aj.monto), "motivo": aj.motivo}  # fmt: skip
        if opciones:
            ev = eventos[opciones[0]]
            nuevo = aj.monto if ev.monto > 0 else -aj.monto
            registro.update(tipo="reemplazo", fecha_original=ev.fecha.isoformat(), monto_original=float(abs(ev.monto)),
                            ref_id=ev.ref_id)  # fmt: skip
            eventos[opciones[0]] = replace(ev, monto=Decimal(nuevo), concepto=f"{ev.concepto} (ajustado)")
        else:
            registro.update(tipo="adicional")
            if aj.monto > 0:
                eventos.append(Evento(aj.fecha, aj.concepto, -Decimal(aj.monto), "ajuste_manual", ref_id=aj.ajuste_id))
        aplicados.append(registro)
    return eventos, aplicados


def _motor(db: Session, empresa: m.Empresa, flujos: dict[date, q.FlujoDia], corte: date, horizonte: int,
           fiados: list[q.FiadoCalc], motor: str | None) -> tuple[fml.PrediccionML | None, Motor]:  # fmt: skip
    """Elige el motor de la serie: LightGBM si está configurado y puede correr; si no, baseline con el motivo."""
    elegido = (motor or motor_configurado()).strip().lower()
    if elegido == MOTOR_BASELINE:
        return None, motor_baseline("FORECAST_MOTOR=baseline: el LightGBM está desactivado por configuración")
    try:
        ml, motivo = fml.predecir_empresa(db, empresa, flujos, corte, horizonte, fiados)
    except Exception as exc:  # noqa: BLE001 - el forecast nunca debe tumbar la app: cae al baseline y lo dice
        log.exception("El forecast LightGBM falló; se usa el baseline")
        ml, motivo = None, f"El LightGBM falló al predecir ({type(exc).__name__}: {str(exc)[:160]})"
    if ml is None:
        return None, motor_baseline(motivo or motivo_fallback_forecast())
    return ml, Motor(MODELO_FORECAST, ml.version, False)


def proyectar(db: Session, empresa_id: str, corte: date | None = None, horizonte: int = 30,
              excluir_deudas: set[str] | frozenset = frozenset(), motor: str | None = None) -> Proyeccion:  # fmt: skip
    corte = q.corte_de(corte)
    horizonte = max(1, min(int(horizonte), HORIZONTE_MAX))
    empresa = q.empresa_o_404(db, empresa_id)
    hasta = corte + timedelta(days=horizonte)
    primer = q.primer_dia_con_datos(db, empresa_id, corte)
    semanas = 0 if primer is None else min(SEMANAS, (corte - primer).days // 7)
    # 62 días: el baseline usa 8 semanas (4 de media + 4 de backtest) y el LightGBM 30 días de historia por día probado
    flujos = q.flujos_ordinarios(db, empresa_id, corte - timedelta(days=62), corte - timedelta(days=1), corte)  # fmt: skip
    if primer is not None:  # días anteriores al primer registro no son "días sin ventas"
        flujos = {d: f for d, f in flujos.items() if d >= primer}
    ing, egr, ret, sigma = _medias(flujos, corte, semanas)
    fiados = q.cuentas_fiado(db, empresa_id, corte)
    riesgos = rsg.riesgos(fiados)
    deudas = q.cuentas_deuda(db, empresa_id, corte)
    impuestos = q.cuentas_impuesto(db, empresa_id, corte)
    eventos = (_eventos_deudas(deudas, corte, hasta, set(excluir_deudas))
               + _eventos_programados(db, empresa_id, corte, hasta) + _eventos_impuestos(impuestos, corte, hasta))  # fmt: skip
    eventos, ajustes = _aplicar_ajustes(db, empresa_id, corte, hasta, eventos)
    eventos.sort(key=lambda e: (e.fecha, e.monto))
    mae, cobertura = backtest_baseline(flujos, corte, sigma=sigma)
    ml, info = _motor(db, empresa, flujos, corte, horizonte, fiados, motor)
    return Proyeccion(
        empresa=empresa, corte=corte, horizonte=horizonte, saldo_actual=q._saldo(db, empresa, corte),
        minimo=redondear(empresa.minimo_operativo), media_ing=ing, media_egr=egr, media_ret=ret, eventos=eventos,
        cobros_fiado=_cobros_fiado(fiados, riesgos, corte, hasta), sigma=sigma, semanas=semanas,
        dias_con_datos=q.dias_con_datos(db, empresa_id, corte), ajustes=ajustes, mae_baseline=mae,
        cobertura=cobertura, fiados=fiados, riesgos=riesgos, deudas=deudas, impuestos=impuestos, ml=ml, motor=info,
        mae_ml=ml.metricas["mae"] if ml and ml.metricas else None,
        cobertura_ml=ml.metricas["cobertura"] if ml and ml.metricas else None,
    )  # fmt: skip


# ── salidas ─────────────────────────────────────────────────────────────────────────────────────


def dia_critico(proy: Proyeccion, puntos: list[Punto], eventos: list[Evento] | None = None) -> DiaCritico | None:
    eventos = proy.eventos if eventos is None else eventos
    h, punto = next(((i, p) for i, p in enumerate(puntos, start=1) if p.p50 < 0), (None, None))
    if punto is None and puntos:
        h, punto = min(enumerate(puntos, start=1), key=lambda x: x[1].p50)
        if punto.p50 >= proy.minimo:
            return None
    if punto is None:
        return None
    deudas_dia = [e for e in eventos if e.fecha == punto.fecha and e.deuda_id]
    obligacion = None
    if deudas_dia:
        e = min(deudas_dia, key=lambda x: x.monto)
        obligacion = ObligacionAsociada(tipo="prestamo_proveedor" if e.proveedor else "prestamo", id=e.deuda_id,
                                        proveedor=e.proveedor, monto=-e.monto)  # fmt: skip
    return DiaCritico(fecha=punto.fecha, saldo_p50=punto.p50, probabilidad_deficit=proy.prob_deficit(punto.p50, h),
                      obligacion_asociada=obligacion)  # fmt: skip


def serie(proy: Proyeccion, puntos: list[Punto]) -> list[PuntoSerie]:
    salida, fiado_acum = [], CERO
    cobros = {}
    for ev in proy.cobros_fiado:
        cobros[ev.fecha] = cobros.get(ev.fecha, CERO) + ev.monto
    for h, p in enumerate(puntos, start=1):
        fiado_acum += cobros.get(p.fecha, CERO)
        salida.append(PuntoSerie(fecha=p.fecha, ingresos_esperados=p.ingresos, egresos_esperados=p.egresos,
                                 p10=p.p50 - proy.ancho_bajo(h), p50=p.p50,
                                 p90=p.p50 + proy.ancho_alto(h) + fiado_acum))  # fmt: skip
    return salida


def confianza(proy: Proyeccion) -> Confianza:
    if proy.semanas < 2:
        return Confianza.baja
    return Confianza.media
