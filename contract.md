# TuCaserito — Contratos de API (v1)

> Contratos para que cada parte del equipo trabaje en paralelo (backend, ML, GenAI, front y bot).
> Implementación sugerida: FastAPI + pydantic. Todos los datos son sintéticos.

---

## 0. Convenciones generales

| Tema | Regla |
|---|---|
| Base URL | `/api/v1` |
| Formato | JSON, UTF-8 |
| Autenticación (demo) | Header `X-API-Key: <clave>` leída desde `.env`. Nunca en el código ni en el repo |
| IDs | Strings con prefijo: `EMP-0001`, `MOV-000123`, `FIA-0045`, `PED-0012`, `ALR-0007`, `BOR-…` (borrador) |
| Dinero | Número decimal en soles con 2 decimales (`2340.00`). Campo `moneda` = `"PEN"` por defecto |
| Fechas | ISO 8601. Fecha: `2026-11-30`. Fecha-hora: `2026-11-14T10:42:00-05:00` (zona America/Lima) |
| Paginación | `?limit=50&cursor=<token>` → respuesta con `next_cursor` (null si no hay más) |
| Idempotencia | Los `POST` que crean registros aceptan header `Idempotency-Key` (evita duplicar si WhatsApp reenvía el mensaje) |
| Trazabilidad | Toda respuesta con salida de un modelo incluye el bloque `meta` (ver abajo) |
| Explicabilidad | Toda recomendación incluye `fundamento`, `limites` y `confianza` |

### Bloque `meta` (en respuestas de modelos)

```json
"meta": {
  "request_id": "req_8f3a1c",
  "generado_en": "2026-11-14T10:42:05-05:00",
  "modelo": "forecast-lgbm-quantile",
  "modelo_version": "0.3.1",
  "prompt_version": null,
  "fallback_usado": false,
  "latencia_ms": 184
}
```

### Formato de error

```json
{
  "error": {
    "codigo": "VALIDACION",
    "mensaje": "El campo 'monto' debe ser mayor que 0.",
    "detalles": [{ "campo": "monto", "problema": "must be > 0" }],
    "request_id": "req_8f3a1c"
  }
}
```

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 400 | `VALIDACION` | Payload inválido |
| 401 | `NO_AUTORIZADO` | Falta o es inválida la API key |
| 404 | `NO_ENCONTRADO` | Empresa, borrador o registro inexistente |
| 409 | `CONFLICTO` | Borrador ya confirmado / idempotency key repetida con otro payload |
| 422 | `NO_INTERPRETABLE` | El LLM/OCR no pudo extraer un movimiento |
| 503 | `SERVICIO_NO_DISPONIBLE` | LLM, Whisper o R2 (almacenamiento de media) caídos o sin configurar (se responde con fallback cuando existe) |

### Enums compartidos

```text
tipo_movimiento : venta | cobro_fiado | prestamo_recibido | otro_ingreso                                        (ingresos)
                | compra | gasto_negocio | retiro_personal | pago_proveedor | pago_prestamo | pago_impuesto   (egresos)
metodo_pago     : efectivo | billetera_digital | transferencia | tarjeta | credito   (credito = fiado o pedido a crédito: no mueve caja)
tipo_deuda      : proveedor | prestamo_informal | familiar | entidad_financiera
canal           : voz | texto | foto | billetera_api | manual
estado_cuenta   : pendiente | por_vencer | vencido | pagado
nivel_riesgo    : bajo | medio | alto
estado_caja     : te_alcanza | justo | no_te_alcanza
tipo_alerta     : faltante_caja | pedido_excesivo | retiro_excesivo | obligacion_proxima | gasto_inusual | caida_ventas | fiado_vencido | meta_lograda | resumen_semanal
```

---

## 1. F1 — Ingesta (registro multicanal)

Flujo: **interpretar → (aclarar) → confirmar → guardar**. Nada se guarda sin confirmación, salvo `billetera_api`.

### 1.0 `POST /media/subidas` (subir audio o foto a Cloudflare R2)
Pide una **URL prefirmada** para subir el archivo directo a R2 (el archivo no pasa por el backend). Requiere `X-API-Key`.

Flujo de 3 pasos:
1. `POST /media/subidas` → devuelve `upload_url` y el `media_url` definitivo (`r2://…`).
2. El cliente hace `PUT` del archivo a `upload_url` con el header `Content-Type` exacto de `headers_requeridos`
   (sin `X-API-Key` ni otros headers; R2 responde `200` sin cuerpo).
3. Llama a `/ingesta/interpretar` (canal `voz`), `/ingesta/cuaderno` o `/webhooks/whatsapp` con `media_url: "r2://…"`.

**Request**
```json
{ "empresa_id": "EMP-0001", "tipo": "audio", "content_type": "audio/ogg", "tamano_bytes": 48213 }
```
- `tipo`: `audio | imagen`. `content_type` permitido por tipo: audio → `audio/ogg`, `audio/webm`, `audio/mpeg`, `audio/mp4`,
  `audio/wav`; imagen → `image/jpeg`, `image/png`, `image/webp`. Los parámetros (`audio/webm;codecs=opus`) se ignoran:
  usa el `Content-Type` que devuelve `headers_requeridos`.
- `tamano_bytes` máximo: 10 MB (audio) y 8 MB (imagen); el valor real se devuelve en `tamano_max_bytes`.

**Response 201**
```json
{
  "media_url": "r2://empresas/EMP-0001/audios/2026/11/0b7c9f0e-6a41-4c52-9d2b-3f1e8a7d5c10.ogg",
  "upload_url": "https://<cuenta>.r2.cloudflarestorage.com/cajaclara-media/empresas/EMP-0001/audios/2026/11/0b7c….ogg?X-Amz-Algorithm=…&X-Amz-Signature=…",
  "metodo": "PUT",
  "headers_requeridos": { "Content-Type": "audio/ogg" },
  "expira_en": "2026-11-14T10:52:00-05:00",
  "tamano_max_bytes": 10485760
}
```
- La URL vale 10 minutos (`R2_PRESIGN_TTL_S`). Si expira, se pide otra.
- El backend solo lee `r2://` con clave bajo `empresas/{empresa_id}/…` de la empresa que consulta; verifica tipo y tamaño
  del objeto antes de descargarlo y borra el temporal tras procesar.

**Errores**: `400 VALIDACION` (tipo, `content_type` o tamaño no permitidos; campos faltantes), `401`, `404 NO_ENCONTRADO`
(empresa), `503 SERVICIO_NO_DISPONIBLE` (R2 sin configurar o caído).

**Configuración del bucket (una vez, en Cloudflare)**
- CORS del bucket: permitir `PUT` desde `http://localhost:5173` (y el dominio de la demo) con `AllowedHeaders: ["Content-Type"]`.
  Ejemplo: `[{"AllowedOrigins":["http://localhost:5173"],"AllowedMethods":["PUT"],"AllowedHeaders":["Content-Type"],"MaxAgeSeconds":3600}]`.
- Recomendado: regla de lifecycle que borre los objetos tras N días (p. ej. 30 en `empresas/`); los audios son datos
  personales y el backend no los necesita después de transcribir.

### 1.1 `POST /webhooks/whatsapp`
Recibe mensajes del proveedor (sandbox de Twilio o chat simulado). Uso interno del bot.

