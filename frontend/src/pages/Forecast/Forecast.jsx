import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/index.js'
import { useApi } from '../../api/useApi.js'
import { useDemo } from '../../lib/useDemo.js'
import { ddmm, soles, weekdayDdmm } from '../../lib/format.js'
import { Button, Card, ErrorState, LoadingBlock, PageHeader, TraceInfo } from '../../components/ui/index.jsx'
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
      <PageHeader kicker="Próximos 30 días" title="Así se mueve tu caja" />
      <div className="fc-body">
        {loading && !data ? (
          <LoadingBlock heights={[300, 200, 52]} />
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

  return (
    <div className="fc-layout">
      <Card className="fc-chart-card">
        <div className="fc-kpis">
          <div>
            <p className="fc-kpi__label">Hoy</p>
            <p className="fc-kpi__value display num">{soles(f.saldo_actual)}</p>
          </div>
          {critico && (
            <div className="fc-kpi--danger">
              <p className="fc-kpi__label">Peor día · {ddmm(critico.fecha)}</p>
              <p className="fc-kpi__value display num">{soles(critico.saldo_p50)}</p>
            </div>
          )}
        </div>

        <ForecastChart points={points} minimo={minimo} worstFecha={critico?.fecha} />

        <ul className="fc-legend" aria-label="Leyenda">
          <li>
            <span className="fc-sw fc-sw--line" aria-hidden="true" />
            Lo esperado
          </li>
          <li>
            <span className="fc-sw fc-sw--band" aria-hidden="true" />
            Rango mejor–peor
          </li>
          {minimo != null && (
            <li>
              <span className="fc-sw fc-sw--min" aria-hidden="true" />
              Mínimo {soles(minimo)}
            </li>
          )}
          <li>
            <span className="fc-sw fc-sw--risk" aria-hidden="true" />
            Días en riesgo
          </li>
        </ul>
      </Card>

      <div className="fc-side">
        <Card className="fc-next">
          <h2 className="fc-card-title">Lo que viene</h2>
          {eventos.length ? (
            <ul className="fc-events">
              {eventos.map((e) => (
                <li key={`${e.fecha}-${e.concepto}`}>
                  <span>
                    {weekdayDdmm(e.fecha)} · {e.concepto}
                  </span>
                  <strong className={'num' + (e.monto > 0 ? ' fc-pos' : '')}>{soles(e.monto, { sign: true })}</strong>
                </li>
              ))}
            </ul>
          ) : (
            <p className="cc-muted">No tienes pagos ni cobros con fecha en los próximos 30 días.</p>
          )}
          {eventos.some((e) => e.tipo === 'cobro_fiado') && (
            <p className="cc-small cc-muted">Fiados contados según qué tan probable es que te paguen.</p>
          )}
        </Card>

        <TraceInfo fundamento={f.fundamento} limites={f.limites} confianza={f.confianza} meta={f.meta} />

        <Button block size="lg" onClick={() => navigate('/simulador')}>
          Probar qué hacer
        </Button>
      </div>
    </div>
  )
}
