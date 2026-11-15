# Ground Truth — CajaClara (IA/ML)

**Autor:** Pedro (scope: IA/ML/analítica + Datos sintéticos y evidencia)
**Alcance:** los 2 modelos predictivos (`modelo_ingreso_egreso_lightgbm.ipynb`, `credit_scoring_bodegas_logreg.ipynb`)

## 1. Qué es el "ground truth" en este proyecto

Como el reto prohíbe usar data real de BBVA, **no existe un historial real de ventas, pagos o
incumplimientos de bodegas** contra el cual entrenar o validar un modelo. La alternativa estándar
en estos casos (y la que se usó aquí) es **simular datos con un generador controlado donde el
"valor correcto" se conoce de antemano por construcción**, y evaluar si el modelo es capaz de
recuperar esa señal a partir de las features. Esto no reemplaza la validación con data real una
vez el MVP esté en producción, pero es la forma correcta de **demostrar que la metodología (no el
número final) es sólida** con la información disponible en el hackathon.

## 2. Ground truth del modelo de forecast (ingreso / egreso)

- **Qué es:** la propia serie simulada de `ingreso` y `egreso` diario por bodega
  (`modelo_ingreso_egreso_lightgbm.ipynb`, sección 1).
- **Cómo se define:** una combinación de tamaño del negocio (`ingreso_base`), estacionalidad
  semanal/mensual, tendencia, shocks de quiebre de stock y ruido log-normal — todo generado con
  `numpy.random.Generator(seed=42)`, por lo que es **100% reproducible**.
- **Por qué es válido como ground truth:** al ser generado por una función conocida, se puede
  comparar la predicción del modelo contra el valor real simulado sin ambigüedad (no hay
  incertidumbre de medición, como sí la habría con data real mal registrada). El modelo se evalúa
  con **backtesting temporal** (train en el pasado, test en el futuro, nunca mezclado), que es la
  misma disciplina que se usaría con data real.
- **Limitación explícita:** el ground truth es sintético, por lo que el modelo aprende los
  patrones *que el generador impuso* (estacionalidad, ruido), no necesariamente los patrones
  reales de una bodega peruana. Validar contra data real es el siguiente paso obligatorio una vez
  el backend tenga transacciones reales.

## 3. Ground truth del modelo de credit scoring (`buen_pagador`)

- **Qué es:** la variable binaria `buen_pagador` (1 = bajo riesgo, 0 = alto riesgo),
  `credit_scoring_bodegas_logreg.ipynb`, sección "Variable objetivo".
- **Cómo se define:** se construye una **probabilidad latente** combinando los 5 criterios
  pedidos por el equipo (regularidad de ventas, pago puntual a proveedores, días desde el último
  registro, % de fiado y su cobro, antigüedad) con pesos que reflejan su importancia relativa, más
  ruido gaussiano (evita que el problema sea trivialmente separable). La etiqueta final sale de un
  sorteo Bernoulli sobre esa probabilidad — es decir, **el ground truth está causalmente ligado a
  las mismas variables que luego se usan como features**, por diseño.
- **Por qué es válido:** esto es exactamente lo que se busca para *validar que el modelo puede
  aprender la relación* entre los 5 criterios del reto y el riesgo — si el modelo no lograra un
  AUC razonable (se obtuvo 0.764-0.771) sobre un ground truth que *por construcción* depende de
  esas variables, sería señal de un error de implementación, no de falta de señal.
- **Limitación explícita:** con data real, nadie sabe de antemano quién es "buen pagador" — eso
  habría que definirlo operativamente (ej. historial de mora, score de BCP/Equifax si estuviera
  disponible, o un proxy que el equipo de producto defina). El valor de este ground truth sintético
  es metodológico (probar el pipeline), no una predicción de la tasa de riesgo real de bodegas
  peruanas.

## 4. Qué NO se usó como ground truth (reglas respetadas)

Siguiendo las convenciones ya definidas en `modelo_datos.dbml` (campos marcados como "ETIQUETA" u
"OCULTO, nunca feature"):
- `cuaderno_fiado.pago_tardio` y `clientes.perfil_pago`: reservados para evaluación, nunca se
  usaron como feature de entrada (solo la **tasa agregada** `pct_fiado_cobrado_a_tiempo` se usa
  como feature, siguiendo la regla acordada con el equipo).
- `eventos` (shocks insertados en el generador): nunca se usaron como feature, solo para poder
  verificar después que el modelo reacciona razonablemente ante ellos.
