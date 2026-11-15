"""Forecast con el LightGBM por cuantiles del equipo de datos (modelo/artifacts/prediccion_ingreso_egreso/).

El modelo predice un paso (el día siguiente) a partir de lo ocurrido hasta el día anterior; aquí se replica EXACTAMENTE
el feature engineering del notebook (`modelo_ingreso_egreso_lightgbm.ipynb`, `add_features`) y se encadena para cubrir el
horizonte:

- Historia: ingreso y egreso diarios del FLUJO ORDINARIO de la empresa (consultas.flujos_ordinarios), días completos hasta
  el día anterior al corte. El día de corte nunca entra como dato (en la demo es un día a medias y distorsionaría `lag1`):
  se predice igual que los demás y su p50 alimenta la recursión.
- Features (orden y nombres de `metadata.json.features_en_orden`): lags 1/7/14, medias y desviaciones (ddof=1) de 7/14/30
  días con `shift(1).rolling(k)`, calendario (dow lunes=0, dom, es_finde = vie–dom, es_quincena_o_finmes = 14–16 o ≥ 28,
  mes) y perfil de la empresa (rubro categórico con las categorías del metadata, n_trabajadores, antigüedad en meses,
  usa_fiado y usa_billetera_digital según `definiciones_acordadas`: ≥ 1 registro en los últimos 90 días).
- Predicción recursiva: el p50 de ingreso y egreso de cada día se agrega a la historia para calcular el día siguiente.
  p10 y p90 se evalúan sobre esas mismas filas (en lote). Los cuantiles se ordenan (p10 ≤ p50 ≤ p90): LightGBM entrena
  cada cuantil por separado y pueden cruzarse.
- Banda del saldo: cada día aporta una dispersión al lado malo (menos ingreso, más egreso) y al bueno; se acumulan como
  suma de cuadrados (días independientes) → `ancho_bajo(h)` y `ancho_alto(h)` crecen con √h.

Dónde el modelo y el backend NO coinciden (train/serve skew; ver README §ML):
1. El modelo se entrenó con el egreso TOTAL de la caja (incluye pagos a proveedores, impuestos y alquiler) y datos
   sintéticos. El backend proyecta aparte los pagos con fecha (deudas, programados, impuestos). Para no contarlos dos veces
   el modelo se usa sobre el flujo ORDINARIO y los eventos conocidos se suman encima. La historia de entrada es la ordinaria.
2. En el entrenamiento los pagos grandes caían siempre los días 5 (proveedor) y 15 (impuesto): el egreso del modelo salta
   ~S/ 1 000 esos días. Sería un pago fantasma que dobla los eventos reales; por eso, SOLO para los modelos de egreso, el
   día del mes 5 se evalúa como 4 y el 15 como 14 (`DOM_NEUTRO_EGRESO`; mismo flag de quincena, sin el pago).
3. Rango de entrenamiento: `mes` solo vio junio–septiembre y las escalas son otras (ingreso_base ≈ S/ 180/día). El modelo
   extrapola por árboles (se queda en el último tramo): documentado, no corregido.
4. Nivel: el modelo aprendió la escala y la forma del egreso de sus bodegas sintéticas (egreso diario ≈ 55 % del ingreso,
   con un pago grande al mes el día 5). Si en los últimos 30 días del flujo ordinario de la empresa no hay egresos grandes,
   el modelo "espera" ese pago y predice un pago fantasma todos los días (~S/ 1 200/día; error a 1 día ≈ S/ 900). Por eso
   el flujo ordinario de Pedro en `data/csv` incluye su compra mensual al contado (día 5): con esa data calibrada el MAE del
   saldo a 1 día en Pedro es 232 vs 251 del baseline (`tests/eval_forecast.py`, README §ML). En otras empresas el nivel
   puede quedar sistemáticamente arriba o abajo. Se probó reescalar el nivel con un factor por empresa (Σ real ÷ Σ predicho en
   los últimos días): inestable (varía 0.5–1.6 entre cortes por las compras grandes) y empeora el MAE del saldo; se dejó el
   modelo crudo y el sesgo se mide en `tests/eval_forecast.py` y se documenta.
5. Banda: los cuantiles del modelo reflejan el ruido de SUS datos sintéticos y son más angostos que el error real sobre una
   empresa (cobertura p10–p90 del saldo medida ≈ 15 % en vez de 80 %). La dispersión diaria se toma como el MAYOR entre la del
   modelo y el error cuadrático medio de 1 paso del propio modelo en los últimos días de esa empresa (`backtest_un_paso`).
6. La recursión usa p50 como si fueran observaciones: las desviaciones móviles de los días futuros salen más chicas que
   las reales y la banda sale algo optimista a horizontes largos.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import reloj
from app.db import models as m
from app.schemas.common import redondear
from app.services.finanzas import consultas as q
from app.services.finanzas.modelo_ml import ModeloForecast, cargar_forecast

log = logging.getLogger("cajaclara.forecast_ml")

HISTORIA_MIN = 30           # media30/std30 necesitan 30 días completos antes de cada día predicho
VENTANA_FLAGS_DIAS = 90     # usa_fiado / usa_billetera_digital (definiciones_acordadas)
DOM_NEUTRO_EGRESO = {5: 4, 15: 14}  # día del mes con el "pago fantasma" del entrenamiento → vecino sin pago
DIAS_BACKTEST = 28
Z80 = 1.2816


# ── perfil de la empresa (features estáticas) ───────────────────────────────────────────────────


def antiguedad_meses(fecha_alta, corte: date) -> int:
    alta = reloj.a_lima(fecha_alta).date() if hasattr(fecha_alta, "date") else fecha_alta
    meses = (corte.year - alta.year) * 12 + (corte.month - alta.month) - (1 if corte.day < alta.day else 0)
    return max(0, meses)


def usa_billetera_digital(db: Session, empresa_id: str, corte: date) -> bool:
    """Regla acordada (metadata.json): ≥ 1 registro en `billeteras_digitales` en los últimos 90 días."""
    return db.scalar(select(m.BilleteraDigital.billetera_mov_id).where(
        m.BilleteraDigital.empresa_id == empresa_id,
        m.BilleteraDigital.fecha_hora >= reloj.inicio_del_dia(corte - timedelta(days=VENTANA_FLAGS_DIAS)),
        m.BilleteraDigital.fecha_hora < q.fin_del_dia(corte)).limit(1)) is not None  # fmt: skip


def usa_fiado(fiados: list[q.FiadoCalc], corte: date) -> bool:
    """Regla acordada: ≥ 1 registro en `cuaderno_fiado` en los últimos 90 días (los anulados no cuentan)."""
    desde = corte - timedelta(days=VENTANA_FLAGS_DIAS)
    return any(desde <= f.fiado.fecha_fiado <= corte for f in fiados)


@dataclass(frozen=True)
class Perfil:
    rubro: str
    n_trabajadores: int
    antiguedad_meses: int
    usa_fiado: bool
    usa_billetera_digital: bool


def perfil_empresa(db: Session, empresa: m.Empresa, corte: date, fiados: list[q.FiadoCalc]) -> Perfil:
    rubro = db.get(m.Rubro, empresa.rubro_id)
    return Perfil(rubro=rubro.nombre if rubro else "", n_trabajadores=int(empresa.n_trabajadores),
                  antiguedad_meses=antiguedad_meses(empresa.fecha_alta, corte), usa_fiado=usa_fiado(fiados, corte),
                  usa_billetera_digital=usa_billetera_digital(db, empresa.empresa_id, corte))  # fmt: skip


# ── features ────────────────────────────────────────────────────────────────────────────────────


def _estadisticas(serie: list[float], nombre: str) -> dict[str, float]:
    """lag1/7/14 y media/std de 7/14/30 días de `serie` (que termina el día anterior al predicho)."""
    import numpy as np  # noqa: PLC0415

    salida = {f"{nombre}_lag{k}": serie[-k] for k in (1, 7, 14)}
    for k in (7, 14, 30):
        ventana = np.asarray(serie[-k:], dtype=float)
        salida[f"{nombre}_media{k}"] = float(ventana.mean())
        salida[f"{nombre}_std{k}"] = float(ventana.std(ddof=1))
    return salida


def fila_features(perfil: Perfil, ingreso: list[float], egreso: list[float], dia: date) -> dict:
    """Una fila de features para predecir `dia` con la historia `ingreso`/`egreso` hasta el día anterior."""
    dow, dom = dia.weekday(), dia.day
    fila = {"rubro": perfil.rubro, "n_trabajadores": perfil.n_trabajadores, "antiguedad_meses": perfil.antiguedad_meses,
            "usa_fiado": int(perfil.usa_fiado), "usa_billetera_digital": int(perfil.usa_billetera_digital)}  # fmt: skip
    fila.update(_estadisticas(ingreso, "ingreso"))
    fila.update(_estadisticas(egreso, "egreso"))
    fila.update(dow=dow, dom=dom, es_finde=int(dow in (4, 5, 6)),
                es_quincena_o_finmes=int(dom in (14, 15, 16) or dom >= 28), mes=dia.month)  # fmt: skip
    return fila


def matriz(modelo: ModeloForecast, filas: list[dict]):
    """DataFrame con las columnas de `features_en_orden` y `rubro` como Categorical (categorías del metadata)."""
    import pandas as pd  # noqa: PLC0415

    X = pd.DataFrame(filas, columns=list(modelo.features))
    X["rubro"] = pd.Categorical(X["rubro"], categories=list(modelo.categorias_rubro))
    return X


def _egreso(fila: dict) -> dict:
    """Fila para los modelos de egreso: el día 5/15 se evalúa como su vecino sin pago fantasma (ver docstring)."""
    return {**fila, "dom": DOM_NEUTRO_EGRESO.get(fila["dom"], fila["dom"])}


def _predecir(modelo: ModeloForecast, target: str, cuantil: int, filas: list[dict]) -> list[float]:
    X = matriz(modelo, filas)
    return [max(0.0, float(v)) for v in modelo.modelos[(target, cuantil)].predict(X)]


# ── predicción ──────────────────────────────────────────────────────────────────────────────────


@dataclass
class PrediccionML:
    """Salida por día de horizonte (h = 1..H, índice 0 = corte + 1)."""

    version: str
    ingreso: list[Decimal]
    egreso: list[Decimal]
    sigma_bajo: list[float]  # dispersión del día hacia el lado malo del saldo (menos ingreso, más egreso)
    sigma_alto: list[float]
    cuantiles: dict[str, list[tuple[float, float, float]]]  # target → (p10, p50, p90) por día (ordenados)
    metricas: dict | None = None  # backtest de 1 paso sobre los últimos días de la propia historia

    def _acum(self, h: int, lado: list[float]) -> float:
        return sum(s * s for s in lado[:h]) ** 0.5

    def ancho_bajo(self, h: int) -> Decimal:
        return redondear(self._acum(h, self.sigma_bajo))

    def ancho_alto(self, h: int) -> Decimal:
        return redondear(self._acum(h, self.sigma_alto))

    def sigma_h(self, h: int) -> float:
        """σ acumulada del saldo a h días (promedio de ambos lados; la banda p10–p90 ≈ ±1.28 σ)."""
        return (self._acum(h, self.sigma_bajo) + self._acum(h, self.sigma_alto)) / 2 / Z80


def _ordenar(p10: float, p50: float, p90: float) -> tuple[float, float, float]:
    """Cuantiles cruzados: se acotan alrededor del p50 (que es el que alimenta la recursión)."""
    return min(p10, p50), p50, max(p90, p50)


def _dispersion(ing: tuple, egr: tuple) -> tuple[float, float]:
    (i10, i50, i90), (e10, e50, e90) = ing, egr
    bajo = ((i50 - i10) ** 2 + (e90 - e50) ** 2) ** 0.5
    alto = ((i90 - i50) ** 2 + (e50 - e10) ** 2) ** 0.5
    return bajo, alto


def predecir(modelo: ModeloForecast, perfil: Perfil, ingreso: list[float], egreso: list[float], corte: date,
             horizonte: int) -> PrediccionML:  # fmt: skip
    """`ingreso`/`egreso`: valores diarios consecutivos que terminan el día anterior al corte (mínimo HISTORIA_MIN)."""
    if len(ingreso) < HISTORIA_MIN or len(egreso) != len(ingreso):
        raise ValueError(f"se necesitan {HISTORIA_MIN} días de historia y hay {len(ingreso)}")
    ing, egr = list(ingreso), list(egreso)
    filas = []
    for k in range(horizonte + 1):  # k = 0 es el día de corte (no se muestra: solo alimenta la recursión)
        dia = corte + timedelta(days=k)
        fila = fila_features(perfil, ing, egr, dia)
        filas.append(fila)
        ing.append(_predecir(modelo, "ingreso", 50, [fila])[0])
        egr.append(_predecir(modelo, "egreso", 50, [_egreso(fila)])[0])
    filas_egr = [_egreso(f) for f in filas]
    p = {("ingreso", c): _predecir(modelo, "ingreso", c, filas) for c in (10, 90)}
    p.update({("egreso", c): _predecir(modelo, "egreso", c, filas_egr) for c in (10, 90)})
    n = len(ingreso)
    cuantiles = {"ingreso": [], "egreso": []}
    bajo, alto = [], []
    for k in range(1, horizonte + 1):
        i = _ordenar(p[("ingreso", 10)][k], ing[n + k], p[("ingreso", 90)][k])
        e = _ordenar(p[("egreso", 10)][k], egr[n + k], p[("egreso", 90)][k])
        cuantiles["ingreso"].append(i)
        cuantiles["egreso"].append(e)
        b, a = _dispersion(i, e)
        bajo.append(b)
        alto.append(a)
    return PrediccionML(version=modelo.version, ingreso=[redondear(v) for v in ing[n + 1:]],
                        egreso=[redondear(v) for v in egr[n + 1:]], sigma_bajo=bajo, sigma_alto=alto, cuantiles=cuantiles)  # fmt: skip


def backtest_un_paso(modelo: ModeloForecast, perfil: Perfil, dias: list[date], ingreso: list[float],
                     egreso: list[float], dias_prueba: int = DIAS_BACKTEST) -> dict | None:  # fmt: skip
    """MAE diario del neto (ingreso − egreso) y cobertura de su banda p10–p90 prediciendo cada día con la historia real
    anterior (1 paso, sin recursión) en los últimos `dias_prueba` días. Comparable con `backtest_baseline`."""
    n = len(dias)
    filas, reales, indices = [], [], []
    for i in range(max(HISTORIA_MIN, n - dias_prueba), n):
        filas.append(fila_features(perfil, ingreso[:i], egreso[:i], dias[i]))
        reales.append((ingreso[i], egreso[i]))
        indices.append(i)
    if len(filas) < 7:
        return None
    filas_egr = [_egreso(f) for f in filas]
    ing = list(zip(*[_predecir(modelo, "ingreso", c, filas) for c in (10, 50, 90)], strict=True))
    egr = list(zip(*[_predecir(modelo, "egreso", c, filas_egr) for c in (10, 50, 90)], strict=True))
    errores, dentro = [], 0
    for (ri, re), i3, e3 in zip(reales, ing, egr, strict=True):
        i3, e3 = _ordenar(*i3), _ordenar(*e3)
        neto, real = i3[1] - e3[1], ri - re
        bajo, alto = _dispersion(i3, e3)
        errores.append(abs(real - neto))
        dentro += int(neto - bajo <= real <= neto + alto)
    return {"mae": round(sum(errores) / len(errores), 2), "cobertura": round(dentro / len(errores), 2), "n": len(errores),
            "rmse": (sum(e * e for e in errores) / len(errores)) ** 0.5}


# ── entrada desde proyectar() ───────────────────────────────────────────────────────────────────


def predecir_empresa(db: Session, empresa: m.Empresa, flujos: dict[date, q.FlujoDia], corte: date, horizonte: int,
                     fiados: list[q.FiadoCalc]) -> tuple[PrediccionML | None, str | None]:  # fmt: skip
    """(predicción, None) o (None, motivo concreto de por qué se usa el baseline). Nunca lanza por falta de modelo/datos."""
    modelo, motivo = cargar_forecast()
    if modelo is None:
        return None, f"Modelo LightGBM no disponible: {motivo}"
    dias = sorted(d for d in flujos if d < corte)
    if len(dias) < HISTORIA_MIN:
        return None, (f"Historia insuficiente para el LightGBM: {len(dias)} días completos de movimientos y necesita "
                      f"{HISTORIA_MIN} (hasta el día anterior al corte)")  # fmt: skip
    perfil = perfil_empresa(db, empresa, corte, fiados)
    if perfil.rubro not in modelo.categorias_rubro:
        return None, f"El rubro '{perfil.rubro}' no está entre los que conoce el modelo {list(modelo.categorias_rubro)}"
    ingreso = [float(flujos[d].ingreso) for d in dias]
    egreso = [float(flujos[d].egreso) for d in dias]
    pred = predecir(modelo, perfil, ingreso, egreso, corte, horizonte)
    pred.metricas = backtest_un_paso(modelo, perfil, dias, ingreso, egreso)
    if pred.metricas is not None:  # la banda nunca es más angosta que el error real reciente del modelo en esta empresa
        piso = pred.metricas["rmse"]
        pred.sigma_bajo = [max(s, piso) for s in pred.sigma_bajo]
        pred.sigma_alto = [max(s, piso) for s in pred.sigma_alto]
    return pred, None
