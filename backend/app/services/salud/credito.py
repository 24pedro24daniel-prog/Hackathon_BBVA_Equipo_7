"""Score crediticio con la regresión logística del equipo de datos (modelo/artifacts/credit_scoring/).

Es un bloque ADICIONAL de `GET /empresas/{id}/salud` (`score_crediticio`); no reemplaza ni se mezcla con el score de 3
hábitos que muestra el front. Fórmula de `metadata.json`: `score = round(predict_proba(scaler.transform(X))[:, 1] * 100)`;
rangos Rojo 0–39 · Amarillo 40–69 · Verde 70–100 (`riesgo_pago_ml` en la propuesta del equipo de datos).

Los 16 features se calculan AQUÍ, en Python, desde el ORM a la fecha de corte (`reloj.hoy()`), con las definiciones del
notebook y de `campos_calculados_credit_scoring.xlsx` (las "vistas" del DBML son solo comentarios y tienen errores):
- Ventana: los últimos 180 días o, si la empresa tiene menos historia, desde su primer movimiento (así `pct_dias_con_venta`
  no se divide entre 180 cuando hay 60 días de historia).
- `ingreso_mensual_prom`: ventas (`tipo = venta`, al contado o fiadas) de la ventana ÷ meses de la ventana (días/30). No es
  el promedio por transacción.
- `pct_dias_con_venta`: días con ≥ 1 venta ÷ días de la ventana. `cv_ventas`: desviación (ddof=1) ÷ media del monto vendido
  por día, sobre los días con venta (así no repite lo que ya mide `pct_dias_con_venta`).
- `pct_pagos_a_tiempo` y `dias_mora_promedio`: deudas con vencimiento en la ventana que ya se pueden juzgar al corte (pagadas
  del todo, o vencidas): a tiempo = pagada antes o el día del vencimiento; mora = max(0, fecha de pago o corte − vencimiento).
  Lo que aún no vence NO cuenta como atrasado. La fecha de pago sale de los pagos registrados (no de una columna guardada).
- `dias_desde_ultimo_registro`: corte − día del último movimiento vigente.
- `pct_fiado_sobre_ventas`: fiados de la ventana ÷ ventas de la ventana. `pct_fiado_cobrado_a_tiempo`: tasa agregada de fiados
  cuyo desenlace ya se conoce al corte (cobrado ≤ compromiso, o vencido sin cobrar). Nunca `pago_tardio` (etiqueta).
- `n_alertas_quiebre_stock`: proxy de "caída de ventas" calculado desde las ventas: episodios (días seguidos cuentan uno) en
  que la venta del día es < 50 % del promedio de ese mismo día de la semana en las 4 semanas previas. No se cuentan filas de
  `alertas` porque el backend no genera `caida_ventas`.
- `tiene_ruc`, `n_trabajadores`, `rubro` (dummies sin "bodega") de `empresas`; `antiguedad_meses` desde `fecha_alta`;
  `usa_billetera_digital` = ≥ 1 registro en `billeteras_digitales` en los últimos 90 días (regla acordada, igual que el forecast).
- Un feature sin datos para calcularlo (p. ej. sin deudas juzgables) se reemplaza por la MEDIA DE ENTRENAMIENTO del scaler
  (aporte neutro) y se marca `imputado`. Sin historia mínima el score no se calcula (`disponible = false`).
Nunca se usan `pago_tardio`, `deficit_14d`, `eventos` ni `clientes.perfil_pago` (PLAN §8).
"""

import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import mean, stdev

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import reloj
from app.core.meta import construir_meta
from app.db import models as m
from app.schemas.common import TipoMovimiento
from app.services.finanzas import consultas as q
from app.services.finanzas.forecast_ml import antiguedad_meses, usa_billetera_digital
from app.services.finanzas.modelo_ml import MODELO_SCORING, cargar_scoring

log = logging.getLogger("cajaclara.credito")

