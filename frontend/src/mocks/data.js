// Datos sintéticos de la demo (Pedro, Bodega Don Pedro). Todas las cifras son ficticias.
// Mantienen las mismas formas que contract.md. Campos marcados "EXT" son extensiones propuestas al contrato
// que el front necesita para el mockup; están documentadas en frontend/README.md.

export const CORTE = '2026-11-14'

const meta = (modelo, modelo_version, extra = {}) => ({
  request_id: `req_${Math.random().toString(16).slice(2, 8)}`,
  generado_en: new Date().toISOString(),
  modelo,
  modelo_version,
  prompt_version: null,
  fallback_usado: false,
  latencia_ms: 120 + Math.round(Math.random() * 120),
  ...extra,
})
export { meta }

export const empresa = {
  empresa_id: 'EMP-0001',
  nombre: 'Bodega Don Pedro',
  duenio: 'Pedro',
}

// ---------- F2 Resumen ----------
export const resumenPedro = {
  empresa_id: 'EMP-0001',
  periodo: '2026-11',
  corte: CORTE,
  dias_con_datos: 92,
  dias_requeridos_forecast: 28,
  indicadores: {
    saldo_caja_negocio: { valor: 2340.0, variacion_pct: null },
    ingresos_mes: { valor: 8540.0, variacion_pct: -6.2 },
    egresos_mes: { valor: 7310.0, variacion_pct: 4.8 },
    ganancia_neta: { valor: 980.0, variacion_pct: -18.5, es_aproximada: true, rango: [760.0, 1210.0] },
    retiros_personales: { valor: 1900.0, sueldo_fijo_definido: 400.0, promedio_historico: 1200.0, sueldo_frecuencia: 'semanal', exceso_vs_promedio: 700.0 },
    pendiente_cobro: { valor: 445.0, n_fiados: 7 },
    pagos_pendientes: { valor: 3215.0, n_obligaciones: 7, detalle: 'Andina, 5 pedidos chicos y RUS' }, // detalle: EXT
  },
  variacion_vs: '2026-10 al mismo día de corte',
}

// Escenario 'sano': mismo Pedro con 92 días de datos, pero la caja sí le alcanza para sus pagos.
export const resumenSano = {
  empresa_id: 'EMP-0001',
  periodo: '2026-11',
  corte: CORTE,
  dias_con_datos: 92,
  dias_requeridos_forecast: 28,
  indicadores: {
    saldo_caja_negocio: { valor: 3620.0, variacion_pct: null },
    ingresos_mes: { valor: 9680.0, variacion_pct: 5.4 },
    egresos_mes: { valor: 7420.0, variacion_pct: -1.2 },
    ganancia_neta: { valor: 1760.0, variacion_pct: 9.8, es_aproximada: true, rango: [1540.0, 1980.0] },
    retiros_personales: { valor: 1100.0, sueldo_fijo_definido: 400.0, promedio_historico: 1150.0, sueldo_frecuencia: 'semanal', exceso_vs_promedio: 0.0 },
    pendiente_cobro: { valor: 85.0, n_fiados: 3 },
    pagos_pendientes: { valor: 2520.0, n_obligaciones: 3, detalle: 'Andina, Panadería y RUS' },
  },
  variacion_vs: '2026-10 al mismo día de corte',
}

export const resumenNuevo = {
  empresa_id: 'EMP-0001',
  periodo: '2026-11',
  corte: CORTE,
  dias_con_datos: 3,
  dias_requeridos_forecast: 28,
  indicadores: {
    saldo_caja_negocio: { valor: 1120.0, variacion_pct: null },
    ingresos_mes: { valor: 1870.0, variacion_pct: null },
    egresos_mes: { valor: 1600.0, variacion_pct: null },
    ganancia_neta: { valor: 235.0, variacion_pct: null, es_aproximada: true, rango: [150.0, 320.0] },
    retiros_personales: { valor: 150.0, sueldo_fijo_definido: null, promedio_historico: null, sueldo_frecuencia: null, exceso_vs_promedio: null },
    pendiente_cobro: { valor: 0, n_fiados: 0 },
    pagos_pendientes: { valor: 0, n_obligaciones: 0 },
  },
  variacion_vs: null,
}

