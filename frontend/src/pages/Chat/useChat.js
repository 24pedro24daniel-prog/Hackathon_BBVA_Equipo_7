// Estado y lógica de la conversación. Todos los datos pasan por api.* (nunca por los mocks directamente).
//
// Mensaje: { id, from: 'me' | 'bot', kind, time, ...datos }
//   me:  text | audio | photo
//   bot: text | error | confirm | clarify | warning | options | alert | assistant | cuaderno | plan
// Las tarjetas con acciones llevan `status`: pending | editing | saving | done | replaced | discarded.
// Todo texto o audio va a POST /chat/mensajes (con el borrador pendiente, si hay): el backend decide si es un registro,
// una corrección/respuesta, un "sí", un "bórralo" o una pregunta. Los botones usan sus endpoints directos.
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/index.js'
import { ddmm, hhmm, soles } from '../../lib/format.js'
import { isAffirmative, isNegative, parseNumero, textoConfirmado } from './chatText.js'
import { capturarFotoCuaderno, capturarNotaDeVoz, DEMO_VOICE_NOTES } from './media.js'
import { DEMO_SCRIPTS } from './demoScripts.js'
import { armarPlanCaja, preguntaPlan } from './planCaja.js'

const now = () => hhmm(new Date())
const HOLA = 'Hola 👋 ¿Qué vendiste o gastaste hoy? Escríbeme, mándame un audio o una foto de tu cuaderno.'
const wait = (ms) => new Promise((r) => setTimeout(r, ms))

