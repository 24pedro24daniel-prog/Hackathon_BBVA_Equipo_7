import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../api/index.js'
import { useApi } from '../../api/useApi.js'
import { useDemo } from '../../lib/useDemo.js'
import { soles, solesRange, weekdayDdmm, daysBetween, diferenciaSoles } from '../../lib/format.js'
import DemoMenu from '../../components/layout/DemoMenu.jsx'
import {
  Card,
  Button,
  Icon,
  PageHeader,
  Section,
  List,
  ListRow,
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

// Acciones rápidas del inicio (solo rutas reales), como la fila "Enviar / Cobrar" de una app bancaria.
const ACCIONES = [
  { to: '/chat', icon: 'mic', label: 'Anotar venta' },
  { to: '/30-dias', icon: 'chart', label: 'Ver 30 días' },
  { to: '/cuentas', icon: 'list', label: 'Cuentas' },
]

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
  const sub = esNuevo
    ? `${NOMBRE_NEGOCIO}${typeof diasConDatos === 'number' ? ` · día ${diasConDatos}` : ''}`
    : `${NOMBRE_NEGOCIO}${corte ? ` · ${weekdayDdmm(corte).toLowerCase()}` : ''}`

  return (
    <div className="inicio">
      <PageHeader sub={sub} title={esNuevo ? 'Estás empezando bien' : '¿Cómo va mi caja?'} right={<DemoMenu />} />
      <div className="inicio__body">
        {resumen.loading && !r ? (
          <LoadingBlock heights={[120, 180, 120, 140]} />
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
  const cobro = ind.pendiente_cobro
  const pagos = ind.pagos_pendientes
  const ganancia = ind.ganancia_neta

  return (
    <div className="inicio__grid">
      <div className="inicio__main">
        <CajaNegocio valor={ind.saldo_caja_negocio.valor} nota="Lo que tienes hoy" acciones />
        <AlertaPrincipal alertas={alertas} corte={resumen.corte} />
        <Disponible forecast={forecast} />
      </div>

      <div className="inicio__side">
        <Section title="Cuentas">
          <List>
            <ListRow
              to="/cuentas"
              title="Te deben"
              sub={`${cobro.n_fiados} ${cobro.n_fiados === 1 ? 'fiado' : 'fiados'}`}
              amount={soles(cobro.valor)}
            />
            <ListRow
              to="/cuentas"
              title="Debes"
              sub={pagos.detalle || `${pagos.n_obligaciones} ${pagos.n_obligaciones === 1 ? 'pago' : 'pagos'}`}
              amount={soles(pagos.valor)}
            />
          </List>
        </Section>

        <Section title="Este mes">
          <List>
            <ListRow
              title="Vendiste"
              sub={comparacion(ind.ingresos_mes.valor, ind.ingresos_mes.variacion_pct, true)}
              amount={soles(ind.ingresos_mes.valor)}
            />
            <ListRow
              title="Gastaste en el negocio"
              sub={comparacion(ind.egresos_mes.valor, ind.egresos_mes.variacion_pct)}
              amount={soles(ind.egresos_mes.valor)}
            />
            <ListRow
              title="Ganancia aproximada"
              amount={ganancia.rango ? solesRange(ganancia.rango) : soles(ganancia.valor)}
            />
          </List>
          {resumen.variacion_vs && <p className="inicio__nota-pie">Comparado con el mes pasado al mismo día.</p>}
        </Section>
      </div>
    </div>
  )
}

/** Diferencia en soles frente al mes pasado, en palabras (sin porcentajes ni flechas). */
function comparacion(valor, variacion, malaSiBaja) {
  const dif = valor != null ? diferenciaSoles(valor, variacion) : null
  if (dif == null || dif === 0) return null
  const baja = dif < 0
  const mala = malaSiBaja && baja
  return (
    <span className={mala ? 'inicio__mala' : undefined}>
      {soles(Math.abs(dif))} {baja ? 'menos' : 'más'} que el mes pasado
    </span>
  )
}

function AlertaPrincipal({ alertas, corte }) {
  const navigate = useNavigate()
  if (alertas.loading && !alertas.data) return <Skeleton height={180} />
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

  return (
    <Card className="inicio__alerta" role="region" aria-label="Alerta de caja">
      <h2 className="inicio__alerta-title">
        <Icon name="warning" size={22} />
        <span>{a.titulo?.replace(/S\/ /g, 'S/ ')}</span>
      </h2>
      {dias != null && <p className="inicio__alerta-when">En {diasTxt(dias)}</p>}
      {porque && <p className="inicio__alerta-why">Por qué: {porque}</p>}
      <Button onClick={() => navigate('/simulador')}>{a.accion?.texto_boton || 'Ver qué puedo hacer'}</Button>
    </Card>
  )
}

/** Cifra protagonista: saldo de la caja del negocio, sin caja de color alrededor. */
function CajaNegocio({ valor, nota, acciones }) {
  return (
    <div className="inicio__hero" role="group" aria-labelledby="inicio-caja-label">
      <p id="inicio-caja-label" className="inicio__hero-label">
        Caja del negocio
      </p>
      <p className="inicio__hero-value display num">{soles(valor)}</p>
      <p className="inicio__hero-note">{nota}</p>
      {acciones && (
        <nav className="inicio__acciones" aria-label="Acciones rápidas">
          {ACCIONES.map((ac) => (
            <Link key={ac.to} to={ac.to} className="inicio__accion">
              <span className="inicio__accion-icon" aria-hidden="true">
                <Icon name={ac.icon} size={22} />
              </span>
              <span className="inicio__accion-label">{ac.label}</span>
            </Link>
          ))}
        </nav>
      )}
    </div>
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
  if (forecast.loading && !forecast.data) return <Skeleton height={140} />
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
    <div className="inicio__disp">
      <Card className="inicio__disp-card" aria-labelledby="inicio-disp-label">
        <div className="inicio__disp-top">
          <p id="inicio-disp-label" className="inicio__disp-label">
            Disponible para gastar
          </p>
          <p className="inicio__disp-value display num">{soles(d.valor)}</p>
        </div>
        {d.mensaje && <p className="inicio__disp-msg">{d.mensaje}</p>}
      </Card>
      <TraceInfo
        fundamento={f.fundamento}
        limites={f.limites}
        confianza={f.confianza}
        meta={f.meta}
        extra={desglose ? [['Cómo se calcula', desglose]] : []}
      />
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
    <div className="inicio__grid">
      <div className="inicio__main">
        {ind && <CajaNegocio valor={ind.saldo_caja_negocio.valor} nota="Según lo que anotaste" />}

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
          <p className="inicio__progreso-txt">
            {diasConDatos} de {diasRequeridos} días · sigue mandando tus ventas por el chat.
          </p>
          <Button size="lg" icon="mic" onClick={() => navigate('/chat')}>
            Anotar una venta
          </Button>
        </Card>
      </div>

      <div className="inicio__side">
        {ind && (
          <Section title="Hasta ahora">
            <List>
              <ListRow title={`Vendiste en ${diasTxt(diasConDatos)}`} amount={soles(ind.ingresos_mes.valor)} />
              <ListRow
                title="Ganancia aproximada"
                sub={ganancia.es_aproximada ? 'Es un rango porque aún no conozco el costo de todos tus productos.' : null}
                amount={
                  ganancia.rango
                    ? `entre ${soles(ganancia.rango[0])} y ${soles(ganancia.rango[1])}`
                    : soles(ganancia.valor)
                }
              />
            </List>
          </Section>
        )}

        <div className="inicio__proximos">
          <Icon name="clock" size={20} />
          <div>
            <h2 className="inicio__proximos-title">Tus próximos 30 días</h2>
            <p className="inicio__proximos-txt">
              Aparecerán aquí en {diasTxt(faltan)}. Mientras, cuéntame tus pagos con fecha (“le debo 800 a Andina para
              el 30”) y te aviso antes de que venzan.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