**Request** (formato normalizado por el adaptador del proveedor)
```json
{
  "telefono_hash": "a91f…",
  "empresa_id": "EMP-0001",
  "tipo": "audio",
  "texto": null,
  "media_url": "file://data/audios/demo_001.ogg",
  "recibido_en": "2026-11-14T10:42:00-05:00",
  "mensaje_id": "wamid.123"
}
```
- `tipo`: `texto | audio | imagen | boton`
- Nunca se guarda el número real: solo `telefono_hash`.
- `media_url`: `r2://…` (devuelto por `POST /media/subidas`) o, solo para demo/tests, `file://data/…` y `demo://…`.
  Nunca se aceptan `http(s)://`.

**Response 200**
```json
{
  "respuesta_texto": "Anotado: 2 cervezas, S/ 13.00, efectivo ✅ ¿Correcto?",
  "botones": [
    { "id": "confirmar:BOR-7781", "texto": "✅ Correcto" },
    { "id": "corregir:BOR-7781", "texto": "✏️ Corregir" }
  ],
  "respuesta_audio_url": null
}
```

### 1.2 `POST /ingesta/interpretar`
Convierte texto, audio o foto en un **borrador** de movimiento.

**Request**
```json
{
  "empresa_id": "EMP-0001",
  "canal": "voz",
  "texto": null,
  "media_url": "file://data/audios/demo_001.ogg"
}
```

- `media_url` (canal `voz`): `r2://…` (§1.0) o, solo para demo, `file://data/…` / `demo://…`. Si no se encuentra el
  archivo y no viene `texto` → `422 NO_INTERPRETABLE`; si es de otra empresa o excede tipo/tamaño → `400 VALIDACION`.

**Response 200**
```json
{
  "borrador_id": "BOR-7781",
  "transcripcion": "vendí dos cervezas",
  "movimiento_propuesto": {
    "tipo": "venta",
    "items": [
      { "producto_id": "PRD-0031", "producto": "Cerveza 620 ml", "cantidad": 2, "precio_unitario": 6.50, "subtotal": 13.00 }
    ],
    "monto": 13.00,
    "moneda": "PEN",
    "metodo_pago": "efectivo",
    "contraparte": null,
    "fecha_hora": "2026-11-14T10:42:00-05:00",
    "fecha_vencimiento": null
  },
  "origen_monto": "catalogo",
  "confianza": 0.93,
  "campos_faltantes": [],
  "pregunta_aclaratoria": null,
  "meta": { "modelo": "whisper-small + llm-extractor", "modelo_version": "0.2.0", "prompt_version": "extractor-v3", "fallback_usado": false }
}
```
- `origen_monto`: `dicho_por_usuario | catalogo | estimado`
- El monto es determinístico: si el usuario dijo cifras de dinero ("2400", "2 400", "2,400", "dos mil cuatrocientos"),
  el monto es una de ellas (nunca el día de una fecha ni un precio del catálogo); si no dijo ninguna, sale del catálogo
  o queda en `campos_faltantes`. El LLM nunca pone un monto que no esté en el texto.
- Si `confianza < 0.75` o hay `campos_faltantes`, `pregunta_aclaratoria` trae el texto a enviar (ej.: *"¿Fue en efectivo o por billetera?"*).
- Ejemplos de interpretación esperada:

| Frase | `tipo` | Destino al confirmar |
|---|---|---|
| "vendí dos cervezas" | `venta` | `transacciones` |
| "saqué 50 para la casa" | `retiro_personal` | `transacciones` |
| "pagué el colegio de mi hijo" | — | No se registra: el bot explica que la app solo lleva el negocio y pregunta si la plata salió de la caja de la tienda; si es así, se anota como `retiro_personal` |
| "le fié a la señora Carmen 2 panes y una leche" | `venta` + `metodo_pago = credito` | `transacciones` (`afecta_caja = false`) + `cuaderno_fiado` |
| "la señora Carmen me pagó 50" | `cobro_fiado` | `transacciones` (con `fiado_id`) |
| "pedí 2 400 a Andina para pagar el 30" | `compra` + `metodo_pago = credito` | `transacciones` (`afecta_caja = false`) + `deudas` con `tipo = proveedor` (+ dispara chequeo de pedido, §4.5) |
| "me prestaron 1 000, pago 40 diarios" | `prestamo_recibido` | `transacciones` + `deudas` con `tipo = prestamo_informal` |
| "pagué mi RUS, 20 soles" | `pago_impuesto` | `transacciones` + `impuestos` |

Tablas y campos: [modelo_datos.dbml](modelo_datos.dbml) · [diccionario_datos.md](diccionario_datos.md) (§4, cómo se registra cada caso).

### 1.3 `POST /ingesta/confirmar`

**Request**
```json
{
  "borrador_id": "BOR-7781",
  "confirmado": true,
  "correcciones": { "metodo_pago": "billetera_digital" }
}
```

**Response 201**
```json
{
  "movimiento_id": "MOV-000123",
  "registros_creados": [
    { "tabla": "transacciones", "id": "MOV-000123" }
  ],
  "alertas_disparadas": [],
  "saldo_caja_negocio": 2353.00
}
```
- Si `confirmado = false` sin correcciones, el borrador se descarta (`204`).
- Con `confirmado = true`, las correcciones hechas conversando (§1.7 o WhatsApp) ya guardadas en el borrador se aplican
  también; las del request tienen prioridad.
- Tras guardar, se recalcula el forecast y se evalúan alertas (§6). Las alertas nuevas vuelven en `alertas_disparadas`.

### 1.4 `POST /ingesta/cuaderno` (foto del cuaderno de fiados)

**Request**
```json
{ "empresa_id": "EMP-0001", "media_url": "r2://empresas/EMP-0001/fotos/2026/11/9a1c….jpg" }
```
- `media_url`: `r2://…` (§1.0, `tipo: "imagen"`) o, solo para demo, `file://data/fotos/…` / `demo://fotos/…`.
  La foto se lee con un modelo de visión (VLM) vía OpenRouter (`VLM_MODEL`); la imagen viaja al proveedor como data
  URL base64. Si el VLM no está disponible (sin key, timeout, error o salida inválida) se usa un fixture por nombre
  de foto (`cuaderno_01..03`, `meta.fallback_usado = true`) o, si la foto es desconocida, `fiados_propuestos: []`.
  Las líneas tachadas (ya pagadas) no se proponen: se cuentan en `lineas_tachadas`. Objeto inexistente → `422`;
  ajeno/tipo/tamaño → `400`.

