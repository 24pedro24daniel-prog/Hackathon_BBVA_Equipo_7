import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../api/index.js'
import { useApi } from '../../api/useApi.js'
import { useDemo } from '../../lib/useDemo.js'
import { soles, solesRange, weekdayDdmm, pct, daysBetween } from '../../lib/format.js'
import DemoMenu from '../../components/layout/DemoMenu.jsx'
import {
  Card,
  Button,
  Icon,
  PageHeader,
  TraceInfo,
  LoadingBlock,
  Skeleton,
  ErrorState,
  Footnote,
} from '../../components/ui/index.jsx'
import './Inicio.css'

// No hay endpoint de empresa en el contrato todavía; el nombre va fijo para la demo.
const NOMBRE_NEGOCIO = 'Bodega Don Pedro'
const DIAS_REQUERIDOS_DEFAULT = 14

/** "2026-11" en hora de Lima */
function periodoActual() {
  const parts = new Intl.DateTimeFormat('en-CA', { year: 'numeric', month: '2-digit', timeZone: 'America/Lima' }).format(new Date())
  return parts.slice(0, 7)
}

const diasTxt = (n) => `${n} ${n === 1 ? 'día' : 'días'}`

export default function Inicio() {
  const [demo] = useDemo()
  const deps = [demo.escenario]
  // Las tres llamadas salen en paralelo; cada bloque se pinta cuando llega su dato.
  const resumen = useApi(() => api.getResumen(periodoActual()), deps)
  const forecast = useApi(() => api.getForecast(30), deps)
  const alertas = useApi(() => api.getAlertas('activa'), deps)

  const r = resumen.data
  const diasConDatos = r?.dias_con_datos
  const diasRequeridos = r?.dias_requeridos_forecast ?? forecast.data?.dias_requeridos ?? DIAS_REQUERIDOS_DEFAULT
  const esNuevo =
    typeof diasConDatos === 'number'
      ? diasConDatos < diasRequeridos
      : forecast.data?.disponible === false || (!r && demo.escenario === 'nuevo')

  const corte = r?.corte ?? forecast.data?.fecha_corte
  const kicker = esNuevo
    ? `${NOMBRE_NEGOCIO}${typeof diasConDatos === 'number' ? ` · día ${diasConDatos}` : ''}`
    : `${NOMBRE_NEGOCIO}${corte ? ` · ${weekdayDdmm(corte).toLowerCase()}` : ''}`

  return (
    <div className="inicio">
      <PageHeader
        kicker={kicker}
        title={esNuevo ? 'Estás empezando bien' : '¿Cómo va mi caja?'}
        right={<DemoMenu />}
      />
      <div className="inicio__body">
        {resumen.loading && !r ? (
          <LoadingBlock heights={[170, 120, 110, 110]} />
        ) : resumen.error ? (
          <ErrorState error={resumen.error} onRetry={resumen.reload} />
        ) : esNuevo ? (
          <InicioNuevo resumen={r} diasConDatos={diasConDatos ?? 0} diasRequeridos={diasRequeridos} />
        ) : (
          <InicioPedro resumen={r} forecast={forecast} alertas={alertas} />
        )}
      </div>
      <Footnote />
    </div>
  )
}

/* ---------------- Página 5: Pedro con historial ---------------- */

function InicioPedro({ resumen, forecast, alertas }) {
  const ind = resumen.indicadores
  const retiros = ind.retiros_personales
  const cobro = ind.pendiente_cobro
  const pagos = ind.pagos_pendientes
  const ganancia = ind.ganancia_neta

  return (
    <>
      <AlertaPrincipal alertas={alertas} corte={resumen.corte} />

      <div className="inicio__pair">
        <SaldoCard tipo="negocio" valor={ind.saldo_caja_negocio.valor} nota="en caja hoy" />
        <SaldoCard
          tipo="casa"
          valor={retiros.valor}
          nota={
            retiros.promedio_historico != null
              ? `sacaste este mes · lo usual ${soles(retiros.promedio_historico)}`
              : 'sacaste este mes'
          }
        />
      </div>

      <Disponible forecast={forecast} />

      <div className="inicio__pair">
        <Link to="/cuentas" className="inicio__link-card">
          <Card as="div" className="inicio__mini">
            <p className="inicio__mini-label">Te deben</p>
            <p className="inicio__mini-value display num">{soles(cobro.valor)}</p>
            <p className="cc-small cc-muted">{cobro.n_fiados} {cobro.n_fiados === 1 ? 'fiado' : 'fiados'}</p>
          </Card>
        </Link>
        <Link to="/cuentas" className="inicio__link-card">
          <Card as="div" className="inicio__mini">
            <p className="inicio__mini-label">Debes</p>
            <p className="inicio__mini-value display num">{soles(pagos.valor)}</p>
            <p className="cc-small cc-muted">
              {pagos.detalle || `${pagos.n_obligaciones} ${pagos.n_obligaciones === 1 ? 'pago' : 'pagos'}`}
            </p>
          </Card>
        </Link>
      </div>

      <Card aria-label="Resumen del mes">
        <dl className="inicio__rows">
          <Fila
            label="Vendiste este mes"
            valor={soles(ind.ingresos_mes.valor)}
            variacion={ind.ingresos_mes.variacion_pct}
            malaSiBaja
          />
          <Fila label="Gastaste en el negocio" valor={soles(ind.egresos_mes.valor)} variacion={ind.egresos_mes.variacion_pct} />
          <Fila
            label="Ganancia aproximada"
            valor={ganancia.rango ? solesRange(ganancia.rango) : soles(ganancia.valor)}
          />
        </dl>
        {resumen.variacion_vs && <p className="cc-xs cc-muted inicio__vs">Comparado con el mes pasado al mismo día.</p>}
      </Card>
    </>
  )
}

