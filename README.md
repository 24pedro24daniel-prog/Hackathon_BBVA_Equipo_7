# TuCaserito

TuCaserito es un copiloto de orden y maduración financiera diseñado específicamente para **bodegueros de barrio con RUC 10 en Perú que operan 100% en efectivo (*cash*)** y llevan sus cuentas de forma manual en cuadernos físicos. Ayuda a digitalizar ventas, fiados y pagos a proveedores; separar el capital del negocio del **mínimo para vivir**; corregir errores al informar impuestos; y anticipar faltantes de caja antes de los vencimientos.

El producto combina una interfaz conversacional autenticada (inspirada en mensajería para registrar movimientos en segundos sin usar bots abiertos en WhatsApp por seguridad bancaria) con un dashboard operativo que muestra el arqueo de efectivo, obligaciones y proyecciones a 30 días. El caso de uso de la demo es Pedro, bodeguero ficticio RUC 10. Todos los nombres, movimientos y montos de demostración son sintéticos.

*(Nota de identidad visual: TuCaserito es una solución independiente con marca e interfaz propias; no utiliza logos, colores ni interfaces bancarias oficiales como si fuera un producto del banco.)*

## El problema

Los bodegueros RUC 10 tradicionales cobran exclusivamente en efectivo y llevan sus cuentas en cuadernos de papel o de memoria, formando parte del núcleo de "No Clientes" invisibles para la banca comercial. Guardan todo el dinero en un solo cajón ("caja única"), mezclan los gastos del negocio con su subsistencia diaria y no tienen claro cuánto les deben ni cuándo vencen sus proveedores.

En campañas estacionales fuertes —como la **campaña navideña**— suelen pedir mercadería de más sin prever sus vencimientos de caja. Además, aunque muchos **sí cumplen con pagar su impuesto básico (Nuevo RUS), lo informan o calculan mal** (confundiendo los tramos de cuota S/ 20 vs. S/ 50 cuando suben sus ventas o registrándolo mezclado con gastos personales). Cuando aparece un faltante, recurren a préstamos informales costosos ("gota a gota"). TuCaserito ordena su información y previene crisis de liquidez sin alterar su rutina en mostrador.

Las referencias y el sustento del problema están documentados en [context.md](./context.md). Las cifras externas deben presentarse junto con sus fuentes; las conversaciones del equipo son evidencia cualitativa y no deben exponerse como estadísticas generales.

## Objetivos del MVP

- Registrar movimientos en efectivo mediante **foto del cuaderno, voz y texto manual**, con **doble confirmación** ante ambigüedades y posibilidad de corregir.
- Realizar el arqueo de efectivo separando el flujo en **3 cubetas**: gastos operativos/mercadería, **mínimo para vivir** (gastos fijos personales) y gastos personales extra, calculando un **sueldo mensual fijo bajo criterio bancario**.
- Proyectar el saldo diario de efectivo a 30 días (incorporando campañas como Navidad y días sin registro), señalar riesgos de faltante y simular escenarios ("What-If").
- Dar seguimiento a fiados, deudas con proveedores y auditar el registro correcto del Nuevo RUS.
- Explicar alertas y cifras con datos verificables, supuestos, límites y nivel de confianza.
- Medir hábitos financieros con un índice pedagógico de maduración explicable.

## Funcionalidades

1. **Registro multicanal con doble confirmación:** captura mediante **foto del cuaderno físico (OCR/Visión), voz y texto manual** dentro de la app autenticada. Ante letra manuscrita poco legible, mala pronunciación o abreviaturas ambiguas, exige doble confirmación antes de guardar. Los posibles duplicados (ej. un apunte dictado por voz y luego fotografiado en el cuaderno) se señalan para revisión humana: nunca se borran ni combinan automáticamente.
2. **Resumen financiero y sueldo bancario:** arqueo de efectivo disponible, ingresos y egresos del mes desglosados en las 3 cubetas, ganancia aproximada, retiros personales vs. **sueldo fijo sugerido** (promedio histórico de gastos fijos para vivir), fiados por cobrar y pagos pendientes.
3. **Proyección de caja (30 días):** horizonte diario con rango pesimista/esperado/optimista, estacionalidad semanal y de campañas (Navidad), saldo mínimo operativo, alertas de déficit y monto **"disponible para gastar hoy"**.
4. **Fiados, proveedores y auditoría de impuestos:** seguimiento de cobros vencidos, calendario de pagos a proveedores, chequeo preventivo antes de pedir stock de campaña, y verificación del tramo/clasificación del **Nuevo RUS** ("paga, pero informa mal").
5. **Análisis:** evolución de ingresos y egresos en efectivo por categoría, producto, proveedor o periodo, con comparativa anónima frente a bodegas RUC 10 similares.
6. **Alertas:** avisos preventivos priorizados ("justo a tiempo"), con evidencia exacta ("¿Por qué veo esto?") y una acción sugerida de un toque; máximo dos al día y respetando horario silencioso.
7. **Asistente:** responde consultas y simula cambios en la caja usando motores determinísticos en Python vía *function calling*; no inventa ni calcula cifras por su cuenta.
8. **Progreso:** ruta de metas y un índice pedagógico de maduración financiera basado en hábitos observables.

