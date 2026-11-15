// Textos y etiquetas del chat. Sin JSX (solo funciones puras). Qué es cada mensaje lo decide el backend (/chat/mensajes).
import { ddmm, soles } from '../../lib/format.js'

export const TIPO_LABEL = {
  venta: 'Venta',
  compra: 'Compra',
  retiro_personal: 'Saqué de la caja',
  pago_impuesto: 'Pago de impuesto',
  cobro_fiado: 'Cobro de fiado',
  gasto: 'Gasto',
  gasto_operativo: 'Gasto del negocio',
  pago_proveedor: 'Pago a proveedor',
}

export const PAGO_LABEL = {
  efectivo: 'Efectivo',
  billetera_digital: 'Billetera',
  tarjeta: 'Tarjeta',
  transferencia: 'Transferencia',
  credito: 'A crédito',
}

const PAGO_CORTO = {
  efectivo: 'en efectivo',
  billetera_digital: 'por billetera',
  tarjeta: 'con tarjeta',
  transferencia: 'por transferencia',
  credito: 'a crédito',
}

const humanize = (s = '') => {
  const t = String(s).replace(/_/g, ' ')
  return t.charAt(0).toUpperCase() + t.slice(1)
}

export const tipoLabel = (t) => TIPO_LABEL[t] || humanize(t)
export const pagoLabel = (p) => PAGO_LABEL[p] || humanize(p)

// Respuestas cortas a la tarjeta del cuaderno de fiados (la única que no pasa por /chat/mensajes)
export const isAffirmative = (text) => /^(si|sii|ok|okey|correcto|listo|dale|esta bien|guardar?)\b/.test(norm(text))
export const isNegative = (text) => /^(no|corregir)\b/.test(norm(text))

const norm = (s = '') => s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim()

/** número suelto o "son 35" → 35 */
export function parseNumero(text) {
  const m = norm(text).match(/(\d+(?:[.,]\d+)?)/)
  return m ? Number(m[1].replace(',', '.')) : null
}

function pluralize(word) {
  return /[aeiou]$/i.test(word) ? `${word}s` : `${word}es`
}

/** items [{producto:'Cerveza 620 ml', cantidad:2}] → "2 cervezas 620 ml" */
export function productoTexto(items = []) {
  if (!items.length) return null
  return items
    .map(({ producto = '', cantidad = 1 }) => {
      const [first, ...rest] = producto.split(' ')
      const name = cantidad > 1 ? pluralize(first.toLowerCase()) : first.toLowerCase()
      return [cantidad, name, ...rest].join(' ')
    })
    .join(', ')
}

/** Filas clave/valor de la tarjeta "Anoté esto, ¿está bien?" */
export function filasMovimiento(mov) {
  const rows = [['Tipo', tipoLabel(mov.tipo)]]
  const prod = productoTexto(mov.items)
  if (prod) rows.push(['Producto', prod])
  if (mov.contraparte) rows.push([mov.tipo === 'compra' ? 'Proveedor' : 'Cliente', mov.contraparte])
  rows.push(['Monto', soles(mov.monto, { cents: true })])
  if (mov.metodo_pago) rows.push(['Pago', pagoLabel(mov.metodo_pago)])
  if (mov.fecha_vencimiento) rows.push(['Pagas el', ddmm(mov.fecha_vencimiento)])
  return rows
}

/** Resumen para la pregunta aclaratoria: "pedido a crédito de **S/ 2 400 a Distribuidora Andina**" */
export function resumenEntendido(mov) {
  if (mov.tipo === 'compra') {
    const cred = mov.metodo_pago === 'credito' ? ' a crédito' : ''
    const monto = mov.monto ? ` de ${soles(mov.monto)}` : ''
    return `Entendí un **pedido${cred}${monto}${mov.contraparte ? ` a ${mov.contraparte}` : ''}**. Me falta un dato:`
  }
  return `Entendí **${tipoLabel(mov.tipo).toLowerCase()} de ${soles(mov.monto, { cents: true })}**. Me falta un dato:`
}

const DUDA = {
  fecha_vencimiento: 'No estaba seguro de la fecha',
  metodo_pago: 'No estaba seguro de cómo te pagaron',
  monto: 'No estaba seguro del monto',
}
export const notaDuda = (campos = []) => DUDA[campos[0]] || 'No estaba seguro de un dato'

/** Respuesta del bot tras POST /ingesta/confirmar */
export function textoConfirmado(mov, correcciones = {}, res) {
  const final = { ...mov, ...correcciones }
  const corregidos = Object.keys(correcciones).filter((k) => k !== 'fecha_vencimiento')
  const lines = []
  if (corregidos.length) {
    let detalle = soles(final.monto, { cents: true })
    if (correcciones.metodo_pago) detalle += ` ${PAGO_CORTO[final.metodo_pago] || pagoLabel(final.metodo_pago)}`
    else if (correcciones.tipo) detalle += ` (${tipoLabel(final.tipo).toLowerCase()})`
    lines.push('Listo, corregido:', `**${detalle}**`)
  } else if (final.tipo === 'compra') {
    const fecha = final.fecha_vencimiento ? `, lo pagas el ${ddmm(final.fecha_vencimiento)}` : ''
    lines.push('Listo, anotado.', `Pedido${final.contraparte ? ` a ${final.contraparte}` : ''} por **${soles(final.monto)}**${fecha}.`)
  } else if (final.tipo === 'pago_impuesto') {
    lines.push('Listo, anotado.', `Pagaste **${soles(final.monto)} de impuesto**. Ya salió de tu caja.`)
  } else {
    lines.push('Listo, anotado.')
  }
  if (res?.saldo_caja_negocio !== undefined && res?.saldo_caja_negocio !== null) {
    lines.push(`Ahora tienes ${soles(res.saldo_caja_negocio)} en la caja.`)
  }
  const alerta = res?.alertas_disparadas?.[0]
  if (alerta) lines.push(`Ojo: ${alerta.titulo || alerta.titulo_corto}.`)
  return lines.join('\n')
}

/** Pone en negrita el monto dentro de un texto: "te faltarían S/ 650" → "te faltarían **S/ 650**" */
export function boldMonto(text = '', monto) {
  if (monto === null || monto === undefined) return text
  const grouped = String(Math.round(Math.abs(monto))).replace(/\B(?=(\d{3})+(?!\d))/g, '[,\\s\\u202F\\u00A0]?')
  const re = new RegExp(`S/[\\s\\u00A0]?${grouped}(?:\\.\\d+)?`)
  // El monto queda con espacios no separables ("S/ 2 400"), igual que el formato del backend
  return text.replace(re, (m) => `**${m.replace(/[\s,]+/g, '\u00A0')}**`)
}

const cap = (s = '') => s.charAt(0).toUpperCase() + s.slice(1)

/** Sugerencia de /pedidos/chequeo → texto de la fila */
export function sugerenciaTexto(s, todas = []) {
  if (s.accion === 'reducir_pedido') return `Pedir ${soles(s.monto_sugerido)}`
  if (s.accion === 'pagar_en_partes') return `Pagar en ${s.partes} partes`
  if (s.accion === 'combinar') {
    const r = todas.find((x) => x.accion === 'reducir_pedido')
    const p = todas.find((x) => x.accion === 'pagar_en_partes')
    if (r && p) return `Pedir ${soles(r.monto_sugerido)} + pagar en ${p.partes} partes`
  }
  return cap(s.detalle || humanize(s.accion))
}
