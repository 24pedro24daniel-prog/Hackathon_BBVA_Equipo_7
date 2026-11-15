# TuCaserito — Dataset sintético: supuestos, diseño y realismo

> **Entregable:** datos sintéticos y evidencia (Hackathon BBVA *"AI Financial Life"*).
> **Esquema:** [`modelo_datos.dbml`](../modelo_datos.dbml) · **Diccionario:** [`diccionario_datos.md`](../diccionario_datos.md) · **DDL:** [`schema.sql`](./schema.sql) (generado desde `backend/app/db/models.py`) · **Generador (`seed = 42`):** [`generate_synthetic_data.mjs`](./generate_synthetic_data.mjs) · **Auditoría:** [`AUDITORIA_CALIDAD_DATOS.md`](./AUDITORIA_CALIDAD_DATOS.md).

---

## 1. Principios

1. **100 % sintético, cero PII.** Nombres, teléfonos (`+5190000…`), montos y negocios son ficticios. Los RUC (`10` + 8 dígitos + dígito verificador) son inventados pero **pasan el módulo 11 de SUNAT**.
2. **Reproducible.** `node data/generate_synthetic_data.mjs` produce siempre los mismos **63 736 registros** en los **25 CSV** y las **153 frases** de evaluación (dos corridas dan archivos idénticos). Cada empresa tiene su propio flujo pseudoaleatorio (`seed 42` + número de empresa): cambiar una no mueve a las demás.
3. **El CSV es idéntico al modelo.** `data/csv` se carga tal cual en la BD creada con `backend/app/db/models.py` (0 errores, sin descartar columnas). El DDL (`schema.sql`) y su descripción (`schema_esquema.json`) se **generan** con [`pipeline_python/generar_schema.py`](./pipeline_python/generar_schema.py); no hay vistas en la BD (el backend calcula todo en Python).
4. **Cero secretos.** La URL de PostgreSQL se lee de `--url`, de `DATABASE_URL` o de `data/.env` (ignorado por git; plantilla en [`.env.example`](./.env.example)). Los cargadores **rechazan** hosts `*.render.com`, `dpg-*` y `APP_ENV=produccion` salvo con `--produccion --confirmar <nombre_de_la_bd>`.

## 2. "Hoy" de la demo y hora de corte

- `FECHA_DEMO = 2026-11-14`. La **hora de corte es las 10:00 (Lima)**: ningún movimiento, borrador, conversación, alerta o predicción del 14/11 es posterior a esa hora (la demo registra "vendí dos cervezas" a las 10:42, así que esa venta **no** está cargada). Ese día los negocios solo tienen ventas y compras de la mañana; los pagos, retiros y cobros de la tarde no existen todavía.
- Pedro (EMP-0001) el 14/11 solo tiene la compra de pan y lácteos de las 07:10 y las ventas de la mañana (09:35); su saldo a esa hora es **S/ 2 340** (ver §6).
- `predicciones_*` y alertas del 14/11 se crearon entre las 08:00 y las 09:00.
- Un evento puede seguir **en curso** a esa fecha: `eventos.fecha_fin = null` (p. ej. `EVT-0002`, el pedido `PED-0012` que vence el 30/11).

## 3. Cómo se parecen y en qué se distinguen las 30 empresas

