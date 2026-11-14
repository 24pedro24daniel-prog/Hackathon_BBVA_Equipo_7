// Formato de dinero y fechas para Pedro: "S/ 2 340", "30/11", "el martes". Zona America/Lima.

const TZ = 'America/Lima'

function groupThousands(intStr) {
  // Espacio fino no separable como separador de miles: "2 340"
  return intStr.replace(/\B(?=(\d{3})+(?!\d))/g, '\u202F')
}

/**
 * soles(2340) → "S/ 2 340"; soles(13, { cents: true }) → "S/ 13.00"; soles(-650) → "−S/ 650"
 * opts.sign: true agrega "+" a positivos (para movimientos).
 */
export function soles(value, { cents = false, sign = false } = {}) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 'S/ —'
  const n = Number(value)
  const abs = Math.abs(n)
  const fixed = cents ? abs.toFixed(2) : String(Math.round(abs))
  const [int, dec] = fixed.split('.')
  const body = `S/\u00A0${groupThousands(int)}${dec ? `.${dec}` : ''}`
  if (n < 0) return `−${body}`
  if (sign && n > 0) return `+${body}`
  return body
}

/** Rango aproximado: [760, 1210] → "S/ 760 – 1 210" */
export function solesRange([lo, hi]) {
  return `${soles(lo)} – ${groupThousands(String(Math.round(hi)))}`
}

function toDate(d) {
  if (d instanceof Date) return d
  // "2026-11-30" se interpreta como fecha local de Lima, no UTC
  if (/^\d{4}-\d{2}-\d{2}$/.test(d)) return new Date(`${d}T12:00:00-05:00`)
  return new Date(d)
}

/** "2026-11-30" → "30/11" */
export function ddmm(d) {
  const parts = new Intl.DateTimeFormat('es-PE', { day: 'numeric', month: 'numeric', timeZone: TZ }).formatToParts(toDate(d))
  const get = (t) => parts.find((x) => x.type === t).value.padStart(2, '0')
  return `${get('day')}/${get('month')}`
}

/** "2026-11-30" → "lun 30/11" */
export function weekdayDdmm(d) {
  const date = toDate(d)
  const wd = new Intl.DateTimeFormat('es-PE', { weekday: 'short', timeZone: TZ }).format(date).replace('.', '')
  return `${wd.charAt(0).toUpperCase()}${wd.slice(1)} ${ddmm(date)}`
}

/** ISO datetime → "10:42" */
export function hhmm(d) {
  return new Intl.DateTimeFormat('es-PE', { hour: 'numeric', minute: '2-digit', hour12: false, timeZone: TZ }).format(toDate(d))
}

/** Probabilidad 0.74 → "74%" */
export function pct(p) {
  return `${Math.round(p * 100)}%`
}

/** Días entre dos fechas "YYYY-MM-DD" */
export function daysBetween(a, b) {
  return Math.round((toDate(b) - toDate(a)) / 86400000)
}

/** confianza textual del contrato ("alta" | "media" | "baja") o numérica → etiqueta */
export function confianzaLabel(c) {
  if (typeof c === 'string') return `Confianza ${c}`
  if (c >= 0.85) return 'Confianza alta'
  if (c >= 0.6) return 'Confianza media'
  return 'Confianza baja'
}