**Response 200**
```json
{
  "borrador_id": "BOR-7790",
  "fiados_propuestos": [
    { "cliente": "Vecina Rosa", "detalle": "pan y huevos", "monto": 12.50, "fecha": "2026-11-12", "confianza": 0.85,
      "cliente_id": "CLI-0110", "cliente_nuevo": false, "posible_duplicado": false },
    { "cliente": "Marcos", "detalle": "fideos y atún", "monto": 8.00, "fecha": "2026-11-10", "confianza": 0.85,
      "cliente_id": null, "cliente_nuevo": true, "posible_duplicado": null }
  ],
  "lineas_no_legibles": 0,
  "lineas_tachadas": 1,
  "meta": { "modelo": "vlm-openrouter", "modelo_version": "openai/gpt-4o-mini", "prompt_version": "cuaderno-v2", "fallback_usado": false }
}
```
Campos extra (opcionales, el front puede ignorarlos): `cliente_id` / `cliente_nuevo` (el nombre se empareja con los
clientes existentes por alias y se devuelve con el nombre del catálogo; si es nuevo se crea recién al confirmar),
`posible_duplicado` (ya existe un fiado igual en `cuaderno_fiado`; al confirmar se omite y vuelve en `duplicados`) y
`lineas_tachadas`. Con fallback a fixture, `meta.modelo = "fixture-cuaderno"`.
Se confirma con `POST /ingesta/confirmar` (puede aceptar o editar cada fiado).

### 1.5 `POST /empresas/{empresa_id}/impuestos`
Registro por menú de botones ("¿Pagaste tu RUS?").

**Request**
```json
{ "periodo": "2026-10", "regimen": "nuevo_rus", "pagado": true, "monto": 20.00, "fecha_pago": "2026-11-12" }
```
**Response 201**
```json
{ "impuesto_id": "IMP-0009", "estado": "al_dia", "proximo_vencimiento": "2026-12-15" }
```

### 1.6 `POST /billeteras/movimientos` (roadmap; en la demo, datos sintéticos)
Movimientos que llegan estructurados. No requieren confirmación.
```json
{
  "empresa_id": "EMP-0001",
  "proveedor_billetera": "billetera_a",
  "operacion_id": "OP-55821",
  "tipo": "ingreso",
  "monto": 18.50,
  "fecha_hora": "2026-11-14T09:12:00-05:00"
}
```
**Response 201** → `{ "movimiento_id": "MOV-000124", "duplicado": false }`

### 1.7 `POST /empresas/{empresa_id}/chat/mensajes` (chat de la app)
Un solo endpoint para el chat: el backend decide si el mensaje es un registro, una corrección o respuesta al borrador
pendiente, una confirmación, una cancelación o algo para el asistente. Primero reglas; si dudan, **una** llamada corta
al LLM para clasificar (si el LLM no responde, siguen las reglas). La misma lógica usa `/webhooks/whatsapp`.

**Request**
```json
{ "texto": "fue por billetera", "canal": "texto", "media_url": null, "borrador_id": "BOR-7781", "conversacion_id": null }
```
- `canal`: `texto | voz` (con `voz`, `media_url` como en §1.2; `texto` opcional como respaldo de la demo).
- `borrador_id`: el borrador que el chat está esperando (confirmar/aclarar/corregir). Si no existe, es de otra empresa
  o ya se resolvió, se ignora y el mensaje se trata como nuevo.

**Response 200**
```json
{
  "tipo": "borrador_actualizado",
  "mensaje": "Listo, lo cambié: 2 Cerveza 620 ml, S/ 13.00, billetera. ¿Ahora sí lo guardo?",
  "transcripcion": null,
  "interpretacion": { "borrador_id": "BOR-7781", "movimiento_propuesto": { "...": "..." }, "origen_monto": "catalogo",
                      "confianza": 0.95, "campos_faltantes": [], "pregunta_aclaratoria": null, "meta": { } },
  "confirmacion": null,
  "asistente": null,
  "conversacion_id": null,
  "meta": { "modelo": "reglas-chat", "fallback_usado": false }
}
```
| `tipo` | Cuándo | Trae |
|---|---|---|
| `registro` | Mensaje nuevo que es un movimiento | `interpretacion` (misma forma que §1.2, con `opciones_aclaracion` / `chequeo_pedido` si aplican) |
| `borrador_actualizado` | Con borrador: corrección ("fue por billetera", "eran 3", "no, 15 soles") o respuesta a la pregunta ("el 30 de noviembre", "noviembre", "30"), o "sí" cuando aún falta un dato | `interpretacion` actualizada (incluye `chequeo_pedido` en un pedido a crédito) |
| `guardado` | "sí", "dale", "está bien"…; o respuesta a la pregunta que completa el borrador (salvo pedido a crédito, que primero muestra el chequeo) | `confirmacion` (misma forma que §1.3) |
| `descartado` | "no, bórralo", "cancela", "no" | — |
| `asistente` | Pregunta, saludo, gracias o mensaje que no es un movimiento (nunca error) | `asistente` (misma forma que §7); `null` solo si `mensaje` lo dice todo (p. ej. gasto personal sin monto) |
- `mensaje`: texto corto y natural para mostrar; en `asistente` es la respuesta completa. `meta.modelo`:
  `llm-chat` si clasificó el LLM, `reglas-chat` si bastaron las reglas (`fallback_usado = true` si el LLM falló); en
  `registro`/`asistente` es el `meta` de §1.2/§7.
- Errores con el formato estándar: `400` sin texto, `404` empresa, `422`/`503` como §1.2 para audio.

---

## 2. Movimientos (consulta y registro manual)

### 2.1 `GET /empresas/{empresa_id}/movimientos`
Query: `desde`, `hasta`, `tipo`, `categoria`, `canal`, `limit`, `cursor`.

```json
{
  "items": [
    {
      "movimiento_id": "MOV-000123",
      "fecha_hora": "2026-11-14T10:42:00-05:00",
      "tipo": "venta",
      "categoria": "bebidas",
      "monto": 13.00,
      "moneda": "PEN",
      "metodo_pago": "efectivo",
      "contraparte": null,
      "canal": "voz",
      "confianza_extraccion": 0.93,
      "afecta_caja": true,
      "saldo_post": 2353.00,
      "descripcion": "2 Cerveza 620 ml",
      "items": [ { "producto": "Cerveza 620 ml", "cantidad": 2, "precio_unitario": 6.50, "subtotal": 13.00 } ]
    }
  ],
  "next_cursor": null
}
```
- `descripcion`: texto del movimiento (puede ser `null`). `items`: líneas de `detalle_transaccion` (vacío si no tiene detalle).

### 2.2 `POST /empresas/{empresa_id}/movimientos`
Registro manual desde la app (`canal = manual`). Mismo esquema que `movimiento_propuesto`. Responde `201` como §1.3.

---

## 3. F2 — Resumen financiero

### `GET /empresas/{empresa_id}/resumen?periodo=2026-11`

```json
{
  "empresa_id": "EMP-0001",
  "periodo": "2026-11",
  "corte": "2026-11-14",
  "indicadores": {
    "saldo_caja_negocio":   { "valor": 2340.00, "variacion_pct": null },
    "ingresos_mes":         { "valor": 8540.00, "variacion_pct": -6.2 },
    "egresos_mes":          { "valor": 7310.00, "variacion_pct": 4.8 },
    "ganancia_neta":        { "valor": 980.00, "variacion_pct": -18.5, "es_aproximada": true, "rango": [760.00, 1210.00] },
    "retiros_personales":   { "valor": 1900.00, "sueldo_fijo_definido": null, "promedio_historico": 1200.00 },
    "pendiente_cobro":      { "valor": 310.00, "n_fiados": 3 },
    "pagos_pendientes":     { "valor": 2420.00, "n_obligaciones": 2 }
  },
  "variacion_vs": "2026-10 al mismo día de corte"
}
```
- `ganancia_neta.es_aproximada = true` cuando faltan costos en el catálogo; entonces se envía `rango`.
- Cálculo determinístico. Sin bloque `meta` de modelo.
- Definiciones (implementación B2): periodo del día 1 al día de corte; variación contra el mes anterior del día 1 al
  mismo día. `ingresos_mes` = entradas de caja (ventas al contado, cobros de fiado, otros ingresos; sin préstamos);
  `egresos_mes` = salidas de caja del negocio (sin el retiro personal); `ganancia_neta` = ventas (incluidas las fiadas) −
  costo de lo vendido − gastos del negocio − impuestos. `saldo_caja_negocio.variacion_pct` también se calcula.
