# TuCaserito — Dataset Sintético: Supuestos, Diseño y Justificación de Realismo (MVP Bodegueros RUC 10 — 100 % Efectivo)

> **Entregable:** Datos sintéticos y evidencia (15 % de la evaluación del Hackathon BBVA *"AI Financial Life"*).
> **Esquema formal:** [`modelo_datos.dbml`](../modelo_datos.dbml) · **Diccionario:** [`diccionario_datos.md`](../diccionario_datos.md) · **DDL y Vistas:** [`data/schema.sql`](./schema.sql) · **Generador determinístico (`seed = 42`):** [`data/generate_synthetic_data.mjs`](./generate_synthetic_data.mjs) · **Reporte de Auditoría:** [`data/AUDITORIA_CALIDAD_DATOS.md`](./AUDITORIA_CALIDAD_DATOS.md).

---

## 1. Principios de privacidad, ética y reproducibilidad

1. **100 % sintético (Cero PII):** Ningún nombre, teléfono (`+5190000...`), monto ni negocio corresponde a una persona natural o jurídica real.
2. **Reproducibilidad determinística (`seed = 42`):** El generador utiliza un PRNG determinístico (`Mulberry32`) con semilla fija `seed = 42`. Cualquier miembro del equipo o jurado que ejecute `node data/generate_synthetic_data.mjs` obtiene exactamente los mismos **15,945 registros** en los **25 archivos CSV** del modelo relacional y los **150 casos** de evaluación de ingesta F1.
3. **Cero secretos en el código:** La cadena de conexión a PostgreSQL se lee exclusivamente desde `data/.env` (ignorado por [`.gitignore`](../.gitignore)), documentando su plantilla en [`data/.env.example`](./.env.example).

---

## 2. Reglas de calibración de negocio del MVP (Bodegueros RUC 10 — 100 % Efectivo)

### 2.1 Público objetivo único y acotado (`empresas.csv`)
- Las **30 empresas sintéticas (`EMP-0001` a `EMP-0030`)** representan exclusivamente **bodegas de barrio con Persona Natural con Negocio (RUC 10)** en Perú.
- En [`data/csv/empresas.csv`](./csv/empresas.csv), el **100 % (30/30)** tiene `rubro_id = 'RUB-01'` (`bodega`), `tiene_ruc = true`, `ruc` de **11 dígitos con prefijo `10`** (`10` = Persona Natural con Negocio + 8 dígitos de DNI ficticio del titular + 1 dígito verificador SUNAT, ej. `10456789012` para `EMP-0001` Bodega Don Pedro) y `regimen_tributario = 'nuevo_rus'`.
- **Escalamiento como Roadmap:** La expansión a otros rubros de Personas Naturales con Negocio (RUC 10) con dinámica similar de efectivo y cuaderno (ferreterías de barrio, farmacias independientes, bazares y librerías) queda documentada estrictamente como **roadmap** post-MVP.

### 2.2 Operación 100 % en Efectivo (`transacciones.csv` y `billeteras_digitales.csv`)
- Nuestro usuario objetivo cobra y paga **únicamente en efectivo (`cash`)** y lleva sus cuentas manualmente en cuadernos físicos (sin POS, tarjetas, transferencias ni billeteras digitales en el MVP).
- En [`data/csv/transacciones.csv`](./csv/transacciones.csv) (**8,102 registros**), los únicos valores presentes en `metodo_pago` son:
  - `'efectivo'` (`afecta_caja = true`): ventas al contado, cobros de fiados, compras al contado, pagos a proveedores, gastos del local, retiros personales y pagos del Nuevo RUS.
  - `'credito'` (`afecta_caja = false`): ventas fiadas anotadas en el cuaderno (`cuaderno_fiado`) y pedidos de mercadería a crédito a distribuidoras (`deudas`).
- La tabla [`data/csv/billeteras_digitales.csv`](./csv/billeteras_digitales.csv) se mantiene **vacía (0 registros, solo encabezados)** en el MVP; su existencia en el esquema prepara la arquitectura para el **roadmap** de integración con pagos digitales (F1.3).

