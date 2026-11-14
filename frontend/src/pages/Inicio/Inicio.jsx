import { useId } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../api/index.js'
import { useApi } from '../../api/useApi.js'
import { useDemo } from '../../lib/useDemo.js'
import { soles, weekdayDdmm, daysBetween, diferenciaSoles } from '../../lib/format.js'
import DemoMenu from '../../components/layout/DemoMenu.jsx'
import {
  Card,
  Button,
  Icon,
  Money,
  List,
  ListRow,
  ProgressBar,
  TraceInfo,
  Skeleton,
  ErrorState,
  Footnote,
} from '../../components/ui/index.jsx'
import './Inicio.css'

// No hay endpoint de empresa en el contrato todavía; nombre del dueño y del negocio van fijos para la demo.
const NOMBRE_DUENIO = 'Pedro'
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
  const sub = `${NOMBRE_NEGOCIO}${corte ? ` · ${weekdayDdmm(corte).toLowerCase()}` : ''}`

  return (
    <div className="inicio">
      <header className="inicio__top">
        <div className="inicio__top-text">
          <h1 className="inicio__hola">Hola, {NOMBRE_DUENIO}</h1>
          <p className="inicio__top-sub">{sub}</p>
        </div>
        <DemoMenu />
      </header>
      <div className="inicio__body">
        {resumen.loading && !r ? (
          <InicioCargando />
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

function InicioCargando() {
  return (
    <div className="inicio__grid" role="status" aria-live="polite">
      <span className="sr-only">Cargando…</span>
      <div className="inicio__main">
        <Skeleton height={224} style={{ borderRadius: 20 }} />
        <Skeleton height={176} />
        <Skeleton height={56} />
      </div>
      <div className="inicio__side">
        <Skeleton height={200} />
        <Skeleton height={268} />
      </div>
    </div>
  )
}

/* ---------------- Pedro con historial ---------------- */

function InicioPedro({ resumen, forecast, alertas }) {
  const ind = resumen.indicadores
  const cobro = ind.pendiente_cobro
  const pagos = ind.pagos_pendientes
  const ganancia = ind.ganancia_neta

  return (
    <div className="inicio__grid">
      <div className="inicio__main">
        <CuentaNegocio valor={ind.saldo_caja_negocio.valor}>
          <DisponibleHoy forecast={forecast} />
        </CuentaNegocio>
        <LoQueViene alertas={alertas} corte={resumen.corte} />
        <DisponibleTrace forecast={forecast} />
      </div>

      <div className="inicio__side">
        <CardLista title="Cuentas" action={<VerTodo to="/cuentas" />}>
          <ListRow
            lead={<Icon name="arrowDown" size={20} />}
            title="Te deben"
            sub={`${cobro.n_fiados} ${cobro.n_fiados === 1 ? 'fiado' : 'fiados'}`}
            amount={<Money value={cobro.valor} sign tone="pos" />}
          />
          <ListRow
            lead={<Icon name="receipt" size={20} />}
            title="Debes"
            sub={pagos.detalle || `${pagos.n_obligaciones} ${pagos.n_obligaciones === 1 ? 'pago' : 'pagos'}`}
            amount={<Money value={pagos.valor} />}
          />
        </CardLista>

        <CardLista
          title="Este mes"
          nota={resumen.variacion_vs ? 'Comparado con el mes pasado al mismo día.' : null}
        >
          <ListRow
            title="Vendiste"
            sub={comparacion(ind.ingresos_mes.valor, ind.ingresos_mes.variacion_pct, true)}
            amount={<Money value={ind.ingresos_mes.valor} />}
          />
          <ListRow
            title="Gastaste en el negocio"
            sub={comparacion(ind.egresos_mes.valor, ind.egresos_mes.variacion_pct)}
            amount={<Money value={ind.egresos_mes.valor} />}
          />
          <ListRow
            title="Ganancia aproximada"
            sub={ganancia.rango ? `Entre ${soles(ganancia.rango[0])} y ${soles(ganancia.rango[1])}` : null}
            amount={<Money value={ganancia.valor} />}
          />
        </CardLista>
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

/** Tarjeta blanca con título dentro (patrón "Activity" de Monzo) y una lista de filas. */
function CardLista({ title, action, nota, children }) {
  const id = useId()
  return (
    <Card flush aria-labelledby={id}>
      <div className="cc-card__head">
        <h2 className="cc-card__title" id={id}>
          {title}
        </h2>
        {action}
      </div>
      <List>{children}</List>
      {nota && <p className="inicio__nota-pie">{nota}</p>}
    </Card>
  )
}

function VerTodo({ to }) {
  return (
    <Link className="cc-section__action" to={to}>
      Ver todo <span aria-hidden="true">→</span>
    </Link>
  )
}

/* ---------------- Tarjeta de cuenta (única superficie de color) ---------------- */

function CuentaNegocio({ valor, nota, children }) {
  const id = useId()
  return (
    <section className="inicio__cuenta" aria-labelledby={id}>
      <h2 className="inicio__cuenta-label" id={id}>
        Caja del negocio
      </h2>
      <p className="inicio__cuenta-saldo">
        <Money size="hero" inverse value={valor} />
      </p>
      {nota && <p className="inicio__cuenta-msg">{nota}</p>}
      {children}
    </section>
  )
}

/** "Puedes gastar hoy" dentro de la tarjeta de cuenta (como "Left to spend" de Monzo). */
function DisponibleHoy({ forecast }) {
  if (forecast.loading && !forecast.data) {
    return (
      <div className="inicio__cuenta-disp" aria-hidden="true">
        <span className="inicio__cuenta-skel" />
      </div>
    )
  }
  const d = forecast.data?.disponible_para_gastar
  if (forecast.error || !d) return null
  return (
    <div className="inicio__cuenta-disp">
      <div className="inicio__cuenta-row">
        <p className="inicio__cuenta-row-label">Puedes gastar hoy</p>
        <Money size="md" inverse value={d.valor} />
      </div>
      {d.mensaje && <p className="inicio__cuenta-msg">{d.mensaje}</p>}
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

/** Explicabilidad del número "Puedes gastar hoy", con el desglose del cálculo. */
function DisponibleTrace({ forecast }) {
  if (forecast.loading && !forecast.data) return <Skeleton height={56} />
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
    <TraceInfo
      label="¿De dónde sale lo que puedes gastar hoy?"
      fundamento={f.fundamento}
      limites={f.limites}
      confianza={f.confianza}
      meta={f.meta}
      extra={desglose ? [['Cómo se calcula', desglose]] : []}
    />
  )
}

/* ---------------- Lo que viene (alerta principal) ---------------- */

// Fechas "30/11" y montos "S/ 650" dentro del texto de la alerta, para resaltarlos.
// (\s en JS también cubre los espacios no separables que usa format.js)
const RE_CIFRAS = /(\d{1,2}\/\d{1,2}|S\/\s?\d[\d\s.,]*\d|S\/\s?\d)/g

/** Resalta fecha y monto dentro de la frase del motor (no se reescribe el texto). */
function frase(texto) {
  return texto.split(RE_CIFRAS).map((parte, i) => {
    if (i % 2 === 0) return parte
    const esMonto = parte.startsWith('S/')
    return (
      <strong key={i} className={esMonto ? 'inicio__alerta-monto' : undefined}>
        {esMonto ? parte.replace(/^S\/\s?/, 'S/ ') : parte}
      </strong>
    )
  })
}

function LoQueViene({ alertas, corte }) {
  const navigate = useNavigate()
  const id = useId()
  if (alertas.loading && !alertas.data) return <Skeleton height={176} />
  if (alertas.error) return <ErrorState error={alertas.error} onRetry={alertas.reload} />

  const items = [...(alertas.data?.items ?? [])].sort((a, b) => (a.prioridad ?? 99) - (b.prioridad ?? 99))
  const a = items[0]

  if (!a) {
    return (
      <Card className="inicio__alerta" aria-labelledby={id}>
        <div className="inicio__alerta-head">
          <Icon name="check" size={20} className="inicio__alerta-icon--ok" />
          <h2 className="inicio__alerta-title" id={id}>
            Lo que viene
          </h2>
        </div>
        <p className="inicio__alerta-insight">Por ahora no veo problemas de caja en tus próximos 30 días.</p>
      </Card>
    )
  }

  const dias = a.dias_para_evento ?? (corte && a.fecha_evento ? daysBetween(corte, a.fecha_evento) : null)
  const porque = a.resumen_causas || a.causas?.map((c) => c.descripcion.toLowerCase()).join(', ')

  return (
    <Card className="inicio__alerta" aria-labelledby={id}>
      <div className="inicio__alerta-head">
        <Icon name="warning" size={20} className="inicio__alerta-icon--danger" />
        <h2 className="inicio__alerta-title" id={id}>
          Lo que viene
        </h2>
      </div>
      {a.titulo && <p className="inicio__alerta-insight">{frase(a.titulo)}</p>}
      {(dias != null || porque) && (
        <div className="inicio__alerta-detalle">
          {dias != null && <p>En {diasTxt(dias)}</p>}
          {porque && <p>Por qué: {porque}</p>}
        </div>
      )}
      <Button variant="ghost" className="inicio__alerta-accion" onClick={() => navigate('/simulador')}>
        {a.accion?.texto_boton || 'Ver qué puedo hacer'} <span aria-hidden="true">→</span>
      </Button>
    </Card>
  )
}

/* ---------------- Día 3: recién empieza ---------------- */

function InicioNuevo({ resumen, diasConDatos, diasRequeridos }) {
  const navigate = useNavigate()
  const idProgreso = useId()
  const ind = resumen?.indicadores
  const faltan = Math.max(diasRequeridos - diasConDatos, 0)
  const ganancia = ind?.ganancia_neta
  const hechos = Math.min(diasConDatos, diasRequeridos)

  return (
    <div className="inicio__grid">
      <div className="inicio__main">
        {ind && <CuentaNegocio valor={ind.saldo_caja_negocio.valor} nota="Según lo que anotaste" />}

        <Card className="inicio__progreso" aria-labelledby={idProgreso}>
          <h2 className="inicio__progreso-title" id={idProgreso}>
            Tus primeros días
          </h2>
          <p className="inicio__progreso-frase">
            Necesito {diasRequeridos} días de ventas para avisarte antes de que te falte plata
          </p>
          <div className="inicio__progreso-barra">
            <ProgressBar value={hechos} max={diasRequeridos} label="Días con ventas anotadas" />
            <p className="inicio__progreso-txt">
              {hechos} de {diasTxt(diasRequeridos)}
            </p>
          </div>
          <Button size="lg" icon="mic" onClick={() => navigate('/chat')}>
            Anotar una venta
          </Button>
        </Card>
      </div>

      <div className="inicio__side">
        {ind && (
          <CardLista title="Hasta ahora">
            <ListRow title={`Vendiste en ${diasTxt(diasConDatos)}`} amount={<Money value={ind.ingresos_mes.valor} />} />
            <ListRow
              title="Ganancia aproximada"
              sub={
                ganancia.rango
                  ? `Entre ${soles(ganancia.rango[0])} y ${soles(ganancia.rango[1])}${
                      ganancia.es_aproximada ? ': aún no conozco el costo de todos tus productos.' : ''
                    }`
                  : null
              }
              amount={<Money value={ganancia.valor} />}
            />
          </CardLista>
        )}

        <div className="inicio__proximos">
          <Icon name="clock" size={20} />
          <p>
            Tus próximos 30 días aparecerán aquí en {diasTxt(faltan)}. Mientras, cuéntame tus pagos con fecha (“le debo
            800 a Andina para el 30”) y te aviso antes de que venzan.
          </p>
        </div>
      </div>
    </div>
  )
}
