import { useEffect, useId, useRef, useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { api, despertarServidor, USE_MOCK } from '../../api/index.js'
import { Icon } from '../../components/ui/index.jsx'
import { setSesion } from '../../lib/sesion.js'
import { useSesion } from '../../lib/useSesion.js'
import { useTitulo } from '../../lib/useTitulo.js'
import SiteBar from '../Landing/SiteBar.jsx'
import DotFan from '../Landing/DotFan.jsx'
import '../Landing/marca.css'
import './Ingresar.css'

// Render (plan free) duerme el backend: si el login tarda más que esto, se avisa que el servidor está despertando.
const AVISO_DESPERTAR_MS = 4000
// El arranque en frío tarda ~30–50 s; pasado este tiempo se corta la espera.
const TIEMPO_MAXIMO_MS = 90000
const MAX_LARGO = 64

const MOTIVOS = {
  expirada: 'Tu sesión venció. Ingresa otra vez para seguir.',
  salir: 'Cerraste la sesión. Puedes entrar con otra demo.',
}

/** Texto para el usuario según el error del login (contrato: 401 CREDENCIALES_INVALIDAS, 429 DEMASIADOS_INTENTOS). */
function mensajeDeError(e) {
  if (e.status === 401) return e.message || 'Usuario o contraseña incorrectos.'
  if (e.status === 429) return null // lo arma la cuenta regresiva
  if (e.status === 422) return 'Revisa el usuario y la contraseña.'
  if (e.codigo === 'TIEMPO_AGOTADO') return 'El servidor no respondió a tiempo. Intenta otra vez en un momento.'
  if (e.status === 0) {
    return typeof navigator !== 'undefined' && navigator.onLine === false
      ? 'No tienes conexión a internet. Revísala e intenta otra vez.'
      : 'No pudimos conectar con el servidor. Revisa tu conexión e intenta otra vez.'
  }
  if (e.status >= 500) return 'El servidor tuvo un problema. Intenta otra vez en un momento.'
  return e.message || 'No pudimos iniciar la sesión. Intenta otra vez.'
}

export default function Ingresar() {
  useTitulo('Ingresar · TuCaserito')
  const sesion = useSesion()
  const location = useLocation()
  const ids = { usuario: useId(), clave: useId(), ayudaUsuario: useId(), ayudaClave: useId(), titulo: useId() }

  const [usuario, setUsuario] = useState('')
  const [clave, setClave] = useState('')
  const [verClave, setVerClave] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [despertando, setDespertando] = useState(false)
  const [error, setError] = useState(null) // { texto, campo? }
  const [esperaHasta, setEsperaHasta] = useState(0) // 429: hora (ms) hasta la que no se puede reintentar
  const [ahora, setAhora] = useState(() => Date.now())

  const refUsuario = useRef(null)
  const refClave = useRef(null)
  const ctrl = useRef(null)

  const motivo = MOTIVOS[location.state?.motivo] ?? null
  const desde = location.state?.desde
  const destino = location.state?.motivo !== 'salir' && typeof desde === 'string' && desde.startsWith('/app') ? desde : '/app'

  useEffect(() => despertarServidor(), [])
  useEffect(() => () => ctrl.current?.abort(), [])

  // Cuenta regresiva del 429
  const segundos = Math.max(0, Math.ceil((esperaHasta - ahora) / 1000))
  useEffect(() => {
    if (!esperaHasta) return undefined
    const t = setInterval(() => {
      const n = Date.now()
      setAhora(n)
      if (n >= esperaHasta) {
        setEsperaHasta(0)
        setError(null)
      }
    }, 1000)
    return () => clearInterval(t)
  }, [esperaHasta])

  if (sesion) return <Navigate to={destino} replace />

  const bloqueado = segundos > 0

  async function enviar(ev) {
    ev.preventDefault()
    if (enviando || bloqueado) return
    const u = usuario.trim()
    if (!u) {
      setError({ texto: 'Escribe tu usuario.', campo: 'usuario' })
      refUsuario.current?.focus()
      return
    }
    if (!clave) {
      setError({ texto: 'Escribe tu contraseña.', campo: 'clave' })
      refClave.current?.focus()
      return
    }

    setError(null)
    setEnviando(true)
    const aviso = USE_MOCK ? null : setTimeout(() => setDespertando(true), AVISO_DESPERTAR_MS)
    ctrl.current = new AbortController()
    try {
      const r = await api.login({ usuario: u, contrasena: clave }, { signal: ctrl.current.signal, timeoutMs: TIEMPO_MAXIMO_MS })
      setSesion(r) // useSesion se actualiza y este componente redirige a la app
    } catch (e) {
      if (e.name === 'AbortError') return
      if (e.status === 429) {
        const s = e.retryAfter ?? null
        if (s) {
          setEsperaHasta(Date.now() + s * 1000)
          setAhora(Date.now())
        }
        setError({ texto: s ? null : 'Hiciste varios intentos seguidos. Espera un momento y vuelve a intentar.' })
      } else {
        setError({ texto: mensajeDeError(e), campo: e.status === 401 ? 'clave' : null })
        if (e.status === 401) {
          setClave('')
          refClave.current?.focus()
        }
      }
    } finally {
      if (aviso) clearTimeout(aviso)
      setEnviando(false)
      setDespertando(false)
    }
  }

  const textoError = bloqueado
    ? `Hiciste varios intentos seguidos. Vuelve a intentar en ${segundos} s.`
    : error?.texto
  const invalido = (campo) => !bloqueado && error?.campo === campo

  return (
    <div className="ing">
      <SiteBar
        accion={
          <Link to="/" className="lp-bar__ingresar">
            <Icon name="back" size={18} />
            Volver
          </Link>
        }
      />
      <main className="ing-stage">
        <div className="ing-stage__panel lp-panel">
          <DotFan className="lp-fan" />
          <section className="ing-card" aria-labelledby={ids.titulo}>
            <h1 className="ing-card__titulo" id={ids.titulo}>
              Ingresa a la demo
            </h1>
            <p className="ing-card__sub">Usa el usuario y la contraseña de la demo que te compartimos.</p>

            {motivo && !error && !bloqueado && (
              <p className="ing-aviso" role="status">
                <Icon name="info" size={18} />
                {motivo}
              </p>
            )}

            <form className="ing-form" onSubmit={enviar} noValidate>
              <div className="ing-campo">
                <label className="ing-campo__label" htmlFor={ids.usuario}>
                  Usuario
                </label>
                <input
                  ref={refUsuario}
                  id={ids.usuario}
                  className="ing-campo__input"
                  name="username"
                  type="text"
                  autoComplete="username"
                  autoCapitalize="none"
                  autoCorrect="off"
                  spellCheck={false}
                  inputMode="text"
                  maxLength={MAX_LARGO}
                  value={usuario}
                  onChange={(e) => setUsuario(e.target.value)}
                  aria-invalid={invalido('usuario') || undefined}
                  aria-describedby={invalido('usuario') ? ids.ayudaUsuario : undefined}
                  disabled={enviando}
                />
              </div>

              <div className="ing-campo">
                <label className="ing-campo__label" htmlFor={ids.clave}>
                  Contraseña
                </label>
                <div className="ing-campo__clave">
                  <input
                    ref={refClave}
                    id={ids.clave}
                    className="ing-campo__input"
                    name="password"
                    type={verClave ? 'text' : 'password'}
                    autoComplete="current-password"
                    autoCapitalize="none"
                    autoCorrect="off"
                    spellCheck={false}
                    maxLength={MAX_LARGO}
                    value={clave}
                    onChange={(e) => setClave(e.target.value)}
                    aria-invalid={invalido('clave') || undefined}
                    aria-describedby={invalido('clave') ? ids.ayudaClave : undefined}
                    disabled={enviando}
                  />
                  <button
                    type="button"
                    className="ing-campo__ver"
                    onClick={() => setVerClave((v) => !v)}
                    aria-pressed={verClave}
                    aria-controls={ids.clave}
                    aria-label={verClave ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                    title={verClave ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                  >
                    <Icon name={verClave ? 'eyeOff' : 'eye'} size={22} />
                  </button>
                </div>
              </div>

              <div className="ing-mensajes" aria-live="polite">
                {textoError && (
                  <p className="ing-error" id={error?.campo === 'usuario' ? ids.ayudaUsuario : ids.ayudaClave} role="alert">
                    <Icon name="warning" size={18} />
                    {textoError}
                  </p>
                )}
                {despertando && (
                  <p className="ing-despertar" role="status">
                    <span className="ing-despertar__puntos" aria-hidden="true">
                      <i />
                      <i />
                      <i />
                    </span>
                    <span>
                      <strong>Despertando el servidor…</strong> La primera vez del día puede tardar hasta un minuto. No cierres esta
                      página.
                    </span>
                  </p>
                )}
              </div>

              <button type="submit" className="lp-cta lp-cta--claro ing-form__enviar" disabled={enviando || bloqueado} aria-busy={enviando}>
                {enviando ? (
                  <>
                    <span className="ing-spinner" aria-hidden="true" />
                    Ingresando…
                  </>
                ) : bloqueado ? (
                  `Espera ${segundos} s`
                ) : (
                  'Ingresar'
                )}
              </button>
            </form>
          </section>
          <p className="ing-stage__nota">Demo con datos ficticios. Tu sesión se cierra al cerrar esta pestaña.</p>
        </div>
      </main>
    </div>
  )
}