// ---------- F3 Forecast ----------
// Serie determinística: la caja baja por compras de mercadería hasta el 29/11, cae con el pago de Andina el 30/11
// y se recupera despacio. Se generan p10/p50/p90 con una banda que se abre con el horizonte.
function buildSerie() {
  const out = []
  const start = new Date('2026-11-15T12:00:00-05:00')
  let p50 = 2340
  const noise = [40, -30, 55, 20, -45, 35, 60, -20, 25, -35, 50, 10, -25, 45, 0, 30, -40, 25, 55, -15, 40, 10, -30, 35, 20, -10, 45, -25, 30, 15]
  for (let i = 0; i < 30; i++) {
    const d = new Date(start.getTime() + i * 86400000)
    const fecha = d.toISOString().slice(0, 10)
    let ingresos = 610 + (d.getDay() === 6 || d.getDay() === 0 ? 120 : 0)
    let egresos = 640 // mercadería y gastos del día
    if (fecha === '2026-11-16') egresos += 180 // luz y agua
    if (fecha === '2026-11-20') ingresos += 190 // fiados que esperas cobrar (ponderado)
    if (fecha === '2026-11-30') egresos += 2400 // pago a Andina
    if (fecha > '2026-11-30') egresos = 560
    p50 = p50 + ingresos - egresos + noise[i]
    if (fecha === '2026-11-30') p50 = -650
    const spread = 90 + i * 14
    out.push({
      fecha,
      ingresos_esperados: ingresos,
      egresos_esperados: egresos,
      p10: Math.round(p50 - spread),
      p50: Math.round(p50),
      p90: Math.round(p50 + spread * 0.85),
    })
  }
  return out
}

export const forecastPedro = () => ({
  empresa_id: 'EMP-0001',
  fecha_corte: CORTE,
  horizonte_dias: 30,
  saldo_actual: 2340.0,
  minimo_operativo: 800.0,
  serie: buildSerie(),
  dia_critico: {
    fecha: '2026-11-30',
    saldo_p50: -650.0,
    probabilidad_deficit: 0.74,
    obligacion_asociada: { tipo: 'prestamo_proveedor', id: 'PED-0012', proveedor: 'Distribuidora Andina', monto: 2400.0 },
  },
  disponible_para_gastar: {
    valor: 0.0,
    formula: 'saldo_actual + cobros_esperados − pagos_comprometidos_hasta_proximo_vencimiento − minimo_operativo − reserva_impuestos',
    // pagos_comprometidos: Andina 2 400 + RUS 20 + pedidos chicos que vencen antes (180 + 140 + 95 + 120)
    componentes: { saldo_actual: 2340.0, cobros_esperados: 190.0, pagos_comprometidos: 2955.0, minimo_operativo: 800.0, reserva_impuestos: 20.0 },
    mensaje: 'Hoy no hagas gastos extra: arriesgas el pago del 30/11.',
  },
  // EXT: lista "Lo que viene" del mockup (30 días)
  proximos_eventos: [
    { fecha: '2026-11-16', concepto: 'Planilla luz y agua', monto: -180.0, tipo: 'gasto_negocio' },
    { fecha: '2026-11-20', concepto: 'Fiados que esperas cobrar', monto: 190.0, tipo: 'cobro_fiado', ponderado: true },
    { fecha: '2026-11-30', concepto: 'Pago a Andina', monto: -2400.0, tipo: 'pago_proveedor', ref_id: 'PED-0012' },
    { fecha: '2026-12-15', concepto: 'RUS', monto: -20.0, tipo: 'pago_impuesto' },
  ],
  ajustes_manuales_aplicados: [],
  baseline: { nombre: 'naive_estacional', mae_backtest: 212.4 },
  modelo_metricas: { mae_backtest: 158.1, cobertura_p10_p90: 0.82 },
  fundamento: 'Tus ventas y gastos de los últimos 3 meses, tus pagos con fecha y los fiados según qué tan probable es que te paguen.', // EXT
  limites: 'No considera gastos o ventas que no hayas anotado. Mientras más lejos el día, más ancho el rango.', // EXT
  confianza: 'media', // EXT
  meta: meta('forecast-lgbm-quantile', '0.3.1'),
})

export const forecastNuevo = () => ({
  empresa_id: 'EMP-0001',
  fecha_corte: CORTE,
  horizonte_dias: 30,
  disponible: false, // EXT
  dias_con_datos: 3, // EXT
  dias_requeridos: 28,
  saldo_actual: 1120.0,
  serie: [],
  meta: meta('forecast-lgbm-quantile', '0.3.1'),
})