function AlertaPrincipal({ alertas, corte }) {
  const navigate = useNavigate()
  if (alertas.loading && !alertas.data) return <Skeleton height={190} />
  if (alertas.error) return <ErrorState error={alertas.error} onRetry={alertas.reload} />

  const items = [...(alertas.data?.items ?? [])].sort((a, b) => (a.prioridad ?? 99) - (b.prioridad ?? 99))
  const a = items[0]
  if (!a) {
    return (
      <Card className="inicio__ok">
        <Icon name="check" size={22} />
        <p>Por ahora no veo problemas de caja en tus próximos 30 días.</p>
      </Card>
    )
  }

  const dias = a.dias_para_evento ?? (corte && a.fecha_evento ? daysBetween(corte, a.fecha_evento) : null)
  const porque = a.resumen_causas || a.causas?.map((c) => c.descripcion.toLowerCase()).join(', ')
  const kicker = [dias != null ? `En ${diasTxt(dias)}` : null, a.probabilidad != null ? `${pct(a.probabilidad)} probable` : null]
    .filter(Boolean)
    .join(' · ')

  return (
    <Card variant="danger" className="inicio__alerta" role="region" aria-label="Alerta de caja">
      {kicker && (
        <p className="inicio__alerta-kicker">
          <Icon name="warning" size={20} />
          {kicker}
        </p>
      )}
      <h2 className="inicio__alerta-title display">{a.titulo}</h2>
      {porque && <p className="inicio__alerta-why">Por qué: {porque}</p>}
      <Button size="lg" onClick={() => navigate('/simulador')}>
        {a.accion?.texto_boton || 'Ver qué puedo hacer'}
      </Button>
    </Card>
  )
}

function SaldoCard({ tipo, valor, nota }) {
  const casa = tipo === 'casa'
  return (
    <Card variant={casa ? 'casa' : undefined} className={`inicio__saldo inicio__saldo--${tipo}`}>
      <p className="inicio__saldo-label">
        <Icon name={casa ? 'house' : 'store'} size={18} />
        {casa ? 'Casa' : 'Negocio'}
      </p>
      <p className="inicio__saldo-value display num">{soles(valor)}</p>
      <p className="cc-small cc-muted">{nota}</p>
    </Card>
  )
}

const LABELS_COMPONENTES = {
  saldo_actual: ['En caja hoy', 1],
  cobros_esperados: ['Cobros que esperas', 1],
  pagos_comprometidos: ['Pagos hasta tu próximo vencimiento', -1],
  minimo_operativo: ['Mínimo para seguir operando', -1],
  reserva_impuestos: ['Reserva para impuestos', -1],
}