## Uso responsable y límites

- El índice de maduración es educativo y explicable. No es un score crediticio, no estima elegibilidad y no determina decisiones de préstamo.
- El asistente puede explicar conceptos generales (como el funcionamiento básico del Nuevo RUS o el costo del crédito informal) y simular el efecto de acciones sobre la caja del negocio. No recomienda ni selecciona préstamos, productos financieros, prestamistas o entidades específicas, ni da asesoría tributaria o legal formal.
- Un historial estructurado podría compartirse o exportarse en el futuro para una revisión humana con un asesor bancario, solo con consentimiento explícito, desactivado por defecto y revocable. Esto no automatiza una decisión ni garantiza aprobación, acceso o mejores condiciones.
- La aplicación no ejecuta operaciones financieras reales, no otorga créditos y no promete aprobaciones ni rentabilidad.
- Los datos de demo son sintéticos (`seed=42`). Las estimaciones y salidas de modelos deben mostrar su origen, supuestos, límites, confianza y trazabilidad. El usuario conserva siempre la decisión final.
- No se deben incluir credenciales, datos bancarios reales ni información personal real.

## Alcance de la demo y potencial de expansión

- **Flujo principal:** registrar una venta/apunte en efectivo mediante foto de cuaderno y voz (activando doble confirmación y detección de duplicados), revisar el arqueo de efectivo frente al sueldo fijo ("mínimo para vivir"), detectar un error de tramo en el Nuevo RUS, entender un faltante proyectado para el **30/11 por sobrecompra de campaña navideña**, ver sus causas y simular alternativas. El relato sintético usa un saldo de S/ 2 340, un pago de S/ 2 400 a Distribuidora Andina, un déficit de S/ 650 y S/ 310 en fiados pendientes.
- **Prioridad del MVP:** registro por voz/texto/foto con doble confirmación, pedidos a crédito de proveedores, auditoría básica de Nuevo RUS, consulta del estado, resumen financiero con 3 cubetas, forecast a 30 días, cuentas por cobrar/pagar y alertas principales. Para la demo se acotan algunas intenciones del asistente, tres subindicadores principales del índice y dos gráficos analíticos.
- **Potencial de expansión (Roadmap):** una vez validado en bodegas RUC 10 en efectivo, la arquitectura parametrizada (`rules.json`) escala hacia bodegas con billeteras digitales (Yape/Plin) y POS, otros rubros minoristas RUC 10 (ferreterías, farmacias de barrio, bazares, restaurantes), comparación con pares reales y exportación consentida de historial para evaluación humana.

## Enfoque técnico previsto

- **Frontend:** React y Vite en [`frontend/`](./frontend/).
- **API y Lógica Determinística:** FastAPI y Pydantic en [`backend/`](./backend/), con contratos previstos bajo `/api/v1` en [`contract.md`](./contract.md) y reglas desacopladas en `rules.json`.
- **Voz, OCR y Asistente:** ejecución local con `faster-whisper` (voz), `PaddleOCR` (cuaderno) y LLM local vía `Ollama` (con fallback por plantillas) para garantizar operación offline.
- **Proyección:** comparar un baseline naive estacional con LightGBM de regresión por cuantiles, justificado por su capacidad para modelar pagos rígidos a proveedores, días sin registro y picos de campaña navideña.
- **Riesgo de atraso y calidad de datos:** comparar un clasificador de atraso en fiados con un baseline histórico y evaluar detección de duplicados/errores de registro; evitar fuga de datos y validar con particiones temporales.
- **Trazabilidad y evaluación:** medir exactitud por campo de la ingesta (foto/voz/texto), WER de transcripción, MAE/cobertura del forecast vs. baseline, métricas de alertas y *groundedness* de las cifras del asistente. Los objetivos son metas de evaluación, no resultados ya demostrados.

## Estado actual del repositorio

La documentación define el producto y los contratos objetivo; no implica que esas funcionalidades ya estén implementadas.

- [`frontend/`](./frontend/) es una base inicial React + Vite.
- [`backend/`](./backend/) pendiente de implementación (API, motor determinístico, dataset sintético y modelos).
- [`PRODUCT.md`](./PRODUCT.md) define usuarios, propósito y principios de producto.
- [`context.md`](./context.md) desarrolla problemática, objetivos, funcionalidades, alcance y storytelling.
- [`contract.md`](./contract.md) describe los contratos previstos para la API.

### Instrucciones de ejecución (Local)

**1. Iniciar el frontend:**
```bash
cd frontend
npm install
npm run dev