// Escenario 'sano': vende un poco más de lo que gasta cada día, así que la caja sube hasta el 29/11,
// baja con el pago de Andina el 30/11 y sigue muy por encima del mínimo operativo (S/ 800).
export const SALDO_SANO = 3620
function buildSerieSano() {
  const out = []
  const start = new Date('2026-11-15T12:00:00-05:00')
  let p50 = SALDO_SANO
  const noise = [30, -25, 40, 15, -35, 25, 45, -15, 20, -30, 35, 10, -20, 30, 0, 25, -30, 20, 40, -10, 30, 5, -25, 30, 15, -10, 35, -20, 25, 10]
  for (let i = 0; i < 30; i++) {
    const d = new Date(start.getTime() + i * 86400000)
    const fecha = d.toISOString().slice(0, 10)
    let ingresos = 660 + (d.getDay() === 6 || d.getDay() === 0 ? 130 : 0)
    let egresos = 590
    if (fecha === '2026-11-16') egresos += 180 // luz y agua
    if (fecha === '2026-11-18') egresos += 100 // Panadería San Jorge
    if (fecha === '2026-11-20') ingresos += 60 // fiados que esperas cobrar (ponderado)
    if (fecha === '2026-11-30') egresos += 2400 // pago a Andina
    if (fecha > '2026-11-30') egresos = 560
    p50 = p50 + ingresos - egresos + noise[i]
    const spread = 80 + i * 12
    out.push({
      fecha,
      ingresos_esperados: ingresos,
      egresos_esperados: egresos,
      p10: Math.round(p50 - spread),
      p50: Math.round(p50),
      p90: Math.round(p50 + spread * 0.85),
    })
  }
  return out
}

/** p50 del día de pago a Andina (30/11) en el escenario sano: base del simulador. */
export const saldoSanoAl3011 = () => buildSerieSano().find((p) => p.fecha === '2026-11-30').p50

export const forecastSano = () => ({
  empresa_id: 'EMP-0001',
  fecha_corte: CORTE,
  horizonte_dias: 30,
  saldo_actual: SALDO_SANO,
  minimo_operativo: 800.0,
  serie: buildSerieSano(),
  dia_critico: null, // ningún día baja del mínimo operativo
  disponible_para_gastar: {
    valor: 180.0,
    formula: 'saldo_actual + cobros_esperados − pagos_comprometidos_hasta_proximo_vencimiento − minimo_operativo − reserva_impuestos',
    // pagos_comprometidos: Andina 2 400 + Panadería 100 + luz y agua 180
    componentes: { saldo_actual: SALDO_SANO, cobros_esperados: 60.0, pagos_comprometidos: 2680.0, minimo_operativo: 800.0, reserva_impuestos: 20.0 },
    mensaje: 'Puedes gastar hasta S/ 180 hoy y igual pagas a Andina el 30/11.',
  },
  proximos_eventos: [
    { fecha: '2026-11-16', concepto: 'Planilla luz y agua', monto: -180.0, tipo: 'gasto_negocio' },
    { fecha: '2026-11-18', concepto: 'Pago a Panadería San Jorge', monto: -100.0, tipo: 'pago_proveedor', ref_id: 'PED-0013' },
    { fecha: '2026-11-20', concepto: 'Fiados que esperas cobrar', monto: 60.0, tipo: 'cobro_fiado', ponderado: true },
    { fecha: '2026-11-30', concepto: 'Pago a Andina', monto: -2400.0, tipo: 'pago_proveedor', ref_id: 'PED-0012', cubierto: true },
    { fecha: '2026-12-15', concepto: 'RUS', monto: -20.0, tipo: 'pago_impuesto' },
  ],
  ajustes_manuales_aplicados: [],
  baseline: { nombre: 'naive_estacional', mae_backtest: 198.7 },
  modelo_metricas: { mae_backtest: 141.3, cobertura_p10_p90: 0.84 },
  fundamento: 'Tus ventas y gastos de los últimos 3 meses, tus pagos con fecha y los fiados según qué tan probable es que te paguen.',
  limites: 'No considera gastos o ventas que no hayas anotado. Mientras más lejos el día, más ancho el rango.',
  confianza: 'alta',
  meta: meta('forecast-lgbm-quantile', '0.3.1'),
})

