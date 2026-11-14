import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/index.js'
import { useApi } from '../../api/useApi.js'
import { useDemo } from '../../lib/useDemo.js'
import { ddmm, soles, weekdayDdmm } from '../../lib/format.js'
import {
  Button,
  Card,
  ErrorState,
  List,
  ListRow,
  LoadingBlock,
  PageHeader,
  Section,
  Status,
  TraceInfo,
} from '../../components/ui/index.jsx'
import ForecastChart from './ForecastChart.jsx'
import './Forecast.css'

/** Serie que arranca en la fecha de corte con el saldo de hoy (sin incertidumbre). */
function buildPoints(forecast) {
  const s0 = forecast.saldo_actual
  return [{ fecha: forecast.fecha_corte, p10: s0, p50: s0, p90: s0, hoy: true }, ...(forecast.serie || [])]
}

export default function Forecast() {
  const [demo] = useDemo()
  const { data, error, loading, reload } = useApi(() => api.getForecast(30), [demo.escenario])

  return (
    <div className="fc-page">
      <PageHeader sub="Próximos 30 días" title="Así se mueve tu caja" />
      <div className="fc-body">
        {loading && !data ? (
          <LoadingBlock heights={[120, 300, 200]} />
        ) : error ? (
          <ErrorState error={error} onRetry={reload} />
        ) : data?.disponible === false || !data?.serie?.length ? (
          <ForecastEmpty data={data} />
        ) : (
          <ForecastContent f={data} />
        )}
      </div>
    </div>
  )
}

function ForecastEmpty({ data }) {
  const navigate = useNavigate()
  const tiene = data?.dias_con_datos ?? 0
  const requiere = data?.dias_requeridos ?? 14
  return (
    <Card className="fc-empty">
      <h2 className="fc-card-title">Todavía estoy conociendo tu negocio</h2>
      <p>
        Para mostrarte cómo se mueve tu caja los próximos 30 días necesito al menos {requiere} días con tus ventas y
        gastos anotados. Llevas <strong>{tiene}</strong>.
      </p>
      <div
        className="fc-progress"
        role="progressbar"
        aria-label="Días con datos"
        aria-valuemin={0}
        aria-valuemax={requiere}
        aria-valuenow={Math.min(tiene, requiere)}
        aria-valuetext={`${tiene} de ${requiere} días`}
      >
        <span style={{ width: `${Math.min(100, (tiene / requiere) * 100)}%` }} />
      </div>
      <p className="cc-small cc-muted">
        {tiene} de {requiere} días · Te faltan {Math.max(0, requiere - tiene)}
      </p>
      <Button block icon="chat" onClick={() => navigate('/chat')}>
        Anotar mis ventas de hoy
      </Button>
    </Card>
  )
}

function ForecastContent({ f }) {
  const navigate = useNavigate()
  const points = useMemo(() => buildPoints(f), [f])
  const critico = f.dia_critico
  const minimo = f.minimo_operativo
  const eventos = f.proximos_eventos || []

  // Punto más bajo: el día crítico del backend o, si no viene, el menor "lo esperado" de la serie.
  const bajo = useMemo(() => {
    if (critico) return { fecha: critico.fecha, saldo: critico.saldo_p50 }
    const m = points.reduce((a, p) => (p.p50 < a.p50 ? p : a), points[0])
    return { fecha: m.fecha, saldo: m.p50 }
  }, [critico, points])

  const riesgo = useMemo(
    () => new Set(minimo == null ? [] : points.filter((p) => !p.hoy && p.p50 < minimo).map((p) => p.fecha)),
    [points, minimo],
  )

  const enRiesgo = minimo != null && bajo.saldo < minimo
  const heroTone = bajo.saldo < 0 ? 'danger' : enRiesgo ? 'warning' : 'ok'

  return (
    <div className="fc-layout">
      <div className="fc-main">
        <section className="fc-hero" aria-labelledby="fc-hero-lead">
          <p id="fc-hero-lead" className="fc-hero__lead">
            {enRiesgo ? `El ${ddmm(bajo.fecha)} tu caja bajaría a` : `Lo más bajo que llegaría tu caja (${ddmm(bajo.fecha)})`}
          </p>
          <p className={`fc-hero__num display num fc-hero__num--${heroTone}`}>{soles(bajo.saldo)}</p>
          <p className="fc-hero__ctx">
            Hoy tienes <span className="num">{soles(f.saldo_actual)}</span>
            {minimo != null && (
              <>
                {' · '}Tu mínimo para operar es <span className="num">{soles(minimo)}</span>
              </>
            )}
          </p>
          {riesgo.size > 0 && (
            <p className="fc-hero__risk">
              <Status tone="danger">
                {riesgo.size === 1 ? '1 día debajo de tu mínimo' : `${riesgo.size} días debajo de tu mínimo`}
              </Status>
            </p>
          )}
        </section>

        <Card className="fc-chart-card">
          <ForecastChart points={points} minimo={minimo} worstFecha={critico?.fecha} />
          <p className="fc-legend">
            La línea es lo esperado; la sombra, el rango entre el peor y el mejor caso.
            {riesgo.size > 0 && ' En naranja, los días debajo de tu mínimo.'}
          </p>
        </Card>
      </div>

      <div className="fc-side">
        <Section title="Lo que viene">
          {eventos.length ? (
            <List>
              {eventos.map((e) => {
                const esRiesgo = riesgo.has(e.fecha)
                return (
                  <ListRow
                    key={`${e.fecha}-${e.concepto}`}
                    title={e.concepto}
                    sub={
                      <>
                        {weekdayDdmm(e.fecha)}
                        {esRiesgo && (
                          <>
                            {' · '}
                            <Status tone="danger">Día en riesgo</Status>
                          </>
                        )}
                      </>
                    }
                    amount={<span className="num">{soles(e.monto, { sign: true })}</span>}
                    amountTone={e.monto > 0 ? 'pos' : undefined}
                  />
                )
              })}
            </List>
          ) : (
            <p className="cc-muted fc-none">No tienes pagos ni cobros con fecha en los próximos 30 días.</p>
          )}
          {eventos.some((e) => e.tipo === 'cobro_fiado') && (
            <p className="cc-small cc-muted fc-note">Fiados contados según qué tan probable es que te paguen.</p>
          )}
        </Section>

        <TraceInfo fundamento={f.fundamento} limites={f.limites} confianza={f.confianza} meta={f.meta} />

        <Button block size="lg" onClick={() => navigate('/simulador')}>
          Probar qué hacer
        </Button>
      </div>
    </div>
  )
}
