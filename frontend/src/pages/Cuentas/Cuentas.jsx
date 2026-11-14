import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../api/index.js'
import { useApi } from '../../api/useApi.js'
import { useDemo } from '../../lib/useDemo.js'
import { ddmm, soles, weekdayDdmm } from '../../lib/format.js'
import {
  Button,
  Card,
  ErrorState,
  Footnote,
  Icon,
  List,
  ListRow,
  LoadingBlock,
  PageHeader,
  Section,
  Status,
  TraceInfo,
} from '../../components/ui/index.jsx'
import RecordatorioSheet from './RecordatorioSheet.jsx'
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
  const e = ESTADO_FIADO[f.estado] || ESTADO_FIADO.pendiente
  const nivel = f.riesgo_atraso?.nivel
  return { tone: e.tone, text: nivel ? `${e.label} · riesgo ${nivel}` : e.label }
}

const dias = (n) => `${n} ${n === 1 ? 'día' : 'días'}`

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
  const [demo] = useDemo()
  const fiados = useApi(() => api.getFiados(), [demo.escenario])
  const pedidos = useApi(() => api.getPedidos(), [demo.escenario])

  const [selected, setSelected] = useState('deben')
  const [sheetFiado, setSheetFiado] = useState(null)
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
  const totals = { deben: totalDeben, debes: totalDebes }
  const hasTotal = (id) => totals[id] !== undefined && totals[id] !== null
  // Total junto al título de la sección: solo se ve en escritorio (en móvil ya está en el control segmentado)
  const sectionTotal = (id) => (hasTotal(id) ? <span className="cuentas-sec-total num">{soles(totals[id])}</span> : null)

  return (
    <div className="cuentas">
      <PageHeader title="Cuentas" sub="Lo que te deben y lo que debes" />

      <div className="cuentas-seg-wrap">
        <div className="cuentas-seg" role="tablist" aria-label="Ir a">
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
              className="cuentas-seg__btn"
              onClick={() => goTo(t.id)}
              onKeyDown={(e) => onTabKey(e, i)}
            >
              {t.label}
              {hasTotal(t.id) && <span className="cuentas-seg__amount num"> {soles(totals[t.id])}</span>}
            </button>
          ))}
        </div>
      </div>

      <div className="cuentas-body">
        <div
          id="cuentas-panel-deben"
          role="tabpanel"
          aria-labelledby="cuentas-tab-deben"
          ref={(el) => (sectionRefs.current.deben = el)}
          className="cuentas-panel cuentas-panel--deben"
        >
          <Section title="Te deben" action={sectionTotal('deben')} headingRef={(el) => (headingRefs.current.deben = el)}>
            <FiadosBlock state={fiados} onRecordar={setSheetFiado} />
          </Section>
        </div>

        <div
          id="cuentas-panel-debes"
          role="tabpanel"
          aria-labelledby="cuentas-tab-debes"
          ref={(el) => (sectionRefs.current.debes = el)}
          className="cuentas-panel cuentas-panel--debes"
        >
          <Section title="Debes" action={sectionTotal('debes')} headingRef={(el) => (headingRefs.current.debes = el)}>
            <DebesBlock state={pedidos} />
          </Section>
        </div>

        <Footnote />
      </div>

      {sheetFiado && <RecordatorioSheet fiado={sheetFiado} onClose={() => setSheetFiado(null)} />}
    </div>
  )
}

function EmptyBlock({ title, cta, children }) {
  return (
    <Card variant="dashed" className="cuentas-empty">
      <p className="cuentas-empty__title">{title}</p>
      <p className="cc-muted cc-small">{children}</p>
      <Link to="/chat" className="cc-btn cc-btn--secondary cc-btn--sm">
        <Icon name="chat" size={20} />
        {cta}
      </Link>
    </Card>
  )
}