// ---------- F4 Fiados / pedidos ----------
// Pedro: total_pendiente = suma de los 7 (445); total_vencido = vencidos + por vencer (120 + 95 + 60 + 35 = 310),
// mismo criterio que antes (215 = Sra. Carmen + Don Luis).
export const fiados = () => ({
  total_pendiente: 445.0,
  total_vencido: 310.0,
  items: [
    {
      fiado_id: 'FIA-0045', cliente_id: 'CLI-0102', cliente: 'Sra. Carmen', detalle: 'panes, leche',
      monto: 120.0, fecha: '2026-10-27', dias_transcurridos: 18, estado: 'vencido',
      riesgo_atraso: { probabilidad: 0.72, nivel: 'alto', baseline_probabilidad: 0.6 },
      accion_sugerida: { tipo: 'recordatorio', texto_boton: 'Recordarle' },
    },
    {
      fiado_id: 'FIA-0046', cliente_id: 'CLI-0087', cliente: 'Don Luis', detalle: 'arroz, aceite',
      monto: 95.0, fecha: '2026-11-02', dias_transcurridos: 12, estado: 'por_vencer',
      riesgo_atraso: { probabilidad: 0.45, nivel: 'medio', baseline_probabilidad: 0.6 },
      accion_sugerida: { tipo: 'recordatorio', texto_boton: 'Recordarle' },
    },
    {
      fiado_id: 'FIA-0047', cliente_id: 'CLI-0110', cliente: 'Vecina Rosa', detalle: 'gaseosas',
      monto: 95.0, fecha: '2026-11-05', dias_transcurridos: 9, estado: 'pendiente',
      riesgo_atraso: { probabilidad: 0.18, nivel: 'bajo', baseline_probabilidad: 0.6 },
      accion_sugerida: null,
    },
    {
      fiado_id: 'FIA-0048', cliente_id: 'CLI-0095', cliente: 'Don Jorge', detalle: 'fideos, atún',
      monto: 60.0, fecha: '2026-10-22', dias_transcurridos: 23, estado: 'vencido',
      riesgo_atraso: { probabilidad: 0.66, nivel: 'alto', baseline_probabilidad: 0.6 },
      accion_sugerida: { tipo: 'recordatorio', texto_boton: 'Recordarle' },
    },
    {
      fiado_id: 'FIA-0049', cliente_id: 'CLI-0121', cliente: 'Sra. Elena', detalle: 'detergente',
      monto: 35.0, fecha: '2026-11-03', dias_transcurridos: 11, estado: 'por_vencer',
      riesgo_atraso: { probabilidad: 0.38, nivel: 'medio', baseline_probabilidad: 0.6 },
      accion_sugerida: { tipo: 'recordatorio', texto_boton: 'Recordarle' },
    },
    {
      fiado_id: 'FIA-0050', cliente_id: 'CLI-0133', cliente: 'Joven Miguel', detalle: 'galletas, gaseosa',
      monto: 18.0, fecha: '2026-11-10', dias_transcurridos: 4, estado: 'pendiente',
      riesgo_atraso: { probabilidad: 0.12, nivel: 'bajo', baseline_probabilidad: 0.6 },
      accion_sugerida: null,
    },
    {
      fiado_id: 'FIA-0051', cliente_id: 'CLI-0140', cliente: 'Sra. Lucía', detalle: 'azúcar',
      monto: 22.0, fecha: '2026-11-12', dias_transcurridos: 2, estado: 'pendiente',
      riesgo_atraso: { probabilidad: 0.1, nivel: 'bajo', baseline_probabilidad: 0.6 },
      accion_sugerida: null,
    },
  ],
  fundamento: 'Cada riesgo sale de cuánto se demoró esa persona antes y de cuántos días lleva este fiado.', // EXT
  limites: 'Es una estimación; no sabe si el vecino tuvo un imprevisto.', // EXT
  meta: meta('riesgo-atraso-baseline', '0.1.0'),
})

export const fiadosSano = () => ({
  total_pendiente: 85.0,
  total_vencido: 0.0,
  items: [
    {
      fiado_id: 'FIA-0045', cliente_id: 'CLI-0102', cliente: 'Sra. Carmen', detalle: 'pan y leche',
      monto: 35.0, fecha: '2026-11-08', dias_transcurridos: 6, estado: 'pendiente',
      riesgo_atraso: { probabilidad: 0.15, nivel: 'bajo', baseline_probabilidad: 0.6 },
      accion_sugerida: null,
    },
    {
      fiado_id: 'FIA-0046', cliente_id: 'CLI-0087', cliente: 'Don Luis', detalle: 'arroz',
      monto: 30.0, fecha: '2026-11-10', dias_transcurridos: 4, estado: 'pendiente',
      riesgo_atraso: { probabilidad: 0.2, nivel: 'bajo', baseline_probabilidad: 0.6 },
      accion_sugerida: null,
    },
    {
      fiado_id: 'FIA-0047', cliente_id: 'CLI-0110', cliente: 'Vecina Rosa', detalle: 'gaseosas',
      monto: 20.0, fecha: '2026-11-12', dias_transcurridos: 2, estado: 'pendiente',
      riesgo_atraso: { probabilidad: 0.08, nivel: 'bajo', baseline_probabilidad: 0.6 },
      accion_sugerida: null,
    },
  ],
  fundamento: 'Cada riesgo sale de cuánto se demoró esa persona antes y de cuántos días lleva este fiado.',
  limites: 'Es una estimación; no sabe si el vecino tuvo un imprevisto.',
  meta: meta('riesgo-atraso-baseline', '0.1.0'),
})