- Campos extra (opcionales): `dias_con_datos`, `dias_requeridos_forecast` (28), `retiros_personales.sueldo_frecuencia`,
  `retiros_personales.exceso_vs_promedio`, `pagos_pendientes.detalle`. `sueldo_fijo_definido` = monto del sueldo fijo
  vigente (por su frecuencia), `null` si no hay.

---

## 4. F3 y F4 — Forecast, cuentas por cobrar/pagar y simulación

### 4.1 `GET /empresas/{empresa_id}/forecast?horizonte_dias=30`

```json
{
  "empresa_id": "EMP-0001",
  "fecha_corte": "2026-11-14",
  "horizonte_dias": 30,
  "saldo_actual": 2340.00,
  "minimo_operativo": 800.00,
  "serie": [
    { "fecha": "2026-11-15", "ingresos_esperados": 650.00, "egresos_esperados": 380.00, "p10": 2420.00, "p50": 2610.00, "p90": 2790.00 },
    { "fecha": "2026-11-30", "ingresos_esperados": 610.00, "egresos_esperados": 2400.00, "p10": -1180.00, "p50": -650.00, "p90": -90.00 }
  ],
  "dia_critico": {
    "fecha": "2026-11-30",
    "saldo_p50": -650.00,
    "probabilidad_deficit": 0.74,
    "obligacion_asociada": { "tipo": "prestamo_proveedor", "id": "PED-0012", "proveedor": "Distribuidora Andina", "monto": 2400.00 }
  },
  "disponible_para_gastar": {
    "valor": 0.00,
    "formula": "saldo_actual + cobros_esperados − pagos_comprometidos_hasta_proximo_vencimiento − minimo_operativo − reserva_impuestos",
    "componentes": { "saldo_actual": 2340.00, "cobros_esperados": 190.00, "pagos_comprometidos": 2420.00, "minimo_operativo": 800.00, "reserva_impuestos": 20.00 },
    "mensaje": "Hoy no conviene sacar plata para la casa: comprometería el pago del 30/11."
  },
  "ajustes_manuales_aplicados": [],
  "baseline": { "nombre": "naive_estacional", "mae_backtest": 212.40 },
  "modelo_metricas": { "mae_backtest": 158.10, "cobertura_p10_p90": 0.82 },
  "meta": { "modelo": "forecast-lgbm-quantile", "modelo_version": "0.3.1", "fallback_usado": false }
}
```
- `cobros_esperados` ya viene ponderado por la probabilidad de pago de cada fiado (§4.3).
- Si el modelo falla, `meta.fallback_usado = true` y la serie sale del baseline.
- **Estado actual (B3):** el modelo LightGBM de `modelo/artifacts/forecast/` no es integrable (4 de sus 27 features —
  `rubro`, `zona`, `usa_fiado`, `usa_billetera_digital` — no tienen equivalente en la BD), así que siempre responde el
  baseline: `meta.modelo = "forecast-naive-estacional"`, `meta.fallback_usado = true`, `meta.fallback_motivo` (extra)
  con el motivo, y `modelo_metricas = null`. `baseline.mae_backtest` = MAE diario del flujo en las últimas 4 semanas.
- Línea esperada (`p50`): saldo + media del mismo día de la semana (últimas 4 semanas) del flujo ordinario + pagos con
  fecha (deudas y cuotas, movimientos programados como luz y sueldo, impuestos impagos) + ajustes manuales. Los fiados
  **no** entran al `p50` (prudencia: cobrarlos a tiempo es incierto; es la palanca del simulador): entran ponderados a
  `cobros_esperados`, a la banda optimista (`p90`) y a `proximos_eventos` con `tipo = "cobro_fiado"`, `ponderado = true`.
  Banda `p10/p90` = ±1.2816·σ·√h (σ = error diario del baseline). Siempre `p10 ≤ p50 ≤ p90`.
- `dia_critico` = primer día con `p50 < 0`; si no hay, el día más bajo si queda bajo el `minimo_operativo`; si no, `null`.
  `probabilidad_deficit` = P(saldo < 0) ese día según la banda.
- `disponible_para_gastar`: la ventana va hasta el día crítico (o el próximo vencimiento de una deuda, o el horizonte);
  `pagos_comprometidos` incluye deudas, programados (con el sueldo) e impuestos con fecha en la ventana;
  `reserva_impuestos` = impuestos impagos que vencen después. Se acota en 0.
- Campos extra: `proximos_eventos`, `fundamento`, `limites`, `confianza`, `disponible` (false si hay < 28 días con
  registros), `dias_con_datos`, `dias_requeridos`.

### 4.2 `POST /empresas/{empresa_id}/forecast/ajustes`
Ajuste manual de partidas ("este mes no pago alquiler").
```json
{ "fecha": "2026-11-28", "concepto": "alquiler", "monto": 0.00, "motivo": "acuerdo con el dueño del local" }
```
**Response 201** → `{ "ajuste_id": "AJU-0003", "forecast_recalculado": true }`
- El ajuste reemplaza el monto de la partida proyectada que coincide (por `programado_id` o por concepto, en el mismo
  mes); si no coincide con ninguna, se suma como egreso extra ese día. `fecha` debe ser posterior a hoy y `monto ≥ 0`
  (`400` si no). El forecast lo lista en `ajustes_manuales_aplicados`
  (`{ajuste_id, fecha, concepto, monto, motivo, tipo: "reemplazo" | "adicional", monto_original?, fecha_original?}`).

### 4.3 `GET /empresas/{empresa_id}/fiados?estado=pendiente`

```json
{
  "total_pendiente": 310.00,
  "total_vencido": 215.00,
  "items": [
    {
      "fiado_id": "FIA-0045",
      "cliente_id": "CLI-0102",
      "cliente": "Sra. Carmen",
      "monto": 120.00,
      "fecha": "2026-10-27",
      "dias_transcurridos": 18,
      "estado": "vencido",
      "riesgo_atraso": { "probabilidad": 0.72, "nivel": "alto", "baseline_probabilidad": 0.60 },
      "accion_sugerida": { "tipo": "recordatorio", "texto_boton": "Recordar a la Sra. Carmen" }
    }
  ],
  "meta": { "modelo": "riesgo-atraso-clf", "modelo_version": "0.2.0", "fallback_usado": false }
}
```

- `estado=pendiente` devuelve todo lo impago (pendiente, por vencer y vencido); `por_vencer` = el compromiso vence en
  ≤ 3 días; `vencido` = ya pasó; `pagado` lista los cobrados. Sin fecha de compromiso se asume a 14 días.
