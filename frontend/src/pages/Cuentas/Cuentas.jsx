import { useEffect, useId, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../../api/index.js'
import { useApi } from '../../api/useApi.js'
import { ddmm, weekdayDdmm } from '../../lib/format.js'
import {
  Button,
  Card,
  ErrorState,
  Icon,
  List,
  ListRow,
  LoadingBlock,
  Money,
  PageHeader,
  Skeleton,
  Status,
} from '../../components/ui/index.jsx'
import './Cuentas.css'

const TABS = [
  { id: 'deben', label: 'Te deben' },
  { id: 'debes', label: 'Debes' },
]

const ESTADO_FIADO = {
  vencido: { tone: 'danger', label: 'Vencido' },
  por_vencer: { tone: 'warning', label: 'Por vencer' },
  pendiente: { tone: 'ok', label: 'Al día' },
}

function fiadoStatus(f) {
  // Fiado al día: sin línea de estado; solo se marca lo que pide atención.
  if (!ESTADO_FIADO[f.estado] || f.estado === 'pendiente') return null
  const e = ESTADO_FIADO[f.estado]
  const nivel = f.riesgo_atraso?.nivel
  return { tone: e.tone, text: nivel ? `${e.label} · riesgo ${nivel}` : e.label }
}

// Listas largas: se ven las primeras 5 y un botón para ver todas.
const LIMITE = 5

/** "Ver los N →" / "Ver menos" de una lista. El botón va en la cabecera y no se mueve al abrir, así el foco queda en él. */
function useVerTodos(total) {
  const [open, setOpen] = useState(false)
  const listId = useId()
  const hayMas = total > LIMITE
  const corta = (arr) => (open || !hayMas ? arr : arr.slice(0, LIMITE))
  const action = hayMas ? (
    <button
      type="button"
      className="cc-section__action"
      aria-expanded={open}
      aria-controls={listId}
      onClick={() => setOpen((o) => !o)}
    >
      {open ? (
        'Ver menos'
      ) : (
        <>
          Ver los {total} <span aria-hidden="true">→</span>
        </>
      )}
    </button>
  ) : null
  return { listId, corta, action }
}

const dias = (n) => `${n} ${n === 1 ? 'día' : 'días'}`
const vence = (fecha) => `Vence ${weekdayDdmm(fecha).toLowerCase()}`

// Iniciales del círculo de la fila: "Sra. Carmen" → "C", "Distribuidora Andina" → "DA"
const TRATAMIENTOS = new Set(['sr', 'sra', 'srta', 'don', 'doña', 'dona', 'vecina', 'vecino', 'tía', 'tia', 'tío', 'tio'])
function iniciales(nombre = '') {
  const words = String(nombre)
    .split(/\s+/)
    .map((w) => w.replace(/[^\p{L}\p{N}]/gu, ''))
    .filter(Boolean)
  const core = words.filter((w) => !TRATAMIENTOS.has(w.toLowerCase()))
  return (core.length ? core : words)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('')
}

const reducedMotion = () => {
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

export default function Cuentas() {
  const fiados = useApi(() => api.getFiados(), [])
  const pedidos = useApi(() => api.getPedidos(), [])

  const [selected, setSelected] = useState('deben')
  const [eliminando, setEliminando] = useState(null)
  const [errorEliminacion, setErrorEliminacion] = useState(null)
  const [recordatorio, setRecordatorio] = useState(null) // { id, loading, mensaje, error, copiado }
  const [params] = useSearchParams()
  const tabRefs = useRef({})
  const headingRefs = useRef({})
  const sectionRefs = useRef({})
  const lockUntil = useRef(0)

  // Mientras la persona hace scroll, el segmento resaltado sigue a la sección visible.
  useEffect(() => {
    let raf = 0
    const onScroll = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        if (Date.now() < lockUntil.current) return
        const debes = sectionRefs.current.debes
        if (!debes) return
        const atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4
        const inDebes = debes.getBoundingClientRect().top < window.innerHeight * 0.35
        setSelected(inDebes || (atBottom && window.scrollY > 0) ? 'debes' : 'deben')
      })
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      cancelAnimationFrame(raf)
    }
  }, [])

  const goTo = (id) => {
    setSelected(id)
    lockUntil.current = Date.now() + 800
    const smooth = !reducedMotion()
    if (id === 'deben') window.scrollTo({ top: 0, behavior: smooth ? 'smooth' : 'auto' })
    else sectionRefs.current[id]?.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'start' })
    headingRefs.current[id]?.focus({ preventScroll: true })
  }

  const onTabKey = (e, i) => {
    let next = null
    if (e.key === 'ArrowRight') next = (i + 1) % TABS.length
    else if (e.key === 'ArrowLeft') next = (i - 1 + TABS.length) % TABS.length
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = TABS.length - 1
    if (next === null) return
    e.preventDefault()
    tabRefs.current[TABS[next].id]?.focus()
    goTo(TABS[next].id)
  }

  const totalDeben = fiados.data?.total_pendiente
  const totalDebes =
    pedidos.data && (Number(pedidos.data.total_pendiente) || 0) + (Number(pedidos.data.impuestos?.monto_estimado) || 0)

  const eliminarCuenta = async (tipo, id) => {
    if (eliminando) return
    setEliminando(`${tipo}:${id}`)
    setErrorEliminacion(null)
    try {
      await api.anularCuenta({ tipo, id })
      fiados.reload()
      pedidos.reload()
    } catch (error) {
      setErrorEliminacion(error)
    } finally {
      setEliminando(null)
    }
  }

  // Texto listo para reenviar al cliente (POST /fiados/{id}/recordatorio). No se envía nada desde la app.
  const recordar = async (fiadoId) => {
    setRecordatorio({ id: fiadoId, loading: true })
    try {
      const r = await api.recordatorioFiado(fiadoId)
      setRecordatorio({ id: fiadoId, mensaje: r.mensaje })
    } catch (error) {
      setRecordatorio({ id: fiadoId, error: error.message || 'No pude preparar el mensaje.' })
    }
  }

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(recordatorio.mensaje)
      setRecordatorio((r) => ({ ...r, copiado: true }))
    } catch {
      setRecordatorio((r) => ({ ...r, error: 'No pude copiarlo. Selecciona el texto y cópialo.' }))
    }
  }

  // Llegar con ?recordar=FIA-… (o ?cliente=CLI-…), por ejemplo desde una alerta de fiado vencido, deja el mensaje listo.
  const recordarParam = params.get('recordar')
  const clienteParam = params.get('cliente')
  const itemsFiados = fiados.data?.items
  const yaAbierto = useRef(false)
  useEffect(() => {
    if (yaAbierto.current || !itemsFiados) return
    const f = itemsFiados.find((x) => (recordarParam ? x.fiado_id === recordarParam : clienteParam && x.cliente_id === clienteParam))
    if (!f) return
    yaAbierto.current = true
    recordar(f.fiado_id)
    document.getElementById(`fiado-${f.fiado_id}`)?.scrollIntoView({ block: 'center' })
  }, [itemsFiados, recordarParam, clienteParam])

  return (
    <div className="cuentas">
      <PageHeader title="Cobros y pagos" sub="Lo que te deben y lo que debes" />

      <div className="cuentas-summary-wrap">
        <Card className="cuentas-summary" aria-label="Resumen">
          <Figure label="Te deben" value={totalDeben} tone="pos" loading={fiados.loading} />
          <Figure label="Debes" value={totalDebes} loading={pedidos.loading} />
        </Card>
      </div>

      <div className="cuentas-seg-wrap">
        <div className="cc-seg cuentas-seg" role="tablist" aria-label="Ir a">
          {TABS.map((t, i) => (
            <button
              key={t.id}
              ref={(el) => (tabRefs.current[t.id] = el)}
              type="button"
              role="tab"
              id={`cuentas-tab-${t.id}`}
              aria-selected={selected === t.id}
              aria-controls={`cuentas-panel-${t.id}`}
              tabIndex={selected === t.id ? 0 : -1}
              className="cc-seg__opt"
              onClick={() => goTo(t.id)}
              onKeyDown={(e) => onTabKey(e, i)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="cuentas-body">
        {errorEliminacion && (
          <p className="cuentas-error-eliminar" role="alert">
            {errorEliminacion.status === 0
              ? errorEliminacion.message
              : `No pude eliminar la cuenta. ${errorEliminacion.message}`}
          </p>
        )}
        <div
          id="cuentas-panel-deben"
          role="tabpanel"
          aria-labelledby="cuentas-tab-deben"
          ref={(el) => (sectionRefs.current.deben = el)}
          className="cuentas-panel"
        >
          <FiadosBlock
            state={fiados}
            recordatorio={recordatorio}
            onRecordar={recordar}
            onCopiar={copiar}
            onEliminar={eliminarCuenta}
            eliminando={eliminando}
            headingRef={(el) => (headingRefs.current.deben = el)}
          />
        </div>

        <div
          id="cuentas-panel-debes"
          role="tabpanel"
          aria-labelledby="cuentas-tab-debes"
          ref={(el) => (sectionRefs.current.debes = el)}
          className="cuentas-panel"
        >
          <DebesBlock
            state={pedidos}
            onEliminar={eliminarCuenta}
            eliminando={eliminando}
            headingRef={(el) => (headingRefs.current.debes = el)}
          />
        </div>

      </div>

    </div>
  )
}

/** Cifra del resumen: monto arriba, etiqueta debajo (SoFi). En el DOM va primero la etiqueta para lectores. */
function Figure({ label, value, tone, loading }) {
  return (
    <div className="cuentas-figure">
      <p className="cuentas-figure__label">{label}</p>
      {loading ? (
        <Skeleton height={31} style={{ width: 104, borderRadius: 8 }} />
      ) : (
        <Money value={value} size="lg" tone={tone} />
      )}
    </div>
  )
}

/** Tarjeta blanca con título dentro (como "Activity" de Monzo). El título recibe el foco al elegir el segmento. */
function ListCard({ title, headingRef, action, children }) {
  const id = useId()
  return (
    <Card flush className="cuentas-card" aria-labelledby={id}>
      <div className="cc-card__head">
        <h2 id={id} ref={headingRef} tabIndex={-1} className="cc-card__title cuentas-card__title">
          {title}
        </h2>
        {action}
      </div>
      {children}
    </Card>
  )
}

/** Vacío: una frase en gris y un solo botón. */
function Empty({ cta, children }) {
  return (
    <div className="cuentas-empty">
      <p className="cc-muted">{children}</p>
      <Link to="/app/chat" className="cc-btn cc-btn--secondary cc-btn--sm">
        {cta}
      </Link>
    </div>
  )
}

function EliminarCuenta({ tipo, id, nombre, onEliminar, eliminando, children }) {
  const pendiente = eliminando === `${tipo}:${id}`
  return (
    <div className="cuentas-row-actions">
      {children}
      <Button
        variant="ghost"
        size="sm"
        className="cuentas-eliminar"
        disabled={eliminando !== null}
        aria-label={`Eliminar ${nombre}`}
        aria-busy={pendiente}
        onClick={() => onEliminar(tipo, id)}
      >
        {pendiente ? 'Eliminando…' : 'Eliminar'}
      </Button>
    </div>
  )
}

/** Mensaje para reenviar al cliente por tu cuenta (la app no lo manda). */
function Recordatorio({ r, onCopiar }) {
  return (
    <div className="cuentas-recordatorio" role="status">
      {r.loading && <p className="cc-muted">Preparando el mensaje…</p>}
      {r.error && <p className="cuentas-error-eliminar">{r.error}</p>}
      {r.mensaje && (
        <>
          <p className="cuentas-recordatorio__texto">“{r.mensaje}”</p>
          <p className="cc-muted cc-small">Cópialo y mándaselo tú; la app no envía nada.</p>
          <Button variant="secondary" size="sm" onClick={onCopiar}>
            {r.copiado ? 'Copiado' : 'Copiar mensaje'}
          </Button>
        </>
      )}
    </div>
  )
}

function FiadosBlock({ state, recordatorio, onRecordar, onCopiar, onEliminar, eliminando, headingRef }) {
  const { data, error, loading, reload } = state
  const items = data?.items || []
  const ver = useVerTodos(loading || error ? 0 : items.length)

  let body
  if (loading) body = <div className="cuentas-card__pad"><LoadingBlock heights={[64, 64, 64]} /></div>
  else if (error) body = <div className="cuentas-card__pad"><ErrorState error={error} onRetry={reload} /></div>
  else if (!items.length) {
    body = (
      <Empty cta="Anotar un fiado">
        Nadie te debe por ahora. Cuando fíes algo, cuéntamelo en el chat, por ejemplo: “le fié S/ 20 a Rosa”.
      </Empty>
    )
  } else {
    body = (
      <List id={ver.listId} aria-label="Fiados pendientes">
        {ver.corta(items).map((f) => {
          const s = fiadoStatus(f)
          return (
            <ListRow
              key={f.fiado_id}
              id={`fiado-${f.fiado_id}`}
              lead={iniciales(f.cliente)}
              title={f.cliente}
              sub={
                <span className="cuentas-sub">
                  <span>
                    Fiado del {ddmm(f.fecha)} · hace {dias(f.dias_transcurridos)}
                  </span>
                  {s && <Status tone={s.tone}>{s.text}</Status>}
                </span>
              }
              amount={<Money value={f.monto} />}
            >
              {recordatorio?.id === f.fiado_id && <Recordatorio r={recordatorio} onCopiar={onCopiar} />}
              <EliminarCuenta
                tipo="fiado"
                id={f.fiado_id}
                nombre={`el fiado de ${f.cliente}`}
                onEliminar={onEliminar}
                eliminando={eliminando}
              >
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={recordatorio?.id === f.fiado_id && recordatorio.loading}
                  onClick={() => onRecordar(f.fiado_id)}
                >
                  {f.accion_sugerida?.texto_boton || `Recordar a ${f.cliente}`}
                </Button>
              </EliminarCuenta>
            </ListRow>
          )
        })}
      </List>
    )
  }

  return (
    <ListCard title="Te deben" headingRef={headingRef} action={ver.action}>
      {body}
    </ListCard>
  )
}

function pedidoStatus(p) {
  const vencido = p.estado === 'vencido' || p.dias_para_vencer < 0
  if (vencido) return { tone: 'danger', text: 'Vencido' }
  if (p.dias_para_vencer === 0) return { tone: 'danger', text: 'Vence hoy' }
  return { tone: 'warning', text: `En ${dias(p.dias_para_vencer)}` }
}

function DebesBlock({ state, onEliminar, eliminando, headingRef }) {
  const { data, error, loading, reload } = state
  const items = data?.items || []
  const imp = data?.impuestos
  const ver = useVerTodos(loading || error ? 0 : items.length)

  let body
  if (loading) body = <div className="cuentas-card__pad"><LoadingBlock heights={[64, 64]} /></div>
  else if (error) body = <div className="cuentas-card__pad"><ErrorState error={error} onRetry={reload} /></div>
  else {
    body = (
      <>
        {(items.length > 0 || imp) && (
          <List id={ver.listId} aria-label="Pagos pendientes">
            {ver.corta(items).map((p) => {
              const s = pedidoStatus(p)
              return (
                <ListRow
                  key={p.pedido_id}
                  lead={iniciales(p.proveedor)}
                  title={p.proveedor}
                  sub={
                    <span className="cuentas-sub">
                      <span>{vence(p.fecha_vencimiento)}</span>
                      <Status tone={s.tone}>{s.text}</Status>
                    </span>
                  }
                  amount={<Money value={p.monto_pendiente ?? p.monto} />}
                >
                  <EliminarCuenta
                    tipo="pedido"
                    id={p.pedido_id}
                    nombre={`la deuda con ${p.proveedor}`}
                    onEliminar={onEliminar}
                    eliminando={eliminando}
                  />
                </ListRow>
              )
            })}
            {imp && (
              <ListRow
                lead={<Icon name="receipt" size={20} />}
                title={imp.nombre || 'Impuesto del mes'}
                sub={
                  <span className="cuentas-sub">
                    {imp.proximo_vencimiento && <span>{vence(imp.proximo_vencimiento)}</span>}
                    {imp.estado === 'al_dia' ? <Status tone="ok">Al día</Status> : <Status tone="warning">Por pagar</Status>}
                  </span>
                }
                amount={imp.monto_estimado != null ? <Money value={imp.monto_estimado} /> : undefined}
              >
                {imp.impuesto_id && (
                  <EliminarCuenta
                    tipo="impuesto"
                    id={imp.impuesto_id}
                    nombre={imp.nombre || 'el impuesto del mes'}
                    onEliminar={onEliminar}
                    eliminando={eliminando}
                  />
                )}
              </ListRow>
            )}
          </List>
        )}
        {items.length === 0 && (
          <Empty cta="Anotar un pedido">
            No le debes a ningún proveedor. Si haces un pedido a crédito, cuéntamelo en el chat, por ejemplo: “pedí 2 400 a
            Andina, pago el 30”. Te aviso antes de que venza.
          </Empty>
        )}
      </>
    )
  }

  return (
    <ListCard title="Debes" headingRef={headingRef} action={ver.action}>
      {body}
    </ListCard>
  )
}
