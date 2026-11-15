// Ajustes de la demo (solo afectan a los mocks): escenario de datos y modo fallback del LLM.
// Se guardan en localStorage con try/catch para que la app funcione aunque el storage esté bloqueado.

const KEY = 'tucaserito-demo'
// escenario: 'pedro' (92 días, no le alcanza el 30/11) | 'sano' (92 días, negocio sano: sí le alcanza) | 'nuevo' (día 3). tecnico: muestra modelo/versión (para el jurado; Pedro no lo ve)
const DEFAULTS = { escenario: 'pedro', fallback: false, tecnico: false }

export function getDemoSettings() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || '{}') }
  } catch {
    return { ...DEFAULTS }
  }
}

export function setDemoSettings(patch) {
  const next = { ...getDemoSettings(), ...patch }
  try {
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    /* sin storage: el ajuste dura hasta recargar */
  }
  window.dispatchEvent(new CustomEvent('tucaserito-demo', { detail: next }))
  return next
}
