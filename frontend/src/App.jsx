import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout.jsx'
import Inicio from './pages/Inicio/Inicio.jsx'
import Forecast from './pages/Forecast/Forecast.jsx'
import Simulador from './pages/Simulador/Simulador.jsx'
import Cuentas from './pages/Cuentas/Cuentas.jsx'
import Progreso from './pages/Progreso/Progreso.jsx'
import Chat from './pages/Chat/Chat.jsx'
import Movimientos from './pages/Movimientos/Movimientos.jsx'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Inicio />} />
          <Route path="30-dias" element={<Forecast />} />
          <Route path="simulador" element={<Simulador />} />
          <Route path="cuentas" element={<Cuentas />} />
          <Route path="progreso" element={<Progreso />} />
          <Route path="chat" element={<Chat />} />
          {/* Ruta oculta: no está en la navegación; se llega desde Inicio → Últimos movimientos */}
          <Route path="movimientos" element={<Movimientos />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
