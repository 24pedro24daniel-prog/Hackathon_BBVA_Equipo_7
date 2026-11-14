import { useId, useState } from 'react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/useApi.js'
import { useDemo } from '../../lib/useDemo.js'
import { ddmm } from '../../lib/format.js'
import {
  Card,
  ErrorState,
  Icon,
  List,
  ListRow,
  LoadingBlock,
  MetaLine,
  Money,
  PageHeader,
  ProgressBar,
} from '../../components/ui/index.jsx'
import './Progreso.css'

const ETAPAS_DEFAULT = ['organizar', 'estabilizar', 'proteger', 'crecer']

const cap = (s = '') => s.charAt(0).toUpperCase() + s.slice(1)
const clamp = (v) => Math.max(0, Math.min(100, Number(v) || 0))

const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

/** "2026-08" → { corto: "Ago", largo: "agosto" } (fijo: Intl es-PE da "Set" y mayúsculas según el motor) */
function mesLabel(mes) {
  const largo = MESES[Number(String(mes).slice(5, 7)) - 1] || String(mes)
  return { corto: cap(largo.slice(0, 3)), largo }
}

/** Palabra del puntaje general (como "Good" en SoFi). */
function calificacion(score) {
  const n = Number(score) || 0
  if (n >= 80) return 'Muy buena'
  if (n >= 60) return 'Buena'
  if (n >= 40) return 'Regular'
  return 'Débil'
}

/** Palabra + tono de cada parte del puntaje. */
function calificacionParte(valor) {
  const n = Number(valor) || 0
  if (n >= 80) return { texto: 'Muy bien', tono: 'ok' }
  if (n >= 60) return { texto: 'Bien', tono: 'neutral' }
  return { texto: 'Por mejorar', tono: 'warning' }
}

/** Peso del factor en palabras ("pesa 25%" sin cifras, como pide el sistema de diseño). */
function pesoEnPalabras(peso) {
  const p = Number(peso)
  if (!(p > 0)) return null
  if (p >= 0.25) return 'Es de lo que más pesa'
  if (p >= 0.2) return 'Pesa bastante'
  return 'Pesa menos'
}

/** Factores de más peso, para la frase que explica cómo se calcula. */
function masPesados(subs) {
  const max = Math.max(...subs.map((s) => Number(s.peso) || 0))
  if (!(max > 0)) return []
  return subs.filter((s) => Number(s.peso) === max)
}

const enFrase = (s = '') => s.charAt(0).toLowerCase() + s.slice(1)
const unirY = (arr) => (arr.length <= 1 ? arr.join('') : `${arr.slice(0, -1).join(', ')} y ${arr[arr.length - 1]}`)

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
      <PageHeader title="Tu progreso" />
      <div className="progreso-body">
        {loading && <LoadingBlock heights={[220, 180, 110, 300]} />}
        {error && <ErrorState error={error} onRetry={reload} />}
        {data && (
          <>
            <div className="progreso-col">
              <Score salud={data} />
              <Historial historial={data.historial || []} />
              <Etapa etapas={data.etapas || ETAPAS_DEFAULT} actual={data.etapa_actual} />
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
      </div>
    </div>
  )
}

/* ---------- Salud de caja (tarjeta de puntaje, patrón SoFi) ---------- */

