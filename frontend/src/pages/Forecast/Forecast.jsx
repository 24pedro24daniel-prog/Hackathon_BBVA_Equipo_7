import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/index.js'
import { useApi } from '../../api/useApi.js'
import { ddmm, soles, solesRange, weekdayDdmm } from '../../lib/format.js'
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
  ProgressBar,
  Status,
} from '../../components/ui/index.jsx'
import ForecastChart from './ForecastChart.jsx'
import './Forecast.css'

/** Serie que arranca en la fecha de corte con el saldo de hoy (sin incertidumbre). */
function buildPoints(forecast) {
  const s0 = forecast.saldo_actual
  return [{ fecha: forecast.fecha_corte, p10: s0, p50: s0, p90: s0, hoy: true }, ...(forecast.serie || [])]
}

/** tone de la página → props de <Money> (Money solo conoce neutral | pos | neg) */
function moneyTone(tone) {
  if (tone === 'danger') return { tone: 'neg' }
  if (tone === 'warning') return { tone: 'neutral', className: 'fc-money--warning' }
  return { tone: 'neutral' }
}

export default function Forecast() {
  const { data, error, loading, reload } = useApi(() => api.getForecast(30), [])

  return (
    <div className="fc-page">
      <PageHeader title="Próximos 30 días" />
      <div className="fc-body">
        {loading && !data ? (
          <LoadingBlock heights={[340, 200]} />
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
  const requiere = data?.dias_requeridos ?? 28
  return (
    <Card className="fc-empty" aria-labelledby="fc-empty-title">
      <h2 id="fc-empty-title" className="cc-card__title">
        Todavía estoy conociendo tu negocio
      </h2>
      <p className="fc-empty__text">
        Registra tus ventas y gastos durante {requiere} días. Con ese historial podremos anticiparte posibles faltantes de caja.
      </p>
      <ProgressBar value={Math.min(tiene, requiere)} max={requiere} label="Días con transacciones anotadas" />
      <p className="cc-small cc-muted">
        {tiene} de {requiere} días
      </p>
      <Button size="lg" icon="mic" onClick={() => navigate('/app/chat')}>
        Registrar transacción
      </Button>
    </Card>
  )
}

function ForecastContent({ f }) {
  const navigate = useNavigate()
  const [sel, setSel] = useState(null)
  const points = useMemo(() => buildPoints(f), [f])
  const critico = f.dia_critico
  const minimo = f.minimo_operativo
  const eventos = f.proximos_eventos || []

  // Día a destacar: el día crítico del backend (primer día en rojo) o, si no viene, el menor "lo esperado" de la serie.
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
  const tone = bajo.saldo < 0 ? 'danger' : enRiesgo ? 'warning' : 'ok'
  const rango = `${ddmm(points[0].fecha)} – ${ddmm(points[points.length - 1].fecha)}`
  const dia = sel !== null ? points[sel] : null

  let estado
  if (riesgo.size > 0) estado = riesgo.size === 1 ? '1 día por debajo de tu mínimo' : `${riesgo.size} días por debajo de tu mínimo`
  else if (minimo != null) estado = `Te mantienes sobre tu mínimo los ${points.length - 1} días`
  const statusTone = riesgo.size === 0 ? 'ok' : tone === 'ok' ? 'warning' : tone

  return (
    <div className="fc-layout">
      <Card className="fc-chart-card" aria-labelledby="fc-chart-title">
        <div className="fc-head">
          <div className="fc-head__start">
            <h2 id="fc-chart-title" className="cc-card__title">
              Tu caja
            </h2>
            <p className="fc-head__muted">{dia ? (dia.hoy ? `Hoy, ${ddmm(dia.fecha)}` : weekdayDdmm(dia.fecha)) : rango}</p>
          </div>
          <div className="fc-head__end">
            {dia ? (
              <>
                <Money value={dia.p50} size="lg" {...moneyTone(dia.p50 < 0 ? 'danger' : 'ok')} />
                <p className="fc-head__muted">{dia.hoy ? 'lo que tienes hoy' : 'lo esperado'}</p>
              </>
            ) : (
              <>
                <Money value={bajo.saldo} size="lg" {...moneyTone(tone)} />
                <p className="fc-head__muted">
                  {critico?.obligacion_asociada?.proveedor
                    ? `al pagar a ${critico.obligacion_asociada.proveedor}, el ${ddmm(bajo.fecha)}`
                    : `lo más bajo, el ${ddmm(bajo.fecha)}`}
                </p>
              </>
            )}
          </div>
        </div>

        <p className="fc-status">
          {dia ? (
            <span className="cc-muted">
              {dia.hoy
                ? minimo != null && `Tu mínimo para operar es ${soles(minimo)}`
                : `Podría estar entre ${solesRange([dia.p10, dia.p90])}`}
            </span>
          ) : estado ? (
            <span className={`fc-status__text fc-status__text--${statusTone}`}>{estado}</span>
          ) : null}
        </p>

        <ForecastChart points={points} minimo={minimo} worstFecha={critico?.fecha} sel={sel} onSel={setSel} />

        <p className="fc-legend">La línea es lo esperado; la sombra, el rango posible. Toca el gráfico para ver cada día.</p>
      </Card>

      <div className="fc-side">
        <Card flush aria-labelledby="fc-next-title">
          <div className="cc-card__head">
            <h2 id="fc-next-title" className="cc-card__title">
              Lo que viene
            </h2>
          </div>
          {eventos.length ? (
            <List>
              {eventos.map((e) => {
                const esRiesgo = riesgo.has(e.fecha)
                const entra = e.monto > 0
                return (
                  <ListRow
                    key={`${e.fecha}-${e.concepto}`}
                    lead={<Icon name={entra ? 'arrowDown' : 'receipt'} size={20} />}
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
                    amount={entra ? <Money value={e.monto} sign tone="pos" /> : <Money value={e.monto} />}
                  />
                )
              })}
            </List>
          ) : (
            <p className="cc-muted fc-pad">No tienes pagos ni cobros con fecha en los próximos {f.horizonte_dias} días.</p>
          )}
          {eventos.some((e) => e.tipo === 'cobro_fiado') && (
            <p className="cc-small cc-muted fc-pad fc-note">Fiados contados según qué tan probable es que te paguen.</p>
          )}
        </Card>

        <Button block size="lg" onClick={() => navigate('/app/chat', { state: { intent: 'plan_caja' } })}>
          Probar qué hacer
        </Button>
      </div>
    </div>
  )
}