export const pedidos = () => ({
  total_pendiente: 3195.0,
  items: [
    {
      pedido_id: 'PED-0012', proveedor: 'Distribuidora Andina', monto: 2400.0, monto_pendiente: 2400.0,
      fecha_pedido: '2026-11-13', fecha_vencimiento: '2026-11-30', estado: 'pendiente', dias_para_vencer: 16,
    },
    {
      pedido_id: 'PED-0015', proveedor: 'Avícola La Granja', monto: 95.0, monto_pendiente: 95.0,
      fecha_pedido: '2026-11-05', fecha_vencimiento: '2026-11-12', estado: 'vencido', dias_para_vencer: -2,
    },
    {
      pedido_id: 'PED-0013', proveedor: 'Panadería San Jorge', monto: 180.0, monto_pendiente: 180.0,
      fecha_pedido: '2026-11-11', fecha_vencimiento: '2026-11-18', estado: 'pendiente', dias_para_vencer: 4,
    },
    {
      pedido_id: 'PED-0014', proveedor: 'Lácteos del Valle', monto: 140.0, monto_pendiente: 140.0,
      fecha_pedido: '2026-11-07', fecha_vencimiento: '2026-11-21', estado: 'pendiente', dias_para_vencer: 7,
    },
    {
      pedido_id: 'PED-0017', proveedor: 'Distribuidora El Sol', monto: 120.0, monto_pendiente: 120.0,
      fecha_pedido: '2026-11-11', fecha_vencimiento: '2026-11-25', estado: 'pendiente', dias_para_vencer: 11,
    },
    {
      pedido_id: 'PED-0016', proveedor: 'Abarrotes Mayorista Lima', monto: 260.0, monto_pendiente: 260.0,
      fecha_pedido: '2026-11-12', fecha_vencimiento: '2026-12-05', estado: 'pendiente', dias_para_vencer: 21,
    },
  ],
  impuestos: { impuesto_id: 'IMP-0011', estado: 'al_dia', proximo_vencimiento: '2026-12-15', monto_estimado: 20.0, nombre: 'RUS de noviembre' },
})

export const pedidosSano = () => ({
  total_pendiente: 2500.0,
  items: [
    {
      pedido_id: 'PED-0012', proveedor: 'Distribuidora Andina', monto: 2400.0, monto_pendiente: 2400.0,
      fecha_pedido: '2026-11-13', fecha_vencimiento: '2026-11-30', estado: 'pendiente', dias_para_vencer: 16,
    },
    {
      pedido_id: 'PED-0013', proveedor: 'Panadería San Jorge', monto: 100.0, monto_pendiente: 100.0,
      fecha_pedido: '2026-11-11', fecha_vencimiento: '2026-11-18', estado: 'pendiente', dias_para_vencer: 4,
    },
  ],
  impuestos: { impuesto_id: 'IMP-0011', estado: 'al_dia', proximo_vencimiento: '2026-12-15', monto_estimado: 20.0, nombre: 'RUS de noviembre' },
})

// ---------- F6 Alertas ----------
export const alertas = () => ({
  items: [
    {
      alerta_id: 'ALR-0007',
      tipo: 'faltante_caja',
      prioridad: 1,
      creada_en: '2026-11-14T08:05:00-05:00',
      fecha_evento: '2026-11-30',
      dias_para_evento: 16, // EXT
      monto: 650.0,
      probabilidad: 0.74,
      nivel_riesgo: 'alto',
      titulo: 'El 30/11 te faltarían S/ 650 para pagar a Andina',
      titulo_corto: 'El 30/11 no te alcanzará', // EXT (chat)
      insight: 'Para pagar S/ 2 400 a Distribuidora Andina te faltarían S/ 650.',
      resumen_causas: 'vendiste menos, pedido grande y fiados sin cobrar.', // EXT
      causas: [
        { descripcion: 'Vendiste menos que el mes pasado', monto: 560.0 },
        { descripcion: 'Pediste más de lo que vendes', monto: 400.0 },
        { descripcion: 'Fiados sin cobrar', monto: 445.0 },
      ],
      accion: { tipo: 'abrir_simulador', texto_boton: 'Ver qué puedo hacer', payload: { pedido_id: 'PED-0012' } },
      microexplicacion: 'Si sacas de la caja sin un monto fijo, es difícil saber cuánto puedes pedir.',
      canales: ['whatsapp', 'app'],
      estado: 'activa',
      enviada_en: null,
      meta: meta('reglas-alertas + forecast-lgbm-quantile', '0.3.1'),
    },
  ],
})

