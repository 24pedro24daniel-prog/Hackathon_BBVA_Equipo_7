import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../api/index.js'
import { useApi } from '../../api/useApi.js'
import { useDemo } from '../../lib/useDemo.js'
import { ddmm, pct, soles, weekdayDdmm } from '../../lib/format.js'
import { Badge, Button, Card, ErrorState, Footnote, Icon, LoadingBlock, PageHeader, TraceInfo } from '../../components/ui/index.jsx'
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

function fiadoBadge(f) {
  const e = ESTADO_FIADO[f.estado] || ESTADO_FIADO.pendiente
  const nivel = f.riesgo_atraso?.nivel
  return { tone: e.tone, text: nivel ? `${e.label} · riesgo ${nivel}` : e.label }
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

  // Mientras la persona hace scroll, la pestaña resaltada sigue a la sección visible.
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

  return (
    <div className="cuentas">
      <PageHeader kicker="Cuentas" title="Lo que te deben y lo que debes" />

      <div className="cuentas-tabs-wrap">
        <div className="cuentas-tabs" role="tablist" aria-label="Ir a">
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
              className="cuentas-tab num"
              onClick={() => goTo(t.id)}
              onKeyDown={(e) => onTabKey(e, i)}
            >
              {t.label}
              {totals[t.id] !== undefined && totals[t.id] !== null ? ` · ${soles(totals[t.id])}` : ''}
            </button>
          ))}
        </div>
      </div>

      <div className="cuentas-body">
        <section
          id="cuentas-panel-deben"
          role="tabpanel"
          aria-labelledby="cuentas-tab-deben"
          ref={(el) => (sectionRefs.current.deben = el)}
          className="cuentas-section"
        >
          <h2 className="sr-only" tabIndex={-1} ref={(el) => (headingRefs.current.deben = el)}>
            Te deben
          </h2>
          <FiadosBlock state={fiados} onRecordar={setSheetFiado} />
        </section>

        <section
          id="cuentas-panel-debes"
          role="tabpanel"
          aria-labelledby="cuentas-tab-debes"
          ref={(el) => (sectionRefs.current.debes = el)}
          className="cuentas-section cuentas-section--debes"
        >
          <h2 className="cc-eyebrow cuentas-eyebrow" tabIndex={-1} ref={(el) => (headingRefs.current.debes = el)}>
            Debes
          </h2>
          <DebesBlock state={pedidos} />
        </section>

        <Footnote />
      </div>

      {sheetFiado && <RecordatorioSheet fiado={sheetFiado} onClose={() => setSheetFiado(null)} />}
    </div>
  )
}

