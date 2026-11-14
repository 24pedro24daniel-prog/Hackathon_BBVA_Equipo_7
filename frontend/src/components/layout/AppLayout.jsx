import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { Icon } from '../ui/index.jsx'
import './AppLayout.css'

const tabs = [
  { to: '/', label: 'Inicio', icon: 'home', end: true },
  { to: '/30-dias', label: 'Pronóstico', icon: 'chart' },
  { to: '/cuentas', label: 'Cuentas', icon: 'list' },
  { to: '/progreso', label: 'Progreso', icon: 'arrowUp' },
  { to: '/chat', label: 'Chat', icon: 'chat' },
]

/**
 * Responsive:
 *  < 768px   teléfono: barra inferior (oculta en el chat, que ocupa toda la pantalla)
 *  768–1099  tablet: riel lateral con íconos y etiquetas
 *  ≥ 1100    escritorio: barra lateral con marca + contenido ancho (dashboard)
 */
export default function AppLayout() {
  const { pathname } = useLocation()
  const isChat = pathname.startsWith('/chat')
  return (
    <div className={isChat ? 'cc-app cc-app--chat' : 'cc-app'}>
      <nav className="cc-nav" aria-label="Secciones">
        <div className="cc-nav__brand" aria-hidden="true">
          <span className="cc-nav__logo">cc</span>
          <span className="cc-nav__name">CajaClara</span>
        </div>
        {tabs.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.end}
            className={({ isActive }) =>
              'cc-nav__link' + (isActive || (t.to === '/' && ['/simulador', '/movimientos'].includes(pathname)) ? ' active' : '')
            }
          >
            <Icon name={t.icon} size={22} />
            <span>{t.label}</span>
          </NavLink>
        ))}
      </nav>
      <main className={isChat ? 'cc-main cc-main--chat' : 'cc-main'}>
        <Outlet />
      </main>
    </div>
  )
}
