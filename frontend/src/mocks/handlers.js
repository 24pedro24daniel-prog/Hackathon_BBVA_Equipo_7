// Mock del backend: resuelve (método, ruta) con respuestas del contrato. Solo se usa con VITE_USE_MOCK=true.
// El simulador es determinístico y coincide con contract.md §4.5–4.6:
//   saldo_30/11 = base + (2400 − monto_pedido) + (2 partes ? monto/2 : 0) + (cobrar fiados ? monto de esos fiados : 0)
// base: −650 en 'pedro'; en 'sano' el p50 del 30/11 de su serie (positivo, sobre el mínimo de S/ 800).
// Escenarios: 'pedro' (92 días, no le alcanza) | 'sano' (92 días, sí le alcanza) | 'nuevo' (día 3).
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
// Caja del negocio y movimientos confirmados en el chat, por escenario (no se mezclan al cambiar de demo)
const saldos = { ...D.SALDO_INICIAL }
const movimientosNuevos = { pedro: [], sano: [], nuevo: [] } // lo que se confirma en el chat aparece en Últimos movimientos
const esc = (e) => (e === 'nuevo' || e === 'sano' ? e : 'pedro')
// Se conserva el registro anulado durante la sesión, separado por escenario.
const cuentasAnuladas = { pedro: new Map(), sano: new Map(), nuevo: new Map() }

function fiadosActivos(escenario) {
  const data = D.fiadosDe(escenario)
  const items = data.items.filter((f) => !cuentasAnuladas[escenario].has(`fiado:${f.fiado_id}`))
  return {
    ...data,
    items,
    total_pendiente: items.reduce((s, f) => s + f.monto, 0),
    total_vencido: items.filter((f) => f.estado === 'vencido' || f.estado === 'por_vencer').reduce((s, f) => s + f.monto, 0),
  }
}

function pedidosActivos(escenario) {
  const data = D.pedidosDe(escenario)
  const items = data.items.filter((p) => !cuentasAnuladas[escenario].has(`pedido:${p.pedido_id}`))
  return {
    ...data,
    items,
    total_pendiente: items.reduce((s, p) => s + (p.monto_pendiente ?? p.monto), 0),
    impuestos: cuentasAnuladas[escenario].has(`impuesto:${data.impuestos?.impuesto_id}`) ? null : data.impuestos,
  }
}

const PEDIDO_BASE = 2400
const SALDO_BASE = -650 // 'pedro': p50 del 30/11

/** Saldo esperado el 30/11 sin acciones, según escenario */
const saldoBase = (escenario) => (esc(escenario) === 'sano' ? D.saldoSanoAl3011() : SALDO_BASE)

/** Monto que entra si cobras fiados: los fiado_ids pedidos o, si no vienen, el total pendiente */
function montoFiados(escenario, fiadoIds) {
  const f = fiadosActivos(esc(escenario))
  if (!fiadoIds?.length) return f.total_pendiente
  return f.items.filter((x) => fiadoIds.includes(x.fiado_id)).reduce((s, x) => s + x.monto, 0)
}

