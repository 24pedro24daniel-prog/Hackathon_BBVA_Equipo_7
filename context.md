# CajaClara — Contexto del proyecto

> Gestor financiero para bodegas y pymes no bancarizadas.
> Hackathon de Ingeniería BBVA "AI Financial Life" (14–15/11/2026).

---

## 0. Reglas del hackathon (restricciones del proyecto)

- **IA/ML con función demostrable y evaluable**, analítica reproducible, interfaz o API utilizable y demo ejecutable.
- **Solo datos sintéticos o públicos autorizados.** Prohibido usar datos personales reales, credenciales bancarias, sistemas internos BBVA o material confidencial.
- **No presentarse como producto oficial de BBVA** (no usar marca, logos ni interfaces bancarias).
- **No prometer rentabilidades ni ejecutar operaciones financieras reales.** Las recomendaciones son orientación educativa o simulación, con supuestos claros; no es asesoría regulada.
- **Cada técnica debe justificarse y compararse con una alternativa sencilla (baseline).**
- **Secretos fuera del código** (`.env`); documentar dependencias, versión del modelo, prompts y mecanismos de fallback.
- **Las recomendaciones incluyen fundamento, límites y nivel de confianza. El usuario conserva la decisión final.**
- BBVA no proporciona API keys, créditos cloud ni GPU → priorizar modelos locales (Whisper local, LLM local vía Ollama) o cuentas propias.
- Se penalizan afirmaciones no verificadas, resultados fabricados y riesgos de privacidad o seguridad.

### Criterios de evaluación

| Criterio | Peso |
|---|---|
| IA / ML / analítica | 25% |
| Valor de producto y UX | 20% |
| Ingeniería y arquitectura | 20% |
| Datos sintéticos y evidencia | 15% |
| Responsible AI | 10% |
| Presentación y storytelling | 10% |

### Entregables

Demo funcional · Dataset sintético (datos, diccionario, supuestos, justificación de realismo) · Modelo/IA (modelos, prompts, features, evaluación) · Evidencia técnica (métricas, casos de prueba, limitaciones, trazabilidad) · Arquitectura (diagrama, componentes, APIs, seguridad) · Pitch final (problema, solución, valor, demo, roadmap).

---

## 1. Problemática

Pedro es un bodeguero (persona natural con negocio) que vende y compra mercadería todos los días sin llevar un registro ordenado. Mezcla el dinero de su casa con el de la tienda ("caja única") y anota sus ventas y fiados en un cuaderno físico. Se asume que Pedro tiene RUC 10, persona natural con negocio.

A fin de mes sufre porque no le alcanza para pagar a sus proveedores, ya sea porque se excedió en gastos personales o porque pidió mercadería de más sin prever sus vencimientos.

Cuando busca un préstamo formal, es rechazado porque no tiene información financiera sistematizada. Además, no entiende las ventajas de formalizarse y se guía por rumores de vecinos.

Esto lo empuja a préstamos informales ("gota a gota") con intereses impagables, que lo atrapan en un círculo difícil de sostener: **no le alcanza → pide prestado → paga cuotas diarias con la venta del día → vuelve a no alcanzarle**.

### Dolores principales

- No sabe cuánto tiene, cuánto gana ni cuánto debe.
- Mezcla el dinero personal con el del negocio.
- Pide mercadería sin prever cuándo y cuánto tendrá que pagar.
- Vende fiado sin control de quién le debe y desde cuándo.
- No accede a crédito formal y termina en préstamos informales caros.

---

## 2. Sustento

- **Más de 100 mil pymes cierran cada año en el Perú, y alrededor del 40% deja de operar por no poder sostener su flujo de caja.**
  Fuente: Cámara de Comercio de Lima, citada por Infobae (agosto 2025).
  <https://www.infobae.com/peru/2025/08/28/unas-100-mil-pymes-cierran-al-ano-el-40-deja-de-operar-por-problemas-de-flujo-de-caja/>

- **Solo 1 de cada 4 microempresas accede a crédito formal.** Cuando la información financiera no está estructurada, el riesgo percibido es mayor: las entidades suben tasas, restringen el crédito o hacen verificaciones adicionales (visitas presenciales, revisiones manuales) cuyo costo termina pagando el emprendedor.
  Fuente: Instituto Peruano de Economía (IPE), citado por Infobae (marzo 2026).
  <https://www.infobae.com/peru/2026/03/24/solo-1-de-cada-4-mypes-accede-a-credito-y-paga-mas-por-falta-de-informacion-financiera/>

