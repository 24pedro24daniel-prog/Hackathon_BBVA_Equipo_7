import { useId, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Icon from './Icon.jsx'
import { confianzaLabel } from '../../lib/format.js'
import { useDemo } from '../../lib/useDemo.js'
import './ui.css'

export { Icon }

const cx = (...c) => c.filter(Boolean).join(' ')

/** variant: default | danger | dashed */
export function Card({ variant, flush, className, as = 'section', children, ...rest }) {
  const Tag = as
  return (
    <Tag className={cx('cc-card', variant && `cc-card--${variant}`, flush && 'cc-card--flush', className)} {...rest}>
      {children}
    </Tag>
  )
}

/** variant: primary | secondary | ghost; size: sm | md | lg */
export function Button({ variant = 'primary', size, block, className, icon, children, ...rest }) {
  return (
    <button
      type="button"
      className={cx('cc-btn', `cc-btn--${variant}`, size && `cc-btn--${size}`, block && 'cc-btn--block', className)}
      {...rest}
    >
      {icon && <Icon name={icon} size={20} />}
      {children}
    </button>
  )
}

/**
 * Estado como texto de color (sin fondo, sin píldora), como en las apps bancarias:
 * "Vencido hace 18 días" en naranja, "Al día" en aqua.  tone: danger | warning | ok | neutral
 */
export function Status({ tone = 'neutral', children, className }) {
  return <span className={cx('cc-status', `cc-status--${tone}`, className)}>{children}</span>
}
/** @deprecated usa <Status>. Se mantiene para no romper importaciones. */
export const Badge = Status

/**
 * Encabezado de página: título grande y, debajo, una línea de contexto (sub).
 * `kicker` se acepta por compatibilidad y se pinta debajo del título, nunca encima.
 */
export function PageHeader({ sub, kicker, title, back, right }) {
  const navigate = useNavigate()
  const subtitle = sub ?? kicker
  return (
    <header className="cc-header">
      {back && (
        <button className="cc-header__back" onClick={() => navigate(-1)} aria-label="Volver">
          <Icon name="back" size={24} />
        </button>
      )}
      <div className="cc-header__text">
        <h1 className="cc-header__title">{title}</h1>
        {subtitle && <p className="cc-header__sub">{subtitle}</p>}
      </div>
      {right}
    </header>
  )
}

/**
 * Sección con título en frase fuera del contenedor (no etiquetas en mayúsculas).
 * <Section title="Este mes" action={<Link className="cc-section__action" to="/x">Ver todo</Link>}>…</Section>
 */
export function Section({ title, action, id, headingRef, className, children, ...rest }) {
  const hid = useId()
  return (
    <section className={cx('cc-section', className)} aria-labelledby={id ?? hid} {...rest}>
      {(title || action) && (
        <div className="cc-section__head">
          {title && (
            <h2 className="cc-section__title" id={id ?? hid} ref={headingRef} tabIndex={headingRef ? -1 : undefined}>
              {title}
            </h2>
          )}
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

/** Lista agrupada: un contenedor, filas separadas por divisores finos. Hijos: <ListRow>. */
export function List({ className, children, ...rest }) {
  return (
    <ul className={cx('cc-list', className)} {...rest}>
      {children}
    </ul>
  )
}

/**
 * Fila de lista estilo movimientos bancarios.
 *  lead: ícono o iniciales a la izquierda (opcional)
 *  title / sub: texto principal y secundario
 *  amount: monto a la derecha (ya formateado); amountTone: pos | neg
 *  end: contenido bajo el monto (p. ej. <Status>) o en lugar del monto
 *  to / onClick: vuelve la fila navegable y muestra chevron
 *  children: contenido extra bajo la fila (p. ej. un botón)
 */
export function ListRow({ lead, title, sub, amount, amountTone, end, to, onClick, chevron, className, children, ...rest }) {
  const inner = (
    <>
      {lead != null && <span className="cc-row__lead" aria-hidden="true">{lead}</span>}
      <span className="cc-row__main">
        <span className="cc-row__title">{title}</span>
        {sub && <span className="cc-row__sub">{sub}</span>}
      </span>
      {(amount != null || end) && (
        <span className="cc-row__end">
          {amount != null && (
            <span className={cx('cc-row__amount', amountTone && `cc-row__amount--${amountTone}`)}>{amount}</span>
          )}
          {end}
        </span>
      )}
      {(to || onClick) && chevron !== false && <Icon name="chevronRight" size={20} className="cc-row__chev" />}
    </>
  )
  let row
  if (to) {
    row = (
      <Link to={to} className={cx('cc-row', className)} {...rest}>
        {inner}
      </Link>
    )
  } else if (onClick) {
    row = (
      <button type="button" onClick={onClick} className={cx('cc-row', className)} {...rest}>
        {inner}
      </button>
    )
  } else {
    row = (
      <div className={cx('cc-row', className)} {...rest}>
        {inner}
      </div>
    )
  }
  return (
    <li>
      {row}
      {children}
    </li>
  )
}

/**
 * Explicabilidad (Responsible AI): muestra fundamento, límites, confianza y trazabilidad del modelo.
 * <TraceInfo fundamento="…" limites="…" confianza="media" meta={data.meta} extra={[['Fórmula', '…']]} />
 */
export function TraceInfo({ label = '¿De dónde sale este número?', fundamento, limites, confianza, meta, extra = [], defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  const id = useId()
  return (
    <Card className="cc-trace">
      <button className="cc-trace__toggle" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}>
        <Icon name="info" size={20} />
        {label}
        <Icon name="chevronDown" size={20} className="cc-trace__chev" />
      </button>
      {open && (
        <dl className="cc-trace__body" id={id}>
          {fundamento && (
            <div>
              <dt>De dónde sale</dt>
              <dd>{fundamento}</dd>
            </div>
          )}
          {extra.map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
          {limites && (
            <div>
              <dt>Lo que no sabe</dt>
              <dd>{limites}</dd>
            </div>
          )}
          {confianza !== undefined && confianza !== null && (
            <div>
              <dt>Qué tan seguro es</dt>
              <dd>{confianzaLabel(confianza)}</dd>
            </div>
          )}
          {meta && <MetaLine meta={meta} />}
        </dl>
      )}
    </Card>
  )
}

/**
 * Línea de trazabilidad del bloque `meta` (modelo, versión, respaldo).
 * Oculta por defecto: no le sirve a Pedro. Se activa en el menú Demo → "Ver detalles técnicos".
 */
export function MetaLine({ meta }) {
  const [demo] = useDemo()
  if (!meta || !demo.tecnico) return null
  return (
    <p className="cc-trace__meta">
      Modelo {meta.modelo} v{meta.modelo_version}
      {meta.prompt_version ? ` · prompt ${meta.prompt_version}` : ''}
      {meta.fallback_usado ? ' · modo básico (respaldo)' : ''}
    </p>
  )
}

export function Skeleton({ height = 96, style }) {
  return <div className="cc-skel" style={{ height, ...style }} aria-hidden="true" />
}

/** Bloque de carga accesible: n skeletons */
export function LoadingBlock({ heights = [140, 96, 96] }) {
  return (
    <div role="status" aria-live="polite" style={{ display: 'grid', gap: 12 }}>
      <span className="sr-only">Cargando…</span>
      {heights.map((h, i) => (
        <Skeleton key={i} height={h} />
      ))}
    </div>
  )
}

export function ErrorState({ error, onRetry }) {
  return (
    <Card className="cc-error" role="alert">
      <p style={{ fontWeight: 600, color: 'var(--title)' }}>No pude traer tus números</p>
      <p className="cc-muted cc-small">{error?.mensaje || error?.message || 'Intenta otra vez en un momento.'}</p>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          Intentar otra vez
        </Button>
      )}
    </Card>
  )
}

export function Footnote({ children = 'Datos ficticios de demostración · Orientación educativa' }) {
  return <p className="cc-footnote">{children}</p>
}
