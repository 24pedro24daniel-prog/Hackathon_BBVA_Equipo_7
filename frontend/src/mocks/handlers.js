// Mock del backend: resuelve (método, ruta) con respuestas del contrato. Solo se usa con VITE_USE_MOCK=true.
// El simulador es determinístico y coincide con contract.md §4.5–4.6:
//   saldo_30/11 = −650 + (2400 − monto_pedido) + (2 partes ? monto/2 : 0) + (cobrar fiados ? 310 : 0)
import * as D from './data.js'
import { getDemoSettings } from '../lib/demo.js'

const wait = (ms) => new Promise((r) => setTimeout(r, ms))
const ok = (body, status = 200) => ({ status, body })
const err = (status, codigo, mensaje) => ({
  status,
  body: { error: { codigo, mensaje, detalles: [], request_id: `req_${Math.random().toString(16).slice(2, 8)}` } },
})

let seq = 7781
const borradores = new Map()
let saldoNegocio = 2340

const PEDIDO_BASE = 2400
const SALDO_BASE = -650
const FIADOS_TOTAL = 310

export function simularSaldo({ monto = PEDIDO_BASE, partes = 1, cobrarFiados = false } = {}) {
  let saldo = SALDO_BASE + (PEDIDO_BASE - monto)
  if (partes >= 2) saldo += monto / 2
  if (cobrarFiados) saldo += FIADOS_TOTAL
  return saldo
}

function estadoCaja(saldo) {
  if (saldo < 0) return 'no_te_alcanza'
  if (saldo < 800) return 'justo'
  return 'te_alcanza'
}

function interpretarTexto(texto = '') {
  const t = texto.toLowerCase()
  const base = { moneda: 'PEN', contraparte: null, fecha_hora: new Date().toISOString(), fecha_vencimiento: null }
  if (t.includes('cerveza')) {
    const c = D.catalogo.cerveza
    const cant = /\b(dos|2)\b/.test(t) ? 2 : /\b(tres|3)\b/.test(t) ? 3 : 1
    return {
      movimiento_propuesto: {
        ...base, tipo: 'venta', metodo_pago: 'efectivo', monto: c.precio_unitario * cant,
        items: [{ ...c, cantidad: cant, subtotal: c.precio_unitario * cant }],
      },
      origen_monto: 'catalogo', confianza: 0.93, campos_faltantes: [], pregunta_aclaratoria: null,
    }
  }
  const saque = t.match(/saqu[eé]\s+(\d+)/)
  if (saque) {
    return {
      movimiento_propuesto: { ...base, tipo: 'retiro_personal', metodo_pago: 'efectivo', monto: Number(saque[1]), items: [] },
      origen_monto: 'dicho_por_usuario', confianza: 0.95, campos_faltantes: [], pregunta_aclaratoria: null,
    }
  }
  const pedido = t.match(/ped[ií]\s+([\d\s.]+)\s+a\s+(\w+)/)
  if (pedido) {
    const monto = Number(pedido[1].replace(/[\s.]/g, ''))
    const prov = pedido[2].toLowerCase() === 'andina' ? 'Distribuidora Andina' : pedido[2]
    return {
      movimiento_propuesto: { ...base, tipo: 'compra', metodo_pago: 'credito', monto, items: [], contraparte: prov },
      origen_monto: 'dicho_por_usuario', confianza: 0.7, campos_faltantes: ['fecha_vencimiento'],
      pregunta_aclaratoria: '¿Lo pagas el 30 de noviembre o el 30 de diciembre?',
      opciones_aclaracion: [ // EXT: botones de respuesta rápida
        { valor: '2026-11-30', texto: '30/11' },
        { valor: '2026-12-30', texto: '30/12' },
      ],
    }
  }
  const pague = t.match(/pagu[eé].*?(\d+)/)
  if (t.includes('rus') && pague) {
    return {
      movimiento_propuesto: { ...base, tipo: 'pago_impuesto', metodo_pago: 'efectivo', monto: Number(pague[1]), items: [] },
      origen_monto: 'dicho_por_usuario', confianza: 0.9, campos_faltantes: [], pregunta_aclaratoria: null,
    }
  }
  return null
}