- **Para un negocio sin historial en el banco, la evaluación de un crédito de capital de trabajo sigue siendo manual: un funcionario visita el negocio y levanta su información financiera (aprox. 1 hora) y luego necesita un día adicional para elaborar el informe que sustenta la decisión.** Si el emprendedor tiene las finanzas personales y del negocio mezcladas, o gasta de más, eso juega en contra de su evaluación.
  Fuente: conversaciones del equipo con ejecutivos de negocio de BBVA (fuente primaria).

- **Para clientes que ya cobran con canales del banco (POS, QR), existe precalificación digital basada en el volumen real de sus ventas.** Pero el banco solo ve lo que pasa por sus canales: las ventas en efectivo y los fiados de un bodeguero como Pedro le son invisibles. CajaClara genera justamente ese historial.
  Fuente: BBVA Perú, página de Soluciones de Cobro.
  <https://www.bbva.pe/pymes/productos/cobros/soluciones-de-cobro.html>

---

## 3. Objetivos

### Objetivo general

Ayudar a bodegas y pymes no bancarizadas a ordenar su flujo de caja, anticipar faltantes y adoptar hábitos financieros saludables, construyendo un historial que les permita acceder a crédito formal de forma más rápida.

### Alcance: solo las finanzas del negocio

- **CajaClara no registra ni analiza los gastos personales o de la casa** (comida del hogar, colegio, salud, servicios de la vivienda, etc.). La aplicación gestiona únicamente la caja del negocio.
- Lo único que se registra del lado personal es el **retiro personal**: la plata que Pedro saca de la caja del negocio para la casa ("saqué 50 para la casa"). Se trata como una salida de caja del negocio, sin detallar en qué se gasta después.
- Así, los retiros personales sí alimentan el resumen (F2), la proyección y el "disponible para gastar" (F3), las alertas (F6) y el score (F8), pero no existe un módulo, categoría ni tabla para gastos del hogar.
- Si Pedro intenta registrar un gasto de la casa pagado con plata de la casa (p. ej. "pagué el colegio de mi hijo"), el bot le explica que la app solo lleva el negocio y le pregunta si esa plata salió de la caja de la tienda; si es así, se anota como retiro personal.

### Los 3 estadios del usuario

**Estadio 1 — Pyme desorganizada ("no cliente" informal) · punto de partida**
- Pedro lleva todo en papel o de memoria.
- Mezcla sus gastos personales con los del negocio.
- Desconfía de la formalidad por desconocimiento.
- Cuando le falta caja, recurre a préstamos informales.

**Estadio 2 — Orden, hábitos y prevención · alcance del MVP**
- Con el gestor financiero, Pedro registra su negocio desde WhatsApp sin cambiar su rutina.
- Organiza su flujo de caja: sabe cuánto tiene, cuánto le deben y cuánto debe.
- Separa la plata de la casa de la del negocio y se pone un sueldo fijo.
- Recibe alertas antes de quedarse sin caja y decide con anticipación (cuánto pedir, a quién cobrar).
- Adopta hábitos financieros saludables medidos por su score de salud.
- Funcionalidades: F1 a F8.

**Estadio 3 — Formalización y acceso a crédito formal · roadmap**
- Al centralizar sus finanzas, Pedro tiene un historial ordenado de ventas (incluidas las de efectivo), gastos, fiados y pagos.
- Pedro da el paso a la formalidad: saca su RUC (p. ej. Nuevo RUS), abre una cuenta de negocio y empieza a usar los canales digitales del banco para personas naturales con negocio (ver sección 4).
- Con su consentimiento explícito, su historial ayuda al banco a evaluarlo más rápido: el asesor ya no tiene que levantar toda la información financiera desde cero.
- Pedro accede a un crédito formal a la medida de sus ciclos de caja, en lugar de un préstamo informal.

### Objetivos específicos del MVP (medibles)

1. Registrar movimientos por voz y texto con alta exactitud (meta: ≥90% de campos correctos y <15% de registros corregidos).
2. Proyectar el saldo diario a 30 días con menor error que un método simple (meta: MAE al menos 20% menor que el baseline).
3. Anticipar faltantes de caja con al menos 7 días de anticipación (meta: recall ≥80% y precision ≥70%).
4. Identificar fiados con alto riesgo de atraso mejor que el historial promedio del cliente (meta: AUC superior al baseline).
5. Explicar cada alerta en lenguaje simple con cifras 100% verificables contra los datos.
6. Medir la evolución de hábitos con un score de salud de caja explicable por subindicadores.

### Beneficio por actor

- **Para Pedro:** deja de quedarse sin caja, entiende su negocio y sale del círculo del préstamo informal.
- **Para el banco:** llega a un segmento hoy no bancarizado con información confiable, evalúa más rápido y a menor costo, y otorga créditos más sanos y alineados a la capacidad real de pago. Además, CajaClara funciona como puerta de entrada que lleva nuevos clientes, ya ordenados, hacia los canales y productos existentes para personas naturales con negocio.