// ---------- F8 Salud ----------
// Los tres hábitos del puntaje (mismo orden y pesos que el backend: score-reglas, contract.md §8.1).
export const FACTORES_SALUD = [
  { id: 'constancia_registro', nombre: 'Anotar todos los días', peso: 0.35 },
  { id: 'separacion_personal', nombre: 'Ponerte un sueldo fijo', peso: 0.4 },
  { id: 'impuestos_al_dia', nombre: 'Impuestos al día', peso: 0.25 },
]
const FUNDAMENTO_SALUD =
  'Sale de 3 hábitos: anotar todos los días, ponerte un sueldo fijo (el que más cuenta) y tener tus impuestos al día.'

/** score = round(Σ valor × peso). Se redondea a 2 decimales antes para evitar errores de coma flotante. */
export const scoreDesdeFactores = (subs) =>
  Math.round(Math.round(subs.reduce((s, f) => s + f.valor * f.peso, 0) * 100) / 100)

/** Une los valores de un escenario { id: { valor, detalle, destacado? } } con FACTORES_SALUD. */
function armarFactores(valores) {
  return FACTORES_SALUD.map((f) => ({ ...f, destacado: true, ...valores[f.id] }))
}

// Pedro: 100·0.35 + 78·0.40 + 100·0.25 = 91.2 → 91 (mismos subindicadores que data/csv/score_salud.csv, 2026-11)
const subsPedro = armarFactores({
  constancia_registro: { valor: 100, detalle: '14 de 14 días anotando este mes' },
  separacion_personal: { valor: 78, detalle: 'Sueldo fijo de S/ 400 por semana; este mes sacaste S/ 1 900 (S/ 700 más de lo usual)' },
  impuestos_al_dia: { valor: 100, detalle: 'Al día' },
})

// Sano: 95·0.35 + 80·0.40 + 100·0.25 = 90.25 → 90
const subsSano = armarFactores({
  constancia_registro: { valor: 95, detalle: '13 de 14 días anotando este mes' },
  separacion_personal: { valor: 80, detalle: 'Sueldo fijo de S/ 400 por semana; este mes sacaste S/ 1 100' },
  impuestos_al_dia: { valor: 100, detalle: 'Al día' },
})

// Nuevo (día 3): 10·0.35 + 50·0.40 + 100·0.25 = 48.5 → 49
const subsNuevo = armarFactores({
  constancia_registro: { valor: 10, detalle: '3 de 30 días anotando; con más días se verá mejor' },
  separacion_personal: { valor: 50, detalle: 'Aún no tienes un sueldo fijo definido' },
  impuestos_al_dia: { valor: 100, detalle: 'Al día' },
})

export const salud = () => ({
  score: scoreDesdeFactores(subsPedro), // 91
  score_anterior: 91,
  etapa_actual: 'crecer', // backend: ≥ 90 → crecer
  etapas: ['organizar', 'estabilizar', 'proteger', 'crecer'], // EXT
  subindicadores: subsPedro,
  historial: [
    { mes: '2026-08', score: 79 },
    { mes: '2026-09', score: 89 },
    { mes: '2026-10', score: 91 },
    { mes: '2026-11', score: 91 },
  ],
  rachas: [{ tipo: 'semanas_registrando', valor: 4 }],
  metas_activas: [
    { meta_id: 'MET-0004', plantilla: 'apartar_para_pedido', titulo: 'Apartar para el pedido', detalle: 'S/ 1 de cada S/ 10 que vendes', acumulado: 420.0, estado: 'activa' },
  ],
  consentimiento_compartir_historial: false,
  fundamento: FUNDAMENTO_SALUD,
  meta: meta('score-reglas', '0.1.0'),
})

export const saludSano = () => ({
  score: scoreDesdeFactores(subsSano), // 90
  score_anterior: 86,
  etapa_actual: 'proteger',
  etapas: ['organizar', 'estabilizar', 'proteger', 'crecer'],
  subindicadores: subsSano,
  historial: [
    { mes: '2026-08', score: 76 },
    { mes: '2026-09', score: 82 },
    { mes: '2026-10', score: 86 },
    { mes: '2026-11', score: 90 },
  ],
  rachas: [{ tipo: 'semanas_registrando', valor: 12 }],
  metas_activas: [
    { meta_id: 'MET-0004', plantilla: 'apartar_para_pedido', titulo: 'Apartar para el pedido', detalle: 'S/ 1 de cada S/ 10 que vendes', acumulado: 760.0, estado: 'activa' },
  ],
  consentimiento_compartir_historial: false,
  fundamento: FUNDAMENTO_SALUD,
  meta: meta('score-reglas', '0.1.0'),
})