VENTANA_DIAS = 180
HISTORIA_MIN_DIAS = 14   # días entre el primer movimiento y el corte
VENTAS_MIN_DIAS = 7      # días con venta para calcular regularidad (cv)
CAIDA_FRACCION = 0.5
SEMANAS_COMPARACION = 4
Z_FUERA_DE_RANGO = 4.0

CATEGORIAS = (("Verde", 70), ("Amarillo", 40), ("Rojo", 0))
FUNDAMENTO = ("Estimación de un modelo de regresión logística que mira qué tan seguido vendes, qué tan parejas son tus "
              "ventas, si pagas a tiempo tus pedidos, cuánto fías y cobras, cuánto hace que no anotas y datos del negocio "
              "(antigüedad, RUC, rubro, trabajadores).")
LIMITES = ("Es una estimación de un modelo entrenado con datos sintéticos de bodegas, no una evaluación crediticia ni una "
           "oferta de crédito, y no la usa ninguna entidad financiera. Con poco historial o sin pedidos/fiados que juzgar "
           "algunos datos se completan con valores neutros. No reemplaza tu score de hábitos.")


def categoria(score: int) -> str:
    return next(nombre for nombre, minimo in CATEGORIAS if score >= minimo)


# ── features ────────────────────────────────────────────────────────────────────────────────────


def _ventas_por_dia(db: Session, empresa_id: str, inicio: date, corte: date) -> dict[date, float]:
    filas = db.execute(select(m.Transaccion.fecha_hora, m.Transaccion.monto).where(
        *q.vigentes(empresa_id, corte), m.Transaccion.tipo == TipoMovimiento.venta,
        m.Transaccion.fecha_hora >= reloj.inicio_del_dia(inicio))).all()  # fmt: skip
    por_dia: dict[date, float] = defaultdict(float)
    for fh, monto in filas:
        por_dia[q.dia_lima(fh)] += float(monto)
    return dict(por_dia)


def _episodios_caida(ventas: dict[date, float], inicio: date, corte: date) -> int:
    """Episodios en que la venta del día cae bajo el 50 % del promedio de ese día de la semana (4 semanas previas)."""
    episodios, en_caida, d = 0, False, inicio
    while d <= corte:
        previos = [ventas.get(d - timedelta(days=7 * k), 0.0) for k in range(1, SEMANAS_COMPARACION + 1)
                   if d - timedelta(days=7 * k) >= inicio]  # fmt: skip
        base = mean(previos) if len(previos) >= 2 else 0.0
        caida = base > 0 and ventas.get(d, 0.0) < CAIDA_FRACCION * base and d < corte  # el día de corte puede estar a medias
        if caida and not en_caida:
            episodios += 1
        en_caida = caida
        d += timedelta(days=1)
    return episodios


def _pagos_deuda(db: Session, empresa_id: str, corte: date) -> dict[str, list[tuple[date, Decimal]]]:
    pagos: dict[str, list] = defaultdict(list)
    for did, fh, monto in db.execute(select(m.Transaccion.deuda_id, m.Transaccion.fecha_hora, m.Transaccion.monto).where(
            *q.vigentes(empresa_id, corte), m.Transaccion.deuda_id.is_not(None),
            m.Transaccion.tipo.in_([TipoMovimiento.pago_proveedor, TipoMovimiento.pago_prestamo]))
            .order_by(m.Transaccion.fecha_hora, m.Transaccion.transaccion_id)):  # fmt: skip
        pagos[did].append((q.dia_lima(fh), Decimal(monto)))
    return pagos


def _puntualidad_deudas(db: Session, empresa_id: str, inicio: date, corte: date) -> tuple[float | None, float | None]:
    """(% pagadas a tiempo, mora promedio en días) de las deudas ya juzgables al corte; None si no hay ninguna."""
    pagos = _pagos_deuda(db, empresa_id, corte)
    a_tiempo, moras = [], []
    for dc in q.cuentas_deuda(db, empresa_id, corte):
        deuda = dc.deuda
        if deuda.fecha_vencimiento < inicio:
            continue
        fecha_pago, acumulado = None, Decimal(0)
        for dia, monto in pagos.get(deuda.deuda_id, []):
            acumulado += monto
            if acumulado >= deuda.monto_total_a_pagar:
                fecha_pago = dia
                break
        if fecha_pago is None and deuda.fecha_vencimiento >= corte:
            continue  # aún no vence ni se pagó: no se puede juzgar
        referencia = fecha_pago or corte
        a_tiempo.append(1.0 if fecha_pago is not None and fecha_pago <= deuda.fecha_vencimiento else 0.0)
        moras.append(float(max(0, (referencia - deuda.fecha_vencimiento).days)))
    if not a_tiempo:
        return None, None
    return mean(a_tiempo), mean(moras)


