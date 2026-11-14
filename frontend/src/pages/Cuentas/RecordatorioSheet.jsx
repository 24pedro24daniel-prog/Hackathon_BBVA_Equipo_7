import { useEffect, useId, useRef, useState } from 'react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/useApi.js'
import { soles } from '../../lib/format.js'
import { Button, ErrorState, Icon, LoadingBlock } from '../../components/ui/index.jsx'

async function copyText(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* sigue con el respaldo */
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}

/** Hoja inferior con el mensaje sugerido. CajaClara no envía nada: Pedro copia o abre WhatsApp. */
export default function RecordatorioSheet({ fiado, onClose }) {
  const ref = useRef(null)
  const msgRef = useRef(null)
  const titleId = useId()
  const [copy, setCopy] = useState('idle') // idle | ok | fail
  const { data, error, loading, reload } = useApi(() => api.recordatorioFiado(fiado.fiado_id), [fiado.fiado_id])

  useEffect(() => {
    const d = ref.current
    // Sin cleanup que llame close(): en StrictMode dispararía onClose y desmontaría la hoja.
    if (d && !d.open) d.showModal?.()
  }, [])

  const mensaje = data?.mensaje || ''

  const onCopy = async () => {
    const ok = await copyText(mensaje)
    setCopy(ok ? 'ok' : 'fail')
    if (!ok && msgRef.current) {
      const range = document.createRange()
      range.selectNodeContents(msgRef.current)
      const sel = window.getSelection()
      sel.removeAllRanges()
      sel.addRange(range)
    }
  }

  return (
    <dialog
      ref={ref}
      className="cuentas-sheet"
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && ref.current.close()}
    >
      <div className="cuentas-sheet__inner">
        <span className="cuentas-sheet__grip" aria-hidden="true" />
        <div className="cuentas-sheet__head">
          <div>
            <h2 id={titleId} className="cuentas-sheet__title">
              Recordarle a {fiado.cliente}
            </h2>
            <p className="cuentas-sheet__sub num">Te debe {soles(fiado.monto)}</p>
          </div>
          <button type="button" className="cuentas-sheet__close" aria-label="Cerrar" onClick={() => ref.current?.close()}>
            <Icon name="close" size={22} />
          </button>
        </div>

        {loading && <LoadingBlock heights={[96]} />}
        {error && <ErrorState error={error} onRetry={reload} />}
        {data && (
          <>
            <div className="cuentas-sheet__group">
              <h3 className="cuentas-sheet__label">Mensaje sugerido</h3>
              <blockquote ref={msgRef} className="cuentas-sheet__msg">
                {mensaje}
              </blockquote>
              <p className="cuentas-sheet__note cc-small">
                CajaClara no lo envía por ti. Tú decides si lo mandas, cuándo y cómo. Puedes cambiarle las palabras.
              </p>
            </div>
            <div className="cuentas-sheet__actions">
              <a
                className="cc-btn cc-btn--primary cc-btn--block cc-btn--lg"
                href={`https://wa.me/?text=${encodeURIComponent(mensaje)}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                <Icon name="send" size={20} />
                Enviar por WhatsApp
              </a>
              <Button variant="secondary" block onClick={onCopy}>
                {copy === 'ok' ? 'Copiado' : 'Copiar mensaje'}
              </Button>
              <Button variant="ghost" block onClick={() => ref.current?.close()}>
                Cancelar
              </Button>
            </div>
            <p className="sr-only" role="status" aria-live="polite">
              {copy === 'ok' ? 'Mensaje copiado' : copy === 'fail' ? 'No pude copiarlo. El mensaje quedó seleccionado para que lo copies.' : ''}
            </p>
            {copy === 'fail' && (
              <p className="cc-small cc-muted">No pude copiarlo solo. Ya lo dejé seleccionado: mantén presionado para copiarlo.</p>
            )}
          </>
        )}
      </div>
    </dialog>
  )
}
