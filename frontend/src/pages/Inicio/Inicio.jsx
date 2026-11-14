import { useId } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../api/index.js'
import { useApi } from '../../api/useApi.js'
import { useDemo } from '../../lib/useDemo.js'
import { soles, ddmm, daysBetween } from '../../lib/format.js'
import DemoMenu from '../../components/layout/DemoMenu.jsx'
import {
  Card,
  Button,
  Icon,
  Money,
  List,
  ListRow,
  Section,
  Status,
  ProgressBar,
  TraceInfo,
  Skeleton,
  ErrorState,
} from '../../components/ui/index.jsx'
import UltimosMovimientos from './UltimosMovimientos.jsx'
import './Inicio.css'

// No hay endpoint de empresa en el contrato todavía; el nombre del dueño va fijo para la demo.
const NOMBRE_DUENIO = 'Pedro'
const DIAS_REQUERIDOS_DEFAULT = 30
const MAX_PROXIMOS = 3

/** "2026-11" en hora de Lima */
function periodoActual() {
  const parts = new Intl.DateTimeFormat('en-CA', { year: 'numeric', month: '2-digit', timeZone: 'America/Lima' }).format(new Date())
  return parts.slice(0, 7)
}

const diasTxt = (n) => `${n} ${n === 1 ? 'día' : 'días'}`
const enDias = (n) => (n <= 0 ? 'hoy' : n === 1 ? 'mañana' : `en ${diasTxt(n)}`)

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

  return (
    <div className="inicio">
      <header className="inicio__top">
        <div className="inicio__top-text">
          <h1 className="inicio__hola">Hola, {NOMBRE_DUENIO}</h1>
        </div>
        <DemoMenu />
      </header>
      <div className="inicio__body">
        {resumen.loading && !r ? (
          <InicioCargando />
        ) : resumen.error ? (
          <ErrorState error={resumen.error} onRetry={resumen.reload} />
        ) : esNuevo ? (
          <InicioNuevo resumen={r} diasConDatos={diasConDatos ?? 0} diasRequeridos={diasRequeridos} escenario={demo.escenario} />
        ) : (
          <InicioCompleto resumen={r} forecast={forecast} alertas={alertas} escenario={demo.escenario} />
        )}
      </div>
    </div>
  )
}

function InicioCargando() {
  return (
    <div className="inicio__grid" role="status" aria-live="polite">
      <span className="sr-only">Cargando…</span>
      <div className="inicio__main">
        <Skeleton height={224} style={{ borderRadius: 20 }} />
        <Skeleton height={48} />
        <Skeleton height={232} />
      </div>
      <div className="inicio__side">
        <Skeleton height={320} />
      </div>
    </div>
  )
}

/** Botón principal de la pantalla: anotar por el chat (voz o texto). */
function AnotarVenta({ label = 'Anotar una venta' }) {
  const navigate = useNavigate()
  return (
    <Button size="lg" icon="mic" className="inicio__anotar" onClick={() => navigate('/chat')}>
      {label}
    </Button>
  )
}

/* ---------------- Con historial (Pedro y negocio sano) ---------------- */

function InicioCompleto({ resumen, forecast, alertas, escenario }) {
  return (
    <div className="inicio__grid">
      <div className="inicio__main">
        <CuentaNegocio valor={resumen.indicadores.saldo_caja_negocio.valor}>
          <DisponibleHoy forecast={forecast} />
        </CuentaNegocio>
        <AnotarVenta />
        <LoQueViene forecast={forecast} alertas={alertas} corte={resumen.corte} />
        <DisponibleTrace forecast={forecast} />
      </div>

      <div className="inicio__side">
        <UltimosMovimientos escenario={escenario} />
      </div>
    </div>
  )
}

/* ---------------- Tarjeta de cuenta (única superficie de color) ---------------- */

function CuentaNegocio({ valor, children }) {
  const id = useId()
  return (
    <section className="inicio__cuenta" aria-labelledby={id}>
      <h2 className="inicio__cuenta-label" id={id}>
        Caja del negocio
      </h2>
      <p className="inicio__cuenta-saldo">
        <Money size="hero" inverse value={valor} />
      </p>
      {children}
    </section>
  )
}

