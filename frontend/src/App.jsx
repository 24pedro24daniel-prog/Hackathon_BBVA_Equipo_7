import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Landing from './pages/Landing/Landing.jsx'
import Ingresar from './pages/Ingresar/Ingresar.jsx'
import RequireAuth from './components/auth/RequireAuth.jsx'

// La app se carga aparte: quien solo abre la landing o el login no descarga las pantallas.
const AppLayout = lazy(() => import('./components/layout/AppLayout.jsx'))
const Inicio = lazy(() => import('./pages/Inicio/Inicio.jsx'))
const Forecast = lazy(() => import('./pages/Forecast/Forecast.jsx'))
const Simulador = lazy(() => import('./pages/Simulador/Simulador.jsx'))
const Cuentas = lazy(() => import('./pages/Cuentas/Cuentas.jsx'))
const Progreso = lazy(() => import('./pages/Progreso/Progreso.jsx'))
const Chat = lazy(() => import('./pages/Chat/Chat.jsx'))
const Movimientos = lazy(() => import('./pages/Movimientos/Movimientos.jsx'))

function Cargando() {
  return (
    <div className="cc-cargando" role="status" aria-live="polite">
      <span className="sr-only">Cargando…</span>
    </div>
  )
}

/**
 *  /           landing pública
 *  /ingresar   login de las demos (con sesión → /app)
 *  /app/*      la app; sin sesión → /ingresar
 */
export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<Cargando />}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/ingresar" element={<Ingresar />} />
          <Route
            path="/app"
            element={
              <RequireAuth>
                <AppLayout />
              </RequireAuth>
            }
          >
            <Route index element={<Inicio />} />
            <Route path="30-dias" element={<Forecast />} />
            <Route path="simulador" element={<Simulador />} />
            <Route path="cuentas" element={<Cuentas />} />
            <Route path="progreso" element={<Progreso />} />
            <Route path="chat" element={<Chat />} />
            {/* Ruta oculta: no está en la navegación; se llega desde Inicio → Últimos movimientos */}
            <Route path="movimientos" element={<Movimientos />} />
            <Route path="*" element={<Navigate to="/app" replace />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