| Aspecto | En `data/csv` |
|---|---|
| **Rubros** (los de los modelos de ML) | 21 `bodega`, 4 `restaurante`, 3 `taller`, 2 `distribuidora`. Cada rubro vende su propio catálogo. EMP-0001 es `bodega`. |
| **RUC** | 24 de 30 con RUC 10 en `nuevo_rus` (dígito verificador SUNAT válido, único). 6 informales: `tiene_ruc = false`, `ruc` y `regimen_tributario` nulos y sin impuestos. |
| **Trabajadores** | 1 a 5 (12 con 1, 1 con 2, 7 con 3, 8 con 4, 2 con 5). |
| **Volumen** | Venta diaria base de S/ 150 a S/ 2 300 según rubro; 206 a 1 130 movimientos por empresa (13 en EMP-0002, de 3 días) y 3 a 195 días de historia. Los negocios no anotan todos los días (constancia 55 %–98 %). |
| **Estacionalidad** | Semana (fin de semana alto, taller y distribuidora bajos), **quincena y fin de mes** (+15 %), inicio de mes en distribuidoras, crecimiento suave y arranque de la campaña navideña (+4 % en noviembre). |
| **Ventas** | Cada venta es una **canasta de varios productos de cantidad entera** (`detalle_transaccion.subtotal = cantidad × precio_unitario`, y la suma del detalle es el monto de la transacción). Hay 1 a 7 ventas por día según el rubro. |
| **Fiado** | 22 empresas fían (152 fiados; 1 a 14 por empresa), con clientes puntuales, ocasionales y morosos, pagos parciales y algunos impagos. |
| **Billetera digital** | 14 empresas cobran parte de sus ventas por `billetera_digital` (6 %–35 %): 1 292 movimientos en `billeteras_digitales`, cada uno enlazado 1–1 a su transacción (`billetera_api` o foto de captura). |
| **Sueldo del dueño** | 13 semanales, 4 quincenales, 6 mensuales y el resto sin sueldo fijo (retiros irregulares). Pedro: S/ 1 350 **al mes**, día 30. |
| **Deudas** | 131 pedidos a proveedores (con detalle de productos a costo; 33 de Pedro), 5 préstamos informales (*gota a gota*, 20 % por 30 días con cuota diaria), 2 familiares y 2 de entidad financiera. |
| **Alertas** | `retiro_excesivo` y `pedido_excesivo` calculados con **las mismas reglas del backend** (`services/alertas/reglas.py`) sobre estos datos; `obligacion_proxima` de lo que vence en 3 días. Las de Pedro (`ALR-0007` faltante de caja, `ALR-0008` fiado vencido, `ALR-0009` pedido excesivo, `ALR-0010` retiro excesivo) son **las que calcula el backend** sobre este CSV (`data/demo_pedro_backend.json`, ver §6). Las causas son listas `{descripcion, monto}`. |
| **Score de salud** | Misma fórmula del backend: 3 subindicadores (constancia 35 %, sueldo fijo 40 %, impuestos 25 %), `version_formula = score-v1`. |

### 3.1 La caja nunca es negativa y hay episodios reales de déficit
- Las compras al contado, los retiros y los gastos se limitan al efectivo disponible; los pagos de pedidos y préstamos se hacen en partes si no alcanza (pago parcial). Ninguna empresa tiene saldo negativo (el auditor lo comprueba día por día).
- 15 empresas (Pedro no) tienen episodios en que el saldo cae bajo su `minimo_operativo`: `saldo_diario.deficit_14d = true` en 712 de 3 858 filas con ventana completa. Para las **409 filas cuyos 14 días siguientes pasan del 14/11, `deficit_14d` es `null`** (no se conoce). Nada se fuerza a mano. Sirve para medir precisión y recall del aviso de faltante.

### 3.2 Shocks (`eventos`)
`retiro_excesivo` (retiros extra sobre el sueldo), `alza_proveedor` (pedido navideño mayor a lo que se vende hasta su vencimiento), `mes_bajo` (−22 % de ventas desde el 25/10), `gasto_extra` (reparación urgente) y `cliente_no_paga` (fiados grandes impagos). Los cinco tipos del enum aparecen y tienen efecto real en los movimientos.

### 3.3 Borradores y conversaciones de Pedro
- `BOR-7790` (foto del cuaderno, `pendiente`, usa la clave `fiados` que lee el backend), `BOR-7791` (voz con ruido, confirmado → venta de S/ 22.00 del 10/11) y `BOR-7792` (foto con confusión 3/8, corregida de 330 a **380**; la compra del 08/11 es de S/ 380.00). La venta de las 2 cervezas (`BOR-7781` / `MOV-000123`) se quitó: se dice en vivo.
- `conversaciones.intencion` solo usa valores de `IntencionAsistente` (`otro`, `explicar_alerta`).
- Solo la demo de Pedro tiene borradores: los demás registros se cargan como si vinieran del formulario o de importación (sin `borrador_id`), aunque su canal diga `voz`/`texto`/`foto`. Es una simplificación conocida.

## 4. Impuestos (Nuevo RUS)

