import { useId, useState } from 'react'
import { useNavigate } from 'react-router-dom'
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

/** tone: danger | warning | ok | neutral */
export function Badge({ tone = 'neutral', children, className }) {
  return <span className={cx('cc-badge', `cc-badge--${tone}`, className)}>{children}</span>
}

/** Encabezado de página: kicker pequeño + título grande. back=true muestra botón volver. */
export function PageHeader({ kicker, title, back, right }) {
  const navigate = useNavigate()
  return (
    <header className="cc-header">
      {back && (
        <button className="cc-header__back" onClick={() => navigate(-1)} aria-label="Volver">
          <Icon name="back" size={22} />
        </button>
      )}
      <div className="cc-header__text">
        {kicker && <p className="cc-header__kicker">{kicker}</p>}
        <h1 className="cc-header__title">{title}</h1>
      </div>
      {right}
    </header>
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
      <p style={{ fontWeight: 700 }}>No pude traer tus números</p>
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
