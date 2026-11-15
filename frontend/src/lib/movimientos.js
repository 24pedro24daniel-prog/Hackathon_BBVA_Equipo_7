// Etiquetas en palabras simples para movimientos (enums de contract.md).

export const TIPO_LABEL = {
  venta: 'Venta',
  cobro_fiado: 'Te pagaron un fiado',
  prestamo_recibido: 'Préstamo recibido',
  otro_ingreso: 'Otro ingreso',
  compra: 'Compra de mercadería',
  gasto_negocio: 'Gasto del negocio',
  retiro_personal: 'Saqué de la caja',
  pago_proveedor: 'Pago a proveedor',
  pago_prestamo: 'Pago de préstamo',
  pago_impuesto: 'Pago de impuesto',
}

const INGRESOS = new Set(['venta', 'cobro_fiado', 'prestamo_recibido', 'otro_ingreso', 'ingreso_billetera'])

/** true si el movimiento suma a la caja */
export const esIngreso = (tipo) => INGRESOS.has(tipo)

export const METODO_LABEL = {
  efectivo: 'Efectivo',
  billetera_digital: 'Billetera digital',
  transferencia: 'Transferencia',
  tarjeta: 'Tarjeta',
  credito: 'Al crédito (no mueve tu caja)',
}

export const CANAL_LABEL = {
  voz: 'Nota de voz',
  texto: 'Mensaje de texto',
  foto: 'Foto',
  billetera_api: 'Billetera (automático)',
  manual: 'Anotado en la app',
}

const capitalizar = (t) => t.charAt(0).toUpperCase() + t.slice(1).replace(/_/g, ' ')

/** Título corto de la fila: descripción → "Venta · Bodega Rosa" → "Venta · Bebidas" → "Venta" */
export function tituloMovimiento(m) {
  if (m.descripcion) return m.descripcion
  const t = TIPO_LABEL[m.tipo] || 'Movimiento'
  if (m.contraparte) return `${t} · ${m.contraparte}`
  if (m.categoria && m.categoria !== m.tipo) return `${t} · ${capitalizar(m.categoria)}`
  return t
}
