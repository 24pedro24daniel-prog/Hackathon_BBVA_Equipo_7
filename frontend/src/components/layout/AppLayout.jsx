import { Suspense } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { Icon } from '../ui/index.jsx'
import { LogoMark } from './Logo.jsx'
import { clearSesion } from '../../lib/sesion.js'
import { useSesion } from '../../lib/useSesion.js'
import './AppLayout.css'

const tabs = [
  { to: '/app', label: 'Inicio', icon: 'home', end: true },
  { to: '/app/30-dias', label: 'Pronóstico', icon: 'chart' },
  { to: '/app/cuentas', label: 'Cuentas', icon: 'list' },
  { to: '/app/progreso', label: 'Progreso', icon: 'arrowUp' },
  { to: '/app/chat', label: 'Chat', icon: 'chat' },
]
// Sub-pantallas sin pestaña propia: se marcan como parte de Inicio.
const DE_INICIO = ['/app/simulador', '/app/movimientos']

/**
 * Responsive:
 *  < 768px   teléfono: barra inferior (oculta en el chat, que ocupa toda la pantalla). "Cerrar sesión" está en el menú Demo de Inicio.
 *  768–1099  tablet: riel lateral con íconos y etiquetas; abajo, el botón de salir
 *  ≥ 1100    escritorio: barra lateral con marca + contenido ancho (dashboard); abajo, el negocio y "Cerrar sesión"
 */
export default function AppLayout() {
  const { pathname } = useLocation()
  const sesion = useSesion()
  const isChat = pathname.startsWith('/app/chat')
  const negocio = sesion?.negocio?.nombre
  return (
    <div className={isChat ? 'cc-app cc-app--chat' : 'cc-app'}>
      <nav className="cc-nav" aria-label="Secciones">
        <div className="cc-nav__brand" aria-hidden="true">
          <LogoMark className="cc-nav__logo" size={36} />
          <span className="cc-nav__name">TuCaserito</span>
        </div>
        {tabs.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.end}
            className={({ isActive }) =>
              'cc-nav__link' + (isActive || (t.to === '/app' && DE_INICIO.includes(pathname)) ? ' active' : '')
            }
          >
            <Icon name={t.icon} size={22} />
            <span>{t.label}</span>
          </NavLink>
        ))}
        <div className="cc-nav__cuenta">
          {negocio && <p className="cc-nav__negocio">{negocio}</p>}
          <button type="button" className="cc-nav__salir" onClick={() => clearSesion('salir')}>
            <Icon name="logout" size={22} />
            <span className="cc-nav__salir-largo">Cerrar sesión</span>
            <span className="cc-nav__salir-corto">Salir</span>
          </button>
        </div>
      </nav>
      <main className={isChat ? 'cc-main cc-main--chat' : 'cc-main'}>
        <Suspense
          fallback={
            <div className="cc-cargando" role="status" aria-live="polite">
              <span className="sr-only">Cargando…</span>
            </div>
          }
        >
          <Outlet />
        </Suspense>
      </main>
    </div>
  )
}
