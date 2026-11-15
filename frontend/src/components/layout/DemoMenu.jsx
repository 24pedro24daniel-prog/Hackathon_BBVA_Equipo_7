import { useState } from 'react'
import { useDemo } from '../../lib/useDemo.js'
import { USE_MOCK, empresaId } from '../../api/index.js'

/** Chip "Demo" (Inicio): cambia la empresa demo (backend real) o el escenario (mocks) y muestra los detalles técnicos. Con mocks, además simula el LLM caído. */
export default function DemoMenu() {
  const [demo, setDemo] = useDemo()
  const [open, setOpen] = useState(false)
  const opt = (label, checked, onClick) => (
    <button className="cc-demo__opt" role="menuitemradio" aria-checked={checked} onClick={() => { onClick(); setOpen(false) }}>
      {label}
    </button>
  )
  // Cambiar de escenario o de empresa recarga la app para que todas las pantallas pidan los datos de nuevo.
  const cambiar = (patch) => () => {
    setDemo(patch)
    window.location.reload()
  }
  const escenario = (e) => cambiar({ escenario: e })
  const empresa = (id) => cambiar({ empresa: id })
  const actual = empresaId()
  return (
    <div className="cc-demo">
      <button className="cc-demo__chip" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        Demo
      </button>
      {open && (
        <div className="cc-demo__menu" role="menu">
          {!USE_MOCK && (
            <>
              {opt('Pedro · 3 meses de datos', actual === 'EMP-0001', empresa('EMP-0001'))}
              {opt('Pedro · día 3', actual === 'EMP-0002', empresa('EMP-0002'))}
            </>
          )}
          {USE_MOCK && (
            <>
              {opt('Pedro · 3 meses de datos', demo.escenario === 'pedro', escenario('pedro'))}
              {opt('Pedro · negocio sano (sí le alcanza)', demo.escenario === 'sano', escenario('sano'))}
              {opt('Pedro · día 3 (recién empieza)', demo.escenario === 'nuevo', escenario('nuevo'))}
            </>
          )}
          {opt(demo.tecnico ? 'Detalles técnicos: visibles ✓' : 'Ver detalles técnicos', demo.tecnico, () => setDemo({ tecnico: !demo.tecnico }))}
          {USE_MOCK &&
            opt(demo.fallback ? 'Asistente: modo básico ✓' : 'Simular asistente caído', demo.fallback, () => setDemo({ fallback: !demo.fallback }))}
        </div>
      )}
    </div>
  )
}