---

## 4. Relación con soluciones existentes (Perfil Mi Negocio)

BBVA Perú ya ofrece el **Perfil Mi Negocio**: una sección dentro de la App BBVA que permite a clientes persona natural con negocio (PNN) gestionar sus finanzas personales y las de su negocio por separado.

- **Requisito:** estar identificado en el banco como PNN (con RUC) y tener la App BBVA.
- **Qué ofrece (según su página pública):** saldos y movimientos de cuentas, ventas hechas con POS del banco, transferencias, pago de servicios, tipo de cambio preferencial, apertura de cuenta corriente de negocio, Tarjeta Capital de Trabajo y acceso al Préstamo Digital Negocio (desde S/ 2,000 para PNN, con Cuenta Negocio o Cuenta Emprendedor activa).
- **Complementos:** Cobro al Toque (el celular como punto de venta) y precalificación a préstamos según el volumen de ventas por canales del banco.
- Fuentes: <https://www.bbva.pe/pymes/productos/canales/perfil-mi-negocio.html> · <https://www.bbva.pe/pymes/productos/financiamiento/prestamo-digital-negocio.html> · <https://www.bbva.pe/pymes/productos/cobros/soluciones-de-cobro.html>

### Por qué CajaClara no compite, sino que complementa

| | Perfil Mi Negocio | CajaClara |
|---|---|---|
| Usuario | PNN ya bancarizado y con RUC | Bodeguero informal, "no cliente", sin RUC ni cuenta de negocio |
| Qué ve | Movimientos bancarios y ventas por POS/QR | Ventas en efectivo, fiados, pedidos a crédito a proveedores, retiros personales |
| Cómo registra | Automático, por los canales del banco | Por WhatsApp (voz, texto, foto del cuaderno) |
| Enfoque | Operar y consultar | Ordenar, anticipar faltantes y crear hábitos (forecast, alertas, educación) |
| Rol en el recorrido | Destino (Estadio 3) | Puerta de entrada (Estadio 2) |

> Las brechas se identificaron solo con información pública; conviene validarlas con alguien que use la app con perfil PNN.

### Recorrido propuesto

1. **Estadio 1:** Pedro, informal, con cuaderno y efectivo.
2. **Estadio 2 (CajaClara):** ordena su caja, separa la plata personal y anticipa faltantes.
3. **Estadio 3 (roadmap):** se formaliza (RUC), abre una cuenta de negocio, usa los canales para PNN y, con su consentimiento, su historial de CajaClara apoya la evaluación de un crédito formal.

### Reglas para el pitch

- No presentar CajaClara como producto oficial ni usar marca, logos o pantallas del banco.
- Mencionar el Perfil Mi Negocio solo como destino natural del usuario; la integración queda como roadmap.

---

## 5. Funcionalidades

### F1. Registro multicanal por WhatsApp
*Historia: "Pedro vende y compra sin anotar".*
Principio: Pedro registra donde ya está (WhatsApp). Todo lo demás es automático o pasivo.

#### 1.1 Registro por voz
- **¿Cómo ingresa la data?** Nota de voz o texto por WhatsApp: "vendí dos cervezas", "saqué 50 para la casa", "compré 380 en abarrotes".
- **¿Cómo opera?**
  - API WhatsApp Business (webhook) recibe el mensaje.
  - Whisper transcribe el audio a texto.
  - LLM con function calling extrae: tipo (venta / compra / retiro personal), producto, cantidad, monto y método de pago.
  - Si no se dice el monto, se calcula con el catálogo de precios de la bodega (2 cervezas × S/ 6.50).
  - El JSON se valida con un esquema (pydantic); si falta un dato o la confianza es baja, el bot repregunta.
- **¿Qué se obtiene?** JSON que se guarda primero como `borradores` y, al confirmar, en `transacciones` (más `cuaderno_fiado`, `deudas` o `impuestos` según el tipo), con `canal` y `confianza_extraccion`.
- **¿Cómo se informa el cliente?** El bot confirma: "Anotado: 2 cervezas, S/ 13, efectivo ✅" con opción ✏️ Corregir.
- **¿Cómo se visualiza?** Recibe audio y texto de confirmación en WhatsApp.
- **Métricas:** WER de la transcripción; exactitud por campo del JSON sobre 100–150 frases de prueba (jerga, errores, montos ambiguos); % de registros corregidos por el usuario.

