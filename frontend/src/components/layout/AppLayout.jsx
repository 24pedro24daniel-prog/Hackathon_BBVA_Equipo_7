import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { Icon } from '../ui/index.jsx'
import './AppLayout.css'

const tabs = [
  { to: '/', label: 'Inicio', icon: 'home', end: true },
  { to: '/30-dias', label: '30 días', icon: 'chart' },
  { to: '/cuentas', label: 'Cuentas', icon: 'list' },
  { to: '/progreso', label: 'Progreso', icon: 'arrowUp' },
  { to: '/chat', label: 'Chat', icon: 'chat' },
]

export default function AppLayout() {
  const { pathname } = useLocation()
  const isChat = pathname.startsWith('/chat')
  return (
    <div className="cc-app">
      <main className={isChat ? 'cc-main cc-main--chat' : 'cc-main'}>
        <Outlet />
      </main>
      {!isChat && (
        <nav className="cc-nav" aria-label="Secciones">
          {tabs.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              end={t.end}
              className={({ isActive }) =>
                'cc-nav__link' + (isActive || (t.to === '/' && pathname === '/simulador') ? ' active' : '')
              }
            >
              <Icon name={t.icon} size={22} />
              {t.label}
            </NavLink>
          ))}
        </nav>
      )}
    </div>
  )
}