/** "Hoy no hagas gastos extra: arriesgas el pago del 30/11." → "Arriesgas el pago del 30/11." */
function razonCorta(mensaje) {
  if (!mensaje) return null
  const i = mensaje.indexOf(':')
  const r = i >= 0 ? mensaje.slice(i + 1).trim() : mensaje.trim()
  return r ? r.charAt(0).toUpperCase() + r.slice(1) : null
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

  if (Math.round(d.valor) <= 0) {
    return (
      <div className="inicio__cuenta-disp">
        <p className="inicio__cuenta-row-label">Hoy no deberías gastar</p>
        {d.mensaje && <p className="inicio__cuenta-msg">{razonCorta(d.mensaje)}</p>}
      </div>
    )
  }
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

/** Desglose corto del número "Puedes gastar hoy": 4 líneas y el resultado. */
function DisponibleTrace({ forecast }) {
  const f = forecast.data
  const d = f?.disponible_para_gastar
  if (!d) return null

  const c = d.componentes ?? {}
  const filas = [
    ['Tienes', c.saldo_actual],
    ['Te pagarán', c.cobros_esperados],
    ['Debes pagar', c.pagos_comprometidos != null ? -c.pagos_comprometidos : null],
    [
      'Reserva',
      c.minimo_operativo != null || c.reserva_impuestos != null
        ? -((c.minimo_operativo ?? 0) + (c.reserva_impuestos ?? 0))
        : null,
    ],
  ].filter(([, v]) => v != null)
  if (filas.length === 0) return null

  const bruto = filas.reduce((s, [, v]) => s + v, 0)
  const desglose = (
    <ul className="inicio__desglose">
      {filas.map(([label, v]) => (
        <li key={label}>
          <span>{label}</span>
          <span className="num">{soles(v)}</span>
        </li>
      ))}
      <li className="inicio__desglose-total">
        <span>Puedes gastar</span>
        <span className="num">{soles(Math.max(0, d.valor))}</span>
      </li>
      {bruto < 0 && <li className="inicio__desglose-nota">No alcanza, por eso hoy es {soles(0)}.</li>}
    </ul>
  )

  return (
    <TraceInfo
      label="¿De dónde sale lo que puedes gastar hoy?"
      confianza={f.confianza}
      meta={f.meta}
      extra={[['Así se calcula', desglose]]}
    />
  )
}

/* ---------------- Lo que viene ---------------- */

const ICONO_EVENTO = {
  pago_proveedor: 'store',
  pago_impuesto: 'receipt',
  gasto_negocio: 'receipt',
  cobro_fiado: 'arrowDown',
}

/** Próximos pagos y cobros (forecast) con la alerta principal pegada a su fila. */
function armarProximos(eventos, alerta, corte) {
  const filas = eventos.map((e) => ({
    key: `${e.fecha}-${e.concepto}`,
    fecha: e.fecha,
    titulo: e.concepto,
    monto: e.monto,
    icono: ICONO_EVENTO[e.tipo] ?? (e.monto >= 0 ? 'arrowDown' : 'receipt'),
    alerta: alerta && e.monto < 0 && e.fecha === alerta.fecha_evento ? alerta : null,
  }))
  // Si la alerta no coincide con ningún evento, igual la mostramos como fila propia.
  if (alerta && !filas.some((f) => f.alerta)) {
    filas.push({
      key: alerta.alerta_id ?? 'alerta',
      fecha: alerta.fecha_evento,
      titulo: alerta.titulo_corto || alerta.titulo,
      monto: null,
      icono: 'warning',
      alerta,
    })
  }
  const futuras = filas
    .filter((f) => !f.fecha || !corte || daysBetween(corte, f.fecha) >= 0)
    .sort((a, b) => (a.fecha ?? '').localeCompare(b.fecha ?? ''))
  // Hasta 3 filas, sin dejar fuera la de la alerta ni el pago más grande.
  const visibles = futuras.slice(0, MAX_PROXIMOS)
  const mayorPago = futuras.reduce((m, f) => (f.monto != null && f.monto < 0 && (!m || f.monto < m.monto) ? f : m), null)
  const clave = futuras.find((f) => f.alerta) ?? mayorPago
  if (clave && !visibles.includes(clave)) visibles[visibles.length - 1] = clave
  return visibles.sort((a, b) => (a.fecha ?? '').localeCompare(b.fecha ?? ''))
}

function LoQueViene({ forecast, alertas, corte }) {
  if ((forecast.loading && !forecast.data) || (alertas.loading && !alertas.data)) return <Skeleton height={232} />
  if (forecast.error && alertas.error) return <ErrorState error={alertas.error} onRetry={alertas.reload} />

  const items = [...(alertas.data?.items ?? [])].sort((a, b) => (a.prioridad ?? 99) - (b.prioridad ?? 99))
  const alerta = items[0] ?? null
  const hoy = corte ?? forecast.data?.fecha_corte
  const filas = armarProximos(forecast.data?.proximos_eventos ?? [], alerta, hoy)

  return (
    <Section title="Próximos movimientos">
      <Card flush>
        {filas.length === 0 ? (
          <p className="inicio__viene-vacio">No tienes pagos ni cobros en los próximos 30 días.</p>
        ) : (
          <List>
            {filas.map((f) => {
              const dias = hoy && f.fecha ? daysBetween(hoy, f.fecha) : null
              const fecha = f.fecha ? `${ddmm(f.fecha)}${dias != null ? ` · ${enDias(dias)}` : ''}` : null
              return (
                <ListRow
                  key={f.key}
                  lead={<Icon name={f.icono} size={20} />}
                  title={f.titulo}
                  sub={fecha}
                  amount={f.monto != null ? <Money value={f.monto} sign tone={f.monto > 0 ? 'pos' : 'neutral'} /> : null}
                >
                  {f.alerta && <Cobertura pago={f.monto} falta={f.alerta.monto} />}
                </ListRow>
              )
            })}
          </List>
        )}
      </Card>
    </Section>
  )
}

/**
 * Solo para el pago en riesgo: barra de cobertura. La parte azul es lo que tendrás,
 * la roja lo que falta. Si el pago sí se cubre, la fila no lleva nada extra.
 */
function Cobertura({ pago, falta }) {
  const total = Math.abs(pago ?? 0)
  const faltante = Math.abs(falta ?? 0)
  if (!faltante) return null
  const cubierto = Math.max(0, total - faltante)
  const pctCubierto = total ? Math.round((cubierto / total) * 100) : 0
  return (
    <div className="inicio__cobertura">
      <div
        className="inicio__cobertura-bar"
        role="img"
        aria-label={`Cubres ${soles(cubierto)} de ${soles(total)}. Faltan ${soles(faltante)}.`}
      >
        <span className="inicio__cobertura-ok" style={{ width: `${pctCubierto}%` }} />
        <span className="inicio__cobertura-falta" />
      </div>
      <p className="inicio__cobertura-texto" aria-hidden="true">
        <span>
          Cubres <span className="num">{soles(cubierto)}</span>
        </span>
        <strong>
          Faltan <span className="num">{soles(faltante)}</span>
        </strong>
      </p>
    </div>
  )
}

/* ---------------- Día 3: recién empieza ---------------- */

function InicioNuevo({ resumen, diasConDatos, diasRequeridos, escenario }) {
  const idProgreso = useId()
  const ind = resumen?.indicadores
  const hechos = Math.min(diasConDatos, diasRequeridos)

  return (
    <div className="inicio__grid">
      <div className="inicio__main">
        {ind && <CuentaNegocio valor={ind.saldo_caja_negocio.valor} />}

        <Card className="inicio__progreso" aria-labelledby={idProgreso}>
          <h2 className="inicio__progreso-title" id={idProgreso}>
            Tus primeros días
          </h2>
          <p className="inicio__progreso-frase">
            Anota lo que vendes y lo que gastas durante {diasRequeridos} días. Con eso podré avisarte antes de que te falte plata.
          </p>
          <div className="inicio__progreso-barra">
            <ProgressBar value={hechos} max={diasRequeridos} label="Días con transacciones anotadas" />
            <p className="inicio__progreso-txt">
              {hechos} de {diasTxt(diasRequeridos)}
            </p>
          </div>
          <AnotarVenta label="Anotar una transacción" />
        </Card>
      </div>

      <div className="inicio__side">
        <UltimosMovimientos escenario={escenario} />
      </div>
    </div>
  )
}