#### 1.2 Fotos del cuadernito (fiados)
- **¿Cómo ingresa la data?** Pedro toma foto de su cuaderno de fiados y la manda por WhatsApp.
- **¿Cómo opera?** Visión/OCR extrae las líneas manuscritas → LLM las estructura (vecino, productos, monto, fecha) → pide confirmación antes de guardar en `cuaderno_fiado`.
- **¿Qué se obtiene?** Historial de fiados (deudas de clientes) digitalizado.
- **¿Cómo se informa el cliente?** El bot repite lo que entendió y pide "Sí / No" para confirmar.
- **¿Cómo se visualiza?** Lista de fiados pendientes en el dashboard, con alertas de mora.
- **¿Cómo la consume?** Revisa el saldo pendiente desde el dashboard o preguntando al chat.
- **Métricas:** exactitud por campo del OCR + estructuración sobre fotos de prueba.

#### 1.3 Billeteras digitales
- **¿Cómo ingresa?** Webhook/API de la billetera, o captura de pantalla reenviada si no hay integración directa.
- **¿Cómo opera?** El dato ya viene estructurado del proveedor; se normaliza al esquema propio (`billeteras_digitales`). Si llega por captura de pantalla, se extrae con visión y se pide confirmación.
- **¿Qué se obtiene?** Ingresos y egresos digitales verificados, sin intervención manual.
- **¿Cómo se informa el cliente?** Por API: no requiere confirmación (es dato oficial de la transacción). Por captura: confirmación "Sí / No".
- **¿Cómo se visualiza?** Integrado directamente al flujo de caja del dashboard.
- **¿Cómo la consume?** De forma pasiva: ya está reflejado en su score y su caja sin que haga nada.

#### 1.4 Pagos de impuestos
- **¿Cómo ingresa?** Foto del comprobante, o respuesta a menú de botones: "¿Pagaste tu RUS? Sí / No, ¿cuánto?".
- **¿Cómo opera?** Visión extrae monto y periodo, o se registra directo la respuesta del botón → tabla `impuestos`.
- **¿Qué se obtiene?** Historial de cumplimiento tributario.
- **¿Cómo se informa el cliente?** Confirmación del registro + recordatorio proactivo antes del vencimiento.
- **¿Cómo se visualiza?** Semáforo "al día / vencido" en el dashboard.
- **¿Cómo la consume?** Recibe alerta preventiva por WhatsApp antes de la fecha límite.

#### 1.5 Préstamos de proveedor (pedidos a crédito)
- **¿Cómo ingresa?** Chat guiado paso a paso (producto, cantidad, proveedor, plazo), o foto de factura/guía. También por voz: "pedí 2 400 a Andina para pagar el 30".
- **¿Cómo opera?** El bot arma el registro estructurado en `deudas` (`tipo = proveedor`) y calcula plazo y monto pendiente. Al registrarlo, ejecuta el chequeo antes del pedido (ver F4).
- **Préstamos de dinero:** la misma tabla `deudas` registra préstamos informales, familiares o de entidades ("me prestaron 1 000, pago 40 diarios"), con monto recibido, total a pagar y cuotas. Así el forecast incluye las cuotas y el asistente muestra el costo real del préstamo.
- **¿Qué se obtiene?** Trazabilidad de deudas con proveedores y su cumplimiento.
- **¿Cómo se informa el cliente?** Confirmación del registro + recordatorio antes del vencimiento del plazo pactado.
- **¿Cómo se visualiza?** Lista de deudas vigentes y vencidas en el dashboard, con impacto en el score.
- **¿Cómo la consume?** Consulta "¿cuánto debo a proveedores?" por chat o ve el detalle en el dashboard.

#### 1.6 Consulta del estado ("¿cómo va mi caja?")
- **¿Cómo ingresa?** Pregunta en lenguaje natural por chat (texto o voz).
- **¿Cómo opera?** LLM con function calling consulta las tablas ya pobladas y los motores de cálculo (F2, F3, F4) y arma la respuesta.
- **¿Qué se obtiene?** Resumen conversacional del estado financiero actual.
- **¿Cómo se informa el cliente?** Respuesta directa en el chat, en lenguaje simple.
- **¿Cómo se visualiza?** También disponible como resumen fijo en la pantalla principal del dashboard.
- **¿Cómo la consume?** Activamente, cuando él pregunta. Es la única interacción que el bodeguero inicia; el resto es automático o pasivo.

> **Nota para el hackathon:** simular WhatsApp con el sandbox de Twilio o un chat propio; Whisper local (faster-whisper); voces y fotos del equipo con datos ficticios.

---

### F2. Resumen financiero
*Historia: "Pedro no sabe cuánto tiene ni cuánto gana".*