function FiadosBlock({ state, onRecordar }) {
  const { data, error, loading, reload } = state
  if (loading) return <LoadingBlock heights={[260, 52]} />
  if (error) return <ErrorState error={error} onRetry={reload} />

  const items = data?.items || []
  if (!items.length) {
    return (
      <Card variant="dashed" className="cuentas-empty">
        <p className="cuentas-empty__title">Nadie te debe por ahora</p>
        <p className="cc-muted cc-small">
          Cuando fíes algo, cuéntamelo en el chat. Por ejemplo: “le fié S/ 20 a Rosa”. Aquí verás cuánto te deben y a quién
          conviene recordarle.
        </p>
        <Link to="/chat" className="cc-btn cc-btn--secondary cc-btn--sm">
          <Icon name="chat" size={20} />
          Anotar un fiado
        </Link>
      </Card>
    )
  }

  const riesgos = items.filter((f) => f.riesgo_atraso)

  return (
    <>
      <Card as="div">
        <ul className="cuentas-list" aria-label="Fiados pendientes">
          {items.map((f) => {
            const b = fiadoBadge(f)
            return (
              <li key={f.fiado_id} className="cuentas-item">
                <div className="cuentas-item__top">
                  <div className="cuentas-item__who">
                    <h3 className="cuentas-item__name">{f.cliente}</h3>
                    <p className="cuentas-item__sub">
                      Fiado del {ddmm(f.fecha)} · hace {f.dias_transcurridos} {f.dias_transcurridos === 1 ? 'día' : 'días'}
                    </p>
                  </div>
                  <p className="cuentas-item__amount display num">{soles(f.monto)}</p>
                </div>
                <div className="cuentas-item__bottom">
                  <Badge tone={b.tone}>{b.text}</Badge>
                  {f.accion_sugerida && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => onRecordar(f)}
                      aria-label={`${f.accion_sugerida.texto_boton || 'Recordarle'} a ${f.cliente}`}
                    >
                      {f.accion_sugerida.texto_boton || 'Recordarle'}
                    </Button>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      </Card>

      <TraceInfo
        fundamento={data.fundamento || 'Cada riesgo sale de cuánto se demoró esa persona antes y de cuántos días lleva este fiado.'}
        extra={
          riesgos.length
            ? [
                [
                  'Riesgo de que se atrase',
                  <ul key="r" className="cuentas-trace-list">
                    {riesgos.map((f) => (
                      <li key={f.fiado_id}>
                        {f.cliente}: {pct(f.riesgo_atraso.probabilidad)}
                        {f.riesgo_atraso.baseline_probabilidad != null &&
                          ` (lo usual en tu bodega: ${pct(f.riesgo_atraso.baseline_probabilidad)})`}
                      </li>
                    ))}
                  </ul>,
                ],
              ]
            : []
        }
        limites={data.limites || 'Es una estimación; no sabe si la persona tuvo un imprevisto.'}
        meta={data.meta}
      />
    </>
  )
}

function DebesBlock({ state }) {
  const navigate = useNavigate()
  const { data, error, loading, reload } = state
  if (loading) return <LoadingBlock heights={[200]} />
  if (error) return <ErrorState error={error} onRetry={reload} />

  const items = data?.items || []
  const imp = data?.impuestos

  return (
    <Card as="div">
      {items.length === 0 && (
        <div className="cuentas-item cuentas-empty cuentas-empty--inline">
          <p className="cuentas-empty__title">No tienes pagos pendientes a proveedores</p>
          <p className="cc-muted cc-small">
            Si haces un pedido a crédito, cuéntamelo en el chat. Por ejemplo: “pedí 2 400 a Andina, pago el 30”. Te aviso antes
            de que venza.
          </p>
          <Link to="/chat" className="cc-btn cc-btn--secondary cc-btn--sm">
            <Icon name="chat" size={20} />
            Anotar un pedido
          </Link>
        </div>
      )}
      {(items.length > 0 || imp) && (
      <ul className="cuentas-list" aria-label="Pagos pendientes">
        {items.map((p) => {
          const monto = p.monto_pendiente ?? p.monto
          const vencido = p.estado === 'vencido' || p.dias_para_vencer < 0
          const badge = vencido
            ? { tone: 'danger', text: 'Vencido' }
            : p.dias_para_vencer === 0
              ? { tone: 'danger', text: 'Vence hoy' }
              : { tone: 'warning', text: `Vence en ${p.dias_para_vencer} ${p.dias_para_vencer === 1 ? 'día' : 'días'}` }
          return (
            <li key={p.pedido_id} className="cuentas-item">
              <div className="cuentas-item__top">
                <div className="cuentas-item__who">
                  <h3 className="cuentas-item__name">{p.proveedor}</h3>
                  <p className="cuentas-item__sub">
                    Pedido del {ddmm(p.fecha_pedido)} · vence {weekdayDdmm(p.fecha_vencimiento).toLowerCase()}
                  </p>
                </div>
                <p className="cuentas-item__amount display num">{soles(monto)}</p>
              </div>
              <div className="cuentas-item__bottom">
                <Badge tone={badge.tone}>{badge.text}</Badge>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => navigate('/simulador')}
                  aria-label={`Ver opciones para pagar a ${p.proveedor}`}
                >
                  Ver opciones
                </Button>
              </div>
            </li>
          )
        })}
        {imp && (
          <li className="cuentas-item">
            <div className="cuentas-item__top">
              <div className="cuentas-item__who">
                <h3 className="cuentas-item__name">{imp.nombre || 'Impuesto del mes'}</h3>
                {imp.proximo_vencimiento && <p className="cuentas-item__sub">Vence {ddmm(imp.proximo_vencimiento)}</p>}
              </div>
              {imp.monto_estimado != null && <p className="cuentas-item__amount display num">{soles(imp.monto_estimado)}</p>}
            </div>
            <div className="cuentas-item__bottom">
              {imp.estado === 'al_dia' ? <Badge tone="ok">Al día</Badge> : <Badge tone="warning">Por pagar</Badge>}
            </div>
          </li>
        )}
      </ul>
      )}
    </Card>
  )
}