function Disponible({ forecast }) {
  if (forecast.loading && !forecast.data) return <Skeleton height={120} />
  if (forecast.error) return <ErrorState error={forecast.error} onRetry={forecast.reload} />
  const f = forecast.data
  const d = f?.disponible_para_gastar
  if (!d) return null

  const comps = Object.entries(d.componentes ?? {})
  const total = comps.reduce((s, [k, v]) => s + (LABELS_COMPONENTES[k]?.[1] ?? 1) * v, 0)
  const desglose = comps.length > 0 && (
    <div>
      <ul className="inicio__desglose">
        {comps.map(([k, v]) => {
          const [label, signo] = LABELS_COMPONENTES[k] ?? [k.replaceAll('_', ' '), 1]
          return (
            <li key={k}>
              <span>{label}</span>
              <span className="num">{soles(signo * v, { sign: true })}</span>
            </li>
          )
        })}
        <li className="inicio__desglose-total">
          <span>Resultado</span>
          <span className="num">{soles(total)}</span>
        </li>
      </ul>
      {total < 0 && Math.round(d.valor) === 0 && (
        <p className="cc-xs">Como el resultado es menor que cero, hoy lo disponible es {soles(0)}.</p>
      )}
    </div>
  )

  return (
    <>
      <Card className="inicio__disponible" aria-labelledby="inicio-disp-label">
        <p id="inicio-disp-label" className="cc-eyebrow">Disponible para gastar</p>
        <p className="inicio__disp-value display num">{soles(d.valor)}</p>
        {d.mensaje && <p className="inicio__disp-msg">{d.mensaje}</p>}
      </Card>
      <TraceInfo
        fundamento={f.fundamento}
        limites={f.limites}
        confianza={f.confianza}
        meta={f.meta}
        extra={desglose ? [['Cómo se calcula', desglose]] : []}
      />
    </>
  )
}

function Fila({ label, valor, variacion, malaSiBaja }) {
  let delta = null
  if (variacion != null && Math.round(Math.abs(variacion)) > 0) {
    const baja = variacion < 0
    const n = Math.round(Math.abs(variacion))
    const mala = malaSiBaja && baja
    delta = (
      <span
        className={`inicio__delta${mala ? ' inicio__delta--mala' : ''}`}
        aria-label={`${baja ? 'bajó' : 'subió'} ${n}% frente al mes pasado`}
      >
        <span aria-hidden="true">{baja ? '▼' : '▲'}</span> {n}%
      </span>
    )
  }
  return (
    <div className="inicio__row">
      <dt>{label}</dt>
      <dd className="num">
        <strong>{valor}</strong>
        {delta}
      </dd>
    </div>
  )
}

/* ---------------- Página 10: día 3 ---------------- */

function InicioNuevo({ resumen, diasConDatos, diasRequeridos }) {
  const navigate = useNavigate()
  const ind = resumen?.indicadores
  const faltan = Math.max(diasRequeridos - diasConDatos, 0)
  const ganancia = ind?.ganancia_neta

  return (
    <>
      <Card className="inicio__progreso">
        <h2 className="inicio__progreso-title">
          Necesito {diasRequeridos} días de tus ventas para avisarte antes de que te falte plata
        </h2>
        <div
          className="inicio__segs"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={diasRequeridos}
          aria-valuenow={Math.min(diasConDatos, diasRequeridos)}
          aria-label="Días con ventas anotadas"
        >
          {Array.from({ length: diasRequeridos }, (_, i) => (
            <span key={i} className={i < diasConDatos ? 'is-on' : undefined} />
          ))}
        </div>
        <p className="cc-small cc-muted">
          {diasConDatos} de {diasRequeridos} días · sigue mandando tus ventas por el chat.
        </p>
        <Button size="lg" block icon="mic" onClick={() => navigate('/chat')}>
          Anotar una venta
        </Button>
      </Card>

      {ind && (
        <>
          <div className="inicio__pair">
            <SaldoCard tipo="negocio" valor={ind.saldo_caja_negocio.valor} nota="según lo que anotaste" />
            <SaldoCard tipo="casa" valor={ind.retiros_personales.valor} nota={`sacaste en ${diasTxt(diasConDatos)}`} />
          </div>

          <Card>
            <dl className="inicio__rows">
              <div className="inicio__row">
                <dt>Vendiste en {diasTxt(diasConDatos)}</dt>
                <dd className="num">
                  <strong>{soles(ind.ingresos_mes.valor)}</strong>
                </dd>
              </div>
              <div className="inicio__row">
                <dt>Ganancia aproximada</dt>
                <dd className="num">
                  <strong>
                    {ganancia.rango
                      ? `entre ${soles(ganancia.rango[0])} y ${soles(ganancia.rango[1])}`
                      : soles(ganancia.valor)}
                  </strong>
                </dd>
              </div>
            </dl>
            {ganancia.es_aproximada && (
              <p className="cc-small cc-muted inicio__vs">
                Es un rango porque aún no conozco el costo de todos tus productos.
              </p>
            )}
          </Card>
        </>
      )}

      <Card variant="dashed" className="inicio__proximos">
        <h2 className="inicio__proximos-title">
          <Icon name="clock" size={20} />
          Tus próximos 30 días
        </h2>
        <p className="cc-muted">
          Aparecerán aquí en {diasTxt(faltan)}. Mientras, cuéntame tus pagos con fecha (“le debo 800 a Andina para el
          30”) y te aviso antes de que venzan.
        </p>
      </Card>
    </>
  )
}