- **Objetivo:** mostrar una visión general de la situación económica del negocio.
- **Ingreso de información:**
  - Registro de ingresos y egresos mediante F1 (voz, cuadernito, billeteras, impuestos, préstamos de proveedor).
  - Cada registro guarda fecha, monto, concepto, categoría y método de pago.
  - La información registrada alimenta automáticamente los demás módulos.
- **Datos que se deben visualizar:**
  - Saldo disponible actual (caja del negocio, separada de la plata de la casa).
  - Ingresos del mes.
  - Egresos del mes.
  - Ganancia o pérdida neta = ventas − costo de mercadería vendida − gastos del negocio (si no hay costos, se muestra como "aproximada" con rango).
  - Retiros personales del mes vs sueldo fijo.
  - Dinero pendiente de cobro (fiados).
  - Pagos pendientes (proveedores e impuestos).
- **¿Cómo opera?** Agregaciones determinísticas sobre las tablas (sin IA).
- **Visualización sugerida:** tarjetas de indicadores financieros con variación respecto al periodo anterior (▲▼ % vs mes pasado).
- **¿Cómo lo consume Pedro?** Pantalla de inicio de la app; resumen por chat ("¿cómo va mi caja?") y resumen semanal opcional por WhatsApp.

---

### F3. Proyección de flujo de caja (forecast) y "disponible para gastar"
*Historia: "a fin de mes no puede pagar lo que pidió".*

- **Objetivo:** proyectar el comportamiento del dinero disponible en el negocio.
- **Entradas:**
  - Transacciones recurrentes y ventas históricas (día de la semana, quincena, estacionalidad).
  - Fiados por cobrar, ponderados por su probabilidad de pago.
  - Préstamos de proveedor por pagar.
  - Impuestos y gastos fijos (luz, alquiler).
- **Salidas:**
  - Ingresos frente a egresos.
  - Saldo diario proyectado para los próximos 30 días (o X semanas).
  - Rangos pesimista / esperado / optimista (banda de incertidumbre).
  - Saldo mínimo operativo.
  - Comparación entre saldo actual y saldo futuro.
  - **"Disponible para gastar"** = saldo actual + cobros esperados − pagos comprometidos hasta el próximo vencimiento grande − mínimo operativo − reserva de impuestos.
    Ej.: *"Hoy puedes sacar hasta S/ 120 para la casa sin arriesgar el pago del 30/11"*.
  - Aviso de faltantes de caja.
  - Ajuste manual de partidas por el usuario.
- **Técnica:** baseline naive estacional vs LightGBM con regresión por cuantiles.
- **Visualización sugerida:** gráfico de líneas con saldo proyectado, mínimo operativo y banda de incertidumbre; días con posible déficit resaltados.
- **Métricas:** MAE, MAPE y cobertura del intervalo vs baseline.

---

### F4. Cuentas por cobrar (fiados) y por pagar (proveedores e impuestos)
*Historia: "vende fiado y pide a crédito sin control".*

- **Objetivo:** controlar las obligaciones pendientes y el dinero que todavía no ingresa al negocio.
- **Cuentas por cobrar (cuaderno de fiados):**
  - Total pendiente de cobro.
  - Fiados vencidos (más de X días).
  - Próximos cobros esperados.
  - Vecinos con mayor riesgo de retraso (baseline: atraso histórico; modelo: clasificador).
  - Acción de un toque: "Enviar recordatorio amable a la Sra. Carmen" (plantilla de WhatsApp).
- **Cuentas por pagar (préstamos de proveedor e impuestos):**
  - Total pendiente de pago.
  - Próximos vencimientos.
  - Pagos atrasados.
  - Principales proveedores (mayor deuda).
  - Estado de impuestos: al día / vencido.
- **Chequeo antes del pedido:** al registrar "pedí 2 400 a Andina para el 30", calcula al instante si podrá pagar y sugiere un monto, pagar en 2 partes o cobrar fiados.
- **Visualización sugerida:** tablas ordenadas por fecha de vencimiento, estado y monto; indicadores visuales para diferenciar pendiente, próximo a vencer y vencido.
- **Métricas:** AUC, F1 y calibración del riesgo de atraso vs baseline.

---

### F5. Análisis de ingresos y egresos
*Historia: "Pedro no sabe en qué se le va la plata".*

- **Objetivo:** ayudar al usuario a comprender de dónde viene su dinero y en qué lo está gastando.
- **Contenido:**
  - Ingresos por categoría de producto (bebidas, abarrotes, limpieza…) y por método de pago (efectivo vs billetera digital).
  - Productos que más dejan (rotación × margen).
  - Gastos por categoría (mercadería, servicios, impuestos, retiros personales).
  - Principales clientes que generan ingresos (en bodega aplica a clientes de fiado; la mayoría de ventas son anónimas).
  - Principales proveedores.
  - Evolución de los gastos.
  - Comparación de ingresos y egresos entre periodos (mes anterior, mismo mes del año pasado).
  - Comparación anónima con bodegas similares (rubro, tamaño, zona). Ej.: *"Tus retiros personales son 35% de tus ventas; en bodegas parecidas, 22%"*.
