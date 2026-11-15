# Trazabilidad — Supuesto → Variable → Regla de simulación

**Autor:** Pedro (scope: IA/ML/analítica + Datos sintéticos y evidencia)
**Objetivo:** que cualquier número del dataset sintético o del motor de recomendación se pueda
rastrear hasta el supuesto que lo justifica y la línea de código que lo implementa.

## A. `modelo_ingreso_egreso_lightgbm.ipynb` (forecast)

| Supuesto | Variable(s) | Regla de simulación (resumen) |
|---|---|---|
| Ventas diarias de pymes informales son asimétricas, con cola larga | `ingreso_base` | `rng.lognormal(mean=5.2, sigma=0.45)` |
| Negocios de más personal / rubros con más rotación venden más | `n_trabajadores`, `rubro` | `ingreso_base *= rubro_factor[rubro] * (1 + 0.12*(n_trabajadores-1))` |
| Más consumo viernes-domingo (retail de barrio) | `factor_semana` | `1 + 0.18 * es_viernes_a_domingo` |
| Más consumo en quincena / fin de mes (pago de sueldos en Perú) | `factor_mes` | `1 + 0.12 * (dia_mes en [14,15,16] o >=28)` |
| Crecimiento/decrecimiento propio del negocio en el tiempo | `tendencia` | `1 + N(0, 0.0004) * dia_del_periodo` |
| Quiebres de stock son eventos reales y frecuentes (~2% de los días) | `shock_quiebre` | `1 - 0.5 * (prob 2% por día)` |
| El problema no debe ser determinista (si no, no hay nada que aprender) | `ruido` | `rng.lognormal(0, sigma=0.15)` por día |
| Egreso = reposición de mercadería en función de lo vendido ayer | `reposicion` | `0.55 * ingreso[dia-1] * ruido` |
| Pago a proveedor y Nuevo RUS ocurren en fechas fijas del mes | `pago_proveedor_mensual`, `impuesto_mensual` | montos en `dia_mes == 5` / `== 15` |
| `rubro` debe calzar con la taxonomía real de la BD (`rubros`) | `rubro` | `["bodega","restaurante","taller","distribuidora"]` (no categorías inventadas) |
| `zona` es texto libre en la BD sin regla de mapeo → se reemplaza | `n_trabajadores` | columna real de `empresas`, no `zona` |
| `usa_fiado`/`usa_billetera_digital` necesitan definición con data real | — | regla acordada: `>=1 registro en los últimos 90 días`, documentada en `metadata.json` y en la vista `v_empresas_flags` (`modelo_datos.dbml`) |

## B. `credit_scoring_bodegas_logreg.ipynb` (riesgo)

| Supuesto | Variable(s) | Regla de simulación (resumen) |
|---|---|---|
| Criterio 1 — regularidad de ventas | `pct_dias_con_venta`, `cv_ventas` | `N(0.85, 0.12)` clip [0.3,1]; `N(0.35,0.15)` clip [0.05,1.2] |
| Criterio 2 — pago puntual a proveedores | `pct_pagos_a_tiempo`, `dias_mora_promedio` | `N(0.80,0.18)`; mora ∝ `(1 - pct_pagos_a_tiempo)` |
| Criterio 3 — % de ventas registradas NO es medible con data real | `dias_desde_ultimo_registro` | proxy: `rng.exponential(escala)`, escala menor si `usa_billetera_digital` o `tiene_ruc` (más digitalizados registran más seguido) |
| Criterio 4 — % de fiado sobre ventas y su cobro | `pct_fiado_sobre_ventas`, `pct_fiado_cobrado_a_tiempo` | `N(0.20,0.12)` clip [0,0.7]; `N(0.70,0.20)` clip [0,1]. La segunda se usa **solo agregada**, nunca el campo individual `pago_tardio` |
| Criterio 5 — antigüedad del negocio | `antiguedad_meses` | `rng.integers(1,200)` |
| `n_alertas_quiebre_stock` no tiene tipo propio en `tipo_alerta` | `n_alertas_quiebre_stock` | proxy vía `alertas.tipo_alerta = caida_ventas`; agregar un tipo nuevo queda como mejora opcional |
| El ground truth debe depender de los 5 criterios, con ruido | `buen_pagador` | `logit = -5.93 + 1.5*(Σ pesos*criterios) + N(0,0.4)` (constante del notebook); `buen_pagador ~ Bernoulli(sigmoid(logit))` |
| `rubro`/`n_trabajadores` alineados con la BD real | `rubro`, `n_trabajadores` | mismos valores y regla que en el notebook de forecast |

## C. `motor_recomendaciones.ipynb` (capa de recomendación)

No es simulación de datos, pero sigue la misma disciplina de trazabilidad: cada regla cita
explícitamente qué variable la dispara (campo `causas`, igual formato que la tabla `alertas`).

| Regla (`tipo_alerta`) | Variable(s) que la disparan | Umbral |
|---|---|---|
| `faltante_caja` | `saldo_proyectado_p10` vs `empresas.minimo_operativo` | `saldo_p10 < minimo_operativo` |
| `gasto_inusual` | `egreso_pred_p50` vs `egreso_media30` | `factor >= 1.5` |
| `caida_ventas` | `pct_dias_con_venta`, `cv_ventas` | `pct_dias < 0.6` o `cv >= 0.5` |
| `fiado_vencido` | `pct_fiado_sobre_ventas`, `pct_fiado_cobrado_a_tiempo` | `pct_fiado >= 0.35` y `pct_cobrado < 0.5` |
| `meta_lograda` | `score` (output del credit scoring) | `score >= 70` |

Todos los umbrales están centralizados en `UMBRALES` (celda de código del notebook) y exportados
en `modelo/artifacts/motor_recomendaciones/config.json` — cambiar un umbral no requiere tocar la
lógica de las reglas.

**Integración en el backend:** `motor_recomendaciones` **no se integra** como motor aparte: sus ideas útiles ya están
implementadas como reglas en `backend/app/services/alertas/reglas.py` (`gasto_inusual`, `fiado_vencido`, `meta_lograda`).

## D. Trazabilidad de las llamadas a LLM en producción (fuera de `modelo/`)

Los notebooks de esta carpeta no llaman a ningún LLM. Las llamadas del backend (extractor, clasificador del chat, lectura
de la foto del cuaderno y asistente) se registran una por una en la tabla `llm_llamadas` (modelo, versión del prompt, tokens,
costo, latencia, estado, si las cifras se verificaron y si se usó el fallback); ver `backend/app/services/ingesta/traza_llm.py`
y `GET /empresas/{id}/llm/llamadas` y `/llm/resumen`. Los modelos de ML integrados (`forecast-lgbm-quantile`, `credit-scoring-logreg`)
devuelven su `meta` (modelo, versión, `fallback_usado`, `fallback_motivo`) en cada respuesta.
