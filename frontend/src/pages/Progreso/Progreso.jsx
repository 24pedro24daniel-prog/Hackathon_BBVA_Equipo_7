import { useId, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/index.js'
import { useApi } from '../../api/useApi.js'
import { useDemo } from '../../lib/useDemo.js'
import { soles } from '../../lib/format.js'
import { Card, ErrorState, Footnote, Icon, LoadingBlock, MetaLine, PageHeader } from '../../components/ui/index.jsx'
import './Progreso.css'

const ETAPAS_DEFAULT = ['organizar', 'estabilizar', 'proteger', 'crecer']

const cap = (s = '') => s.charAt(0).toUpperCase() + s.slice(1)
const lowerFirst = (s = '') => s.charAt(0).toLowerCase() + s.slice(1)

const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

/** "2026-08" → { corto: "Ago", largo: "agosto" } (fijo: Intl es-PE da "Set" y mayúsculas según el motor) */
function mesLabel(mes) {
  const largo = MESES[Number(String(mes).slice(5, 7)) - 1] || String(mes)
  return { corto: cap(largo.slice(0, 3)), largo }
}

export default function Progreso() {
  const [demo] = useDemo()
  const { data, error, loading, reload } = useApi(() => api.getSalud(), [demo.escenario])

  return (
    <div className="progreso">
      <PageHeader kicker="Tu progreso" title="Tu negocio, más ordenado" />
      <div className="progreso-body">
        {loading && <LoadingBlock heights={[230, 90, 280, 90]} />}
        {error && <ErrorState error={error} onRetry={reload} />}
        {data && (
          <>
            <div className="progreso-col">
              <ScoreCard salud={data} />
              <Etapas etapas={data.etapas || ETAPAS_DEFAULT} actual={data.etapa_actual} />
            </div>
            <div className="progreso-col">
              <Componentes salud={data} />
              <Metas metas={data.metas_activas || []} />
            </div>
            <p className="progreso-privacy cc-small">
              Tu historial es tuyo. Solo se comparte si tú lo activas, y puedes retirarlo cuando quieras.
            </p>
          </>
        )}
        <Footnote />
      </div>
    </div>
  )
}

function ScoreCard({ salud }) {
  const historial = salud.historial || []
  const prev = historial.length >= 2 ? historial[historial.length - 2] : null
  const delta = salud.score_anterior != null ? salud.score - salud.score_anterior : null
  const desde = prev ? ` desde ${mesLabel(prev.mes).largo}` : ''
  let tendencia = null
  if (delta > 0) tendencia = `Subiste ${delta} ${delta === 1 ? 'punto' : 'puntos'}${desde}.`
  else if (delta < 0) tendencia = `Bajaste ${-delta} ${delta === -1 ? 'punto' : 'puntos'}${desde}. Abajo ves qué parte lo movió.`
  else if (delta === 0) tendencia = `Te mantienes igual${desde}.`

  const alt = historial.map((h) => `${mesLabel(h.mes).largo}: ${h.score}`).join(', ')

  return (
    <Card className="progreso-score" aria-labelledby="progreso-score-title">
      <div className="progreso-score__head">
        <h2 id="progreso-score-title" className="progreso-h2">
          Salud de caja
        </h2>
        <p className="progreso-score__value">
          <span className="progreso-score__num display num">{salud.score}</span>
          <span className="progreso-score__den num">/100</span>
          <span className="sr-only"> puntos</span>
        </p>
      </div>
      {tendencia && <p className="progreso-score__trend">{tendencia}</p>}

      {historial.length > 0 && (
        <figure className="progreso-chart">
          <div className="progreso-chart__bars" aria-hidden="true">
            {historial.map((h, i) => {
              const actual = i === historial.length - 1
              return (
                <div key={h.mes} className="progreso-chart__col">
                  <div className="progreso-chart__track">
                    <span className="progreso-chart__val num">{h.score}</span>
                    <div
                      className={`progreso-chart__bar${actual ? ' progreso-chart__bar--now' : ''}`}
                      style={{ '--h': Math.max(4, Math.min(100, h.score)) }}
                    />
                  </div>
                  <span className={`progreso-chart__label${actual ? ' progreso-chart__label--now' : ''}`}>
                    {mesLabel(h.mes).corto}
                  </span>
                </div>
              )
            })}
          </div>
          <figcaption className="sr-only">Salud de caja por mes, sobre 100. {alt}.</figcaption>
        </figure>
      )}
    </Card>
  )
}

function Etapas({ etapas, actual }) {
  const idx = Math.max(0, etapas.indexOf(actual))
  return (
    <Card as="nav" aria-label="Etapas de tu plan" className="progreso-steps-card">
      <ol className="progreso-steps">
        {etapas.map((e, i) => {
          const state = i < idx ? 'done' : i === idx ? 'current' : 'todo'
          return (
            <li key={e} className={`progreso-step progreso-step--${state}`} aria-current={state === 'current' ? 'step' : undefined}>
              <span className="progreso-step__dot num" aria-hidden="true">
                {state === 'done' ? <Icon name="check" size={18} strokeWidth={2.2} /> : i + 1}
              </span>
              <span className="progreso-step__label">
                {cap(e)}
                <span className="sr-only">
                  {state === 'done' ? ' (completada)' : state === 'current' ? ' (etapa actual)' : ' (por venir)'}
                </span>
              </span>
            </li>
          )
        })}
      </ol>
    </Card>
  )
}

function Indicador({ s }) {
  return (
    <li className="progreso-ind">
      <div className="progreso-ind__head">
        <h3 className="progreso-ind__name">{s.nombre}</h3>
        <span className="progreso-ind__val num">{s.valor}/100</span>
      </div>
      <div className="progreso-ind__track" aria-hidden="true">
        <div className="progreso-ind__fill" style={{ width: `${Math.max(0, Math.min(100, s.valor))}%` }} />
      </div>
      {s.detalle && <p className="progreso-ind__detail cc-small">{s.detalle}</p>}
    </li>
  )
}

function Componentes({ salud }) {
  const [open, setOpen] = useState(false)
  const listId = useId()
  const subs = salud.subindicadores || []
  const destacados = subs.filter((s) => s.destacado)
  const resto = subs.filter((s) => !s.destacado)
  const visibles = destacados.length ? destacados : subs.slice(0, 3)
  const ocultos = destacados.length ? resto : subs.slice(3)

  if (!subs.length) return null
  const porMejorar = subs.reduce((min, s) => (s.valor < min.valor ? s : min), subs[0])

  return (
    <Card aria-labelledby="progreso-comp-title">
      <h2 id="progreso-comp-title" className="progreso-h2">
        Qué lo compone
      </h2>
      {porMejorar.valor < 100 && (
        <p className="progreso-hint cc-small">
          Donde más puedes avanzar: <strong>{lowerFirst(porMejorar.nombre)}</strong>.
        </p>
      )}
      <ul className="progreso-inds" id={listId}>
        {visibles.map((s) => (
          <Indicador key={s.id} s={s} />
        ))}
        {open && ocultos.map((s) => <Indicador key={s.id} s={s} />)}
      </ul>

      {ocultos.length > 0 && (
        <button
          type="button"
          className="progreso-more"
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => setOpen((o) => !o)}
        >
          {open ? 'Ver menos' : `Ver los ${subs.length}`}
          <Icon name="chevronDown" size={20} className="progreso-more__chev" />
        </button>
      )}
      <MetaLine meta={salud.meta} />
    </Card>
  )
}

function Metas({ metas }) {
  const activas = metas.filter((m) => !m.estado || m.estado === 'activa')
  if (!activas.length) {
    return (
      <Card variant="dashed" className="progreso-meta-empty">
        <p className="cc-small cc-muted">
          Aún no tienes una meta activa. Puedes crear una desde el chat, por ejemplo “quiero apartar para el pedido”.
        </p>
        <Link to="/chat" className="cc-btn cc-btn--secondary cc-btn--sm">
          Crear una meta
        </Link>
      </Card>
    )
  }
  return (
    <>
      {activas.map((m) => (
        <Card key={m.meta_id} className="progreso-meta">
          <span className="progreso-meta__icon" aria-hidden="true">
            <Icon name="check" size={22} strokeWidth={2.2} />
          </span>
          <div>
            <h2 className="progreso-meta__title">Meta activa: {lowerFirst(m.titulo)}</h2>
            <p className="progreso-meta__detail num">
              {m.detalle}
              {m.acumulado != null && ` · llevas ${soles(m.acumulado)}`}
            </p>
          </div>
        </Card>
      ))}
    </>
  )
}
