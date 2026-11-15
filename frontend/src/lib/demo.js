// Ajustes de la demo: detalles técnicos (siempre) y, con mocks, el modo fallback del LLM.
// La empresa (y, con mocks, el escenario de datos) ya no se eligen aquí: los decide la sesión (src/lib/sesion.js).
// Se guardan en localStorage con try/catch para que la app funcione aunque el storage esté bloqueado.

const KEY = 'tucaserito-demo'
// tecnico: muestra modelo/versión (para el jurado; Pedro no lo ve). fallback: con mocks, simula el asistente caído.
const DEFAULTS = { fallback: false, tecnico: false }

export function getDemoSettings() {
  try {
    const guardado = JSON.parse(localStorage.getItem(KEY) || '{}')
    return { fallback: guardado.fallback === true, tecnico: guardado.tecnico === true }
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