Cuota de S/ 20 (categoría 1) o S/ 50 (categoría 2) según las ventas del mes (> S/ 5 000). Algunos negocios **pagan S/ 20 aunque ya venden más** ("paga, pero informa mal"), y 2 negocios dejaron sin pagar el periodo `2026-09` (impuesto **vencido**) y 3 el `2026-10` (vence el 15/11: `obligacion_proxima`). Simplificación: el régimen Nuevo RUS tiene tope de S/ 8 000 mensuales, que algunos negocios del dataset superan; se ignora para no cambiar de régimen a mitad de historia.

## 5. Volumen de los 25 CSV (`seed = 42`)

| Archivo | Filas | Notas |
|---|---:|---|
| `rubros.csv` | 4 | `bodega`, `restaurante`, `taller`, `distribuidora` |
| `empresas.csv` | 30 | EMP-0001 Don Pedro, EMP-0002 (día 3) y 28 negocios |
| `preferencias_alertas.csv` | 30 | Canales, tope diario (1–3) y horario silencioso distintos |
| `categorias.csv` | 16 | Las 13 de siempre + `cobro_fiados`, `prestamos_recibidos`, `otros_gastos` |
| `productos.csv` | 376 | Catálogo propio por empresa y rubro |
| `clientes.csv` | 117 | Con `perfil_pago` oculto (solo del generador) |
| `proveedores.csv` | 82 | Plazos de 7, 15 y 30 días |
| `conversaciones.csv` | 4 | Solo Pedro |
| `borradores.csv` | 3 | `BOR-7790`, `BOR-7791`, `BOR-7792` |
| `movimientos_programados.csv` | 81 | Sueldo, luz, alquiler, internet, 2 ventas fijas semanales |
| `cuaderno_fiado.csv` | 152 | |
| `deudas.csv` | 140 | 131 proveedor (33 de Pedro), 5 gota a gota, 2 familiares, 2 entidad financiera |
| `billeteras_digitales.csv` | 1 292 | 14 empresas |
| `impuestos.csv` | 136 | 24 empresas con RUC |
| `transacciones.csv` | 14 651 | 13 076 efectivo, 1 292 billetera, 283 crédito |
| `detalle_transaccion.csv` | 41 998 | Cantidades enteras |
| `reglas_meta.csv` | 41 | `sueldo_fijo` = `monto_fijo` + movimiento programado |
| `forecast_ajustes.csv` | 4 | |
| `alertas.csv` | 18 | Pedro: las 4 que calcula el backend |
| `consentimientos.csv` | 10 | `CNS-0001` de Pedro inactivo |
| `saldo_diario.csv` | 4 267 | `deficit_14d` null donde la ventana pasa del corte |
| `eventos.csv` | 23 | |
| `predicciones_saldo.csv` | 60 | Solo Pedro: la salida real del backend al 14/11 (`lgbm_cuantiles-1.0` y `naive-estacional-0.1.0`) |
| `predicciones_fiado.csv` | 31 | Baseline del backend (`riesgo-atraso-baseline-0.1.0`, umbrales ≥ 0.6 alto, ≥ 0.3 medio), Pedro incluido |
| `score_salud.csv` | 170 | Un score por empresa y mes con datos |

## 6. Pedro (`EMP-0001`) al corte

Historia día por día (generador §2.2, flujo pseudoaleatorio propio): vende ~S/ 600 al día con su patrón de semana y
quincena (todas sus ventas con detalle de productos), repone cada mañana al contado ~47 % de lo vendido el día anterior,
hace una compra grande del mes en el mercado mayorista (día 5) y el resto le llega **a crédito**: Mayorista Santa Anita
(viernes) y Lácteos del Sur (jueves) a 7 días, Abarrotes El Sol y Distribuidora Andina a 15 días; paga a tiempo. Su sueldo
fijo es de S/ 1 350 el día 30 (vinculado a `PRG-0003` solo cuando retira el monto exacto, como el registrador del backend)
y además saca montos sueltos "para la casa". En agosto y a inicios de septiembre no anotaba todos los días.

