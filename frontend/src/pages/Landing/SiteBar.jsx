import { Link } from 'react-router-dom'
import { LogoMark } from '../../components/layout/Logo.jsx'

/** Barra superior oscura de la landing y del login: marca a la izquierda, una acción a la derecha. */
export default function SiteBar({ accion }) {
  return (
    <header className="lp-bar">
      <div className="lp-bar__in">
        <Link to="/" className="lp-bar__marca" aria-label="TuCaserito, ir al inicio">
          <LogoMark size={36} className="lp-bar__logo" />
          <span className="lp-bar__nombre" aria-hidden="true">
            TuCaserito
          </span>
        </Link>
        {accion}
      </div>
    </header>
  )
}
