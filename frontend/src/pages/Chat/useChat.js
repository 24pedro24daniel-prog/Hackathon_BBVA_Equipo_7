// Estado y lógica de la conversación. Todos los datos pasan por api.* (nunca por los mocks directamente).
//
// Mensaje: { id, from: 'me' | 'bot', kind, time, ...datos }
//   me:  text | audio | photo
//   bot: text | error | confirm | clarify | warning | options | alert | assistant | cuaderno
// Las tarjetas con acciones llevan `status`: pending | editing | saving | done.
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/index.js'
import { hhmm, soles } from '../../lib/format.js'
import {
  isAffirmative,
  isNegative,
  isQuestion,
  norm,
  parseCorreccion,
  parseNumero,
  textoConfirmado,
} from './chatText.js'
import { capturarFotoCuaderno, capturarNotaDeVoz, DEMO_VOICE_NOTES } from './media.js'
import { DEMO_SCRIPTS } from './demoScripts.js'

const now = () => hhmm(new Date())
const wait = (ms) => new Promise((r) => setTimeout(r, ms))

export function useChat({ demo } = {}) {
  const navigate = useNavigate()
  const [messages, setMessages] = useState([])
  const [typing, setTyping] = useState(null) // texto del indicador "…" o null
  const [busy, setBusy] = useState(false)
  const [flujo, setFlujo] = useState(demo === 'alertas' ? 'Alertas y preguntas' : 'Registro')

  // Fuente de verdad síncrona (los handlers leen de aquí; el estado es el espejo para renderizar)
  const store = useRef([])
  const seq = useRef(0)
  const conversacionId = useRef(null)
  // Qué tarjeta está esperando una respuesta escrita
  const pending = useRef({ draftId: null, clarifyId: null, warningId: null, cuadernoId: null })

  const commit = () => setMessages(store.current)
  const get = (id) => store.current.find((m) => m.id === id)
  function push(from, kind, data = {}) {
    const msg = { id: `m${++seq.current}`, from, kind, time: now(), ...data }
    store.current = [...store.current, msg]
    commit()
    return msg.id
  }
  const me = (kind, data) => push('me', kind, data)
  const bot = (kind, data) => push('bot', kind, data)
  function update(id, patch) {
    store.current = store.current.map((m) => (m.id === id ? { ...m, ...patch } : m))
    commit()
  }

  async function withTyping(label, fn) {
    setTyping(label)
    setBusy(true)
    try {
      return await fn()
    } finally {
      setTyping(null)
      setBusy(false)
    }
  }

  function handleError(err, retry) {
    if (err?.codigo === 'NO_INTERPRETABLE' || err?.codigo === 'NO_ENCONTRADO') {
      bot('text', { text: err.message })
      return
    }
    bot('error', { text: 'No pude procesarlo ahora. Intenta otra vez.', retry, status: 'pending' })
  }

  function retry(id) {
    const m = get(id)
    if (!m?.retry || m.status === 'done') return
    update(id, { status: 'done' })
    return m.retry()
  }

  // ---------- F1: interpretar → confirmar ----------

  async function interpretar({ canal, texto, media_url = null, audioId = null }) {
    setFlujo('Registro')
    try {
      const res = await withTyping(canal === 'voz' ? 'Escuchando tu audio…' : 'Anotando…', () =>
        api.interpretar({ canal, texto, media_url }),
      )
      if (audioId) update(audioId, { transcripcion: res.transcripcion || texto })
      mostrarInterpretacion(res)
    } catch (err) {
      if (audioId) update(audioId, { transcripcion: texto })
      handleError(err, () => interpretar({ canal, texto, media_url, audioId }))
    }
  }

  function mostrarInterpretacion(res) {
    const mov = res.movimiento_propuesto
    if (mov?.tipo === 'compra') setFlujo('Pedido')
    const faltan = res.campos_faltantes || []
    const dudoso = (res.confianza ?? 1) < 0.75
    if (res.pregunta_aclaratoria && (faltan.length || dudoso)) {
      pending.current.clarifyId = bot('clarify', { res, status: 'pending' })
      return
    }
    pending.current.draftId = bot('confirm', { res, status: 'pending', dudoso })
  }

  /** Guarda el borrador de una tarjeta (confirm | clarify | warning) con correcciones opcionales */
  async function guardar(id, correcciones = {}) {
    const m = get(id)
    if (!m || m.status === 'done' || m.status === 'saving') return
    const prev = m.status
    update(id, { status: 'saving' })
    try {
      const r = await withTyping('Guardando…', () =>
        api.confirmar({ borrador_id: m.res.borrador_id, confirmado: true, correcciones }),
      )
      update(id, { status: 'done' })
      store.current.filter((x) => x.warningId === id).forEach((x) => update(x.id, { status: 'done' }))
      for (const k of Object.keys(pending.current)) if (pending.current[k] === id) pending.current[k] = null
      bot('text', { text: textoConfirmado(m.res.movimiento_propuesto, correcciones, r) })
    } catch (err) {
      update(id, { status: prev })
      handleError(err, () => guardar(id, correcciones))
    }
  }

  function corregir(id) {
    const m = get(id)
    if (!m || m.status !== 'pending') return
    me('text', { text: '✏️ Corregir' })
    update(id, { status: 'editing' })
    pending.current.draftId = id
    bot('text', { text: '¿Qué cambio? Escríbeme, por ejemplo: «fue por billetera», «fueron 15» o «era una venta».' })
  }

  function correcto(id) {
    const m = get(id)
    if (!m || (m.status !== 'pending' && m.status !== 'editing')) return
    me('text', { text: '✅ Correcto' })
    return guardar(id)
  }

  // ---------- Pedido: aclaración → chequeo → advertencia ----------

  async function elegirOpcion(id, opcion, { echo = true } = {}) {
    const m = get(id)
    if (!m || m.status !== 'pending') return
    if (echo) me('text', { text: opcion.texto })
    update(id, { status: 'done', elegido: opcion.valor })
    pending.current.clarifyId = null
    const campo = m.res.campos_faltantes?.[0] || 'fecha_vencimiento'
    const correcciones = { [campo]: opcion.valor }
    const mov = m.res.movimiento_propuesto
    if (mov.tipo === 'compra' && campo === 'fecha_vencimiento') return chequear(id, correcciones)
    update(id, { status: 'pending' })
    return guardar(id, correcciones)
  }

  async function chequear(id, correcciones) {
    const m = get(id)
    const mov = m.res.movimiento_propuesto
    try {
      const chequeo = await withTyping('Revisando tu caja…', () =>
        api.chequearPedido({ proveedor: mov.contraparte, monto: mov.monto, fecha_vencimiento: correcciones.fecha_vencimiento }),
      )
      if (chequeo.estado_caja === 'te_alcanza') {
        update(id, { status: 'pending' })
        return guardar(id, correcciones)
      }
      pending.current.warningId = bot('warning', { res: m.res, chequeo, correcciones, status: 'pending' })
    } catch (err) {
      handleError(err, () => chequear(id, correcciones))
    }
  }

  function verOpciones(id, { echo = true } = {}) {
    const w = get(id)
    if (!w || w.opcionesVistas) return
    if (echo) me('text', { text: 'Ver opciones' })
    update(id, { opcionesVistas: true })
    bot('options', { chequeo: w.chequeo, fecha: w.correcciones.fecha_vencimiento, warningId: id, status: w.status })
  }

  function registrarIgual(id, { echo = true } = {}) {
    const w = get(id)
    if (!w || w.status !== 'pending') return
    if (echo) me('text', { text: 'Registrar igual' })
    return guardar(id, w.correcciones)
  }

  // ---------- F6: alerta proactiva ----------

  async function abrirAlerta(id) {
    const m = get(id)
    if (!m) return
    try {
      await api.accionAlerta(m.alerta.alerta_id, 'ejecutada')
    } catch {
      /* registrar la acción no debe impedir abrir el simulador */
    }
    navigate('/simulador')
  }

  // ---------- F7: asistente ----------

  async function preguntar(texto) {
    setFlujo('Alertas y preguntas')
    try {
      const res = await withTyping('Escribiendo…', () =>
        api.enviarAsistente({ conversacion_id: conversacionId.current, mensaje: texto, canal: 'app' }),
      )
      conversacionId.current = res.conversacion_id || conversacionId.current
      bot('assistant', { res })
    } catch (err) {
      handleError(err, () => preguntar(texto))
    }
  }

  function accionAsistente(accion) {
    if (accion.tipo === 'abrir_simulador') return navigate('/simulador')
    if (accion.tipo === 'hablar_humano') {
      me('text', { text: accion.texto || 'Hablar con una persona' })
      bot('text', {
        text: 'Listo. Le pasé tu consulta a una persona del equipo y te escribirá por este chat.\n(En esta demo no se envía nada.)',
      })
    }
  }

  // ---------- Cuaderno de fiados ----------

  async function leerCuaderno(media_url) {
    setFlujo('Fiados')
    try {
      const res = await withTyping('Leyendo tu cuaderno…', () => api.leerCuaderno({ media_url }))
      if (!res.fiados_propuestos?.length) {
        bot('text', { text: 'No encontré fiados en la foto. ¿Puedes tomarla más de cerca y con buena luz?' })
        return
      }
      pending.current.cuadernoId = bot('cuaderno', {
        res,
        montos: res.fiados_propuestos.map((f) => f.monto),
        status: 'pending',
      })
    } catch (err) {
      handleError(err, () => leerCuaderno(media_url))
    }
  }

  async function guardarCuaderno(id, { echo = true } = {}) {
    const m = get(id)
    if (!m || m.status === 'done' || m.status === 'saving') return
    if (echo) me('text', { text: 'Sí, guardar' })
    const prev = m.status
    update(id, { status: 'saving' })
    const fiados = m.res.fiados_propuestos.map((f, i) => ({
      cliente: f.cliente,
      detalle: f.detalle,
      fecha: f.fecha,
      monto: m.montos[i],
    }))
    try {
      await withTyping('Guardando…', () =>
        api.confirmar({ borrador_id: m.res.borrador_id, confirmado: true, correcciones: { fiados } }),
      )
      update(id, { status: 'done' })
      pending.current.cuadernoId = null
      const total = fiados.reduce((s, f) => s + Number(f.monto || 0), 0)
      bot('text', { text: `Guardé ${fiados.length} fiados por **${soles(total)}** ✅` })
    } catch (err) {
      update(id, { status: prev })
      handleError(err, () => guardarCuaderno(id, { echo: false }))
    }
  }

  function corregirCuaderno(id, { echo = true } = {}) {
    const m = get(id)
    if (!m || m.status !== 'pending') return
    if (echo) me('text', { text: 'No, corregir' })
    update(id, { status: 'editing' })
    const dudoso = m.res.fiados_propuestos.find((f) => f.alternativas_monto?.length || f.confianza < 0.75)
    bot('text', {
      text: dudoso
        ? `Dime el monto correcto de ${dudoso.cliente}, por ejemplo «${dudoso.alternativas_monto?.[1] ?? 35}».`
        : 'Dime qué nombre está mal y el monto correcto.',
    })
  }

  /** Respuesta escrita a la tarjeta del cuaderno: "95", "sí", "no" */
  function textoCuaderno(id, texto) {
    const m = get(id)
    const n = parseNumero(texto)
    if (n !== null) {
      const fiados = m.res.fiados_propuestos
      let idx = fiados.findIndex((f) => f.alternativas_monto?.includes(n))
      if (idx < 0) idx = fiados.findIndex((f) => f.alternativas_monto?.length || f.confianza < 0.75)
      if (idx < 0) return false
      update(id, { montos: m.montos.map((x, i) => (i === idx ? n : x)) })
      guardarCuaderno(id, { echo: false })
      return true
    }
    if (isAffirmative(texto)) {
      guardarCuaderno(id, { echo: false })
      return true
    }
    if (isNegative(texto)) {
      corregirCuaderno(id, { echo: false })
      return true
    }
    return false
  }

  // ---------- Entrada del compositor ----------

  async function enviarTexto(raw) {
    const texto = raw.trim()
    if (!texto) return
    me('text', { text: texto })
    const t = norm(texto)
    const p = pending.current

    if (p.cuadernoId && textoCuaderno(p.cuadernoId, texto)) return

    if (p.warningId) {
      if (/opciones/.test(t)) return verOpciones(p.warningId, { echo: false })
      if (/registrar|igual/.test(t)) return registrarIgual(p.warningId, { echo: false })
    }

    if (p.clarifyId) {
      const c = get(p.clarifyId)
      const ops = c?.res.opciones_aclaracion || []
      const op =
        ops.find((o) => norm(o.texto) === t || t.includes(norm(o.texto))) ||
        (/nov/.test(t) && ops.find((o) => o.valor.slice(5, 7) === '11')) ||
        (/dic/.test(t) && ops.find((o) => o.valor.slice(5, 7) === '12'))
      if (op) return elegirOpcion(p.clarifyId, op, { echo: false })
    }

    if (p.draftId) {
      const d = get(p.draftId)
      if (d && d.status !== 'done') {
        if (isAffirmative(texto)) return guardar(p.draftId)
        const corr = parseCorreccion(texto)
        if (corr && !isQuestion(texto)) return guardar(p.draftId, corr)
      }
    }

    if (isQuestion(texto)) return preguntar(texto)
    return interpretar({ canal: 'texto', texto })
  }

  async function enviarVoz(note) {
    const nota = await capturarNotaDeVoz(note)
    const audioId = me('audio', { duracion: nota.duracion, transcripcion: null })
    return interpretar({ canal: 'voz', texto: nota.texto, media_url: nota.media_url, audioId })
  }

  async function enviarFoto() {
    const foto = await capturarFotoCuaderno()
    me('photo', { caption: foto.caption })
    return leerCuaderno(foto.media_url)
  }

  // ---------- Al montar: alerta del día + guion de demo opcional ----------

  const actions = {
    enviarTexto, enviarVoz, enviarFoto, correcto, corregir, elegirOpcion, verOpciones, registrarIgual,
    abrirAlerta, accionAsistente, guardarCuaderno, corregirCuaderno, retry,
  }
  const actionsRef = useRef(actions)
  actionsRef.current = actions

  const mounted = useRef(false)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const started = useRef(false)
  useEffect(() => {
    if (started.current) return // StrictMode monta dos veces: la alerta se muestra una sola vez
    started.current = true
    ;(async () => {
      try {
        const { items = [] } = await api.getAlertas()
        const top = [...items].sort((a, b) => (a.prioridad ?? 9) - (b.prioridad ?? 9))[0]
        if (top) {
          bot('alert', { alerta: top, total: items.length, time: top.creada_en ? hhmm(top.creada_en) : now() })
        } else {
          bot('text', { text: 'Hola 👋 Cuéntame qué vendiste o gastaste. Puedes escribir, mandar un audio o una foto de tu cuaderno.' })
        }
      } catch {
        bot('text', { text: 'Hola 👋 Cuéntame qué vendiste o gastaste. Puedes escribir, mandar un audio o una foto de tu cuaderno.' })
      }
      const script = DEMO_SCRIPTS[demo]
      if (!script) return
      for (const step of script) {
        await wait(step.pausa ?? 1400)
        if (!mounted.current) return
        const a = actionsRef.current
        if (step.texto) await a.enviarTexto(step.texto)
        else if (step.voz) await a.enviarVoz(DEMO_VOICE_NOTES.find((n) => n.id === step.voz))
        else if (step.foto) await a.enviarFoto()
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { messages, typing, busy, flujo, actions }
}