- **Visualización sugerida:** gráficos de barras, gráficos circulares y comparaciones temporales; filtros por fechas y categorías.

---

### F6. Alertas y nudges (proactivo)
*Historia: "Pedro se entera del problema cuando ya pasó".*

- **Objetivo:** identificar riesgos financieros y notificarlos al usuario antes de que se conviertan en problemas.
- **Fuente de información:** ingresos, egresos, fiados, préstamos de proveedor, impuestos, vencimientos y proyecciones de caja (F1–F4). Después de cada movimiento registrado se recalcula la proyección y se evalúan las reglas.
- **Información que debe procesar:**
  - Posibles déficits de caja.
  - Gastos inusuales o caída de ingresos.
  - Pagos próximos a vencer (proveedores e impuestos).
  - Fiados vencidos.
  - Clientes con retrasos frecuentes.
  - Retiros personales por encima del sueldo o del disponible.
- **Disparadores en orden de prioridad:**
  1. Faltante de caja proyectado: *"El 30/11 te faltarían S/ 650 para pagar a Andina"*.
  2. Pedido mayor de lo que puede pagar (al registrarlo): *"Este pedido es S/ 400 más de lo que vendes en 2 semanas"*.
  3. Retiro personal por encima del sueldo o del disponible: *"Con este retiro ya sacaste S/ 1 900 este mes"*.
  4. Obligación próxima (3 días antes): *"El martes vence tu pago a Andina"* / *"Tu RUS vence el viernes"*.
  5. Gasto inusual o caída de ventas: *"Vendiste 25% menos que un sábado normal"*.
  6. Fiado vencido o cliente con retrasos frecuentes: *"Don Luis te debe S/ 95 hace 12 días"*.
  7. Meta lograda o racha: *"4 semanas seguidas anotando todo"*.
  8. Resumen semanal (opcional).
- **Información que debe mostrar cada alerta:** tipo de alerta; fecha en la que ocurrirá el problema; monto involucrado; nivel de riesgo o probabilidad; causas que originan la alerta; posible acción para reducir el riesgo (un botón).
- **Formato:** un insight + un motivo + un botón ("Ajustar pedido", "Recordar a Carmen", "Ver por qué").
- **Canales:** WhatsApp (principal), app y email.
- **Límites:** máximo 2 alertas por día; horario silencioso; nunca enlaces que pidan credenciales.
- **Métricas:** precision y recall de la alerta de faltante; días de anticipación; % de alertas con acción tomada.

---

### F7. Asistente financiero (chatbot)
*Historia: "Pedro no tiene a quién preguntar".*

- **¿Dónde vive?** En el mismo WhatsApp donde Pedro registra (incluye la consulta "¿cómo va mi caja?" de F1.6).
- **¿Qué hace?**
  - Explica el score, los gráficos, las alertas y las variaciones.
  - Simula escenarios: *"¿qué pasa si pago a 30 días?"*, *"¿y si pago a Andina en 2 partes?"*, *"¿y si pido solo 1 800?"*.
  - Enseña conceptos en contexto (qué es TCEA, por qué separar la plata de la casa).
  - Ayuda a crear metas y alertas.
  - Ante *"¿pido un préstamo?"*: muestra el costo real del préstamo informal y primero las alternativas propias.
- **¿Cómo opera?**
  - No calcula cifras: los números salen de motores determinísticos (F2, F3, F4) vía function calling.
  - Verificación automática de que cada número de la respuesta existe en los datos.
  - Fallback por plantilla si el LLM falla.
- **Fuera de alcance:** recomendar inversiones, acciones, cripto o un producto de crédito o entidad específica; opinión tributaria o legal más allá de información general.
- **Confianza:** siempre ofrece pasar a una persona; registra las conversaciones (trazabilidad).
- **Métricas:** groundedness (% de cifras verificables); % de rechazos correctos en casos adversos; utilidad percibida.

---

### F8. Plan de salud y score (hitos y metas)
*Historia: "Pedro no accede a crédito formal porque sus finanzas no están ordenadas".*

- **Metas plantilla en orden:**
  1. **Organizar:** anotar todo durante 30 días.
  2. **Estabilizar:** separar la plata de la casa y ponerse un sueldo fijo.
  3. **Proteger:** colchón de caja y apartar un % de cada venta para impuestos y pedidos.
  4. **Crecer responsablemente:** historial listo.