export const saludNuevo = () => ({
  score: scoreDesdeFactores(subsNuevo), // 49
  score_anterior: null,
  etapa_actual: 'organizar',
  etapas: ['organizar', 'estabilizar', 'proteger', 'crecer'],
  subindicadores: subsNuevo,
  historial: [{ mes: '2026-11', score: 49 }],
  rachas: [{ tipo: 'semanas_registrando', valor: 0 }],
  metas_activas: [],
  consentimiento_compartir_historial: false,
  fundamento: FUNDAMENTO_SALUD,
  meta: meta('score-reglas', '0.1.0'),
})

// ---------- Catálogo (para interpretar ventas) ----------
export const catalogo = {
  cerveza: { producto_id: 'PRD-0031', producto: 'Cerveza 620 ml', precio_unitario: 6.5 },
}

// ---------- Movimientos (GET /movimientos) ----------
// [fecha_hora, tipo, monto, metodo_pago, canal, descripcion, contraparte, items?]
const movsNuevo = [
  ['2026-11-12T07:10', 'venta', 420, 'efectivo', 'voz', 'Ventas de la mañana', null],
  ['2026-11-12T09:30', 'compra', 600, 'efectivo', 'texto', 'Gaseosas y cervezas', 'Distribuidora Andina'],
  ['2026-11-12T13:05', 'venta', 210, 'billetera_digital', 'billetera_api', 'Ventas por billetera', null],
  ['2026-11-12T19:40', 'venta', 310, 'efectivo', 'voz', 'Ventas de la tarde', null],
  ['2026-11-13T08:00', 'gasto_negocio', 60, 'efectivo', 'texto', 'Bolsas y envases', 'Mercado Ceres'],
  ['2026-11-13T11:20', 'venta', 250, 'efectivo', 'voz', 'Ventas de la mañana', null],
  ['2026-11-13T15:45', 'compra', 480, 'efectivo', 'voz', 'Pan y leche', 'Panadería San Jorge'],
  ['2026-11-13T20:10', 'venta', 180, 'billetera_digital', 'billetera_api', 'Ventas por billetera', null],
  ['2026-11-14T07:30', 'venta', 200, 'efectivo', 'voz', 'Ventas de la mañana', null],
  ['2026-11-14T09:00', 'pago_impuesto', 20, 'efectivo', 'texto', 'RUS de octubre', 'SUNAT'],
  ['2026-11-14T10:42', 'venta', 13, 'efectivo', 'voz', '2 cervezas 620 ml', null,
    [{ producto_id: 'PRD-0031', producto: 'Cerveza 620 ml', cantidad: 2, precio_unitario: 6.5, subtotal: 13 }]],
  ['2026-11-14T12:15', 'gasto_negocio', 440, 'efectivo', 'texto', 'Luz del local', 'Luz del Sur'],
  ['2026-11-14T13:40', 'venta', 287, 'billetera_digital', 'billetera_api', 'Ventas por billetera', null],
]

const movsPedro = [
  ['2026-11-13T08:10', 'venta', 640, 'efectivo', 'voz', 'Ventas de la mañana', null],
  ['2026-11-13T10:00', 'compra', 2400, 'credito', 'voz', 'Pedido para el 30/11', 'Distribuidora Andina'],
  ['2026-11-13T12:30', 'cobro_fiado', 50, 'efectivo', 'voz', 'Abono de fiado', 'Sra. Carmen'],
  ['2026-11-13T16:20', 'gasto_negocio', 35, 'efectivo', 'texto', 'Bolsas y envases', 'Mercado Ceres'],
  ['2026-11-13T19:50', 'venta', 520, 'efectivo', 'voz', 'Ventas de la tarde', null],
  ['2026-11-13T20:30', 'venta', 160, 'billetera_digital', 'billetera_api', 'Ventas por billetera', null],
  ['2026-11-14T07:20', 'venta', 380, 'efectivo', 'voz', 'Ventas de la mañana', null],
  ['2026-11-14T08:45', 'compra', 520, 'efectivo', 'texto', 'Pan, leche y huevos', 'Panadería San Jorge'],
  ['2026-11-14T09:30', 'venta', 95, 'credito', 'foto', 'Fiado: arroz y aceite', 'Don Luis'],
  ['2026-11-14T10:42', 'venta', 13, 'efectivo', 'voz', '2 cervezas 620 ml', null,
    [{ producto_id: 'PRD-0031', producto: 'Cerveza 620 ml', cantidad: 2, precio_unitario: 6.5, subtotal: 13 }]],
  ['2026-11-14T11:15', 'pago_impuesto', 20, 'efectivo', 'texto', 'RUS de octubre', 'SUNAT'],
  ['2026-11-14T12:05', 'venta', 210, 'billetera_digital', 'billetera_api', 'Ventas por billetera', null],
]