export function useChat({ demo, intent } = {}) {
  const navigate = useNavigate()
  const [messages, setMessages] = useState([])
  const [typing, setTyping] = useState(null) // texto del indicador "…" o null
  const [busy, setBusy] = useState(false)
  const [flujo, setFlujo] = useState(demo === 'alertas' ? 'Alertas y preguntas' : 'Registro')

  // Fuente de verdad síncrona (los handlers leen de aquí; el estado es el espejo para renderizar)
  const store = useRef([])
  const seq = useRef(0)
  const conversacionId = useRef(null)
  // Tarjeta cuyo borrador espera respuesta (se manda como borrador_id) y cuaderno pendiente
  const pending = useRef({ cardId: null, cuadernoId: null })

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
    // Mensajes del backend que ya están escritos para Pedro (no interpretable, ya confirmado, falta el monto…)
    const paraPedro = ['NO_INTERPRETABLE', 'NO_ENCONTRADO', 'CONFLICTO'].includes(err?.codigo) || (err?.codigo === 'VALIDACION' && err.status === 400)
    if (paraPedro) {
      bot('text', { text: err.message })
      return
    }
    bot('error', { text: 'Uy, no me llegó bien. ¿Lo intentamos otra vez?', retry, status: 'pending' })
  }

  function retry(id) {
    const m = get(id)
    if (!m?.retry || m.status === 'done') return
    update(id, { status: 'done' })
    return m.retry()
  }

  // ---------- Conversación: todo texto o audio va a POST /chat/mensajes; el backend decide qué es ----------

  /** Tarjeta (confirm | clarify | warning) cuyo borrador espera respuesta, si sigue abierta */
  function cardPendiente() {
    const m = get(pending.current.cardId)
    return m && (m.status === 'pending' || m.status === 'editing') ? m : null
  }

  async function conversar({ texto, canal = 'texto', media_url = null, audioId = null }) {
    const card = cardPendiente()
    try {
      const r = await withTyping(canal === 'voz' ? 'Escuchando tu audio…' : 'Escribiendo…', () =>
        api.chat({ texto, canal, media_url, borrador_id: card?.res.borrador_id ?? null, conversacion_id: conversacionId.current }),
      )
      if (audioId) update(audioId, { transcripcion: r.transcripcion || texto })
      conversacionId.current = r.conversacion_id || conversacionId.current
      mostrarRespuesta(r, card)
    } catch (err) {
      if (audioId) update(audioId, { transcripcion: texto })
      handleError(err, () => conversar({ texto, canal, media_url, audioId }))
    }
  }

  function mostrarRespuesta(r, card) {
    switch (r.tipo) {
      case 'registro':
      case 'borrador_actualizado':
        // Una corrección o respuesta se muestra como tarjeta nueva, debajo de lo que escribió Pedro; la anterior queda cerrada.
        if (r.tipo === 'borrador_actualizado' && card) cerrar(card.id, 'replaced')
        return mostrarInterpretacion(r.interpretacion, r.mensaje)
      case 'guardado':
        if (card) cerrar(card.id, 'done')
        // El backend ya redacta el "listo" con el saldo; si no viene, se arma aquí
        return bot('text', { text: r.mensaje || textoConfirmado(card?.res.movimiento_propuesto, {}, r.confirmacion) })
      case 'descartado':
        if (card) cerrar(card.id, 'discarded')
        return bot('text', { text: r.mensaje || 'Listo, no lo anoto.' })
      default:
        setFlujo('Alertas y preguntas')
        if (r.mensaje && !r.asistente) return bot('text', { text: r.mensaje })
        return bot('assistant', { res: r.asistente })
    }
  }

  /** Cierra una tarjeta (y sus opciones) y deja de esperar respuesta sobre ella */
  function cerrar(id, status) {
    update(id, { status })
    store.current.filter((x) => x.warningId === id).forEach((x) => update(x.id, { status }))
    if (pending.current.cardId === id) pending.current.cardId = null
  }

  /** `mensaje`: texto natural del backend; encabeza la tarjeta o va antes, sin repetir la pregunta */
  function mostrarInterpretacion(res, mensaje = null) {
    const mov = res.movimiento_propuesto
    setFlujo(mov?.tipo === 'compra' ? 'Pedido' : 'Registro')
    const faltan = res.campos_faltantes || []
    const dudoso = (res.confianza ?? 1) < 0.75
    if (res.pregunta_aclaratoria && (faltan.length || dudoso)) {
      if (mensaje && mensaje !== res.pregunta_aclaratoria) bot('text', { text: mensaje })
      pending.current.cardId = bot('clarify', { res, status: 'pending' })
      return
    }
    // Pedido completo: antes de guardarlo se revisa si te alcanza la caja ese día
    if (mov?.tipo === 'compra' && mov.fecha_vencimiento && mov.monto) {
      return chequear(res, { fecha_vencimiento: mov.fecha_vencimiento }, mensaje)
    }
    pending.current.cardId = bot('confirm', { res, status: 'pending', dudoso, titulo: mensaje })
  }

  /** POST /ingesta/confirmar del borrador `res`; `ids` son las tarjetas que quedan guardadas */
  async function confirmarBorrador(res, correcciones, ids) {
    const prev = ids.map((id) => get(id)?.status)
    ids.forEach((id) => update(id, { status: 'saving' }))
    try {
      const r = await withTyping('Guardando…', () =>
        api.confirmar({ borrador_id: res.borrador_id, confirmado: true, correcciones }),
      )
      ids.forEach((id) => cerrar(id, 'done'))
      bot('text', { text: textoConfirmado(res.movimiento_propuesto, correcciones, r) })
    } catch (err) {
      ids.forEach((id, i) => update(id, { status: prev[i] }))
      handleError(err, () => confirmarBorrador(res, correcciones, ids))
    }
  }

  /** Guarda el borrador de una tarjeta (confirm | clarify | warning) con correcciones opcionales */
  function guardar(id, correcciones = {}) {
    const m = get(id)
    if (!m || m.status === 'done' || m.status === 'saving') return
    return confirmarBorrador(m.res, correcciones, [id])
  }

  function corregir(id) {
    const m = get(id)
    if (!m || m.status !== 'pending') return
    me('text', { text: '✏️ Corregir' })
    update(id, { status: 'editing' })
    pending.current.cardId = id
    bot('text', { text: 'Dale, ¿qué cambio?' })
  }

  function correcto(id) {
    const m = get(id)
    if (!m || (m.status !== 'pending' && m.status !== 'editing')) return
    me('text', { text: '✅ Correcto' })
    return guardar(id)
  }

  // ---------- Pedido: aclaración → chequeo → advertencia ----------

  function elegirOpcion(id, opcion) {
    const m = get(id)
    if (!m || m.status !== 'pending') return
    me('text', { text: opcion.texto })
    update(id, { elegido: opcion.valor })
    const mov = m.res.movimiento_propuesto
    const campo = m.res.campos_faltantes?.[0] || 'fecha_vencimiento'
    // Fecha de un pedido con monto: se revisa la caja directo. Cualquier otra respuesta la entiende el backend.
    if (mov.tipo === 'compra' && campo === 'fecha_vencimiento' && mov.monto) {
      update(id, { status: 'done' })
      if (pending.current.cardId === id) pending.current.cardId = null
      return chequear(m.res, { fecha_vencimiento: opcion.valor })
    }
    pending.current.cardId = id
    return conversar({ texto: opcion.texto })
  }

  async function chequear(res, correcciones, mensaje = null) {
    const mov = res.movimiento_propuesto
    const fecha = correcciones.fecha_vencimiento
    try {
      // El backend ya suele traer el chequeo para esa fecha; si no, se pide.
      const chequeo =
        res.chequeo_pedido?.fecha_vencimiento === fecha
          ? res.chequeo_pedido
          : await withTyping('Revisando tu caja…', () =>
              api.chequearPedido({ proveedor: mov.contraparte, monto: mov.monto, fecha_vencimiento: fecha }),
            )
      // Ese pedido ya está anotado (mismo proveedor, monto y fecha): se descarta el borrador para no duplicarlo.
      const yaRegistrado = !!chequeo.pedido_coincidente_id
      if (yaRegistrado) await api.confirmar({ borrador_id: res.borrador_id, confirmado: false }).catch(() => {})
      else if (mensaje) bot('text', { text: mensaje })
      if (chequeo.estado_caja === 'te_alcanza') {
        if (yaRegistrado) return bot('text', { text: `Ese pedido ya lo tenías anotado. Y tranquilo: te alcanza para pagarlo el ${ddmm(fecha)}.` })
        return confirmarBorrador(res, correcciones, [])
      }
      const id = bot('warning', { res, chequeo, correcciones, yaRegistrado, status: yaRegistrado ? 'done' : 'pending' })
      if (!yaRegistrado) pending.current.cardId = id
    } catch (err) {
      handleError(err, () => chequear(res, correcciones, mensaje))
    }
  }

  function verOpciones(id) {
    const w = get(id)
    if (!w || w.opcionesVistas) return
    me('text', { text: 'Ver opciones' })
    update(id, { opcionesVistas: true })
    bot('options', { chequeo: w.chequeo, fecha: w.correcciones.fecha_vencimiento, warningId: id, status: w.status, yaRegistrado: w.yaRegistrado })
  }

  function registrarIgual(id) {
    const w = get(id)
    if (!w || w.yaRegistrado || w.status !== 'pending') return
    me('text', { text: 'Registrar igual' })
    return confirmarBorrador(w.res, w.correcciones, [id])
  }

  // ---------- F6: alerta proactiva ----------

  // Solo abre el simulador: no marca la alerta como atendida (Pedro aún no hizo nada).
  const abrirAlerta = () => navigate('/simulador')

  // ---------- F7: asistente ----------

  function accionAsistente(accion) {
    if (accion.tipo === 'abrir_simulador') return navigate('/simulador')
    if (accion.tipo === 'hablar_humano') {
      me('text', { text: accion.texto || 'Hablar con una persona' })
      bot('text', {
        text: 'Listo, le paso tu consulta a una persona del equipo y te escribe por aquí.\n(En esta demo no se envía nada.)',
      })
    }
  }

  // ---------- Plan de caja ("Probar qué hacer" desde 30 días) ----------

  async function planCaja() {
    setFlujo('Alertas y preguntas')
    try {
      const plan = await armarPlanCaja()
      me('text', { text: preguntaPlan(plan.fecha) })
      await withTyping('Revisando tus cuentas…', () => wait(700))
      bot('plan', { plan, usadas: [] })
    } catch (err) {
      handleError(err, () => planCaja())
    }
  }

  async function accionPlan(id, accion) {
    const m = get(id)
    if (!m) return
    if (accion.tipo === 'abrir_simulador') return navigate('/simulador')
    if (accion.tipo !== 'recordar_fiado' || m.usadas.includes(accion.tipo)) return
    me('text', { text: accion.texto })
    update(id, { usadas: [...m.usadas, accion.tipo] })
    const f = accion.fiado
    try {
      const r = await withTyping('Preparando el mensaje…', () => api.recordatorioFiado(f.fiado_id))
      bot('text', { text: `Te dejo el mensaje para ${f.cliente}:\n“${r.mensaje}”\n(En esta demo no se envía nada.)` })
    } catch (err) {
      update(id, { usadas: get(id).usadas.filter((t) => t !== accion.tipo) })
      handleError(err, () => accionPlan(id, accion))
    }
  }

  // ---------- Cuaderno de fiados ----------

  async function leerCuaderno(media_url) {
    setFlujo('Fiados')
    try {
      const res = await withTyping('Leyendo tu cuaderno…', () => api.leerCuaderno({ media_url }))
      if (!res.fiados_propuestos?.length) {
        bot('text', { text: 'No logré ver fiados en la foto. ¿Me la mandas más de cerca y con buena luz?' })
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
      const r = await withTyping('Guardando…', () =>
        api.confirmar({ borrador_id: m.res.borrador_id, confirmado: true, correcciones: { fiados } }),
      )
      update(id, { status: 'done' })
      pending.current.cuadernoId = null
      const repetidos = r?.duplicados?.length || 0
      const nuevos = fiados.length - repetidos
      const total = fiados.reduce((s, f) => s + Number(f.monto || 0), 0) - (r?.duplicados || []).reduce((s, f) => s + f.monto, 0)
      const lines = []
      if (nuevos > 0) lines.push(`Guardé ${nuevos} ${nuevos === 1 ? 'fiado' : 'fiados'} por **${soles(total)}** ✅`)
      if (repetidos > 0) lines.push(`${repetidos} ya ${repetidos === 1 ? 'estaba' : 'estaban'} en tu cuaderno; no los dupliqué.`)
      bot('text', { text: lines.join('\n') })
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
    const otro = dudoso?.alternativas_monto?.find((x) => x !== dudoso.monto)
    bot('text', {
      text: dudoso
        ? `Dime el monto correcto de ${dudoso.cliente}${otro ? `, por ejemplo «${otro}»` : ''}.`
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
    if (pending.current.cuadernoId && textoCuaderno(pending.current.cuadernoId, texto)) return
    return conversar({ texto })
  }

  async function enviarVoz(note) {
    const nota = await capturarNotaDeVoz(note)
    const audioId = me('audio', { duracion: nota.duracion, transcripcion: null })
    return conversar({ canal: 'voz', texto: nota.texto, media_url: nota.media_url, audioId })
  }

  async function enviarFoto() {
    const foto = await capturarFotoCuaderno()
    me('photo', { caption: foto.caption })
    return leerCuaderno(foto.media_url)
  }

  // ---------- Al montar: alerta del día + guion de demo opcional ----------

  const actions = {
    enviarTexto, enviarVoz, enviarFoto, correcto, corregir, elegirOpcion, verOpciones, registrarIgual,
    abrirAlerta, accionAsistente, accionPlan, planCaja, guardarCuaderno, corregirCuaderno, retry,
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
      // Llegó desde "Probar qué hacer": la respuesta es el plan, sin saludo ni alerta del día.
      if (intent === 'plan_caja') return actionsRef.current.planCaja()
      try {
        const { items = [] } = await api.getAlertas()
        const top = [...items].sort((a, b) => (a.prioridad ?? 9) - (b.prioridad ?? 9))[0]
        if (top) {
          bot('alert', { alerta: top, total: items.length, time: top.creada_en ? hhmm(top.creada_en) : now() })
        } else {
          bot('text', { text: HOLA })
        }
      } catch {
        bot('text', { text: HOLA })
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
        else if (step.tap) a[step.tap](store.current.findLast((m) => m.kind === step.kind)?.id)
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { messages, typing, busy, flujo, actions }
}