### 2.3 Canales manuales, Doble Confirmación y Duplicados (`borradores.csv` y `frases_ingesta_eval.json`)
- El 100 % de los registros proviene de los **3 canales manuales del bodeguero**: `'foto'` (cuaderno físico), `'voz'` y `'texto'` (sin `'billetera_api'`).
- En [`data/csv/borradores.csv`](./csv/borradores.csv) y en los **150 casos** de [`data/eval/frases_ingesta_eval.json`](./eval/frases_ingesta_eval.json):
  - **Baja confianza (`confianza < 0.75`) y Doble Confirmación:** Se incluyen apuntes manuscritos borrosos (confusión de dígitos OCR `8` ↔ `3`/`0`, `95` ↔ `35`, como en `BOR-7790` y `BOR-7792`) y notas de voz con jerga o ruido fonético (`"bendi 3 chelas"`, `BOR-7791`) que activan obligatoriamente `pregunta_aclaratoria` antes de confirmar.
  - **Posibles duplicados sin borrado automático:** Cuando un bodeguero dicta un fiado por `'voz'` (`FIA-0044` de Don Luis) y días después envía la `'foto'` de la página del cuaderno (`BOR-7790`), el sistema señala la coincidencia en `posibles_duplicados` para revisión humana, sin eliminar ni fusionar registros por su cuenta.

### 2.4 Separación de caja y Cálculo Bancario del Sueldo ("Mínimo para vivir")
- En una microempresa RUC 10 de "caja única", un analista de crédito bancario estima el sueldo del conductor como el **promedio histórico de sus gastos fijos mínimos para vivir**.
- Para **Pedro (`EMP-0001`)**, su sueldo mensual bajo criterio bancario de mínimo para vivir está registrado en [`data/csv/movimientos_programados.csv`](./csv/movimientos_programados.csv) (`PRG-0003`, `es_sueldo = true`) en **S/ 1,350.00/mes** (con un promedio histórico a mitad de mes de `S/ 1,200.00`).
- En los primeros 14 días de noviembre de 2026, además de los retiros para cubrir su mínimo para vivir, Pedro realizó **retiros personales variables/extra por S/ 700.00** (sumando **S/ 1,900.00** en `retiro_personal`), descapitalizando la caja de la bodega antes del vencimiento con su proveedor.

### 2.5 Estacionalidad de Campaña Navideña y Nuevo RUS mal informado (`impuestos.csv` y `eventos.csv`)
- **Campaña Navideña:**
  - **Noviembre (sobrecompra de stock):** Las bodegas incrementan sus compras de mercadería e inventario estacional (panetones `PRD-0020`, bebidas, abarrotes). Esta sobrecompra explica el pedido a crédito de **S/ 2,400.00** de Pedro a *Distribuidora Andina* (`PED-0012` con vencimiento `2026-11-30`, superior en `S/ 400.00` a su rotación quincenal normal) y los eventos `alza_proveedor` en [`data/csv/eventos.csv`](./csv/eventos.csv).
  - **Diciembre (alza de ventas):** En la serie proyectada ([`data/csv/predicciones_saldo.csv`](./csv/predicciones_saldo.csv)), las ventas diarias de diciembre reflejan un incremento estacional navideño de **+42 %** (`+40 %` a `+45 %`).
- **Tramos reales del Nuevo RUS (SUNAT) y caso *"paga impuesto, pero lo informa mal"*:**
  - Según SUNAT, el **Nuevo RUS Categoría 1** paga una cuota mensual de **S/ 20.00** si los ingresos o compras mensuales no superan **S/ 5,000.00**, y **Categoría 2** paga **S/ 50.00** cuando superan **S/ 5,000.00** (hasta S/ 8,000.00).
  - En [`data/csv/impuestos.csv`](./csv/impuestos.csv) y [`data/csv/transacciones.csv`](./csv/transacciones.csv) se modelan los tres comportamientos reales:
    1. Bodegas pequeñas con ventas/compras $\le \text{S/ } 5,000.00$ que pagan correctamente **S/ 20.00**.
    2. Bodegas con ventas/compras $> \text{S/ } 5,000.00$ que actualizan y pagan correctamente **S/ 50.00** (14 empresas).
    3. **Caso *"paga impuesto, pero lo informa mal"* (11 empresas, incluido Pedro `EMP-0001`):** Cuando sus ventas o compras suben por encima de **S/ 5,000.00** por la campaña navideña, el bodeguero sigue declarando y pagando por inercia **S/ 20.00** (Categoría 1) en lugar de **S/ 50.00** (Categoría 2).