- `riesgo_atraso` (baseline, no hay clasificador entregado): tasa histórica de atraso del cliente a la fecha de corte
  (fiados pagados después del compromiso o impagos ya vencidos), suavizada hacia la tasa de la bodega
  (`baseline_probabilidad`). Nunca usa `pago_tardio` ni `perfil_pago`. `meta.modelo = "riesgo-atraso-baseline"`,
  `meta.fallback_usado = true`. `nivel`: alto ≥ 0.6, medio ≥ 0.3. `accion_sugerida.texto_boton = "Recordar a <cliente>"`.

**`POST /fiados/{fiado_id}/recordatorio`** → genera el texto a reenviar (no lo envía al vecino):
```json
{ "mensaje": "Hola, Sra. Carmen 😊 Le recuerdo amablemente los S/ 120 pendientes en la bodega. ¡Gracias!" }
```

### 4.4 `GET /empresas/{empresa_id}/pedidos?estado=pendiente`
Préstamos de proveedor (cuentas por pagar). Lee la tabla `deudas` con `tipo = proveedor`; `pedido_id` es su `deuda_id`. `monto_pendiente`, `estado` y `dias_para_vencer` se calculan al momento de responder (no se guardan). Los préstamos de dinero (`tipo ≠ proveedor`) entran al forecast y al asistente; su endpoint de consulta queda como roadmap.
```json
{
  "total_pendiente": 2400.00,
  "items": [
    { "pedido_id": "PED-0012", "proveedor": "Distribuidora Andina", "monto": 2400.00, "monto_pendiente": 2400.00, "fecha_pedido": "2026-11-13", "fecha_vencimiento": "2026-11-30", "estado": "pendiente", "dias_para_vencer": 16 }
  ],
  "impuestos": { "estado": "al_dia", "impuesto_id": "IMP-0004", "proximo_vencimiento": "2026-12-15", "monto_estimado": 20.00, "nombre": "RUS de noviembre" }
}
```
- `impuestos.impuesto_id`: el impuesto impago más próximo; `null` si no hay ninguno registrado y lo mostrado es la
  estimación del siguiente mes.
- `estado` del pedido: `por_vencer` solo si vence en ≤ 3 días (con 16 días es `pendiente`); el filtro `estado` se
  comporta como en §4.3. `impuestos.estado`: `vencido` si hay un periodo impago con el vencimiento pasado.

### 4.4.1 `POST /empresas/{empresa_id}/cuentas/anular`
Anula un fiado, pedido o impuesto registrado por error. **Nada se borra**: fiado/pedido → se marcan `anulada = true`
sus transacciones de origen (venta fiada, compra a crédito o préstamo recibido); impuesto → se marca su régimen
(`anulado_…`). Desde ese momento no aparece en `/fiados`, `/pedidos`, `/resumen`, `/forecast`, `/simular` ni en las
alertas (sus alertas activas pasan a `descartada` y los faltantes activos se recalculan). Los cobros/pagos que ya tuviera
se conservan. Repetirlo es idempotente.
```json
{ "tipo": "fiado", "id": "FIA-0045" }
```
- `tipo`: `fiado | pedido | impuesto`. **Response 200** → `{ "id": "FIA-0045", "anulada": true }`
- `404 NO_ENCONTRADO` si no existe para esa empresa · `400 VALIDACION` si el body es inválido · `409 CONFLICTO` si el
  impuesto ya tiene un pago anotado (primero se anula ese pago).

### 4.5 `POST /empresas/{empresa_id}/pedidos/chequeo`
Chequeo **antes de confirmar** un pedido a crédito.

**Request**
```json
{ "proveedor": "Distribuidora Andina", "monto": 2400.00, "fecha_vencimiento": "2026-11-30" }
```

**Response 200**
```json
{
  "saldo_proyectado_al_vencimiento": -650.00,
  "estado_caja": "no_te_alcanza",
  "venta_esperada_periodo": 2000.00,
  "exceso_vs_ventas": 400.00,
  "sugerencias": [
    { "accion": "reducir_pedido", "monto_sugerido": 1800.00, "saldo_resultante": -50.00 },
    { "accion": "pagar_en_partes", "partes": 2, "saldo_resultante": 550.00 },
    { "accion": "combinar", "detalle": "pedir 1 800 + pagar en 2 partes", "saldo_resultante": 850.00 }
  ],
  "fundamento": "En 2 semanas sueles vender alrededor de S/ 2 000 y el 30/11 también vencen otros pagos.",
  "limites": "Proyección basada en tus ventas de los últimos 3 meses; no considera eventos que no hayas registrado.",
  "confianza": "media",
  "meta": { "modelo": "forecast-lgbm-quantile", "modelo_version": "0.3.1", "fallback_usado": false }
}
```
- `venta_esperada_periodo`: lo que sueles vender (precio de venta, al contado o fiado) de los productos que te trae ese
  proveedor, desde mañana hasta el vencimiento (tasa de las últimas 4 semanas × días), redondeado a centenas
  (≥ S/ 1 000) porque es una estimación. Proveedor sin historial de productos → todas tus ventas.
  `exceso_vs_ventas = max(0, monto − venta_esperada_periodo)`.
- Si ya hay una deuda igual registrada (mismo proveedor, monto y vencimiento, impaga) se toma como este pedido y no se
  cuenta dos veces (pasa al confirmar y en la demo con PED-0012): `pedido_coincidente_id` (extra).
- Sugerencias solo si no te alcanza holgado: `reducir_pedido` a ~90 % de la venta esperada (redondeado hacia abajo),
  `pagar_en_partes` (2 partes: vencimiento y +15 días) y `combinar`. `saldo_resultante` = saldo más bajo hasta el
  vencimiento; una parte que cae fuera del horizonte (30 días) no se evalúa y se avisa en `limites`.
- Campos extra: `saldo_minimo_hasta_vencimiento`, `fecha_saldo_minimo`, `pedido_coincidente_id`. Hoy
  `meta.modelo = "forecast-naive-estacional"` con `fallback_usado = true` (ver §4.1).

### 4.6 `POST /empresas/{empresa_id}/simular`
Simulador de escenarios (lo usan la app y el asistente).

**Request**
```json
{
  "acciones": [
    { "tipo": "reducir_pedido", "pedido_id": "PED-0012", "nuevo_monto": 1800.00 },
    { "tipo": "pagar_en_partes", "pedido_id": "PED-0012", "partes": 2, "fechas": ["2026-11-30", "2026-12-15"] },
    { "tipo": "cobrar_fiados", "fiado_ids": ["FIA-0045", "FIA-0046", "FIA-0047"], "fecha": "2026-11-20" }
  ]
}
```
- `acciones: []` es válido: devuelve la base (`con_acciones` = `sin_acciones`, `mejora` = 0).
- Tipos de acción: `reducir_pedido | pagar_en_partes | diferir_pago | cobrar_fiados | limitar_retiros | ajustar_gasto`
- Parámetros: `reducir_pedido` (`pedido_id`, `nuevo_monto` = nuevo total), `pagar_en_partes` (`partes` ≥ 2, `fechas`
  opcional, por defecto vencimiento y +15 días), `diferir_pago` (`fecha`), `cobrar_fiados` (`fiado_ids`, por defecto todos
  los pendientes; `fecha`, por defecto mañana), `limitar_retiros` (`monto` = tope semanal de retiros fuera del sueldo
  fijo; 0 = solo el sueldo), `ajustar_gasto` (`monto` extra ese día, negativo = gastas menos; `fecha`). Sin `pedido_id`
  se usa el pedido del día crítico. Pedido o fiado inexistente/pagado → `400`. El orden de las acciones no importa.
