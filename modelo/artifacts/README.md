# Modelos entrenados (artefactos para consumo por el backend)

Formato: `.joblib` (serialización estándar de scikit-learn/LightGBM en Python).
**No son `.pt`** — ese formato es de PyTorch y no aplica aquí; `joblib` es el equivalente correcto
para modelos de scikit-learn y LightGBM.

## `prediccion_ingreso_egreso/` — Predicción de ingreso y egreso diario (LightGBM)

Generado por: `modelo/modelo_ingreso_egreso_lightgbm.ipynb`

| Archivo | Contenido |
|---|---|
| `ingreso_p10.joblib`, `ingreso_p50.joblib`, `ingreso_p90.joblib` | `LGBMRegressor` para ingreso, cuantiles 10/50/90 |
| `egreso_p10.joblib`, `egreso_p50.joblib`, `egreso_p90.joblib` | `LGBMRegressor` para egreso, cuantiles 10/50/90 |
| `metadata.json` | Orden exacto de features, columna categórica (`rubro`) y sus categorías válidas |

**Cómo consumir:**
```python
import joblib, json
import pandas as pd

with open("metadata.json") as f:
    meta = json.load(f)

modelo_p50 = joblib.load("ingreso_p50.joblib")

# X debe tener las columnas de meta["features_en_orden"], en ese orden,
# con 'rubro' como pandas Categorical usando meta["categorias_rubro"]
pred = modelo_p50.predict(X)
```

## `credit_scoring/` — Score de salud financiera (Regresión Logística)

Generado por: `modelo/credit_scoring_bodegas_logreg.ipynb`

| Archivo | Contenido |
|---|---|
| `logreg_model.joblib` | `LogisticRegression` entrenado (AUC test = 0.7643, el de `metadata.json`) |
| `scaler.joblib` | `StandardScaler` ajustado — **debe aplicarse antes de predecir** |
| `metadata.json` | Orden de columnas post one-hot encoding, rangos del score y fórmula |

**Cómo consumir:**
```python
import joblib, json

with open("metadata.json") as f:
    meta = json.load(f)

modelo = joblib.load("logreg_model.joblib")
scaler = joblib.load("scaler.joblib")

# X debe tener las columnas de meta["columnas_en_orden"] (generadas con pd.get_dummies
# igual que en el notebook; rellenar con 0 las categorías de rubro ausentes; `bodega` es la categoría base y no tiene columna)
proba = modelo.predict_proba(scaler.transform(X))[:, 1]
score = round(proba[0] * 100)  # 0-100, ver meta["rangos_categoria"]
```

## `motor_recomendaciones/` — Umbrales del motor de reglas

Generado por: `modelo/motor_recomendaciones.ipynb`. Solo contiene `config.json` (umbrales de reglas, no es un modelo
entrenado). **El backend no lo integra**: sus ideas útiles ya están implementadas como las reglas `gasto_inusual`,
`fiado_vencido` y `meta_lograda` de `backend/app/services/alertas/reglas.py`.

## Cómo los usa el backend

`backend/Dockerfile` copia `prediccion_ingreso_egreso/` y `credit_scoring/` a la imagen (`/app/ml/artifacts`), así que
local y Render sirven los mismos archivos. Los carga de forma perezosa (`backend/app/services/finanzas/modelo_ml.py`) y
valida nombres/orden de features contra cada `metadata.json`. Detalle del feature engineering, el train/serve skew y el
fallback: `backend/README.md` §Modelos de ML. Versiones que cargan los `.joblib` sin warnings: `lightgbm==4.7.0`,
`scikit-learn==1.9.1`, `pandas==3.1.1`, `numpy==2.5.4`, `scipy==1.18.1`, `joblib==1.6.0`.

## Regenerar los artefactos

Los tres notebooks (forecast, credit scoring y motor de recomendaciones) son reproducibles (seed fijo). Basta con
correrlos de nuevo (kernel "Python 3.15 (BBVA)") para regenerar estos mismos archivos con los mismos resultados.