function Score({ salud }) {
  const titleId = useId()
  const historial = salud.historial || []
  const prev = historial.length >= 2 ? historial[historial.length - 2] : null
  const delta = salud.score_anterior != null ? salud.score - salud.score_anterior : null
  const desde = prev ? `desde ${mesLabel(prev.mes).largo}` : 'desde el mes pasado'

  let tendencia = null
  let tono = 'neutral'
  if (delta > 0) {
    tendencia = `Subiste ${delta} ${delta === 1 ? 'punto' : 'puntos'}`
    tono = 'ok'
  } else if (delta < 0) {
    tendencia = `Bajaste ${-delta} ${delta === -1 ? 'punto' : 'puntos'}`
    tono = 'warning'
  } else if (delta === 0) {
    tendencia = 'Te mantienes igual'
  }

  const palabra = salud.etiqueta || calificacion(salud.score)
  const fechaFuente = salud.actualizado_en || salud.fecha_corte || salud.meta?.generado_en
  const fecha = fechaFuente ? ddmm(fechaFuente) : null
  const pos = clamp(salud.score)

  return (
    <Card className="progreso-score" aria-labelledby={titleId}>
      <h2 id={titleId} className="cc-card__title">
        Salud de caja
      </h2>
      <div className="progreso-score__top">
        <div className="progreso-score__main">
          <p className="progreso-score__value">
            <span className="progreso-score__num display num">{salud.score}</span>
            <span className="progreso-score__den num"> de 100</span>
          </p>
          <p className="progreso-score__rating">
            {palabra}
            {fecha && <> · actualizado {fecha}</>}
          </p>
        </div>
        {tendencia && (
          <div className="progreso-score__trend">
            <p className={`progreso-score__trend-main progreso-score__trend-main--${tono}`}>{tendencia}</p>
            <p className="progreso-score__trend-sub">{desde}</p>
          </div>
        )}
      </div>

      <div className="progreso-scale" aria-hidden="true">
        <div className="progreso-scale__bar">
          <span className="progreso-scale__seg progreso-scale__seg--1" />
          <span className="progreso-scale__seg progreso-scale__seg--2" />
          <span className="progreso-scale__seg progreso-scale__seg--3" />
          <span className="progreso-scale__seg progreso-scale__seg--4" />
          <span className="progreso-scale__marker" style={{ '--pos': pos }} />
        </div>
        <div className="progreso-scale__labels">
          <span>0</span>
          <span>100</span>
        </div>
      </div>
    </Card>
  )
}

/* ---------- Últimos meses: barras finas, mes actual en Electric ---------- */