- **Score de salud (0–100), con un subindicador por regla:**
  - Constancia de registro (días anotados).
  - Separación personal/negocio (retiros vs sueldo fijo).
  - Colchón de caja (días de gastos cubiertos).
  - Pedidos acordes a las ventas y préstamos de proveedor pagados a tiempo.
  - Cobro de fiados a tiempo.
  - Impuestos al día.
  - Meses sin faltantes.
- **Mecanismos de compromiso:** cada meta puede activar una regla automática (ej.: *"aparta 3% de cada cobro"* o *"S/ 1 de cada S/ 10 vendidos para el pedido del mes"*); recordatorios específicos, progreso y rachas.
- **Puente al crédito formal (roadmap):** con consentimiento explícito (desactivado por defecto), el historial puede compartirse para una evaluación de crédito. La app no ofrece ni otorga créditos.

---

## 6. Principios de diseño educativo (transversales)

- **Justo a tiempo:** cada insight trae una microexplicación (30–60 s) y una sola acción sugerida.
- **Simplicidad:** 5–7 reglas prácticas, cada una medida por un subindicador del score (separar dinero personal y del negocio, pagarse un sueldo fijo, reservar impuestos al cobrar).
- **Mecanismos de compromiso:** metas conectadas a reglas automáticas que el dueño activa (ej.: apartar 3% de cada cobro).
- **Atención y visibilidad:** alertas proactivas por eventos, sin depender de que el dueño abra el dashboard.
- **Personalización:** comparación anónima con negocios similares (rubro, tamaño, región).
- **Refuerzo positivo:** celebrar hitos y rachas con un diseño sobrio, no infantil.
- **Menos fricción:** acciones de un toque desde la alerta o desde WhatsApp.
- **Confianza:** cada número muestra de dónde sale y su nivel de seguridad; la decisión final siempre es del dueño.

---

## 7. Prioridad para el MVP (2 días)

**Debe estar en la demo**
- F1.1 voz/texto (Whisper local en chat simulado), F1.5 préstamos de proveedor, F1.6 consulta del estado
- F2
- F3
- F4
- F6 (prioridades 1 a 4)

**Versión simplificada**
- F1.2 fotos del cuadernito (2–3 fotos de prueba)
- F1.4 impuestos (menú de botones, sin foto)
- F7 (3–4 intenciones + casos adversos)
- F8 (score con 3 subindicadores)
- F5 (2 gráficos)

**Fuera de alcance (no se incluirá)**
- Registro y análisis de gastos personales o de la casa (ver sección 3, "Alcance"); solo se registra el retiro personal desde la caja del negocio.

**Roadmap**
- WhatsApp Business oficial
- Integración real con billeteras digitales (F1.3)
- Foto de comprobantes de impuestos y facturas
- Comparación real con pares
- Compartir historial (con consentimiento) para evaluación de crédito
- Guía de formalización (RUC, Nuevo RUS) y paso a cuenta de negocio y canales digitales para PNN

---

## 8. Modelo de datos

Entidad central: la bodega/empresa. Todas las tablas se relacionan con ella.

- **Esquema formal (DBML):** [modelo_datos.dbml](modelo_datos.dbml) — se visualiza pegándolo en <https://dbdiagram.io>.
- **Diccionario de datos:** [diccionario_datos.md](diccionario_datos.md) — campos, tipos, ejemplos, uso en modelos y cómo se registra cada caso.

