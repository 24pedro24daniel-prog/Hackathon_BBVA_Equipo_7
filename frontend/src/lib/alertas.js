// Alertas del backend (contract.md §6): qué hacer al tocar el botón de una alerta y cómo pintarla.
// El backend puede agregar tipos y acciones nuevos: todo lo desconocido cae en un valor genérico y nunca rompe la pantalla.

/** Ícono y tono por tipo de alerta. Tipos desconocidos: aviso genérico. */
const POR_TIPO = {
  faltante_caja: { icon: 'warning', tone: 'danger' },
  pedido_excesivo: { icon: 'warning', tone: 'warning' },
  retiro_excesivo: { icon: 'warning', tone: 'warning' },
  obligacion_proxima: { icon: 'clock', tone: 'warning' },
  gasto_inusual: { icon: 'warning', tone: 'warning' },
  caida_ventas: { icon: 'arrowDown', tone: 'warning' },
  fiado_vencido: { icon: 'clock', tone: 'warning' },
  meta_lograda: { icon: 'check', tone: 'ok' },
  resumen_semanal: { icon: 'info', tone: 'neutral' },
}
const GENERICO = { icon: 'bell', tone: 'warning' }

export const estiloAlerta = (alerta) => POR_TIPO[alerta?.tipo] ?? GENERICO

/** Solo estas alertas significan "te falta plata un día concreto": la barra de cobertura de Inicio solo aplica a ellas. */
export const esFaltante = (alerta) => alerta?.tipo === 'faltante_caja'

const qs = (obj) => {
  const p = new URLSearchParams(Object.entries(obj).filter(([, v]) => v !== undefined && v !== null && v !== ''))
  const s = p.toString()
  return s ? `?${s}` : ''
}

// Acción sugerida por el backend → ruta de la app (con el payload como parámetros).
const RUTA_POR_ACCION = {
  abrir_simulador: (p) => `/app/simulador${qs({ pedido_id: p.pedido_id })}`,
  ver_retiros: () => `/app/movimientos${qs({ tipo: 'retiro_personal' })}`,
  ver_movimientos: (p) => `/app/movimientos${qs({ tipo: p.tipo })}`,
  ver_cuentas: () => '/app/cuentas',
  recordar_cliente: (p) => `/app/cuentas${qs({ recordar: p.fiado_id ?? p.fiado_ids?.[0], cliente: p.cliente_id })}`,
  ver_progreso: () => '/app/progreso',
  ver_metas: () => '/app/progreso',
  ver_forecast: () => '/app/30-dias',
}

// Si la alerta llega sin acción (o con una que esta versión no conoce), se elige por su tipo.
const ACCION_POR_TIPO = {
  faltante_caja: 'abrir_simulador',
  pedido_excesivo: 'abrir_simulador',
  retiro_excesivo: 'ver_retiros',
  obligacion_proxima: 'ver_cuentas',
  fiado_vencido: 'recordar_cliente',
  gasto_inusual: 'ver_movimientos',
  caida_ventas: 'ver_forecast',
  meta_lograda: 'ver_progreso',
}

const TEXTO_POR_ACCION = {
  abrir_simulador: 'Ver qué puedo hacer',
  ver_retiros: 'Ver mis retiros',
  ver_movimientos: 'Ver mis movimientos',
  ver_cuentas: 'Ver mis pagos',
  recordar_cliente: 'Recordar al cliente',
  ver_progreso: 'Ver mi progreso',
  ver_metas: 'Ver mi progreso',
  ver_forecast: 'Ver mis próximos 30 días',
}

/**
 * Destino del botón de una alerta: { to: '/app/simulador?pedido_id=PED-0012', texto: 'Ver qué puedo hacer' } o null si no hay a dónde llevar.
 * Usa `accion.tipo` y `accion.payload` del backend; el texto del botón también viene del backend.
 */
export function destinoAlerta(alerta) {
  if (!alerta) return null
  const payload = alerta.accion?.payload ?? {}
  const tipo = RUTA_POR_ACCION[alerta.accion?.tipo] ? alerta.accion.tipo : ACCION_POR_TIPO[alerta.tipo]
  const ruta = RUTA_POR_ACCION[tipo]
  if (!ruta) return null
  return { to: ruta(payload), texto: alerta.accion?.texto_boton || TEXTO_POR_ACCION[tipo] || 'Ver más' }
}