- `saldo_minimo` = saldo más bajo desde mañana hasta el día crítico de la proyección (si no hay, hasta el final del
  horizonte de 30 días). Si una acción mueve un pago a una fecha posterior dentro del horizonte, la ventana se alarga
  hasta esa fecha; un pago que cae fuera del horizonte no se evalúa y se avisa en `limites` y `notas`.
- Campos extra: `fundamento`, `limites`, `confianza`, `ventana_hasta`, `notas`. `serie_con_acciones` trae los 30 días.

**Response 200**
```json
{
  "sin_acciones": { "saldo_minimo": -650.00, "fecha": "2026-11-30", "estado_caja": "no_te_alcanza" },
  "con_acciones": { "saldo_minimo": 1160.00, "fecha": "2026-11-30", "estado_caja": "te_alcanza" },
  "mejora": 1810.00,
  "serie_con_acciones": [ { "fecha": "2026-11-30", "p50": 1160.00 } ],
  "meta": { "modelo": "simulador-deterministico", "modelo_version": "0.1.0", "fallback_usado": false }
}
```

---

## 5. F5 — Análisis de ingresos y egresos

### `GET /empresas/{empresa_id}/analisis`
Query: `desde`, `hasta`, `agrupar_por` (`categoria | producto | proveedor | cliente_fiado | metodo_pago | mes`), `tipo` (`ingreso | egreso`), `comparar_con` (`periodo_anterior | mismo_periodo_anio_anterior`).

```json
{
  "agrupar_por": "categoria",
  "tipo": "egreso",
  "periodo": { "desde": "2026-11-01", "hasta": "2026-11-14" },
  "grupos": [
    { "clave": "mercaderia", "monto": 4980.00, "participacion_pct": 68.1, "variacion_pct": 12.4 },
    { "clave": "retiros_personales", "monto": 1900.00, "participacion_pct": 26.0, "variacion_pct": 58.3 }
  ],
  "comparacion_pares": {
    "metrica": "retiros_personales_sobre_ventas",
    "valor_empresa": 0.35,
    "mediana_pares": 0.22,
    "grupo_pares": "bodegas · 1–3 trabajadores · Lima Este",
    "n_pares": 120,
    "nota": "Comparación anónima con datos sintéticos."
  }
}
```
- Base caja (lo que entró o salió de la caja) para `categoria`, `producto` y `mes`; `metodo_pago` incluye lo fiado o
  pedido a crédito (`credito`); `proveedor` = pedidos a crédito; `cliente_fiado` = ventas fiadas. `clave` de categoría =
  nombre con `_` (p. ej. `retiro_personal`). Variación contra el periodo anterior (mes en curso: mes anterior al mismo día).
- `comparacion_pares` se calcula con las empresas del mismo rubro en la BD (mediana de retiros/ventas) y es `null` con
  menos de 5 pares (la BD de la demo solo tiene a Pedro); el extra `comparacion_pares_motivo` explica por qué. Extra: `total`.

---

## 6. F6 — Alertas y nudges

### 6.1 `GET /empresas/{empresa_id}/alertas?estado=activa`

```json
{
  "items": [
    {
      "alerta_id": "ALR-0007",
      "tipo": "faltante_caja",
      "prioridad": 1,
      "creada_en": "2026-11-14T10:42:06-05:00",
      "fecha_evento": "2026-11-30",
      "monto": 650.00,
      "probabilidad": 0.74,
      "nivel_riesgo": "alto",
      "titulo": "El 30/11 no te alcanzará",
      "insight": "Para pagar S/ 2 400 a Distribuidora Andina te faltarían S/ 650.",
      "causas": [
        { "descripcion": "Retiraste más para la casa", "monto": 700.00 },
        { "descripcion": "Pediste más de lo que vendes", "monto": 400.00 },
        { "descripcion": "Fiados sin cobrar", "monto": 310.00 }
      ],
      "accion": { "tipo": "abrir_simulador", "texto_boton": "Ver qué puedo hacer", "payload": { "pedido_id": "PED-0012" } },
      "microexplicacion": "Cuando el dinero de la casa y del negocio se mezclan, es difícil saber cuánto puedes pedir.",
      "canales": ["whatsapp", "app"],
      "estado": "activa",
      "meta": { "modelo": "reglas-alertas + forecast-lgbm-quantile", "modelo_version": "0.3.1", "fallback_usado": false }
    }
  ]
}
```
- Cada alerta lleva: tipo, fecha del problema, monto, probabilidad o nivel de riesgo, causas y una acción.
- Prioridad (1 = más alta): `faltante_caja` → `pedido_excesivo` → `retiro_excesivo` → `obligacion_proxima` → `gasto_inusual`/`caida_ventas` → `fiado_vencido` → `meta_lograda` → `resumen_semanal`.
- Implementadas (B10): las prioridades 1–4. `faltante_caja` (algún día con saldo esperado < 0; causas = retiros del mes
  sobre lo usual al mismo día, exceso del pedido que vence ese día sobre lo que vendes de esa mercadería, fiados sin
  cobrar), `pedido_excesivo` (pedido a crédito > venta esperada hasta su vencimiento, §4.5), `retiro_excesivo` (retiros
  del mes > sueldo fijo esperado a la fecha, o > lo usual si no hay sueldo), `obligacion_proxima` (deuda o impuesto
  impago que vence en ≤ 3 días).
- `GET /alertas?estado=activa` primero evalúa las reglas (sin duplicar) y luego lista; otros estados: `atendida`,
  `descartada`, `todas`. Una alerta ya atendida o descartada no se vuelve a crear al consultar.
- Los textos (`titulo`, `titulo_corto`, `insight`, `resumen_causas`) se arman al leer. `accion.tipo`:
  `abrir_simulador` (payload `pedido_id`), `ver_retiros`, `ver_cuentas`. Campos extra: `dias_para_evento`,
  `titulo_corto`, `resumen_causas`, `enviada_en` (`null` = guardada sin notificar: horario silencioso o límite diario).

### 6.2 `POST /alertas/{alerta_id}/accion`
```json
{ "accion": "ejecutada", "detalle": "abrió simulador" }
```
- `accion`: `ejecutada | descartada | posponer`
- **Response 200** → `{ "estado": "atendida" }` (`ejecutada` → `atendida`, `descartada` → `descartada`, `posponer` →
  `pospuesta`: sigue activa y se vuelve a notificar). Alerta inexistente → `404`.

### 6.3 `POST /empresas/{empresa_id}/alertas/evaluar` (interno)
Se llama después de cada movimiento confirmado. Devuelve las alertas nuevas.
- Respeta límites: máximo 2 notificaciones al día por empresa, horario silencioso (21:00–07:00), y ninguna alerta incluye enlaces que pidan credenciales.
- Body opcional `{ "disparador": "compra_credito" | "<tipo_movimiento>" | null, "entidad_id": "PED-0013" }`. Reglas por
  disparador: `compra_credito` → faltante + pedido excesivo; `retiro_personal` → faltante + retiro excesivo; otros
  egresos → faltante; ingresos → ninguna; `null` → las 4. No se duplica una alerta activa (misma regla y entidad, y para
  el faltante la misma fecha). Toda alerta nueva se guarda y vuelve en la respuesta; queda `enviada_en = null` si es
  horario silencioso o ya se notificaron `max_por_dia` ese día (se evalúan por prioridad).

