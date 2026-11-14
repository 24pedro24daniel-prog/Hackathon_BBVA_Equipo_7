import { useState } from 'react'
import { useDemo } from '../../lib/useDemo.js'
import { USE_MOCK } from '../../api/index.js'

/** Chip "Demo" (Inicio): cambia escenario de datos y simula LLM caído. Solo actúa sobre los mocks. */
export default function DemoMenu() {
  const [demo, setDemo] = useDemo()
  const [open, setOpen] = useState(false)
  const opt = (label, checked, onClick) => (
    <button className="cc-demo__opt" role="menuitemradio" aria-checked={checked} onClick={() => { onClick(); setOpen(false) }}>
      {label}
    </button>
  )
  return (
    <div className="cc-demo">
      <button className="cc-demo__chip" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        Demo
      </button>
      {open && (
        <div className="cc-demo__menu" role="menu">
          {!USE_MOCK && <p>Backend real: estos ajustes no aplican</p>}
          {opt('Pedro · 3 meses de datos', demo.escenario === 'pedro', () => setDemo({ escenario: 'pedro' }))}
          {opt('Pedro · día 3 (recién empieza)', demo.escenario === 'nuevo', () => setDemo({ escenario: 'nuevo' }))}
          {opt(demo.tecnico ? 'Detalles técnicos: visibles ✓' : 'Ver detalles técnicos', demo.tecnico, () => setDemo({ tecnico: !demo.tecnico }))}
          {opt(demo.fallback ? 'Asistente: modo básico ✓' : 'Simular asistente caído', demo.fallback, () => setDemo({ fallback: !demo.fallback }))}
        </div>
      )}
    </div>
  )
}
