# CajaClara

CajaClara es una propuesta de gestor de caja para bodegas y pequeños negocios no bancarizados en Perú. Ayuda a ordenar ventas, gastos, fiados y pagos; separar la plata del negocio de la plata de la casa; y anticipar faltantes antes de los vencimientos.

El producto combina un chat inspirado en WhatsApp, pensado para registrar movimientos en pocos segundos, con un dashboard que muestra la caja, las deudas y las proyecciones. El caso de uso de la demo es Pedro, bodeguero ficticio. Todos los nombres, movimientos y montos de demostración son sintéticos.

## El problema

Muchos bodegueros llevan sus cuentas en papel o de memoria, mezclan el dinero personal con el del negocio y no tienen claro cuánto les deben ni cuándo deben pagar a sus proveedores. Cuando aparece un faltante, pueden recurrir a préstamos informales costosos. CajaClara busca ayudarlos a ordenar la información y tomar decisiones con anticipación, sin cambiar su rutina diaria.

Las referencias y el sustento del problema están documentados en [context.md](./context.md). Las cifras externas deben presentarse junto con sus fuentes; las conversaciones del equipo son evidencia cualitativa y no deben exponerse como estadísticas generales.

## Objetivos del MVP

- Registrar movimientos por voz o texto, con confirmación y posibilidad de corregir.
- Resumir la caja del negocio y distinguirla de los retiros para la casa.
- Proyectar el saldo diario a 30 días, señalar riesgos de faltante y simular escenarios.
- Dar seguimiento a fiados, deudas con proveedores e impuestos básicos.
- Explicar alertas y cifras con datos verificables, supuestos, límites y nivel de confianza.
- Medir hábitos financieros con un índice pedagógico de maduración explicable.

## Funcionalidades

1. **Registro multicanal:** voz y texto; fotos del cuaderno de fiados en la demo. Los posibles duplicados se señalan para revisión de la persona: nunca se borran ni combinan automáticamente.
2. **Resumen financiero:** saldo del negocio, ingresos, egresos, ganancia aproximada, retiros personales, fiados y pagos pendientes.
3. **Proyección de caja:** horizonte de 30 días, rango pesimista/esperado/optimista, saldo mínimo operativo, alertas y monto disponible para gastar.
4. **Fiados y pagos:** seguimiento de cobros, proveedores e impuestos, con recordatorios y chequeo del impacto de un pedido a crédito.
5. **Análisis:** ingresos y egresos por categoría, producto o periodo.
6. **Alertas:** avisos preventivos priorizados, con una explicación y una acción posible; máximo dos al día y respetando horario silencioso.
7. **Asistente:** responde consultas y simula cambios en la caja usando los motores de cálculo; no inventa ni calcula cifras por su cuenta.
8. **Progreso:** metas y un índice de maduración financiera basado en hábitos observables.

## Uso responsable y límites

- El índice de maduración es educativo y explicable. No es un score crediticio, no estima elegibilidad y no determina decisiones de préstamo.
- El asistente puede explicar conceptos generales y simular el efecto de acciones sobre la caja del negocio. No recomienda ni selecciona préstamos, productos financieros, prestamistas o entidades específicas, ni da recomendaciones personalizadas de financiamiento.
- Un historial estructurado podría compartirse o exportarse en el futuro para una revisión humana, solo con consentimiento explícito, desactivado por defecto y revocable. Esto no automatiza una decisión ni garantiza aprobación, acceso o mejores condiciones.
- La aplicación no ejecuta operaciones financieras, no otorga créditos y no promete aprobaciones ni rentabilidad.
- Los datos de demo son sintéticos. Las estimaciones y salidas de modelos deben mostrar su origen, supuestos, límites, confianza y trazabilidad.
- No se deben incluir credenciales, datos bancarios reales ni información personal real.

## Alcance de la demo

**Flujo principal:** registrar una venta por voz, revisar la caja del negocio, entender un faltante proyectado para el 30/11, ver sus causas y simular alternativas. El relato sintético usa un saldo de S/ 2 340, un pago de S/ 2 400 a Distribuidora Andina, un déficit de S/ 650 y S/ 310 en fiados pendientes.

**Prioridad del MVP:** registro por voz/texto, pedidos a crédito de proveedores, consulta del estado, resumen financiero, forecast, cuentas por cobrar/pagar y alertas principales. Para la demo se simplifican la lectura de fotos, el registro de impuestos, algunas intenciones del asistente, tres subindicadores del índice y dos gráficos.

**Roadmap:** WhatsApp Business oficial, integración real con billeteras, lectura de comprobantes, comparación con pares reales, guía de formalización y compartir el historial con consentimiento para una evaluación humana.

## Enfoque técnico previsto

- **Frontend:** React y Vite en [`frontend/`](./frontend/).
- **API:** FastAPI y Pydantic, con contratos previstos bajo `/api/v1` en [`contract.md`](./contract.md).
- **Voz y asistente:** faster-whisper y un LLM local vía Ollama, con alternativas de fallback.
- **Proyección:** comparar un baseline naive estacional con LightGBM de regresión por cuantiles.
- **Riesgo de atraso:** comparar un clasificador con un baseline de atraso histórico; evitar fuga de datos y validar con particiones temporales y por empresa.
- **Trazabilidad y evaluación:** medir exactitud por campo de la ingesta, WER de transcripción, MAE/cobertura del forecast, métricas de alertas y groundedness de las cifras del asistente. Los objetivos son metas de evaluación, no resultados ya demostrados.

## Estado actual del repositorio

La documentación define el producto y los contratos objetivo; no implica que esas funcionalidades ya estén implementadas.

- [`frontend/`](./frontend/) es una base inicial React + Vite.
- [`backend/`](./backend/) todavía no tiene implementación.
- [`PRODUCT.md`](./PRODUCT.md) define usuarios, propósito y principios de producto.
- [`context.md`](./context.md) desarrolla problemática, objetivos, funcionalidades, alcance y storytelling.
- [`contract.md`](./contract.md) describe los contratos previstos para la API.

Para iniciar el frontend:

```bash
cd frontend
npm install
npm run dev
```