function FiadosBlock({ state, onRecordar }) {
  const { data, error, loading, reload } = state
  if (loading) return <LoadingBlock heights={[220, 52]} />
  if (error) return <ErrorState error={error} onRetry={reload} />

  const items = data?.items || []
  if (!items.length) {
    return (
      <EmptyBlock title="Nadie te debe por ahora" cta="Anotar un fiado">
        Cuando fíes algo, cuéntamelo en el chat. Por ejemplo: “le fié S/ 20 a Rosa”. Aquí verás cuánto te deben y a quién
        conviene recordarle.
      </EmptyBlock>
    )
  }

  return (
    <div className="cuentas-stack">
      <List aria-label="Fiados pendientes">
        {items.map((f) => {
          const s = fiadoStatus(f)
          const label = f.accion_sugerida?.texto_boton || 'Recordarle'
          return (
            <ListRow
              key={f.fiado_id}
              lead={iniciales(f.cliente)}
              title={f.cliente}
              sub={
                <span className="cuentas-sub">
                  <span>
                    Fiado del {ddmm(f.fecha)} · hace {dias(f.dias_transcurridos)}
                  </span>
                  <Status tone={s.tone}>{s.text}</Status>
                </span>
              }
              amount={soles(f.monto)}
            >
              {f.accion_sugerida && (
                <div className="cuentas-row-actions">
                  {/* Solo el vencido lleva botón con borde; los demás, enlace discreto */}
                  <Button
                    variant={f.estado === 'vencido' ? 'secondary' : 'ghost'}
                    size="sm"
                    className="cuentas-row-btn"
                    onClick={() => onRecordar(f)}
                    aria-label={`${label} a ${f.cliente}`}
                  >
                    {label}
                  </Button>
                </div>
              )}
            </ListRow>
          )
        })}
      </List>

      <TraceInfo
        fundamento={data.fundamento || 'Cada riesgo sale de cuánto se demoró esa persona antes y de cuántos días lleva este fiado.'}
        limites={data.limites || 'Es una estimación; no sabe si la persona tuvo un imprevisto.'}
        meta={data.meta}
      />
    </div>
  )
}

function pedidoStatus(p) {
  const vencido = p.estado === 'vencido' || p.dias_para_vencer < 0
  if (vencido) return { tone: 'danger', text: 'Vencido' }
  if (p.dias_para_vencer === 0) return { tone: 'danger', text: 'Vence hoy' }
  return { tone: 'warning', text: `Vence en ${dias(p.dias_para_vencer)}` }
}

function DebesBlock({ state }) {
  const navigate = useNavigate()
  const { data, error, loading, reload } = state
  if (loading) return <LoadingBlock heights={[160]} />
  if (error) return <ErrorState error={error} onRetry={reload} />

  const items = data?.items || []
  const imp = data?.impuestos

  return (
    <div className="cuentas-stack">
      {items.length === 0 && (
        <EmptyBlock title="No tienes pagos pendientes a proveedores" cta="Anotar un pedido">
          Si haces un pedido a crédito, cuéntamelo en el chat. Por ejemplo: “pedí 2 400 a Andina, pago el 30”. Te aviso antes
          de que venza.
        </EmptyBlock>
      )}
      {(items.length > 0 || imp) && (
        <List aria-label="Pagos pendientes">
          {items.map((p) => {
            const s = pedidoStatus(p)
            return (
              <ListRow
                key={p.pedido_id}
                lead={iniciales(p.proveedor)}
                title={p.proveedor}
                sub={
                  <span className="cuentas-sub">
                    <span>
                      Pedido del {ddmm(p.fecha_pedido)} · vence {weekdayDdmm(p.fecha_vencimiento).toLowerCase()}
                    </span>
                    <Status tone={s.tone}>{s.text}</Status>
                  </span>
                }
                amount={soles(p.monto_pendiente ?? p.monto)}
              >
                <div className="cuentas-row-actions">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="cuentas-row-btn"
                    onClick={() => navigate('/simulador')}
                    aria-label={`Ver opciones para pagar a ${p.proveedor}`}
                  >
                    Ver opciones
                  </Button>
                </div>
              </ListRow>
            )
          })}
          {imp && (
            <ListRow
              lead={<Icon name="receipt" size={20} />}
              title={imp.nombre || 'Impuesto del mes'}
              sub={
                <span className="cuentas-sub">
                  {imp.proximo_vencimiento && <span>Vence {ddmm(imp.proximo_vencimiento)}</span>}
                  {imp.estado === 'al_dia' ? <Status tone="ok">Al día</Status> : <Status tone="warning">Por pagar</Status>}
                </span>
              }
              amount={imp.monto_estimado != null ? soles(imp.monto_estimado) : undefined}
            />
          )}
        </List>
      )}
    </div>
  )
}
