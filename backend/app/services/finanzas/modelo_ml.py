"""Estado de los modelos de ML del equipo de datos (forecast LightGBM por cuantiles y riesgo de atraso).

Regla del equipo: un modelo solo se integra si sus artefactos cargan y TODOS sus features se pueden construir desde
la BD sin inventar valores. Aquí solo se lee `metadata.json` (JSON, sin dependencias de ML ni deserializar .joblib):
si algún feature no tiene equivalente en la BD, el modelo queda "no_disponible" con el motivo concreto y los motores
usan el baseline determinístico con `meta.fallback_usado = true`.

Diagnóstico al 15/11 (artefactos de modelo/artifacts/prediccion_ingreso_egreso/, notebook
modelo_ingreso_egreso_lightgbm.ipynb). El equipo de ML ya resolvió `rubro` (ahora usa la taxonomía real de
`rubros`: bodega/restaurante/taller/distribuidora) y reemplazó `zona` por `n_trabajadores` (existe directo en
`empresas.n_trabajadores`). Este chequeo automático solo reconoce como "construible" lo que matchea
`_CONSTRUIBLE` (lags/medias/stds/calendario); `rubro`, `n_trabajadores` y `antiguedad_meses` seguirán
apareciendo en `features_no_construibles` hasta que alguien actualice esa regex/MOTIVOS_FEATURE para
reflejar que sí son construibles vía join/columna directa con la BD real.
- `usa_fiado`, `usa_billetera_digital`: siguen sin definición acordada para datos reales (propuesta en el
  `metadata.json` del notebook: ">=1 registro en los últimos 90 días", a confirmar con backend).
Los 23 features de lags, medias, desviaciones de ingreso/egreso diario y calendario sí son construibles.
"""

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.core.meta import construir_meta
from app.schemas.common import Meta

log = logging.getLogger("cajaclara.ml")

ARCHIVOS_FORECAST = [f"{t}_p{q}.joblib" for t in ("ingreso", "egreso") for q in (10, 50, 90)]
_CONSTRUIBLE = re.compile(r"^(ingreso|egreso)_(lag(1|7|14)|media(7|14|30)|std(7|14|30))$|^(dow|dom|es_finde|es_quincena_o_finmes|mes)$")
MOTIVOS_FEATURE = {
    "rubro": "rubro: el modelo espera {cats}; la BD solo tiene la taxonomía de `rubros` (bodega, restaurante, taller, "
             "distribuidora) y no hay regla para mapearla",
    "zona": "zona: el modelo espera {cats}; la BD guarda la zona/distrito como texto libre y no hay regla para mapearla",
    "usa_fiado": "usa_fiado: bandera fija del dataset simulado; no hay definición acordada para calcularla con datos reales",
    "usa_billetera_digital": "usa_billetera_digital: bandera fija del dataset simulado; no hay definición acordada para "
                             "calcularla con datos reales",
}  # fmt: skip


def directorio() -> Path:
    return settings.ml_artifacts_dir


def _mtime(ruta: Path) -> float | None:
    try:
        return ruta.stat().st_mtime
    except OSError:
        return None


@lru_cache(maxsize=8)
def _diagnostico_forecast(ruta: str, _mtime_cache: float | None) -> dict:
    base = Path(ruta)
    meta_path = base / "metadata.json"
    if not meta_path.exists():
        return {"estado": "no_disponible", "artefactos": False, "motivos": [f"No existe {meta_path}"]}
    faltan = [a for a in ARCHIVOS_FORECAST if not (base / a).exists()]
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"estado": "no_disponible", "artefactos": True, "motivos": [f"metadata.json ilegible: {exc}"]}
    motivos = [f"Falta el artefacto {a}" for a in faltan]
    no_construibles = []
    for feat in meta.get("features_en_orden", []):
        if _CONSTRUIBLE.match(feat):
            continue
        no_construibles.append(feat)
        cats = meta.get(f"categorias_{feat}")
        plantilla = MOTIVOS_FEATURE.get(feat, f"{feat}: feature sin equivalente conocido en la BD")
        motivos.append(plantilla.format(cats=", ".join(cats) if cats else "?"))
    estado = "ok" if not motivos else "no_disponible"
    if estado == "ok":  # pragma: no cover - hoy no ocurre; integrar requiere lightgbm y el cargador
        motivos = ["Features construibles, pero el cargador LightGBM no está integrado en el backend"]
        estado = "no_disponible"
    return {
        "estado": estado,
        "artefactos": not faltan,
        "tipo_modelo": meta.get("tipo_modelo"),
        "features_no_construibles": no_construibles,
        "motivos": motivos,
    }


def diagnostico_forecast() -> dict:
    """Estado del modelo LightGBM de forecast sin cargarlo (barato: lee metadata.json y lo cachea por mtime)."""
    base = directorio() / "prediccion_ingreso_egreso"
    return _diagnostico_forecast(str(base), _mtime(base / "metadata.json"))


def diagnostico_riesgo_atraso() -> dict:
    base = directorio()
    candidatos = [p for p in (base / "riesgo_atraso", base / "riesgo") if p.exists()]
    if not candidatos:
        return {"estado": "no_disponible", "artefactos": False,
                "motivos": ["No hay artefactos de un clasificador de riesgo de atraso en modelo/artifacts/"]}  # fmt: skip
    return {"estado": "no_disponible", "artefactos": True,  # pragma: no cover - aún no existe
            "motivos": ["Hay artefactos de riesgo de atraso pero no están integrados (sin metadata de features)"]}


def motivo_fallback_forecast() -> str:
    d = diagnostico_forecast()
    return "Modelo LightGBM no integrable: " + "; ".join(d["motivos"]) if d["motivos"] else ""


def meta_b(modelo: str, version: str, *, fallback: bool, motivo: str | None = None) -> Meta:
    meta = construir_meta(modelo, version, fallback_usado=fallback)
    if motivo:
        return Meta(**meta.model_dump(), fallback_motivo=motivo)
    return meta
