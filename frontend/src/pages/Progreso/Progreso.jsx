import { useId, useState } from 'react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/useApi.js'
import { useDemo } from '../../lib/useDemo.js'
import { soles } from '../../lib/format.js'
import { ErrorState, Footnote, List, ListRow, LoadingBlock, MetaLine, PageHeader, Section } from '../../components/ui/index.jsx'
import './Progreso.css'

const ETAPAS_DEFAULT = ['organizar', 'estabilizar', 'proteger', 'crecer']

const cap = (s = '') => s.charAt(0).toUpperCase() + s.slice(1)
const lowerFirst = (s = '') => s.charAt(0).toLowerCase() + s.slice(1)
const clamp = (v) => Math.max(0, Math.min(100, Number(v) || 0))

const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

/** "2026-08" → { corto: "Ago", largo: "agosto" } (fijo: Intl es-PE da "Set" y mayúsculas según el motor) */
function mesLabel(mes) {
  const largo = MESES[Number(String(mes).slice(5, 7)) - 1] || String(mes)
  return { corto: cap(largo.slice(0, 3)), largo }
}

/** El subindicador más bajo (donde más puede avanzar), o null si todos están en 100. */
function masBajo(subs) {
  if (!subs.length) return null
  const min = subs.reduce((m, s) => (s.valor < m.valor ? s : m), subs[0])
  return min.valor < 100 ? min : null
}

/** Rachas conocidas → texto llano. Las de tipo desconocido no se muestran. */
const RACHAS = {
  semanas_registrando: (n) => ({ titulo: 'Anotar cada semana', sub: `${n} ${n === 1 ? 'semana seguida' : 'semanas seguidas'}` }),
}