const movsSano = [
  ['2026-11-13T07:50', 'venta', 690, 'efectivo', 'voz', 'Ventas de la mañana', null],
  ['2026-11-13T10:00', 'compra', 2400, 'credito', 'voz', 'Pedido para el 30/11', 'Distribuidora Andina'],
  ['2026-11-13T12:10', 'cobro_fiado', 40, 'efectivo', 'voz', 'Pagó su fiado', 'Sra. Carmen'],
  ['2026-11-13T16:00', 'gasto_negocio', 30, 'efectivo', 'texto', 'Bolsas y envases', 'Mercado Ceres'],
  ['2026-11-13T19:40', 'venta', 560, 'efectivo', 'voz', 'Ventas de la tarde', null],
  ['2026-11-13T20:30', 'venta', 210, 'billetera_digital', 'billetera_api', 'Ventas por billetera', null],
  ['2026-11-14T07:15', 'venta', 420, 'efectivo', 'voz', 'Ventas de la mañana', null],
  ['2026-11-14T08:40', 'compra', 380, 'efectivo', 'texto', 'Pan, leche y huevos', 'Panadería San Jorge'],
  ['2026-11-14T09:30', 'pago_proveedor', 150, 'efectivo', 'texto', 'Pago a tiempo', 'Lácteos del Valle'],
  ['2026-11-14T10:42', 'venta', 13, 'efectivo', 'voz', '2 cervezas 620 ml', null,
    [{ producto_id: 'PRD-0031', producto: 'Cerveza 620 ml', cantidad: 2, precio_unitario: 6.5, subtotal: 13 }]],
  ['2026-11-14T11:15', 'pago_impuesto', 20, 'efectivo', 'texto', 'RUS de octubre', 'SUNAT'],
  ['2026-11-14T12:05', 'venta', 260, 'billetera_digital', 'billetera_api', 'Ventas por billetera', null],
]

const INGRESO = new Set(['venta', 'cobro_fiado', 'prestamo_recibido', 'otro_ingreso'])

/** Construye la lista (más reciente primero) con saldo_post que termina en saldoFinal */
function buildMovs(rows, saldoFinal, prefijo) {
  const base = rows.map(([fh, tipo, monto, metodo_pago, canal, descripcion, contraparte, items], i) => ({
    movimiento_id: `MOV-${prefijo}${String(i + 1).padStart(3, '0')}`,
    fecha_hora: `${fh}:00-05:00`,
    tipo,
    categoria: null,
    descripcion, // EXT: texto corto para la lista
    items: items || [], // EXT
    monto,
    moneda: 'PEN',
    metodo_pago,
    contraparte,
    canal,
    confianza_extraccion: canal === 'voz' ? 0.92 : canal === 'foto' ? 0.8 : 1,
    afecta_caja: metodo_pago !== 'credito',
  }))
  let saldo = saldoFinal
  for (let i = base.length - 1; i >= 0; i--) {
    base[i].saldo_post = saldo
    const m = base[i]
    if (m.afecta_caja) saldo += INGRESO.has(m.tipo) ? -m.monto : m.monto
  }
  return base.reverse()
}

export const movimientos = (escenario) =>
  escenario === 'nuevo'
    ? buildMovs(movsNuevo, 1120, '0')
    : escenario === 'sano'
      ? buildMovs(movsSano, SALDO_SANO, '2')
      : buildMovs(movsPedro, 2340, '1')

// ---------- Por escenario ('pedro' | 'sano' | 'nuevo') ----------
export const SALDO_INICIAL = { pedro: 2340, sano: SALDO_SANO, nuevo: 1120 }
export const resumenDe = (e) => (e === 'nuevo' ? resumenNuevo : e === 'sano' ? resumenSano : resumenPedro)
export const forecastDe = (e) => (e === 'nuevo' ? forecastNuevo() : e === 'sano' ? forecastSano() : forecastPedro())
export const saludDe = (e) => (e === 'nuevo' ? saludNuevo() : e === 'sano' ? saludSano() : salud())
export const fiadosDe = (e) =>
  e === 'nuevo' ? { total_pendiente: 0, total_vencido: 0, items: [], meta: meta('riesgo-atraso-baseline', '0.1.0') } : e === 'sano' ? fiadosSano() : fiados()
export const pedidosDe = (e) =>
  e === 'nuevo'
    ? { total_pendiente: 0, items: [], impuestos: { impuesto_id: 'IMP-0011', estado: 'al_dia', proximo_vencimiento: '2026-12-15', monto_estimado: 20 } }
    : e === 'sano'
      ? pedidosSano()
      : pedidos()
export const alertasDe = (e) => (e === 'pedro' || !e ? alertas() : { items: [] })