async function handle(method, path, { query, body }) {
  const { escenario, fallback } = getDemoSettings()
  const nuevo = escenario === 'nuevo'
  const key = `${method} ${path.replace(/\/empresas\/[^/]+/, '/empresas/:id').replace(/\/(fiados|alertas)\/[A-Z]+-\d+/, '/$1/:id')}`

  switch (key) {
    case 'GET /health':
      return ok({ estado: 'ok', version_api: '1.0.0', componentes: { base_datos: 'ok', llm: { estado: fallback ? 'caido' : 'ok' } } })

    case 'GET /empresas/:id/resumen': {
      const r = structuredClone(nuevo ? D.resumenNuevo : D.resumenPedro)
      if (!nuevo) r.indicadores.saldo_caja_negocio.valor = saldoNegocio
      return ok({ ...r, periodo: query.periodo || r.periodo })
    }

    case 'GET /empresas/:id/forecast':
      return ok(nuevo ? D.forecastNuevo() : D.forecastPedro())

    case 'POST /empresas/:id/forecast/ajustes':
      return ok({ ajuste_id: 'AJU-0003', forecast_recalculado: true }, 201)

    case 'GET /empresas/:id/fiados':
      return ok(nuevo ? { total_pendiente: 0, total_vencido: 0, items: [], meta: D.meta('riesgo-atraso-clf', '0.2.0') } : D.fiados())

    case 'POST /fiados/:id/recordatorio': {
      const f = D.fiados().items.find((x) => path.includes(x.fiado_id))
      if (!f) return err(404, 'NO_ENCONTRADO', 'No encontré ese fiado.')
      return ok({ mensaje: `Hola, ${f.cliente} 😊 Le recuerdo amablemente los S/ ${f.monto} pendientes en la bodega. ¡Gracias!` })
    }

    case 'GET /empresas/:id/pedidos':
      return ok(nuevo ? { total_pendiente: 0, items: [], impuestos: { estado: 'al_dia', proximo_vencimiento: '2026-12-15', monto_estimado: 20 } } : D.pedidos())

    case 'POST /empresas/:id/pedidos/chequeo': {
      const monto = Number(body?.monto ?? PEDIDO_BASE)
      const saldo = simularSaldo({ monto })
      return ok({
        saldo_proyectado_al_vencimiento: saldo,
        estado_caja: estadoCaja(saldo),
        venta_esperada_periodo: 2000.0,
        exceso_vs_ventas: Math.max(0, monto - 2000),
        sugerencias: [
          { accion: 'reducir_pedido', monto_sugerido: 1800.0, saldo_resultante: simularSaldo({ monto: 1800 }) },
          { accion: 'pagar_en_partes', partes: 2, saldo_resultante: simularSaldo({ monto, partes: 2 }) },
          { accion: 'combinar', detalle: 'pedir 1 800 + pagar en 2 partes', saldo_resultante: simularSaldo({ monto: 1800, partes: 2 }) },
        ],
        fundamento: 'En 2 semanas sueles vender unos S/ 2 000 y ese día no tendrás colchón.',
        limites: 'Proyección basada en tus ventas de los últimos 3 meses; no considera eventos que no hayas registrado.',
        confianza: 'media',
        meta: D.meta('forecast-lgbm-quantile', '0.3.1'),
      })
    }

    case 'POST /empresas/:id/simular': {
      const acciones = body?.acciones || []
      let monto = PEDIDO_BASE, partes = 1, cobrarFiados = false
      for (const a of acciones) {
        if (a.tipo === 'reducir_pedido') monto = Number(a.nuevo_monto)
        if (a.tipo === 'pagar_en_partes') partes = Number(a.partes || 2)
        if (a.tipo === 'cobrar_fiados') cobrarFiados = true
      }
      const con = simularSaldo({ monto, partes, cobrarFiados })
      return ok({
        sin_acciones: { saldo_minimo: SALDO_BASE, fecha: '2026-11-30', estado_caja: 'no_te_alcanza' },
        con_acciones: { saldo_minimo: con, fecha: '2026-11-30', estado_caja: estadoCaja(con) },
        mejora: con - SALDO_BASE,
        serie_con_acciones: [{ fecha: '2026-11-30', p50: con }],
        fundamento: 'Simulación con tus ventas de los últimos 3 meses.', // EXT
        limites: 'Tú decides; nada se ejecuta solo. Pagar en partes depende de que Andina acepte.', // EXT
        confianza: 'media', // EXT
        meta: D.meta('simulador-deterministico', '0.1.0'),
      })
    }

    case 'GET /empresas/:id/alertas':
      return ok(nuevo ? { items: [] } : D.alertas())

    case 'POST /alertas/:id/accion':
      return ok({ estado: 'atendida' })

    case 'GET /empresas/:id/salud':
      return ok(D.salud())

    case 'POST /empresas/:id/metas':
      return ok({ meta_id: 'MET-0005', estado: 'activa' }, 201)

    case 'GET /empresas/:id/movimientos':
      return ok({ items: [], next_cursor: null })

    case 'POST /empresas/:id/movimientos':
    case 'POST /empresas/:id/impuestos':
      return ok({ movimiento_id: `MOV-000${++seq}`, registros_creados: [], alertas_disparadas: [], saldo_caja_negocio: saldoNegocio }, 201)

    case 'GET /empresas/:id/analisis':
      return ok({ agrupar_por: query.agrupar_por || 'categoria', tipo: query.tipo || 'egreso', grupos: [] })

    case 'POST /ingesta/interpretar': {
      await wait(body?.canal === 'voz' ? 1400 : 500) // "Escuchando tu audio…"
      const texto = body?.texto || ''
      const res = interpretarTexto(texto)
      if (!res) return err(422, 'NO_INTERPRETABLE', 'No entendí bien. ¿Me lo dices de otra forma? Por ejemplo: "vendí 2 cervezas".')
      const borrador_id = `BOR-${++seq}`
      borradores.set(borrador_id, res.movimiento_propuesto)
      return ok({
        borrador_id,
        transcripcion: body?.canal === 'voz' ? texto : null,
        ...res,
        meta: D.meta('whisper-small + llm-extractor', '0.2.0', { prompt_version: 'extractor-v3', fallback_usado: fallback }),
      })
    }

    case 'POST /ingesta/confirmar': {
      const mov = borradores.get(body?.borrador_id)
      if (!mov) return err(404, 'NO_ENCONTRADO', 'Ese registro ya no existe. Vuelve a enviarlo.')
      if (body.confirmado === false && !Object.keys(body.correcciones || {}).length) {
        borradores.delete(body.borrador_id)
        return ok(null, 204)
      }
      const final = { ...mov, ...(body.correcciones || {}) }
      borradores.delete(body.borrador_id)
      if (final.tipo === 'venta' && final.metodo_pago !== 'credito') saldoNegocio += final.monto
      if (final.tipo === 'retiro_personal' || final.tipo === 'pago_impuesto') saldoNegocio -= final.monto
      return ok({
        movimiento_id: `MOV-000${++seq}`,
        registros_creados: [{ tabla: final.tipo === 'compra' ? 'deudas' : 'transacciones', id: `MOV-000${seq}` }],
        alertas_disparadas: final.tipo === 'compra' ? D.alertas().items : [],
        saldo_caja_negocio: saldoNegocio,
      }, 201)
    }

    case 'POST /ingesta/cuaderno': {
      await wait(1500)
      const borrador_id = `BOR-${++seq}`
      borradores.set(borrador_id, { tipo: 'venta', metodo_pago: 'credito', monto: 310 })
      return ok({
        borrador_id,
        fiados_propuestos: [
          { cliente: 'Sra. Carmen', detalle: 'panes, leche', monto: 120.0, fecha: '2026-10-27', confianza: 0.81 },
          { cliente: 'Don Luis', detalle: 'arroz, aceite', monto: 95.0, fecha: '2026-11-02', confianza: 0.64, alternativas_monto: [95, 35] },
          { cliente: 'Vecina Rosa', detalle: 'gaseosas', monto: 95.0, fecha: '2026-11-05', confianza: 0.88 },
        ],
        lineas_no_legibles: 1,
        meta: D.meta('ocr-manuscrito + llm-estructurador', '0.1.0', { prompt_version: 'cuaderno-v1' }),
      })
    }

    case 'POST /empresas/:id/asistente/mensajes':
      await wait(900)
      return ok(asistente(body?.mensaje || '', body?.conversacion_id, fallback))

    default:
      return err(404, 'NO_ENCONTRADO', `Mock sin ruta para ${method} ${path}`)
  }
}