export default function Progreso() {
  const [demo] = useDemo()
  const { data, error, loading, reload } = useApi(() => api.getSalud(), [demo.escenario])

  return (
    <div className="progreso">
      <PageHeader title="Tu progreso" sub="Tu negocio, más ordenado" />
      <div className="progreso-body">
        {loading && <LoadingBlock heights={[230, 90, 280, 90]} />}
        {error && <ErrorState error={error} onRetry={reload} />}
        {data && (
          <>
            <div className="progreso-col">
              <Score salud={data} />
              <Etapas
                etapas={data.etapas || ETAPAS_DEFAULT}
                actual={data.etapa_actual}
                porMejorar={masBajo(data.subindicadores || [])}
              />
            </div>
            <div className="progreso-col">
              <Componentes salud={data} />
              <Metas metas={data.metas_activas || []} rachas={data.rachas || []} />
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

function Score({ salud }) {
  const historial = salud.historial || []
  const prev = historial.length >= 2 ? historial[historial.length - 2] : null
  const delta = salud.score_anterior != null ? salud.score - salud.score_anterior : null
  const desde = prev ? ` desde ${mesLabel(prev.mes).largo}` : ''
  let tendencia = null
  let tono = 'neutral'
  if (delta > 0) {
    tendencia = `Subiste ${delta} ${delta === 1 ? 'punto' : 'puntos'}${desde}.`
    tono = 'ok'
  } else if (delta < 0) {
    tendencia = `Bajaste ${-delta} ${delta === -1 ? 'punto' : 'puntos'}${desde}. Abajo ves qué parte lo movió.`
    tono = 'warning'
  } else if (delta === 0) {
    tendencia = `Te mantienes igual${desde}.`
  }

  const alt = historial.map((h) => `${mesLabel(h.mes).largo}: ${h.score}`).join(', ')

  return (
    <section className="progreso-score" aria-labelledby="progreso-score-title">
      <h2 id="progreso-score-title" className="progreso-score__label">
        Salud de caja
      </h2>
      <p className="progreso-score__value">
        <span className="progreso-score__num display num">{salud.score}</span>
        <span className="progreso-score__den num"> de 100</span>
      </p>
      {tendencia && <p className={`progreso-score__trend progreso-score__trend--${tono}`}>{tendencia}</p>}

      {historial.length > 0 && (
        <figure className="progreso-chart">
          <div className="progreso-chart__bars" aria-hidden="true">
            {historial.map((h, i) => {
              const actual = i === historial.length - 1
              return (
                <div key={h.mes} className={`progreso-chart__col${actual ? ' progreso-chart__col--now' : ''}`}>
                  <div className="progreso-chart__track">
                    <div className="progreso-chart__bar" style={{ '--h': Math.max(4, clamp(h.score)) }} />
                  </div>
                  <span className="progreso-chart__label">{mesLabel(h.mes).corto}</span>
                </div>
              )
            })}
          </div>
          <figcaption className="sr-only">Salud de caja por mes, sobre 100. {alt}.</figcaption>
        </figure>
      )}
    </section>
  )
}

function Etapas({ etapas, actual, porMejorar }) {
  const idx = Math.max(0, etapas.indexOf(actual))
  const siguiente = etapas[idx + 1]
  return (
    <Section title="Tu etapa" className="progreso-etapas">
      <nav aria-label="Etapas de tu plan" className="progreso-stepper">
        <p className="progreso-stepper__now">
          Etapa {idx + 1} de {etapas.length}: <strong>{cap(etapas[idx])}</strong>
        </p>
        <ol className="progreso-stepper__track">
          {etapas.map((e, i) => {
            const state = i < idx ? 'done' : i === idx ? 'current' : 'todo'
            return (
              <li
                key={e}
                className={`progreso-stepper__step progreso-stepper__step--${state}`}
                aria-current={state === 'current' ? 'step' : undefined}
              >
                <span className="progreso-stepper__seg" aria-hidden="true" />
                <span className="progreso-stepper__name">
                  {cap(e)}
                  <span className="sr-only">
                    {state === 'done' ? ' (completada)' : state === 'current' ? ' (etapa actual)' : ' (por venir)'}
                  </span>
                </span>
              </li>
            )
          })}
        </ol>
        <p className="progreso-stepper__next">
          {siguiente ? (
            <>
              Siguiente: {cap(siguiente)}.
              {porMejorar && <> Donde más puedes avanzar: {lowerFirst(porMejorar.nombre)}.</>}
            </>
          ) : (
            'Estás en la última etapa.'
          )}
        </p>
      </nav>
    </Section>
  )
}

function Indicador({ s, esMasBajo }) {
  const sub = (
    <>
      {esMasBajo && <span className="progreso-ind__flag">Donde más puedes avanzar</span>}
      {s.detalle && <span className="progreso-ind__detail">{s.detalle}</span>}
      <span className="progreso-ind__track" aria-hidden="true">
        <span className="progreso-ind__fill" style={{ width: `${clamp(s.valor)}%` }} />
      </span>
    </>
  )
  return (
    <ListRow
      className="progreso-ind"
      title={s.nombre}
      sub={sub}
      amount={
        <span className="num">
          {s.valor}
          <span className="progreso-ind__den"> de 100</span>
        </span>
      }
    />
  )
}

function Componentes({ salud }) {
  const [open, setOpen] = useState(false)
  const listId = useId()
  const subs = salud.subindicadores || []
  if (!subs.length) return null

  const porMejorar = masBajo(subs)
  const destacados = subs.filter((s) => s.destacado)
  // Siempre a la vista: los destacados y el más bajo (para que se vea dónde avanzar).
  const visibles = destacados.length
    ? subs.filter((s) => s.destacado || s === porMejorar)
    : subs.slice(0, 3).concat(porMejorar && subs.indexOf(porMejorar) >= 3 ? [porMejorar] : [])
  const ocultos = subs.filter((s) => !visibles.includes(s))
  const mostrados = open ? subs : visibles

  return (
    <Section
      title="Qué lo compone"
      action={
        ocultos.length > 0 && (
          <button
            type="button"
            className="cc-section__action"
            aria-expanded={open}
            aria-controls={listId}
            onClick={() => setOpen((o) => !o)}
          >
            {open ? 'Ver menos' : `Ver los ${subs.length}`}
          </button>
        )
      }
    >
      <List id={listId}>
        {mostrados.map((s) => (
          <Indicador key={s.id} s={s} esMasBajo={s === porMejorar} />
        ))}
      </List>
      <MetaLine meta={salud.meta} />
    </Section>
  )
}

function Metas({ metas, rachas }) {
  const activas = metas.filter((m) => !m.estado || m.estado === 'activa')
  const rachasVisibles = rachas
    .filter((r) => RACHAS[r.tipo] && r.valor > 0)
    .map((r) => ({ key: r.tipo, ...RACHAS[r.tipo](r.valor) }))

  return (
    <Section title="Tus metas">
      <List>
        {activas.map((m) => (
          <ListRow
            key={m.meta_id}
            title={cap(m.titulo)}
            sub={m.detalle}
            amount={m.acumulado != null ? <span className="num">{soles(m.acumulado)}</span> : undefined}
            end={m.acumulado != null ? <span className="cc-row__sub">apartado</span> : undefined}
          />
        ))}
        {!activas.length && (
          <ListRow
            to="/chat"
            title="Crear una meta"
            sub="Aún no tienes una meta activa. Puedes crearla desde el chat, por ejemplo “quiero apartar para el pedido”."
          />
        )}
        {rachasVisibles.map((r) => (
          <ListRow key={r.key} title={r.titulo} sub={<span className="progreso-racha">{r.sub}</span>} />
        ))}
      </List>
    </Section>
  )
}