---

## 3. Volumen y cobertura de los 25 archivos CSV (`seed = 42`)

| Grupo | Archivo CSV | Filas | Propósito en el MVP y modelos de IA/ML |
|---|---|---:|---|
| **Maestras** | `rubros.csv` | 4 | `RUB-01` (`bodega`) activo en MVP + 3 rubros RUC 10 de referencia para roadmap |
| **Maestras** | `empresas.csv` | 30 | 30 bodegas RUC 10 (`EMP-0001` Don Pedro, `EMP-0002` día 3 y 28 bodegas pares en Nuevo RUS) |
| **Maestras** | `preferencias_alertas.csv` | 30 | Configuración 1–1 por empresa (máx. 2 alertas/día, silencio 21:00–07:00) |
| **Maestras** | `categorias.csv` | 13 | 6 de ingreso y 7 de egreso (sin categorías de gastos del hogar; solo `retiro_personal`) |
| **Maestras** | `productos.csv` | 133 | Catálogo con precios, costos, alias de voz (`"chela"`), panetón navideño y costos nulos controlados |
| **Maestras** | `clientes.csv` | 89 | Vecinos de fiado con alias y `perfil_pago` oculto (`puntual`, `ocasional`, `moroso`) |
| **Maestras** | `proveedores.csv` | 60 | Distribuidoras mayoristas con plazos habituales de 7 y 15 días |
| **Ingesta** | `conversaciones.csv` | 4 | Trazabilidad de turnos de WhatsApp y verificación de cifras del asistente (F7) |
| **Ingesta** | `borradores.csv` | 4 | `BOR-7781` (confirmado) + `BOR-7790`, `BOR-7791`, `BOR-7792` (`confianza < 0.75`, `pregunta_aclaratoria` y duplicados) |
| **Transaccional** | `transacciones.csv` | 8,102 | 100 % en `'efectivo'` o `'credito'` y canales manuales (`'voz'`, `'texto'`, `'foto'`) |
| **Transaccional** | `detalle_transaccion.csv` | 3,375 | Ítems vendidos con su `costo_unitario` histórico copiado al momento de la venta |
| **Cobrar / Pagar** | `cuaderno_fiado.csv` | 181 | Fiados en cuaderno físico con etiqueta `pago_tardio` para el clasificador F4 |
| **Cobrar / Pagar** | `deudas.csv` | 36 | Pedidos a crédito de campaña navideña (`PED-0012`) y préstamos informales (*gota a gota*) |
| **Cobrar / Pagar** | `billeteras_digitales.csv` | 0 | Vacía en el MVP (solo encabezados; operación 100 % en efectivo, reservada para roadmap) |
| **Cobrar / Pagar** | `impuestos.csv` | 116 | Cuotas Nuevo RUS (`S/ 20.00` y `S/ 50.00`), incluyendo casos mal informados en campaña |
| **Planificación** | `movimientos_programados.csv` | 59 | Luz/agua, alquiler y sueldo fijo bajo criterio bancario de mínimo para vivir (`es_sueldo = true`) |
| **Planificación** | `reglas_meta.csv` | 29 | Metas activas (`apartar_para_pedido`, `sueldo_fijo`, `colchon_caja`) |
| **Planificación** | `forecast_ajustes.csv` | 1 | `AJU-0003`: ajuste manual de alquiler para simulación en F3 |
| **Interacción** | `alertas.csv` | 12 | `ALR-0007` (`faltante_caja`), `ALR-0008` (`fiado_vencido`) y alertas de sobrecompra/retiros |
| **Interacción** | `consentimientos.csv` | 1 | `CNS-0001`: desactivado por defecto (`activo = false`) |
| **Etiquetas / ML** | `saldo_diario.csv` | 3,455 | Serie diaria materializada en efectivo con etiqueta `deficit_14d` |
| **Etiquetas / ML** | `eventos.csv` | 13 | Ground truth de shocks (`retiro_excesivo`, `alza_proveedor` navideño, `mes_bajo`, `cliente_no_paga`) |
| **Resultados** | `predicciones_saldo.csv` | 60 | Horizonte de 30 días (`p10`, `p50`, `p90`) con alza navideña en diciembre (`forecast-lgbm-quantile` vs `naive_estacional`) |
| **Resultados** | `predicciones_fiado.csv` | 22 | Probabilidades de atraso y de pago a 14 días (`riesgo-atraso-clf` vs `baseline_historial`) |
| **Resultados** | `score_salud.csv` | 116 | Evolución mensual (ago–nov 2026) del índice pedagógico de maduración financiera |