| Indicador (backend sobre `data/csv`, 14/11, forecast LightGBM) | Valor |
|---|---:|
| Saldo de caja | **S/ 2 340.00** |
| Ingresos / egresos de caja de noviembre (1–14) | S/ 7 976.00 / S/ 6 697.70 |
| Retiros de noviembre / lo usual al 14 (prom. sep. y oct.) / sueldo prorrateado | S/ 1 005 / S/ 305 / S/ 630 |
| Fiados pendientes (`FIA-0045/46/47`) | S/ 310.00 |
| Pedidos pendientes | Lácteos del Sur 233.40 (19/11), Santa Anita 475.30 (20/11), El Sol 2 340 (27/11), **Andina `PED-0012` 2 400 (30/11)** |
| 30/11 (pago a Andina + sueldo) | p50 **−S/ 650.00** (p10 −1 221.99 / p90 57.71; prob. de déficit 0.94). Baseline: −S/ 1 592.42 |
| Causas del faltante | S/ 700 más de retiros que lo usual · pedido S/ 400 mayor a lo que vende de eso (S/ 2 000) · S/ 310 en fiados |
| Chequeo del pedido / pedir 1 800 en 2 partes | −50 / 550 / 850 · simulador: S/ 850 |
| Score de salud (ago → nov) | 79 → 89 → 91 → 91 · credit scoring: 86 (verde) |
| Saldo mínimo de la historia | S/ 1 244.10 (nunca bajo su mínimo de S/ 800) |

- **Por qué el flujo ordinario tiene esa forma.** El LightGBM se entrenó con bodegas cuyo egreso diario es ~55 % del
  ingreso con un pago grande al mes: con una historia sin ese pago mensual el modelo predice un pago "fantasma" de
  ~S/ 1 200 cada día (error a 1 día ≈ S/ 900). Con la compra mensual al contado su error a 1 día en Pedro es S/ 82
  (baseline S/ 145) y el backtest de 14 días le gana al baseline (MAE del saldo 675 vs 823; ver `backend/README.md`).
- **Perillas de la calibración** (sin tocar el patrón diario): el recibo de luz esperado de noviembre (`PRG-0001`,
  S/ 176.37; los de ago–oct fueron 168.40, 176.90 y 183.30), el pedido de campaña a El Sol (S/ 2 340), los retiros de
  noviembre (lo usual + 700) y lo que vende de lo que trae Andina en las 4 semanas previas (S/ 3 500 → S/ 2 000 hasta
  el 30/11). El saldo de 2 340 se cuadra repartiendo el residuo en la reposición de agosto (fuera de toda ventana del
  forecast y de las alertas).
- **Filas de resultado de Pedro que salen del backend.** `predicciones_saldo` (LightGBM y baseline) y sus `alertas` se
  leen de [`demo_pedro_backend.json`](./demo_pedro_backend.json), que escribe
  [`pipeline_python/exportar_demo_backend.py`](./pipeline_python/exportar_demo_backend.py) corriendo el backend sobre
  este mismo CSV (no son entrada del forecast: basta generar → exportar → generar). Nada está escrito a mano.

## 7. Fuga de datos

- Todo lo que existe a la fecha de corte tiene `creado_en` y pagos anteriores a la hora de corte del 14/11 (el auditor lo verifica).
- `cuaderno_fiado.pago_tardio`, `saldo_diario.deficit_14d` y `eventos` son **etiquetas**, nunca features; `clientes.perfil_pago` es una variable oculta del generador.

## 8. Cómo regenerar, auditar y cargar

```bash
node data/generate_synthetic_data.mjs                    # CSV + eval (determinístico; GEN_OUT_DIR=<dir> escribe en otra carpeta)
# si cambió la historia de Pedro: exportar lo que calcula el backend y volver a generar (ver pipeline_python/exportar_demo_backend.py)
PYTHONPATH=backend python data/pipeline_python/generar_schema.py   # schema.sql y schema_esquema.json desde models.py
node data/audit_quality.mjs                              # 30 controles contra el esquema real
node data/audit_mutations.mjs                            # prueba que el auditor detecta 22 errores inyectados
python data/pipeline_python/validate_pandera.py          # chequeo complementario (pandas + pandera)
python data/load_postgres.py --url <BD de pruebas> [--recrear]    # o: node data/load_postgres.mjs
```