function asistente(mensaje, conversacion_id, fallback) {
  const m = mensaje.toLowerCase()
  const base = {
    conversacion_id: conversacion_id || 'CNV-0031',
    herramientas_llamadas: [],
    cifras_usadas: [],
    verificacion_cifras: { ok: true, no_verificadas: [] },
    fuera_de_alcance: false,
    ofrecer_humano: false,
    disclaimer: 'Orientación educativa · no es asesoría',
    meta: D.meta('llm-local', 'qwen2.5-7b-instruct', { prompt_version: 'asistente-v2', fallback_usado: fallback }),
  }

  if (/pr[eé]stamo|prestar|gota/.test(m)) {
    return {
      ...base,
      intencion: 'prestamo',
      fuera_de_alcance: true,
      ofrecer_humano: true,
      respuesta: 'No te puedo recomendar un préstamo ni una entidad, pero sí mostrarte el costo:',
      // EXT: bloque de ejemplo ilustrativo de préstamo informal
      ejemplo_prestamo_informal: { recibes: 1000, devuelves: 1200, dias: 30, cuota_diaria: 40 },
      respuesta_post: 'Antes, prueba esto: pedir menos, pagar en 2 partes y cobrar fiados. Con eso ya llegas al 30/11.',
      acciones: [{ tipo: 'abrir_simulador', texto: 'Ver mi plan' }, { tipo: 'hablar_humano', texto: 'Hablar con una persona' }], // EXT
      cifras_usadas: [{ valor: 1000, fuente: 'microexplicaciones.prestamo_informal.ejemplo' }],
    }
  }

  if (/c[oó]mo va|mi caja|cu[aá]nto tengo/.test(m) || fallback) {
    const tabla = [ // EXT: cifras crudas para el "Modo básico"
      { etiqueta: 'Caja del negocio', valor: saldoNegocio },
      { etiqueta: 'Te deben (fiados)', valor: 310 },
      { etiqueta: 'Debes (30/11)', valor: 2400 },
    ]
    if (fallback) {
      return {
        ...base,
        intencion: 'estado_caja',
        respuesta: 'Ahora no puedo redactar una explicación, pero aquí están tus números:',
        tabla,
        meta: { ...base.meta, fallback_usado: true },
      }
    }
    return {
      ...base,
      intencion: 'estado_caja',
      respuesta: `Hoy tienes S/ ${saldoNegocio} en la caja del negocio. Te deben S/ 310 en fiados y el 30/11 pagas S/ 2 400 a Andina. Si no cambias nada, ese día te faltarían S/ 650.`,
      tabla,
      herramientas_llamadas: [{ nombre: 'obtener_resumen', args: { periodo: '2026-11' } }, { nombre: 'obtener_forecast', args: { horizonte_dias: 30 } }],
      cifras_usadas: [{ valor: saldoNegocio, fuente: 'resumen.saldo_caja_negocio' }, { valor: 650, fuente: 'forecast.dia_critico.saldo_p50' }],
    }
  }

  if (/por qu[eé]|falta|alcanza/.test(m)) {
    return {
      ...base,
      intencion: 'explicar_alerta',
      ofrecer_humano: true,
      respuesta: 'El 30/11 vence tu pago de S/ 2 400 a Distribuidora Andina. Este mes vendiste unos S/ 560 menos que el mes pasado, el pedido es S/ 400 mayor a lo que sueles vender y tienes S/ 310 en fiados sin cobrar. Si pides S/ 1 800 y pagas en 2 partes, ese día tendrías S/ 850.',
      herramientas_llamadas: [{ nombre: 'obtener_alertas', args: { estado: 'activa' } }, { nombre: 'simular', args: { acciones: ['reducir_pedido:1800', 'pagar_en_partes:2'] } }],
      cifras_usadas: [{ valor: 2400, fuente: 'pedidos.PED-0012.monto' }, { valor: 850, fuente: 'simular.con_acciones.saldo_minimo' }],
    }
  }

  if (/2 partes|dos partes|si pago/.test(m)) {
    return {
      ...base,
      intencion: 'simular',
      respuesta: `Si pagas a Andina en 2 partes (30/11 y 15/12), ese día te quedarían S/ ${simularSaldo({ partes: 2 })}. Tendrías que pedírselo a Andina.`,
      herramientas_llamadas: [{ nombre: 'simular', args: { acciones: ['pagar_en_partes:2'] } }],
      cifras_usadas: [{ valor: simularSaldo({ partes: 2 }), fuente: 'simular.con_acciones.saldo_minimo' }],
    }
  }

  return {
    ...base,
    intencion: 'otro',
    respuesta: 'Puedo ayudarte con: cómo va tu caja, por qué te faltaría plata, o qué pasa si cambias un pedido. ¿Qué quieres saber?',
  }
}

export async function mockRequest(method, path, opts) {
  await wait(250 + Math.random() * 200)
  return handle(method, path, opts)
}
