// Ajustes de la demo: detalles técnicos (siempre); con backend real, la empresa demo; con mocks, escenario de datos y modo fallback del LLM.
// Se guardan en localStorage con try/catch para que la app funcione aunque el storage esté bloqueado.

const KEY = 'tucaserito-demo'
// escenario: 'pedro' (92 días, no le alcanza el 30/11) | 'sano' (92 días, negocio sano: sí le alcanza) | 'nuevo' (día 3). tecnico: muestra modelo/versión (para el jurado; Pedro no lo ve)
// empresa: id de la empresa demo con backend real (null = VITE_EMPRESA_ID). 'EMP-0001' (3 meses) | 'EMP-0002' (día 3)
const DEFAULTS = { escenario: 'pedro', empresa: null, fallback: false, tecnico: false }

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
