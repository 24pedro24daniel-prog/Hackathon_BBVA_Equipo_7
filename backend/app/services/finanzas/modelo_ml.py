"""Modelos de ML del equipo de datos (modelo/artifacts/): carga perezosa y cacheada, diagnóstico y `meta`.

- `prediccion_ingreso_egreso/`: 6 LGBMRegressor (ingreso/egreso × p10/p50/p90) + `metadata.json` → forecast (forecast_ml.py).
- `credit_scoring/`: LogisticRegression + StandardScaler + `metadata.json` → `score_crediticio` (salud/credito.py).
- `riesgo_atraso`: no hay artefacto; sigue el baseline determinístico (riesgo.py).

Reglas de carga:
- Nunca al importar la app: `lightgbm`, `sklearn`, `pandas` y `joblib` se importan dentro de las funciones de carga
  (el arranque y los tests que no usan ML no pagan su memoria).
- Se carga una sola vez por proceso (caché con candado, válida mientras no cambie la carpeta ni el `metadata.json`).
  Un fallo también se cachea (con su motivo) para no reintentar una carga pesada en cada request; `limpiar_cache()` lo
  reinicia (tests, o tras reemplazar los artefactos con un reinicio en caliente).
- Los artefactos se validan contra su `metadata.json` (nombres y orden de features, categorías, número de columnas): si
  algo no cuadra el modelo queda "no disponible" con el motivo concreto y los motores usan su baseline con
  `meta.fallback_usado = true` y `meta.fallback_motivo`.
- `FORECAST_MOTOR=baseline` apaga el LightGBM sin tocar nada más.
"""

import json
import logging
import threading
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.meta import construir_meta
from app.schemas.common import Meta

log = logging.getLogger("cajaclara.ml")

DIR_FORECAST = "prediccion_ingreso_egreso"
DIR_SCORING = "credit_scoring"
CUANTILES = (10, 50, 90)
TARGETS = ("ingreso", "egreso")
ARCHIVOS_FORECAST = [f"{t}_p{q}.joblib" for t in TARGETS for q in CUANTILES]
ARCHIVOS_SCORING = ["logreg_model.joblib", "scaler.joblib"]

MODELO_FORECAST = "forecast-lgbm-quantile"  # `meta.modelo` del forecast con el modelo real (contract §4.1)
MODELO_SCORING = "credit-scoring-logreg"
MOTOR_LIGHTGBM, MOTOR_BASELINE = "lightgbm", "baseline"


def directorio() -> Path:
    return settings.ml_artifacts_dir


def motor_configurado() -> str:
    """`FORECAST_MOTOR` normalizado (lightgbm | baseline). Cualquier otro valor se trata como lightgbm."""
    return MOTOR_BASELINE if str(settings.FORECAST_MOTOR).strip().lower() == MOTOR_BASELINE else MOTOR_LIGHTGBM


# ── artefactos cargados ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ModeloForecast:
    version: str
    tipo: str
    features: tuple[str, ...]
    categorias_rubro: tuple[str, ...]
    modelos: dict[tuple[str, int], Any]  # ("ingreso", 10) → LGBMRegressor
    definiciones: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ModeloScoring:
    version: str
    tipo: str
    columnas: tuple[str, ...]
    categorias_rubro: tuple[str, ...]
    modelo: Any  # LogisticRegression
    scaler: Any  # StandardScaler
    rangos: dict = field(default_factory=dict)
    auc_test: float | None = None


# ── caché ───────────────────────────────────────────────────────────────────────────────────────


class _Carga:
    """Carga única por proceso de un grupo de artefactos. `obtener()` → (objeto | None, motivo | None)."""

    def __init__(self, subcarpeta: str, cargador):
        self.subcarpeta, self._cargador = subcarpeta, cargador
        self._lock = threading.Lock()
        self._clave: tuple | None = None
        self._objeto: Any = None
        self._motivo: str | None = None

    def ruta(self) -> Path:
        return directorio() / self.subcarpeta

    def _clave_actual(self) -> tuple:
        meta = self.ruta() / "metadata.json"
        try:
            mtime = meta.stat().st_mtime_ns
        except OSError:
            mtime = None
        return (str(self.ruta()), mtime)

    def cargado(self) -> bool:
        return self._objeto is not None and self._clave == self._clave_actual()

    def intentado(self) -> bool:
        return self._clave is not None and self._clave == self._clave_actual()

    def obtener(self) -> tuple[Any, str | None]:
        clave = self._clave_actual()
        if self._clave == clave:
            return self._objeto, self._motivo
        with self._lock:
            if self._clave != clave:
                try:
                    self._objeto, self._motivo = self._cargador(self.ruta()), None
                except Exception as exc:  # noqa: BLE001 - cualquier fallo de carga deja el modelo no disponible
                    self._objeto = None
                    self._motivo = f"{type(exc).__name__}: {exc}"[:300]
                    log.warning("No se pudo cargar %s: %s", self.subcarpeta, self._motivo)
                self._clave = clave
            return self._objeto, self._motivo

    def limpiar(self) -> None:
        with self._lock:
            self._clave, self._objeto, self._motivo = None, None, None


