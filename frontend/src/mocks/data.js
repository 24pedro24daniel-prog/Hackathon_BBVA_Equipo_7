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
  dias_con_datos: 92, // EXT: para el estado "día 3"
  indicadores: {
    saldo_caja_negocio: { valor: 2340.0, variacion_pct: null },
    ingresos_mes: { valor: 8540.0, variacion_pct: -6.2 },
    egresos_mes: { valor: 7310.0, variacion_pct: 4.8 },
    ganancia_neta: { valor: 980.0, variacion_pct: -18.5, es_aproximada: true, rango: [760.0, 1210.0] },
    retiros_personales: { valor: 1900.0, sueldo_fijo_definido: null, promedio_historico: 1200.0 },
    pendiente_cobro: { valor: 310.0, n_fiados: 3 },
    pagos_pendientes: { valor: 2420.0, n_obligaciones: 2, detalle: 'Andina + RUS' }, // detalle: EXT
  },
  variacion_vs: '2026-10 al mismo día de corte',
}

export const resumenNuevo = {
  empresa_id: 'EMP-0001',
  periodo: '2026-11',
  corte: CORTE,
  dias_con_datos: 3,
  dias_requeridos_forecast: 14, // EXT
  indicadores: {
    saldo_caja_negocio: { valor: 1120.0, variacion_pct: null },
    ingresos_mes: { valor: 1870.0, variacion_pct: null },
    egresos_mes: { valor: 1600.0, variacion_pct: null },
    ganancia_neta: { valor: 235.0, variacion_pct: null, es_aproximada: true, rango: [150.0, 320.0] },
    retiros_personales: { valor: 150.0, sueldo_fijo_definido: null, promedio_historico: null },
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
    componentes: { saldo_actual: 2340.0, cobros_esperados: 190.0, pagos_comprometidos: 2420.0, minimo_operativo: 800.0, reserva_impuestos: 20.0 },
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
  dias_requeridos: 14, // EXT
  saldo_actual: 1120.0,
  serie: [],
  meta: meta('forecast-lgbm-quantile', '0.3.1'),
})

// ---------- F4 Fiados / pedidos ----------
export const fiados = () => ({
  total_pendiente: 310.0,
  total_vencido: 215.0,
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
  ],
  fundamento: 'Cada riesgo sale de cuánto se demoró esa persona antes y de cuántos días lleva este fiado.', // EXT
  limites: 'Es una estimación; no sabe si el vecino tuvo un imprevisto.', // EXT
  meta: meta('riesgo-atraso-clf', '0.2.0'),
})

export const pedidos = () => ({
  total_pendiente: 2400.0,
  items: [
    {
      pedido_id: 'PED-0012', proveedor: 'Distribuidora Andina', monto: 2400.0, monto_pendiente: 2400.0,
      fecha_pedido: '2026-11-13', fecha_vencimiento: '2026-11-30', estado: 'por_vencer', dias_para_vencer: 16,
    },
  ],
  impuestos: { estado: 'al_dia', proximo_vencimiento: '2026-12-15', monto_estimado: 20.0, nombre: 'RUS de noviembre' },
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
        { descripcion: 'Fiados sin cobrar', monto: 310.0 },
      ],
      accion: { tipo: 'abrir_simulador', texto_boton: 'Ver qué puedo hacer', payload: { pedido_id: 'PED-0012' } },
      microexplicacion: 'Si pides más de lo que vendes en el plazo de pago, la caja no llega a la fecha.',
      canales: ['whatsapp', 'app'],
      estado: 'activa',
      meta: meta('reglas-alertas + forecast-lgbm-quantile', '0.3.1'),
    },
  ],
})

// ---------- F8 Salud ----------
export const salud = () => ({
  score: 71,
  score_anterior: 64,
  etapa_actual: 'estabilizar',
  etapas: ['organizar', 'estabilizar', 'proteger', 'crecer'], // EXT
  subindicadores: [
    { id: 'constancia_registro', nombre: 'Anotar todos los días', valor: 92, detalle: '92 días anotando · 4 semanas seguidas', peso: 0.2, destacado: true },
    { id: 'colchon_caja', nombre: 'Colchón de caja', valor: 45, detalle: '5 días de gastos cubiertos', peso: 0.25 },
    { id: 'pedidos_acordes', nombre: 'Pedir según lo que vendes', valor: 60, detalle: '1 de 3 pedidos fue más grande que tus ventas', peso: 0.25, destacado: true },
    { id: 'cobro_fiados', nombre: 'Cobrar fiados a tiempo', valor: 80, detalle: '8 de cada 10 fiados cobrados en menos de 15 días', peso: 0.1, destacado: true },
    { id: 'impuestos_al_dia', nombre: 'Impuestos al día', valor: 100, detalle: 'Al día', peso: 0.1 },
    { id: 'meses_sin_faltante', nombre: 'Meses sin faltantes', valor: 50, detalle: '1 de 2 meses', peso: 0.1 },
  ],
  historial: [
    { mes: '2026-08', score: 38 },
    { mes: '2026-09', score: 52 },
    { mes: '2026-10', score: 64 },
    { mes: '2026-11', score: 71 },
  ],
  rachas: [{ tipo: 'semanas_registrando', valor: 4 }],
  metas_activas: [ // EXT
    { meta_id: 'MET-0004', plantilla: 'apartar_para_pedido', titulo: 'Apartar para el pedido', detalle: 'S/ 1 de cada S/ 10 que vendes', acumulado: 420.0, estado: 'activa' },
  ],
  consentimiento_compartir_historial: false,
  meta: meta('score-reglas', '0.1.0'),
})

// ---------- Catálogo (para interpretar ventas) ----------
export const catalogo = {
  cerveza: { producto_id: 'PRD-0031', producto: 'Cerveza 620 ml', precio_unitario: 6.5 },
}