function Historial({ historial }) {
  const [open, setOpen] = useState(false)
  const titleId = useId()
  const panelId = useId()
  if (!historial.length) return null
  const alt = historial.map((h) => `${mesLabel(h.mes).largo}: ${h.score}`).join(', ')

  return (
    <Card flush className="progreso-hist" aria-labelledby={titleId}>
      <h2 className="progreso-hist__heading">
        <button
          type="button"
          id={titleId}
          className="progreso-hist__toggle"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((o) => !o)}
        >
          <span>Últimos meses</span>
          <Icon name="chevronDown" size={20} className="progreso-hist__chev" />
        </button>
      </h2>
      <figure className="progreso-chart" id={panelId} hidden={!open}>
        <div className="progreso-chart__bars" aria-hidden="true">
          {historial.map((h, i) => {
            const actual = i === historial.length - 1
            return (
              <div key={h.mes} className={`progreso-chart__col${actual ? ' progreso-chart__col--now' : ''}`}>
                <span className="progreso-chart__val num">{h.score}</span>
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
    </Card>
  )
}

/* ---------- Etapa: texto + pista de 4 tramos ---------- */

function Etapa({ etapas, actual }) {
  const titleId = useId()
  const idx = Math.max(0, etapas.indexOf(actual))
  const siguiente = etapas[idx + 1]
  return (
    <Card className="progreso-etapa" aria-labelledby={titleId}>
      <h2 id={titleId} className="cc-card__title">
        Etapa {idx + 1} de {etapas.length}: {cap(etapas[idx])}
      </h2>
      <ol className="progreso-etapa__track" aria-label="Etapas de tu plan">
        {etapas.map((e, i) => {
          const state = i < idx ? 'done' : i === idx ? 'current' : 'todo'
          return (
            <li
              key={e}
              className={`progreso-etapa__step progreso-etapa__step--${state}`}
              aria-current={state === 'current' ? 'step' : undefined}
            >
              <span className="progreso-etapa__seg" aria-hidden="true" />
              <span className="progreso-etapa__name">
                {cap(e)}
                <span className="sr-only">
                  {state === 'done' ? ' (completada)' : state === 'current' ? ' (etapa actual)' : ' (por venir)'}
                </span>
              </span>
            </li>
          )
        })}
      </ol>
      <p className="progreso-etapa__next">{siguiente ? `Siguiente: ${cap(siguiente)}` : 'Estás en la última etapa'}</p>
    </Card>
  )
}

/* ---------- Qué lo compone (factores, patrón SoFi) ---------- */

function Factor({ s, esMasBajo }) {
  const { texto, tono } = calificacionParte(s.valor)
  const explica = s.que_mide || s.detalle
  const peso = pesoEnPalabras(s.peso)
  const sub = (
    <>
      {esMasBajo && <span className="progreso-factor__flag">Donde más puedes avanzar</span>}
      {explica && <span className="progreso-factor__detail">{explica}</span>}
      {s.que_mide && s.detalle && <span className="progreso-factor__detail">{s.detalle}</span>}
      <ProgressBar value={clamp(s.valor)} label={s.nombre} className="progreso-factor__bar" />
      {peso && <span className="progreso-factor__peso">{peso}</span>}
    </>
  )
  return (
    <ListRow
      className="progreso-factor"
      title={s.nombre}
      sub={sub}
      end={
        <>
          <span className={`progreso-factor__rating progreso-factor__rating--${tono}`}>{texto}</span>
          <span className="progreso-factor__value num">{s.valor} de 100</span>
        </>
      }
    />
  )
}

function Componentes({ salud }) {
  const titleId = useId()
  const subs = (salud.subindicadores || []).filter((s) => s && s.id)
  if (!subs.length) return null

  const porMejorar = masBajo(subs)
  const pesados = masPesados(subs).map((s) => enFrase(s.nombre))
  const cuantos = ['', 'una', 'dos', 'tres', 'cuatro', 'cinco', 'seis'][subs.length] || String(subs.length)

  return (
    <Card flush className="progreso-factores" aria-labelledby={titleId}>
      <div className="cc-card__head progreso-factores__head">
        <h2 id={titleId} className="cc-card__title">
          Qué lo compone
        </h2>
        <p className="progreso-factores__intro">
          Tu puntaje junta {cuantos} {subs.length === 1 ? 'cosa' : 'cosas'} de cómo manejas tu negocio.
          {pesados.length > 0 && <> Lo que más pesa: {unirY(pesados)}.</>}
        </p>
      </div>
      <List>
        {subs.map((s) => (
          <Factor key={s.id} s={s} esMasBajo={s === porMejorar} />
        ))}
      </List>
      {salud.meta && (
        <div className="progreso-factores__meta">
          <MetaLine meta={salud.meta} />
        </div>
      )}
    </Card>
  )
}

/* ---------- Metas (patrón "pots" de Monzo) ---------- */

/** Avance 0–100 solo si los datos traen un objetivo; nunca se inventa. */
function avanceMeta(m) {
  const objetivo = m.objetivo ?? m.monto_objetivo
  if (objetivo > 0 && m.acumulado != null) return clamp((m.acumulado / objetivo) * 100)
  if (m.progreso != null) return clamp(Number(m.progreso) <= 1 ? Number(m.progreso) * 100 : m.progreso)
  return null
}

function Metas({ metas, rachas }) {
  const titleId = useId()
  const activas = metas.filter((m) => !m.estado || m.estado === 'activa')
  const rachasVisibles = rachas
    .filter((r) => RACHAS[r.tipo] && r.valor > 0)
    .map((r) => ({ key: r.tipo, ...RACHAS[r.tipo](r.valor) }))

  return (
    <Card flush className="progreso-metas" aria-labelledby={titleId}>
      <div className="cc-card__head">
        <h2 id={titleId} className="cc-card__title">
          Tus metas
        </h2>
      </div>
      <List>
        {activas.map((m) => {
          const avance = avanceMeta(m)
          return (
            <ListRow
              key={m.meta_id}
              className="progreso-meta"
              title={cap(m.titulo)}
              sub={
                <>
                  {m.detalle && <span className="progreso-meta__detail">{m.detalle}</span>}
                  {avance != null && (
                    <ProgressBar value={Math.round(avance)} tone="ok" label={`Avance de ${m.titulo}`} className="progreso-meta__bar" />
                  )}
                </>
              }
              amount={m.acumulado != null ? <Money value={m.acumulado} /> : undefined}
              end={m.acumulado != null ? <span className="cc-row__sub">apartado</span> : undefined}
            />
          )
        })}
        {!activas.length && (
          <ListRow to="/chat" title="Crear una meta" sub="Dila en el chat, por ejemplo “quiero apartar para el pedido”." />
        )}
        {rachasVisibles.map((r) => (
          <ListRow key={r.key} title={r.titulo} sub={r.sub} />
        ))}
      </List>
    </Card>
  )
}