---

## 4. Cuadre quirúrgico de Bodega Don Pedro (`EMP-0001` al corte `2026-11-14`)

| Indicador / Entidad | Valor en BD / CSV | Referencia en [`contract.md`](../contract.md) y [`context.md`](../context.md) |
|---|---:|---|
| `saldo_caja_negocio` (`v_saldo_caja`) | **S/ 2,340.00** (100 % efectivo) | §3 Resumen y §4.1 Forecast (`saldo_actual: 2340.00`) |
| `ingresos_mes` (`2026-11-01`..`14`) | **S/ 8,540.00** (`-6.2 %` vs oct) | §3 Resumen (`8540.00`, `variacion_pct: -6.2`) |
| `egresos_mes` (`2026-11-01`..`14`) | **S/ 7,310.00** (`+4.8 %` vs oct) | §3 Resumen (`7310.00`, `variacion_pct: 4.8`) |
| `mercaderia` en egresos de nov | **S/ 4,980.00** (`68.1 %` part., `+12.4 %` var.) | §5 Análisis (`4980.00`, sobrecompra pre-campaña navideña) |
| `retiros_personales` en nov | **S/ 1,900.00** (`26.0 %` part., `+58.3 %` var.) | Sueldo mínimo para vivir (`S/ 1,350/mes`) + `S/ 700` de retiros extra sobre el promedio quincenal (`S/ 1,200`) |
| `pendiente_cobro` (`v_fiados`) | **S/ 310.00** (3 fiados: `120 + 95 + 95`) | §3 Resumen y §4.3 Fiados (`FIA-0045`, `FIA-0046`, `FIA-0047`) |
| `pagos_pendientes` (`PED-0012` + `IMP-0010`) | **S/ 2,420.00** (`2400.00 + 20.00`) | Pedido navideño a Distribuidora Andina (`PED-0012`) + RUS `S/ 20.00` (mal informado en Cat. 1) |
| `dia_critico` proyectado (`2026-11-30`) | **-S/ 650.00** (`p10: -1180`, `p90: -90`) | §4.1 Forecast y §6.1 Alerta `ALR-0007` |
| `disponible_para_gastar` (`v_disponible_gastar`) | **S/ 0.00** | §4.1 Forecast (`disponible_para_gastar.valor = 0.00`) |
| `score_salud` (`2026-08` a `2026-11`) | **38 → 52 → 64 → 71** | §8.1 Salud |

---

## 5. Prevención de fuga de datos (*Data Leakage*) en entrenamiento y evaluación

- Todas las consultas y vistas a fecha de corte filtran `creado_en <= '2026-11-14'` y `fecha_pago_total <= '2026-11-14'`.
- Las columnas `cuaderno_fiado.pago_tardio`, `saldo_diario.deficit_14d` y la tabla `eventos` se utilizan exclusivamente como **etiquetas (`ground truth`)**, nunca como features.
- La columna `clientes.perfil_pago` es una variable latente del generador (**uso ML: prohibido**); el clasificador de riesgo de atraso aprende únicamente del historial de fiados cerrados antes de `fecha_corte`.
