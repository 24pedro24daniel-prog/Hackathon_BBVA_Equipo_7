# Prompts / uso de IA — Datos sintéticos y Modelos predictivos

**Declaración de autoría:** esta sección (`modelo/`, carpeta completa: datos sintéticos,
notebooks de forecast y credit scoring, motor de recomendación, documentación de ground truth y
trazabilidad) fue construida por **Pedro**, con asistencia de un agente de IA (Claude, vía Claude
Code) como herramienta de prompt engineering y generación de código bajo su dirección y revisión
directa. El resto del equipo documentará sus propios prompts/agentes para sus componentes
respectivos (p. ej. el extractor de borradores por voz/foto, el asistente conversacional del
chat — `backend/app/services/ingesta/llm_consultas.py`, `traza_llm.py` — que sí usan LLM en
producción).

## Por qué esto es "evidencia técnica" válida

Ningún notebook de `modelo/` llama a un LLM en tiempo de ejecución — son modelos clásicos
(LightGBM, regresión logística) y un motor de reglas. El prompt engineering aquí fue la
**herramienta de construcción** (igual que un IDE o un copiloto de código), no una pieza del
pipeline de inferencia. Se documenta de todas formas porque el reto pide transparencia sobre el
uso de IA generativa en el desarrollo del entregable.

## Prompts resaltantes (orden cronológico, verbatim)

1. **Asignación de rol y entregables**
   > "me corresponde -IA / ML / analítica -Datos sintéticos y evidencia -Dataset sintético
   > -Modelo / IA guarda esa información para enfocarnos a partir de ahora. considera los pesos y
   > entregables."

2. **Generación del notebook de forecast**
   > "empieza con LightGBM haz un notebook donde: -simule data -habrán miles de bodegueros
   > -target a predecir ingreso y egresos -y lo que consideres como para que se pueda insertar y
   > ser bien visto en el mvp por el jurado"

3. **Generación del notebook de credit scoring**
   > "ahora otro notebook para un analisis credit scoring end to end. considere: [5 criterios:
   > regularidad de ventas, pago puntual a proveedores, % de ventas registradas, % de fiado y su
   > cobro, antigüedad del negocio] y demas campos pertinentes con bodegas peruanas -se puede
   > probar con un sujeto que se muestre una aguja (como imagen) -ingresará en el mvp movil
   > -considere data suficiente para entrenamiento facil -use regresion logistica"

4. **Alineación con el modelo de datos real del equipo (iterativo)**
   > "revise el modelo de datos que propone el github grupal" → "¿podemos manejar los campos que
   > aparecen en el modelo de datos o es necesario agregar nuevos campos?" → "ajusta el notebook
   > de credit scoring con esas reglas"

5. **Decisión de negocio resuelta y propagada al esquema**
   > "me dijeron ok. me dijeron que como son campos derivados del modelo de datos por que no
   > intentar solo agregar campos calculados?" → "ok agrega esa vista al modelo_datos.dbml"

6. **Capa de recomendación (gap detectado en revisión de evaluación)**
   > "empieza con capa de recomendación"

7. **Entregables de evidencia técnica (este documento y los otros 2)**
   > "documento de ground truth / Documento de trazabilidad (supuesto → variable → regla de
   > simulación) / prompts/agentes de IA resaltantes"

## Rol del agente de IA en cada entrega

| Entregable | Qué hizo Pedro (dirección) | Qué generó el agente (ejecución) |
|---|---|---|
| Dataset sintético (ambos) | Definió criterios de negocio, pidió ajustes de balance/realismo, validó métricas | Código de simulación, calibración de pesos, ejecución y verificación |
| Notebook forecast | Pidió el enfoque (LightGBM, miles de bodegas), corrigió alcance (rubro/zona reales) | Feature engineering, entrenamiento, exportación de artefactos |
| Notebook credit scoring | Definió los 5 criterios y el formato de visualización (velocímetro) | Simulación del ground truth, calibración del balance de clases, entrenamiento |
| Motor de recomendación | Identificó el gap de evaluación ("solo predicción, no recomendación") | Diseño de reglas, mapeo a `tipo_alerta`/`accion_sugerida` del `.dbml` |
| Documentos de evidencia (ground truth, trazabilidad, este) | Pidió explícitamente cada documento | Redacción basada en el trabajo ya realizado y verificado |

Todo el código fue **revisado y ejecutado en el entorno de Pedro** (no es un entregable generado
a ciegas): cada notebook se corrió de punta a punta, se verificaron 0 errores y las métricas antes
de subir cualquier cambio al repositorio del equipo.
