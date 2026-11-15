import { useEffect, useRef, useState } from 'react'
import { useDemo } from '../../lib/useDemo.js'
import { clearSesion } from '../../lib/sesion.js'
import { USE_MOCK } from '../../api/index.js'

/**
 * Chip "Demo" (Inicio): muestra u oculta los detalles técnicos y, con mocks, simula el asistente caído.
 * "Cerrar sesión" vuelve al login para entrar con otra demo (la empresa la decide la sesión, no este menú).
 */
export default function DemoMenu() {
  const [demo, setDemo] = useDemo()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  // Se cierra con Escape o al tocar fuera.
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => e.key === 'Escape' && setOpen(false)
    const onDown = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false)
    document.addEventListener('keydown', onKey)
    document.addEventListener('pointerdown', onDown)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onDown)
    }
  }, [open])

  const opt = (label, checked, onClick) => (
    <button className="cc-demo__opt" role="menuitemcheckbox" aria-checked={checked} onClick={() => { onClick(); setOpen(false) }}>
      {label}
    </button>
  )
  return (
    <div className="cc-demo" ref={ref}>
      <button className="cc-demo__chip" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        Demo
      </button>
      {open && (
        <div className="cc-demo__menu" role="menu">
          {opt(demo.tecnico ? 'Detalles técnicos: visibles ✓' : 'Ver detalles técnicos', demo.tecnico, () => setDemo({ tecnico: !demo.tecnico }))}
          {USE_MOCK &&
            opt(demo.fallback ? 'Asistente: modo básico ✓' : 'Asistente sin conexión', demo.fallback, () => setDemo({ fallback: !demo.fallback }))}
          <button className="cc-demo__opt cc-demo__opt--salir" role="menuitem" onClick={() => clearSesion('salir')}>
            Cerrar sesión
          </button>
        </div>
      )}
    </div>
  )
}