| Tabla | Tipo | Contenido |
|---|---|---|
| `rubros` | Maestra | Rubro del negocio (bodega, restaurante, taller, distribuidora) |
| `empresas` | Maestra | Pyme ficticia: rubro, tamaño, zona, teléfono de WhatsApp (ficticio), saldo inicial, mínimo operativo |
| `preferencias_alertas` | Maestra | Canales, máximo de alertas por día y horario silencioso |
| `categorias` | Maestra | Bebidas, abarrotes, servicios, impuestos, retiro personal, etc. (no hay categorías de gastos del hogar; ver §3 "Alcance") |
| `productos` | Maestra | Catálogo: precio, costo, categoría y alias (para calcular montos y margen) |
| `clientes` | Maestra | Vecinos/clientes de fiado con teléfono ficticio; `perfil_pago` oculto (no es feature) |
| `proveedores` | Maestra | Proveedores y plazo de pago acordado |
| `borradores` | Ingesta | Lo que entendió la IA (transcripción, propuesta, confianza, correcciones) antes de que el usuario confirme |
| `transacciones` | Transaccional | **Única tabla** de movimientos: ventas, compras, gastos, retiros, cobros y pagos. Campos `tipo`, `metodo_pago`, `afecta_caja`, `canal`, `confianza_extraccion` |
| `detalle_transaccion` | Transaccional | Productos de cada venta o compra, con el costo del momento |
| `cuaderno_fiado` | Transaccional | Fiados digitalizados: cliente, monto, fecha, fecha de compromiso y de pago |
| `deudas` | Transaccional | Lo que el negocio debe: pedidos a crédito a proveedores **y** préstamos de dinero (gota a gota, familiar, entidad), con cuotas |
| `billeteras_digitales` | Transaccional | Movimientos digitales normalizados (sin duplicados por `operacion_id`) |
| `impuestos` | Transaccional | Periodo, monto, vencimiento y fecha de pago |
| `movimientos_programados` | Planificación | Ingresos y egresos recurrentes del negocio (luz, alquiler del local) y el **sueldo fijo** del dueño (`es_sueldo`) |
| `reglas_meta` | Planificación | Metas y reglas automáticas activadas por el usuario |
| `forecast_ajustes` | Planificación | Ajustes manuales de partidas ("este mes no pago alquiler") |
| `alertas` | Interacción | Alertas con causas, entidad que la causa, acción sugerida y acción tomada |
| `conversaciones` | Interacción | Mensajes del asistente con intención, herramientas usadas y verificación de cifras |
| `consentimientos` | Interacción | Permiso para compartir el historial (desactivado por defecto) |
| `saldo_diario` | Etiqueta | Saldo de cierre por día + etiqueta `deficit_14d` (target de la alerta) |
| `eventos` | Etiqueta | Shocks insertados en el dataset sintético (ground truth) |
| `predicciones_saldo` | Resultado | Salidas del forecast (p10/p50/p90) con versión de modelo |
| `predicciones_fiado` | Resultado | Riesgo de atraso y probabilidad de pago de cada fiado |
| `score_salud` | Resultado | Score mensual y subindicadores |

### Decisiones de diseño

- **Una sola tabla de movimientos.** Todo pasa por `transacciones`; las tablas de fiados, deudas, impuestos, billeteras y recurrentes se enlazan por FK.
- **Lo fiado o pedido a crédito no mueve caja.** `metodo_pago = credito` → `afecta_caja = false`. Saldo de caja = saldo inicial + Σ movimientos con `afecta_caja`.
- **Nada calculado se guarda.** Saldo, monto pendiente, días de atraso y estados (por vencer, vencido, al día) salen de vistas a una fecha de corte; así no se desfasan ni filtran información del futuro.
- **El sueldo vive en un solo lugar:** `movimientos_programados` con `es_sueldo = true`, con historial por `fecha_inicio` / `fecha_fin`. El forecast lo proyecta y la alerta de retiro excesivo lo compara.
- **Préstamos de dinero incluidos.** `deudas` guarda lo recibido y lo que se devolverá, para mostrar el costo real del préstamo informal con los datos del propio usuario.
- **Nada se borra:** se anula (`anulada = true`), por trazabilidad.

### Reglas para evitar fuga de datos

- En una `fecha_corte`, solo se usan registros guardados (`creado_en`) y pagos y atrasos ocurridos **antes** de esa fecha.
- `pago_tardio`, `deficit_14d` y `eventos` son **solo etiquetas**, nunca features.
- `perfil_pago` del cliente nunca entra al modelo; se infiere del historial.
- `dias_atraso`, `monto_pendiente` y los estados se calculan a la fecha de corte, nunca se leen de una columna guardada.
- Split temporal (entrenar con los primeros meses, evaluar con los últimos) y por empresa.

---

## 9. Storytelling para la demo (Pedro)

1. **Inicio:** Pedro ve la caja de su negocio (S/ 2 340), separada de la plata de su casa, y una alerta: "El 30/11 no te alcanzará".
2. **Anotar:** registra por voz "vendí dos cervezas" y el bot confirma.
3. **Alerta y causas:** el 30/11 le faltarán S/ 650 para pagar S/ 2 400 a Distribuidora Andina. Causas: retiró S/ 700 más de lo usual para la casa, pidió S/ 400 más de lo que vende y tiene S/ 310 en fiados sin cobrar. Sin esas tres, cerraría con S/ 760.
4. **Antes de pedir:** simula pedir menos, pagar en 2 partes o cobrar fiados, y ve cómo cambia su caja.
5. **Costo del préstamo informal:** ejemplo ilustrativo de recibir S/ 1 000 y devolver S/ 1 200 en 30 días; primero se muestran las alternativas propias.
6. **Mi progreso:** su score de salud sube y construye un historial que, con su permiso, podría servir para acceder a un crédito formal.

> Todos los nombres, montos y negocios son ficticios.