### 6.4 `PUT /empresas/{empresa_id}/preferencias-alertas`
```json
{ "canales": ["whatsapp"], "max_por_dia": 2, "silencio_desde": "21:00", "silencio_hasta": "07:00", "resumen_semanal": true }
```
- **Response 200** con las preferencias guardadas (tabla `preferencias_alertas`). Canal fuera de
  `whatsapp | app | email` u hora inválida → `400`; empresa inexistente → `404`.

---

## 7. F7 — Asistente financiero

### `POST /empresas/{empresa_id}/asistente/mensajes`

**Request**
```json
{ "conversacion_id": "CNV-0031", "mensaje": "¿Por qué me va a faltar plata a fin de mes?", "canal": "whatsapp" }
```

**Response 200**
```json
{
  "conversacion_id": "CNV-0031",
  "respuesta": "El 30/11 vence tu pago de S/ 2 400 a Distribuidora Andina. Este mes sacaste de la caja S/ 700 más de lo usual, el pedido es S/ 400 mayor a lo que sueles vender y tienes S/ 310 en fiados sin cobrar. Si pides S/ 1 800 y pagas en 2 partes, ese día tendrías S/ 850.",
  "intencion": "explicar_alerta",
  "herramientas_llamadas": [
    { "nombre": "obtener_alertas", "args": { "estado": "activa" } },
    { "nombre": "simular", "args": { "acciones": ["reducir_pedido:1800", "pagar_en_partes:2"] } }
  ],
  "cifras_usadas": [
    { "valor": 2400.00, "fuente": "pedidos.PED-0012.monto" },
    { "valor": 700.00, "fuente": "alertas.ALR-0007.causas[0]" },
    { "valor": 400.00, "fuente": "alertas.ALR-0007.causas[1]" },
    { "valor": 310.00, "fuente": "alertas.ALR-0007.causas[2]" },
    { "valor": 850.00, "fuente": "simular.con_acciones.saldo_minimo" }
  ],
  "verificacion_cifras": { "ok": true, "no_verificadas": [] },
  "fuera_de_alcance": false,
  "ofrecer_humano": true,
  "disclaimer": "Orientación educativa. No es asesoría financiera.",
  "meta": { "modelo": "llm-local", "modelo_version": "qwen2.5-7b-instruct", "prompt_version": "asistente-v3", "fallback_usado": false }
}
```
- `intencion`: `estado_caja | explicar_alerta | simular | concepto | crear_meta | prestamo | fuera_de_alcance | otro`
- Si alguna cifra no se puede verificar, `verificacion_cifras.ok = false` y la respuesta se reemplaza por la plantilla de fallback.
- `otro` (saludo, gracias, despedida, charla o mensaje poco claro): con LLM, respuesta corta y natural dentro del
  alcance del negocio, **sin cifras** (el verificador solo admite las del propio mensaje) y con el historial reciente de
  la conversación; sin LLM (o si no pasa la verificación), una plantilla corta según el tipo de mensaje (saludo,
  gracias, despedida o una pregunta para entender mejor). Nunca un menú fijo.
- Textos para Pedro: tono de vecino, de tú; sin porcentajes ni probabilidades; nunca "la casa"/"plata de la casa"
  (los retiros son "lo que sacaste de la caja"). Una respuesta del LLM con `%` o "casa" se descarta (plantilla).
- Si la pregunta pide un crédito o entidad específica, inversión, cripto u opinión tributaria o legal: `fuera_de_alcance = true` con una respuesta educativa y una derivación.

### Herramientas (function calling) disponibles para el LLM
El LLM **no calcula**: solo llama a estas funciones, que envuelven los endpoints anteriores.

| Función | Endpoint que usa |
|---|---|
| `obtener_resumen(periodo)` | `GET /resumen` |
| `obtener_forecast(horizonte_dias)` | `GET /forecast` |
| `obtener_alertas(estado)` | `GET /alertas` |
| `obtener_fiados(estado)` | `GET /fiados` |
| `obtener_pedidos(estado)` | `GET /pedidos` |
| `simular(acciones)` | `POST /simular` |
| `obtener_salud()` | `GET /salud` |
| `crear_meta(plantilla, regla)` | `POST /metas` |
| `explicar_concepto(tema)` | Base de microexplicaciones (texto fijo, revisado por el equipo) |

---

## 8. F8 — Plan de salud y score

### 8.1 `GET /empresas/{empresa_id}/salud`

```json
{
  "score": 72,
  "score_anterior": 64,
  "etapa_actual": "estabilizar",
  "etapas": ["organizar", "estabilizar", "proteger", "crecer"],
  "subindicadores": [
    { "id": "constancia_registro", "nombre": "Anotar todos los días", "valor": 100, "detalle": "13 de 13 días anotando este mes", "peso": 0.35, "destacado": true },
    { "id": "separacion_personal", "nombre": "Ponerte un sueldo fijo", "valor": 65, "detalle": "Sueldo fijo de S/ 400 por semana; este mes sacaste S/ 1 900 (S/ 1 100 más)", "peso": 0.40, "destacado": true },
    { "id": "impuestos_al_dia", "nombre": "Impuestos al día", "valor": 100, "detalle": "Al día", "peso": 0.25, "destacado": true }
  ],
  "historial": [ { "mes": "2026-08", "score": 38 }, { "mes": "2026-09", "score": 52 }, { "mes": "2026-10", "score": 64 }, { "mes": "2026-11", "score": 72 } ],
  "rachas": [ { "tipo": "semanas_registrando", "valor": 14 }, { "tipo": "dias_seguidos", "valor": 13 } ],
  "metas_activas": [ { "meta_id": "MET-0001", "plantilla": "apartar_para_pedido", "titulo": "Apartar para el pedido", "detalle": "S/ 1 de cada S/ 10 que vendes", "acumulado": 420.0, "estado": "activa" } ],
  "consentimiento_compartir_historial": false,
  "fundamento": "Sale de 3 hábitos: anotar todos los días, ponerte un sueldo fijo (el que más cuenta) y tener tus impuestos al día.",
  "meta": { "modelo": "score-reglas", "modelo_version": "0.1.0", "fallback_usado": false }
}
```
- El score es la suma ponderada de los subindicadores (determinístico y explicable). Los textos (`nombre`, `detalle`,
  `fundamento`) no usan porcentajes ni hablan de "la casa".

### 8.2 `POST /empresas/{empresa_id}/metas`
```json
{
  "plantilla": "apartar_para_pedido",
  "regla": { "tipo": "porcentaje_de_venta", "valor": 0.10, "destino": "fondo_pedidos" },
  "recordatorio": { "frecuencia": "semanal", "dia": "lunes" }
}
```
- Plantillas: `registrar_30_dias | sueldo_fijo | colchon_caja | apartar_para_pedido | reservar_impuestos`
- **Response 201** → `{ "meta_id": "MET-0004", "estado": "activa" }`