def _leer_metadata(base: Path) -> dict:
    ruta = base / "metadata.json"
    if not ruta.exists():
        raise FileNotFoundError(f"No existe {ruta}")
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"metadata.json ilegible: {exc}") from exc


def _cargar_joblib(ruta: Path):
    if not ruta.exists():
        raise FileNotFoundError(f"Falta el artefacto {ruta.name}")
    import joblib  # noqa: PLC0415 - perezoso a propósito (ver docstring)

    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        objeto = joblib.load(ruta)
    for a in avisos:
        log.warning("Aviso al cargar %s: %s", ruta.name, a.message)
    return objeto


def _cargar_forecast(base: Path) -> ModeloForecast:
    meta = _leer_metadata(base)
    features = tuple(meta["features_en_orden"])
    categorias = tuple(meta["categorias_rubro"])
    cuantiles = tuple(int(round(q * 100)) for q in meta.get("quantiles", [0.1, 0.5, 0.9]))
    if cuantiles != CUANTILES:
        raise ValueError(f"cuantiles {cuantiles} distintos de {CUANTILES}")
    import lightgbm  # noqa: F401, PLC0415 - falla con ImportError/OSError (libgomp) si el entorno no sirve

    modelos = {}
    for target in TARGETS:
        for q in CUANTILES:
            modelo = _cargar_joblib(base / f"{target}_p{q}.joblib")
            nombres = tuple(getattr(modelo, "feature_name_", ()))
            if nombres != features:
                raise ValueError(f"{target}_p{q}: features del modelo ≠ metadata.json ({len(nombres)} vs {len(features)})")
            cats = getattr(getattr(modelo, "booster_", None), "pandas_categorical", None)
            if cats is not None and [list(c) for c in cats] != [list(categorias)]:
                raise ValueError(f"{target}_p{q}: categorías de rubro del modelo ≠ metadata.json")
            modelo.set_params(n_jobs=1)  # una fila por predicción: más hilos solo suman latencia (y CPU en el plan free)
            modelos[(target, q)] = modelo
    return ModeloForecast(version=str(meta.get("modelo_version") or "desconocida"), tipo=meta.get("tipo_modelo", ""),
                          features=features, categorias_rubro=categorias, modelos=modelos,
                          definiciones=meta.get("definiciones_acordadas", {}))  # fmt: skip


def _cargar_scoring(base: Path) -> ModeloScoring:
    meta = _leer_metadata(base)
    columnas = tuple(meta["columnas_en_orden"])
    import sklearn  # noqa: F401, PLC0415

    modelo = _cargar_joblib(base / "logreg_model.joblib")
    scaler = _cargar_joblib(base / "scaler.joblib")
    n = len(columnas)
    if getattr(scaler, "n_features_in_", None) != n or modelo.coef_.shape[1] != n:
        raise ValueError(f"el scaler/modelo no tienen {n} columnas como dice metadata.json")
    return ModeloScoring(version=f"logreg-auc{meta.get('auc_test')}", tipo=meta.get("tipo_modelo", ""), columnas=columnas,
                         categorias_rubro=tuple(meta["categorias_rubro"]), modelo=modelo, scaler=scaler,
                         rangos=meta.get("rangos_categoria", {}), auc_test=meta.get("auc_test"))  # fmt: skip


_FORECAST = _Carga(DIR_FORECAST, _cargar_forecast)
_SCORING = _Carga(DIR_SCORING, _cargar_scoring)


def cargar_forecast() -> tuple[ModeloForecast | None, str | None]:
    """(modelo, None) o (None, motivo concreto). Carga la primera vez; luego sale del caché."""
    return _FORECAST.obtener()


def cargar_scoring() -> tuple[ModeloScoring | None, str | None]:
    return _SCORING.obtener()


def limpiar_cache() -> None:
    _FORECAST.limpiar()
    _SCORING.limpiar()


# ── diagnóstico (lo usan /health, meta y eval) ──────────────────────────────────────────────────