def _fiados(fiados: list[q.FiadoCalc], inicio: date, ventas_total: float) -> tuple[float, float | None]:
    """(% de las ventas que se fió, % de fiados con desenlace conocido que se cobraron a tiempo | None)."""
    en_ventana = [f for f in fiados if f.fiado.fecha_fiado >= inicio]
    fiado = sum(float(f.fiado.monto) for f in en_ventana)
    pct_sobre = min(1.0, fiado / ventas_total) if ventas_total > 0 else 0.0
    juzgables = [f for f in en_ventana if f.atrasado is not None]
    return pct_sobre, (mean(0.0 if f.atrasado else 1.0 for f in juzgables) if juzgables else None)


def calcular_features(db: Session, empresa: m.Empresa, corte: date) -> tuple[dict[str, float | None], dict]:
    """(features por nombre —None = sin datos para calcularlo—, info de la ventana). Lanza ValueError si no hay historia."""
    primer = q.primer_dia_con_datos(db, empresa.empresa_id, corte)
    if primer is None:
        raise ValueError("La empresa todavía no tiene movimientos registrados")
    if (corte - primer).days + 1 < HISTORIA_MIN_DIAS:
        raise ValueError(f"Historia insuficiente: {(corte - primer).days + 1} días de movimientos y se necesitan "
                         f"{HISTORIA_MIN_DIAS}")  # fmt: skip
    inicio = max(corte - timedelta(days=VENTANA_DIAS - 1), primer)
    dias_ventana = (corte - inicio).days + 1
    ventas = _ventas_por_dia(db, empresa.empresa_id, inicio, corte)
    if len(ventas) < VENTAS_MIN_DIAS:
        raise ValueError(f"Pocas ventas registradas: {len(ventas)} días con venta y se necesitan {VENTAS_MIN_DIAS}")
    total = sum(ventas.values())
    diarias = list(ventas.values())
    ultimo = db.scalar(select(m.Transaccion.fecha_hora).where(*q.vigentes(empresa.empresa_id, corte))
                       .order_by(m.Transaccion.fecha_hora.desc()).limit(1))  # fmt: skip
    a_tiempo, mora = _puntualidad_deudas(db, empresa.empresa_id, inicio, corte)
    pct_fiado, fiado_a_tiempo = _fiados(q.cuentas_fiado(db, empresa.empresa_id, corte), inicio, total)
    rubro = db.get(m.Rubro, empresa.rubro_id)
    features: dict[str, float | None] = {
        "antiguedad_meses": float(antiguedad_meses(empresa.fecha_alta, corte)),
        "ingreso_mensual_prom": total / (dias_ventana / 30),
        "pct_dias_con_venta": len(ventas) / dias_ventana,
        "cv_ventas": stdev(diarias) / mean(diarias) if mean(diarias) > 0 else 0.0,
        "pct_pagos_a_tiempo": a_tiempo,
        "dias_mora_promedio": mora,
        "dias_desde_ultimo_registro": float(max(0, (corte - q.dia_lima(ultimo)).days)),
        "pct_fiado_sobre_ventas": pct_fiado,
        "pct_fiado_cobrado_a_tiempo": fiado_a_tiempo,
        "n_alertas_quiebre_stock": float(_episodios_caida(ventas, inicio, corte)),
        "n_trabajadores": float(empresa.n_trabajadores),
        "tiene_ruc": float(bool(empresa.tiene_ruc)),
        "usa_billetera_digital": float(usa_billetera_digital(db, empresa.empresa_id, corte)),
    }
    info = {"ventana_dias": dias_ventana, "desde": inicio, "rubro": rubro.nombre if rubro else ""}
    return features, info