### 8.3 `PUT /empresas/{empresa_id}/consentimiento` (roadmap)
```json
{ "compartir_historial_para_evaluacion": true, "alcance": ["resumen_12_meses", "score"], "vigencia_hasta": "2027-05-14" }
```
- Desactivado por defecto. Revocable en cualquier momento. No ofrece ni otorga créditos.

---

## 9. Salud del servicio

### `GET /health`
```json
{
  "estado": "ok",
  "version_api": "1.0.0",
  "componentes": {
    "base_datos": "ok",
    "whisper": { "estado": "ok", "modelo": "faster-whisper-small" },
    "almacenamiento": { "estado": "ok", "bucket": "cajaclara-media" },
    "llm": { "estado": "ok", "modelo": "qwen2.5-7b-instruct", "prompt_versions": { "extractor": "v3", "asistente": "v2", "cuaderno": "v2" } },
    "vlm": { "estado": "ok", "modelo": "openai/gpt-4o-mini", "proveedor": "openrouter" },
    "forecast": { "estado": "baseline", "modelo": "forecast-naive-estacional", "modelo_version": "0.1.0",
                  "ml": { "tipo": "lightgbm-quantile", "estado": "no_disponible", "artefactos": true,
                          "motivo": "rubro: el modelo espera abarrotes, bebidas, mixto, panaderia; …" } },
    "riesgo_atraso": { "estado": "baseline", "modelo": "riesgo-atraso-baseline", "modelo_version": "0.1.0",
                       "ml": { "tipo": "clasificador", "estado": "no_disponible", "artefactos": false,
                               "motivo": "No hay artefactos de un clasificador de riesgo de atraso en modelo/artifacts/" } }
  }
}
```
- `forecast.estado` / `riesgo_atraso.estado`: `ok` (modelo de ML en uso) o `baseline` (responde el baseline
  determinístico); `ml.motivo` dice por qué el modelo no está. No carga modelos: solo lee `metadata.json` (cacheado).

---

## 10. Mapa endpoint → funcionalidad → responsable

| Funcionalidad | Endpoints | Responsable sugerido |
|---|---|---|
| F1 Ingesta | `/webhooks/whatsapp`, `/media/subidas`, `/ingesta/*`, `/impuestos`, `/billeteras/movimientos` | Backend + GenAI |
| F2 Resumen | `/resumen` | Backend |
| F3 Forecast | `/forecast`, `/forecast/ajustes` | ML |
| F4 Cuentas | `/fiados`, `/fiados/{id}/recordatorio`, `/pedidos`, `/pedidos/chequeo` | ML + Backend |
| Simulador | `/simular` | Backend |
| F5 Análisis | `/analisis` | Datos / BI |
| F6 Alertas | `/alertas`, `/alertas/{id}/accion`, `/alertas/evaluar`, `/preferencias-alertas` | Backend + ML |
| F7 Asistente | `/asistente/mensajes` | GenAI |
| F8 Salud | `/salud`, `/metas`, `/consentimiento` | Backend |
| Operación | `/health` | Backend |

### Mock para trabajar en paralelo
Hasta que los modelos estén listos, el backend publica respuestas fijas con estos mismos JSON (datos de Pedro: saldo S/ 2 340, déficit −S/ 650 el 30/11, pedido S/ 2 400 a Distribuidora Andina, fiados S/ 310). El front y el bot consumen el mock desde el primer momento.

---

## 11. Observabilidad del LLM (interna)

> Uso interno del equipo (costos, latencia, calidad de la salida del modelo). **No forma parte de las pantallas del producto**; llevan `X-API-Key` como el resto. Cada llamada al LLM/VLM (extractor, asistente, cuaderno) deja una fila en la tabla técnica `llm_llamadas`, también si falla. Parámetros: `LLM_TRAZA_ACTIVA`, `LLM_TRAZA_GUARDAR_CONTENIDO`.

### 11.1 `GET /empresas/{empresa_id}/llm/llamadas`
Query: `origen` (`extractor | asistente | vision`), `estado` (`ok | timeout | http_error | red | respuesta_invalida | sin_configurar`), `desde`, `hasta` (fechas, zona America/Lima), `limit`, `cursor`, `incluir_contenido` (`true` agrega `request` y `respuesta`; por defecto no). Orden: más reciente primero.

```json
{
  "items": [
    {
      "llamada_id": "LLM-000012",
      "origen": "extractor",
      "referencia_tipo": "borrador",
      "referencia_id": "BOR-0042",
      "prompt_version": "extractor-v3",
      "proveedor": "openrouter",
      "modelo_solicitado": "openai/gpt-4o-mini",
      "modelo_respondido": "openai/gpt-4o-mini-2024-07-18",
      "generation_id": "gen-1731600000-abc",
      "estado": "ok",
      "http_status": 200,
      "error": null,
      "resultado_uso": "aceptada",
      "prompt_tokens": 1480,
      "completion_tokens": 60,
      "total_tokens": 1540,
      "costo_usd": 0.00026,
      "latencia_ms": 1280,
      "creado_en": "2026-11-14T10:42:05-05:00"
    }
  ],
  "next_cursor": null,
  "meta": { "request_id": "req_8f3a1c", "generado_en": "2026-11-14T10:42:06-05:00", "fallback_usado": false, "latencia_ms": 12 }
}
```
- `resultado_uso`: `aceptada | rechazada_validacion` (la salida no pasó el esquema) `| rechazada_verificador` (el verificador de cifras del asistente la rechazó) `| null` (la llamada falló o aún no se resolvió).
- `referencia_id` es el borrador (`extractor`, `vision`) o el mensaje del asistente (`asistente`).
- Las imágenes nunca se guardan: en `request` aparecen como `{"imagen": {"sha256", "bytes", "mime"}}`.

### 11.2 `GET /empresas/{empresa_id}/llm/resumen`
Query: `desde`, `hasta` (opcionales). `pct_fallback` = % de llamadas cuya salida no se usó (`estado ≠ ok` o rechazada por validación/verificador). Latencias p50/p95 en ms sobre las llamadas que llegaron a salir a la red.

```json
{
  "desde": null,
  "hasta": null,
  "totales": {
    "llamadas": 12, "ok": 11, "errores": 1, "pct_fallback": 16.7,
    "prompt_tokens": 14800, "completion_tokens": 700, "costo_usd": 0.0031,
    "latencia_p50_ms": 1100, "latencia_p95_ms": 2300
  },
  "por_dia": [ { "fecha": "2026-11-14", "llamadas": 12, "ok": 11, "errores": 1, "pct_fallback": 16.7,
                 "prompt_tokens": 14800, "completion_tokens": 700, "costo_usd": 0.0031,
                 "latencia_p50_ms": 1100, "latencia_p95_ms": 2300 } ],
  "por_origen": [ { "origen": "extractor", "llamadas": 8, "ok": 8, "errores": 0, "pct_fallback": 0.0,
                    "prompt_tokens": 9000, "completion_tokens": 400, "costo_usd": 0.0019,
                    "latencia_p50_ms": 1000, "latencia_p95_ms": 1800 } ],
  "meta": { "request_id": "req_8f3a1c", "generado_en": "2026-11-14T10:42:06-05:00", "fallback_usado": false, "latencia_ms": 15 }
}
```