def _archivos_faltantes(base: Path, archivos: list[str]) -> list[str]:
    return [a for a in archivos if not (base / a).exists()]


def _diagnostico(carga: _Carga, archivos: list[str], tipo_ml: str, *, activo: bool = True, motivo_inactivo: str = "",
                 cargar: bool = True) -> dict:  # fmt: skip
    base = carga.ruta()
    faltan = _archivos_faltantes(base, archivos) if base.exists() else archivos
    existe = (base / "metadata.json").exists()
    salida: dict = {"tipo_ml": tipo_ml, "artefactos": existe and not faltan, "cargado": carga.cargado()}
    if not activo:
        return {**salida, "estado": "desactivado", "motivos": [motivo_inactivo]}
    if not existe:
        return {**salida, "estado": "no_disponible", "motivos": [f"No existe {base / 'metadata.json'}"]}
    if faltan:
        return {**salida, "estado": "no_disponible", "motivos": [f"Falta el artefacto {a}" for a in faltan]}
    if not cargar and not carga.intentado():
        return {**salida, "estado": "sin_cargar", "motivos": []}
    objeto, motivo = carga.obtener()
    salida["cargado"] = objeto is not None
    if objeto is None:
        return {**salida, "estado": "no_disponible", "motivos": [f"No se pudo cargar el modelo: {motivo}"]}
    return {**salida, "estado": "ok", "motivos": [], "modelo_version": objeto.version, "tipo_modelo": objeto.tipo}


def diagnostico_forecast(cargar: bool = True) -> dict:
    """Estado del LightGBM de forecast: ok | no_disponible | desactivado (FORECAST_MOTOR=baseline) | sin_cargar.
    `cargar=False` no dispara la carga (solo informa si ya se intentó). Con `cargar=True` la primera llamada la hace."""
    return _diagnostico(_FORECAST, ARCHIVOS_FORECAST, "lightgbm-quantile", activo=motor_configurado() == MOTOR_LIGHTGBM,
                        motivo_inactivo="FORECAST_MOTOR=baseline (LightGBM desactivado por configuración)", cargar=cargar)  # fmt: skip


def diagnostico_scoring(cargar: bool = True) -> dict:
    return _diagnostico(_SCORING, ARCHIVOS_SCORING, "logreg", cargar=cargar)


def diagnostico_riesgo_atraso() -> dict:
    base = directorio()
    candidatos = [p for p in (base / "riesgo_atraso", base / "riesgo") if p.exists()]
    if not candidatos:
        return {"estado": "no_disponible", "artefactos": False,
                "motivos": ["No hay artefactos de un clasificador de riesgo de atraso en modelo/artifacts/"]}  # fmt: skip
    return {"estado": "no_disponible", "artefactos": True,  # pragma: no cover - aún no existe
            "motivos": ["Hay artefactos de riesgo de atraso pero no están integrados (sin metadata de features)"]}


# ── motor de forecast vigente y `meta` ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Motor:
    """Qué motor produjo (o producirá) la serie: modelo/versión de `meta` y, si es baseline, por qué."""

    modelo: str
    version: str
    fallback: bool
    motivo: str | None = None

    @property
    def es_ml(self) -> bool:
        return not self.fallback


def motor_baseline(motivo: str) -> Motor:
    from app.services.finanzas.proyeccion import MODELO, VERSION  # noqa: PLC0415 - evita el ciclo de imports

    return Motor(MODELO, VERSION, True, motivo)


def motivo_fallback_forecast() -> str:
    """Por qué el LightGBM no está en uso a nivel de proceso ('' si lo está)."""
    d = diagnostico_forecast()
    if d["estado"] == "ok":
        return ""
    return "Modelo LightGBM no disponible: " + "; ".join(d["motivos"]) if d["estado"] != "desactivado" else d["motivos"][0]


def motor_forecast() -> Motor:
    """Motor que usará el forecast, sin mirar los datos de una empresa (alertas, health). Carga el modelo si hace falta."""
    d = diagnostico_forecast()
    if d["estado"] == "ok":
        return Motor(MODELO_FORECAST, d["modelo_version"], False)
    return motor_baseline(motivo_fallback_forecast())


def meta_b(modelo: str, version: str, *, fallback: bool, motivo: str | None = None) -> Meta:
    meta = construir_meta(modelo, version, fallback_usado=fallback)
    if motivo:
        return Meta(**meta.model_dump(), fallback_motivo=motivo)
    return meta


def meta_de(motor: Motor) -> Meta:
    return meta_b(motor.modelo, motor.version, fallback=motor.fallback, motivo=motor.motivo)