export function simularSaldo({ monto = PEDIDO_BASE, partes = 1, cobrarFiados = false, fiadoIds = null, escenario } = {}) {
  const e = escenario ?? getDemoSettings().escenario
  let saldo = saldoBase(e) + (PEDIDO_BASE - monto)
  if (partes >= 2) saldo += monto / 2
  if (cobrarFiados) saldo += montoFiados(e, fiadoIds)
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
  const { fallback } = getDemoSettings()
  const escenario = esc(getDemoSettings().escenario)
  const sano = escenario === 'sano'
  const key = `${method} ${path.replace(/\/empresas\/[^/]+/, '/empresas/:id').replace(/\/(fiados|alertas)\/[A-Z]+-\d+/, '/$1/:id')}`

  switch (key) {
    case 'GET /health':
      return ok({ estado: 'ok', version_api: '1.0.0', componentes: { base_datos: 'ok', llm: { estado: fallback ? 'caido' : 'ok' } } })

    case 'GET /empresas/:id/resumen': {
      const r = structuredClone(D.resumenDe(escenario))
      r.indicadores.saldo_caja_negocio.valor = saldos[escenario]
      if (cuentasAnuladas[escenario].size > 0) {
        const f = fiadosActivos(escenario)
        const p = pedidosActivos(escenario)
        r.indicadores.pendiente_cobro = { valor: f.total_pendiente, n_fiados: f.items.length }
        r.indicadores.pagos_pendientes = {
          valor: p.total_pendiente + (p.impuestos?.monto_estimado ?? 0),
          n_obligaciones: p.items.length + (p.impuestos ? 1 : 0),
        }
      }
      return ok({ ...r, periodo: query.periodo || r.periodo })
    }

    case 'GET /empresas/:id/forecast':
      return ok(D.forecastDe(escenario))

    case 'POST /empresas/:id/forecast/ajustes':
      return ok({ ajuste_id: 'AJU-0003', forecast_recalculado: true }, 201)

    case 'GET /empresas/:id/fiados':
      return ok(fiadosActivos(escenario))

    case 'POST /fiados/:id/recordatorio': {
      const f = fiadosActivos(escenario).items.find((x) => path.includes(x.fiado_id))
      if (!f) return err(404, 'NO_ENCONTRADO', 'No encontré ese fiado.')
      return ok({ mensaje: `Hola, ${f.cliente} 😊 Le recuerdo amablemente los S/ ${f.monto} pendientes en la bodega. ¡Gracias!` })
    }

    case 'GET /empresas/:id/pedidos':
      return ok(pedidosActivos(escenario))

    case 'POST /empresas/:id/cuentas/anular': {
      const { tipo, id } = body ?? {}
      if (!['fiado', 'pedido', 'impuesto'].includes(tipo) || !id) {
        return err(422, 'CUENTA_INVALIDA', 'Indica qué cuenta quieres eliminar.')
      }
      const clave = `${tipo}:${id}`
      if (cuentasAnuladas[escenario].has(clave)) return ok({ id, anulada: true })
      const pedidos = pedidosActivos(escenario)
      const cuenta = tipo === 'fiado'
        ? fiadosActivos(escenario).items.find((f) => f.fiado_id === id)
        : tipo === 'pedido'
          ? pedidos.items.find((p) => p.pedido_id === id)
          : pedidos.impuestos?.impuesto_id === id ? pedidos.impuestos : null
      if (!cuenta) return err(404, 'NO_ENCONTRADO', 'No encontré esa cuenta.')
      cuentasAnuladas[escenario].set(clave, { ...cuenta, anulada: true, anulado_en: new Date().toISOString() })
      return ok({ id, anulada: true })
    }

    case 'POST /empresas/:id/pedidos/chequeo': {
      const monto = Number(body?.monto ?? PEDIDO_BASE)
      const saldo = simularSaldo({ monto, escenario })
      const ventaEsperada = sano ? 2600.0 : 2000.0
      const estado = estadoCaja(saldo)
      return ok({
        saldo_proyectado_al_vencimiento: saldo,
        estado_caja: estado,
        venta_esperada_periodo: ventaEsperada,
        exceso_vs_ventas: Math.max(0, monto - ventaEsperada),
        // Si ya te alcanza, no hay nada que sugerir
        sugerencias: estado === 'te_alcanza' ? [] : [
          { accion: 'reducir_pedido', monto_sugerido: 1800.0, saldo_resultante: simularSaldo({ monto: 1800, escenario }) },
          { accion: 'pagar_en_partes', partes: 2, saldo_resultante: simularSaldo({ monto, partes: 2, escenario }) },
          { accion: 'combinar', detalle: 'pedir 1,800 + pagar en 2 partes', saldo_resultante: simularSaldo({ monto: 1800, partes: 2, escenario }) },
        ],
        fundamento: estado === 'te_alcanza'
          ? 'En 2 semanas sueles vender unos S/ 2,600 y ese día te quedaría colchón.'
          : 'En 2 semanas sueles vender unos S/ 2,000 y ese día no tendrás colchón.',
        limites: 'Proyección basada en tus ventas de los últimos 3 meses; no considera eventos que no hayas registrado.',
        confianza: 'media',
        meta: D.meta('forecast-lgbm-quantile', '0.3.1'),
      })
    }

    case 'POST /empresas/:id/simular': {
      const acciones = body?.acciones || []
      let monto = PEDIDO_BASE, partes = 1, cobrarFiados = false, fiadoIds = null
      for (const a of acciones) {
        if (a.tipo === 'reducir_pedido') monto = Number(a.nuevo_monto)
        if (a.tipo === 'pagar_en_partes') partes = Number(a.partes || 2)
        if (a.tipo === 'cobrar_fiados') {
          cobrarFiados = true
          fiadoIds = a.fiado_ids || null
        }
      }
      const base = saldoBase(escenario)
      const con = simularSaldo({ monto, partes, cobrarFiados, fiadoIds, escenario })
      return ok({
        sin_acciones: { saldo_minimo: base, fecha: '2026-11-30', estado_caja: estadoCaja(base) },
        con_acciones: { saldo_minimo: con, fecha: '2026-11-30', estado_caja: estadoCaja(con) },
        mejora: con - base,
        serie_con_acciones: [{ fecha: '2026-11-30', p50: con }],
        fundamento: 'Simulación con tus ventas de los últimos 3 meses.', // EXT
        limites: 'Tú decides; nada se ejecuta solo. Pagar en partes depende de que Andina acepte.', // EXT
        confianza: 'media', // EXT
        meta: D.meta('simulador-deterministico', '0.1.0'),
      })
    }

    case 'GET /empresas/:id/alertas':
      return ok(D.alertasDe(escenario))

    case 'POST /alertas/:id/accion':
      return ok({ estado: 'atendida' })

    case 'GET /empresas/:id/salud':
      return ok(D.saludDe(escenario))

    case 'POST /empresas/:id/metas':
      return ok({ meta_id: 'MET-0005', estado: 'activa' }, 201)

    case 'GET /empresas/:id/movimientos': {
      const todos = [...movimientosNuevos[escenario], ...D.movimientos(escenario)]
      const desde = Number(query.cursor || 0)
      const limit = Number(query.limit || 50)
      const items = todos.slice(desde, desde + limit)
      return ok({ items, next_cursor: desde + limit < todos.length ? String(desde + limit) : null })
    }

    case 'POST /empresas/:id/movimientos':
    case 'POST /empresas/:id/impuestos':
      return ok({ movimiento_id: `MOV-000${++seq}`, registros_creados: [], alertas_disparadas: [], saldo_caja_negocio: saldos[escenario] }, 201)

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
      if (final.tipo === 'venta' && final.metodo_pago !== 'credito') saldos[escenario] += final.monto
      if (final.tipo === 'retiro_personal' || final.tipo === 'pago_impuesto') saldos[escenario] -= final.monto
      const movimiento_id = `MOV-000${++seq}`
      movimientosNuevos[escenario].unshift({
        movimiento_id,
        fecha_hora: final.fecha_hora || new Date().toISOString(),
        tipo: final.tipo,
        categoria: null,
        descripcion: final.items?.length ? final.items.map((it) => `${it.cantidad} ${it.producto}`).join(', ') : null,
        items: final.items || [],
        monto: final.monto,
        moneda: 'PEN',
        metodo_pago: final.metodo_pago,
        contraparte: final.contraparte || null,
        canal: 'voz',
        confianza_extraccion: 0.93,
        afecta_caja: final.metodo_pago !== 'credito',
        saldo_post: saldos[escenario],
      })
      return ok({
        movimiento_id,
        registros_creados: [{ tabla: final.tipo === 'compra' ? 'deudas' : 'transacciones', id: `MOV-000${seq}` }],
        alertas_disparadas: final.tipo === 'compra' ? D.alertasDe(escenario).items : [],
        saldo_caja_negocio: saldos[escenario],
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
      return ok(asistente(body?.mensaje || '', body?.conversacion_id, fallback, escenario))

    default:
      return err(404, 'NO_ENCONTRADO', `Mock sin ruta para ${method} ${path}`)
  }
}

function asistente(mensaje, conversacion_id, fallback, escenario = 'pedro') {
  const m = mensaje.toLowerCase()
  const saldoNegocio = saldos[escenario]
  const teDeben = fiadosActivos(escenario).total_pendiente
  const sano = escenario === 'sano'
  const nuevo = escenario === 'nuevo'
  const saldo3011 = saldoBase(escenario)
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
      respuesta_post: sano
        ? 'Además, con lo que vendes ya llegas al 30/11 sin pedir prestado.'
        : 'Antes, prueba esto: pedir menos, pagar en 2 partes y cobrar fiados. Con eso ya llegas al 30/11.',
      acciones: [{ tipo: 'abrir_simulador', texto: 'Ver mi plan' }, { tipo: 'hablar_humano', texto: 'Hablar con una persona' }], // EXT
      cifras_usadas: [{ valor: 1000, fuente: 'microexplicaciones.prestamo_informal.ejemplo' }],
    }
  }

  if (/c[oó]mo va|mi caja|cu[aá]nto tengo/.test(m) || fallback) {
    const tabla = [ // EXT: cifras crudas para el "Modo básico"
      { etiqueta: 'Caja del negocio', valor: saldoNegocio },
      { etiqueta: 'Te deben (fiados)', valor: teDeben },
      ...(nuevo ? [] : [{ etiqueta: 'Debes (30/11)', valor: 2400 }]),
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
      respuesta: nuevo
        ? `Hoy tienes S/ ${saldoNegocio} en la caja del negocio. Con unos días más de datos te digo cómo vienen tus próximas semanas.`
        : sano
          ? `Hoy tienes S/ ${saldoNegocio} en la caja del negocio. Te deben S/ ${teDeben} en fiados y el 30/11 pagas S/ 2,400 a Andina. Ese día te quedarían unos S/ ${saldo3011}: sí te alcanza.`
          : `Hoy tienes S/ ${saldoNegocio} en la caja del negocio. Te deben S/ ${teDeben} en fiados y el 30/11 pagas S/ 2,400 a Andina. Si no cambias nada, ese día te faltarían S/ 650.`,
      tabla,
      herramientas_llamadas: [{ nombre: 'obtener_resumen', args: { periodo: '2026-11' } }, { nombre: 'obtener_forecast', args: { horizonte_dias: 30 } }],
      cifras_usadas: [{ valor: saldoNegocio, fuente: 'resumen.saldo_caja_negocio' }, ...(nuevo ? [] : [{ valor: sano ? saldo3011 : 650, fuente: sano ? 'forecast.serie.p50' : 'forecast.dia_critico.saldo_p50' }])],
    }
  }

  if (/por qu[eé]|falta|alcanza/.test(m) && sano) {
    return {
      ...base,
      intencion: 'explicar_alerta',
      respuesta: `Sí te alcanza: el 30/11 pagas S/ 2,400 a Distribuidora Andina y ese día te quedarían unos S/ ${saldo3011}, por encima de tu mínimo de S/ 800. Vendes parejo todos los días y tus fiados son pocos (S/ ${teDeben}).`,
      herramientas_llamadas: [{ nombre: 'obtener_forecast', args: { horizonte_dias: 30 } }],
      cifras_usadas: [{ valor: 2400, fuente: 'pedidos.PED-0012.monto' }, { valor: saldo3011, fuente: 'forecast.serie.p50' }],
    }
  }

  if (/por qu[eé]|falta|alcanza/.test(m)) {
    return {
      ...base,
      intencion: 'explicar_alerta',
      ofrecer_humano: true,
      respuesta: `El 30/11 vence tu pago de S/ 2,400 a Distribuidora Andina. Este mes vendiste unos S/ 560 menos que el mes pasado, el pedido es S/ 400 mayor a lo que sueles vender y tienes S/ ${teDeben} en fiados sin cobrar. Si pides S/ 1,800 y pagas en 2 partes, ese día tendrías S/ 850.`,
      herramientas_llamadas: [{ nombre: 'obtener_alertas', args: { estado: 'activa' } }, { nombre: 'simular', args: { acciones: ['reducir_pedido:1800', 'pagar_en_partes:2'] } }],
      cifras_usadas: [{ valor: 2400, fuente: 'pedidos.PED-0012.monto' }, { valor: 850, fuente: 'simular.con_acciones.saldo_minimo' }],
    }
  }

  if (/2 partes|dos partes|si pago/.test(m)) {
    return {
      ...base,
      intencion: 'simular',
      respuesta: `Si pagas a Andina en 2 partes (30/11 y 15/12), ese día te quedarían S/ ${simularSaldo({ partes: 2, escenario })}. Tendrías que pedírselo a Andina.`,
      herramientas_llamadas: [{ nombre: 'simular', args: { acciones: ['pagar_en_partes:2'] } }],
      cifras_usadas: [{ valor: simularSaldo({ partes: 2, escenario }), fuente: 'simular.con_acciones.saldo_minimo' }],
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