def vector(modelo, features: dict[str, float | None], rubro: str) -> tuple[list[float], list[str]]:
    """Fila X en el orden de `columnas_en_orden` (dummies de rubro como `get_dummies(drop_first=True)`). Los None se
    reemplazan por la media de entrenamiento del scaler. Devuelve (fila, nombres imputados)."""
    fila, imputados = [], []
    for i, col in enumerate(modelo.columnas):
        if col.startswith("rubro_"):
            fila.append(1.0 if rubro == col.removeprefix("rubro_") else 0.0)
            continue
        valor = features.get(col)
        if valor is None:
            valor = float(modelo.scaler.mean_[i])
            imputados.append(col)
        fila.append(float(valor))
    return fila, imputados


# ── bloque `score_crediticio` ───────────────────────────────────────────────────────────────────


def _meta(fallback: bool, motivo: str | None = None, version: str | None = None) -> dict:
    meta = construir_meta(MODELO_SCORING, version, fallback_usado=fallback)
    datos = meta.model_dump(mode="json")
    if motivo:
        datos["fallback_motivo"] = motivo
    return datos


def _no_disponible(motivo: str, *, fallo_modelo: bool, version: str | None = None) -> dict:
    return {"disponible": False, "score": None, "categoria": None, "motivo": motivo, "fundamento": FUNDAMENTO,
            "limites": LIMITES, "meta": _meta(fallo_modelo, motivo if fallo_modelo else None, version)}  # fmt: skip


def score_crediticio(db: Session, empresa_id: str, fecha_corte: date | None = None) -> dict:
    """Bloque `score_crediticio`. Nunca lanza por falta de modelo o de datos: sale con `disponible = false` y el motivo."""
    corte = fecha_corte or reloj.hoy()
    modelo, motivo = cargar_scoring()
    if modelo is None:
        return _no_disponible(f"Modelo de credit scoring no disponible: {motivo}", fallo_modelo=True)
    empresa = q.empresa_o_404(db, empresa_id)
    try:
        features, info = calcular_features(db, empresa, corte)
        fila, imputados = vector(modelo, features, info["rubro"])
        if info["rubro"] not in modelo.categorias_rubro:
            raise ValueError(f"El rubro '{info['rubro']}' no está entre los que conoce el modelo")
        import pandas as pd  # noqa: PLC0415 - el scaler se ajustó con nombres de columna (como en el notebook)

        z = modelo.scaler.transform(pd.DataFrame([fila], columns=list(modelo.columnas)))
        score = int(round(float(modelo.modelo.predict_proba(z)[0, 1]) * 100))
    except ValueError as exc:
        return _no_disponible(str(exc), fallo_modelo=False, version=modelo.version)
    except Exception as exc:  # noqa: BLE001
        log.exception("El credit scoring falló")
        return _no_disponible(f"El credit scoring falló ({type(exc).__name__})", fallo_modelo=True, version=modelo.version)
    score = max(0, min(100, score))
    fuera = [c for c, v in zip(modelo.columnas, z[0], strict=True) if abs(v) > Z_FUERA_DE_RANGO and not c.startswith("rubro_")]
    usados = {c: (None if features.get(c) is None else round(float(features[c]), 4)) for c in modelo.columnas
              if not c.startswith("rubro_")}  # fmt: skip
    usados["rubro"] = info["rubro"]
    return {
        "disponible": True, "score": score, "categoria": categoria(score), "motivo": None,
        "rangos": {"Rojo": "0-39", "Amarillo": "40-69", "Verde": "70-100"},
        "features": usados, "features_imputados": imputados, "features_fuera_de_rango": fuera,
        "ventana_dias": info["ventana_dias"], "fundamento": FUNDAMENTO, "limites": LIMITES,
        "meta": _meta(False, None, modelo.version),
    }  # fmt: skip

