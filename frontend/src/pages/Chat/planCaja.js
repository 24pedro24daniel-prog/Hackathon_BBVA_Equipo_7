// "¿Qué hago para llegar a mi próximo pago?" — respuesta armada con los datos reales de api.*
// (forecast, alertas, pedidos, fiados y simulador). Devuelve los datos de la tarjeta `plan`.
import { api } from '../../api/index.js'
import { ddmm, soles } from '../../lib/format.js'

const settle = (p) => p.then((v) => v, () => null)

/** Próximo pago a proveedor pendiente (el que vence primero) */
function proximoPedido(pedidos) {
  const items = (pedidos?.items || []).filter((p) => (p.monto_pendiente ?? p.monto) > 0 && p.fecha_vencimiento)
  // El pago que define el mes: el más grande pendiente (p. ej. Andina), no el más próximo.
  const monto = (p) => p.monto_pendiente ?? p.monto
  return [...items].sort((a, b) => monto(b) - monto(a))[0] || null
}

/** Saldo esperado (p50) en una fecha; si no está en la serie, el más bajo */
function saldoEn(forecast, fecha) {
  const serie = forecast?.serie || []
  const p = (fecha && serie.find((d) => d.fecha === fecha)) || serie.reduce((m, d) => (!m || d.p50 < m.p50 ? d : m), null)
  return p ? { fecha: p.fecha, saldo: p.p50 } : null
}

/** Pregunta que se muestra como mensaje de Pedro */
export function preguntaPlan(fecha) {
  return fecha ? `¿Qué hago para llegar al ${ddmm(fecha)}?` : '¿Qué hago con mi caja este mes?'
}

export async function armarPlanCaja() {
  const [forecast, alertas, pedidos, fiados] = await Promise.all([
    api.getForecast(30),
    settle(api.getAlertas()),
    settle(api.getPedidos()),
    settle(api.getFiados()),
  ])

  if (forecast?.disponible === false || !forecast?.serie?.length) {
    return {
      tone: 'warning',
      titulo: 'Todavía no puedo calcularlo',
      problema: 'Necesito más días con tus ventas y gastos anotados para ver cómo llegas a tus pagos.',
      pasos: [],
      acciones: [],
      fecha: null,
    }
  }

  const minimo = forecast.minimo_operativo
  const critico = forecast.dia_critico
  const pedido = proximoPedido(pedidos)
  const alerta = (alertas?.items || []).find((a) => a.tipo === 'faltante_caja')
  const fecha = alerta?.fecha_evento || pedido?.fecha_vencimiento || critico?.fecha || null
  const pago = pedido ? pedido.monto_pendiente ?? pedido.monto : critico?.obligacion_asociada?.monto
  const proveedor = pedido?.proveedor || critico?.obligacion_asociada?.proveedor || null
  const proveedorCorto = proveedor ? proveedor.replace(/^Distribuidora\s+/i, '') : null
  const enFecha = saldoEn(forecast, fecha)

  const falta =
    alerta?.monto ?? (critico && critico.saldo_p50 < 0 ? -critico.saldo_p50 : enFecha && enFecha.saldo < 0 ? -enFecha.saldo : 0)
  const justo = !falta && minimo != null && enFecha && enFecha.saldo < minimo

  const fiadosItems = (fiados?.items || []).filter((x) => x.monto > 0)
  const fiadosTotal = fiados?.total_pendiente ?? fiadosItems.reduce((s, x) => s + x.monto, 0)
  // Primero los que ya vencieron o están por vencer
  const orden = { vencido: 0, por_vencer: 1 }
  const fiadosOrden = [...fiadosItems].sort((a, b) => (orden[a.estado] ?? 2) - (orden[b.estado] ?? 2))
  const recordar = fiadosOrden.find((x) => x.accion_sugerida?.tipo === 'recordatorio') || null

  // ---------- Caso sano: le alcanza ----------
  if (!falta && !justo) {
    const queda = enFecha?.saldo
    const margen = minimo != null && queda != null ? queda - minimo : null
    const problema =
      pago && fecha
        ? `Te alcanza para pagar **${soles(pago)}**${proveedorCorto ? ` a ${proveedorCorto}` : ''} el ${ddmm(fecha)}.` +
          (queda != null ? ` Ese día te quedarían unos **${soles(queda)}**` : '') +
          (margen != null && margen > 0 ? `, ${soles(margen)} más que tu mínimo.` : queda != null ? '.' : '')
        : `Tu caja se mantiene sobre tu mínimo los próximos ${forecast.serie.length} días.`
    const habitos = []
    if (pedido) {
      const dias = Math.max(1, pedido.dias_para_vencer ?? 15)
      habitos.push({
        texto: `Después de pagar${proveedorCorto ? ` a ${proveedorCorto}` : ''}, aparta unos ${soles(Math.ceil(pago / dias / 5) * 5)} al día para tu siguiente pedido.`,
      })
    } else {
      habitos.push({ texto: 'Aparta un poco de la venta de cada día para tu siguiente pedido.' })
    }
    if (fiadosItems.length) {
      habitos.push({ texto: `Cobra tus fiados a tiempo: hoy te deben ${soles(fiadosTotal)}.`, monto: fiadosTotal })
    } else {
      habitos.push({ texto: 'Sigue anotando lo que vendes y gastas. Así te aviso con tiempo si algo cambia.' })
    }
    return {
      tone: 'ok',
      titulo: 'Vas bien',
      problema,
      pasosTitulo: 'Para seguir así:',
      pasos: habitos,
      acciones: [{ tipo: 'abrir_simulador', texto: 'Probar opciones' }],
      fecha,
    }
  }

  // ---------- Caso con faltante (o por debajo del mínimo) ----------
  const problema = falta
    ? `El ${ddmm(fecha)} te faltarían **${soles(falta)}**` +
      (pago ? ` para pagar ${soles(pago)}${proveedorCorto ? ` a ${proveedorCorto}` : ''}.` : '.')
    : `El ${ddmm(enFecha.fecha)} tu caja bajaría a **${soles(enFecha.saldo)}**, menos que tu mínimo de ${soles(minimo)}.`

  const pasos = []
  const simAcciones = []
  if (fiadosItems.length) {
    // Los 3 más urgentes por nombre; el resto se resume para no amontonar la tarjeta.
    const nombres = fiadosOrden.slice(0, 3).map((x) => `${x.cliente} ${soles(x.monto)}${x.estado === 'vencido' ? ' (ya venció)' : ''}`)
    const resto = fiadosOrden.length - nombres.length
    const lista = resto > 0 ? `${nombres.join(', ')} y ${resto} más` : nombres.join(', ')
    pasos.push({ texto: `Cobra tus fiados: ${lista}.`, monto: fiadosTotal })
    simAcciones.push({ tipo: 'cobrar_fiados' })
  }
  if (pago && proveedorCorto) {
    pasos.push({
      texto: `Pide a ${proveedorCorto} pagar en 2 partes. El ${ddmm(fecha)} pagarías ${soles(pago / 2)} y no ${soles(pago)}.`,
      monto: pago / 2,
    })
    simAcciones.push({ tipo: 'pagar_en_partes', partes: 2 })
  }
  pasos.push({ texto: `No hagas gastos extra hasta el ${ddmm(fecha)}. Así no se agranda lo que te falta.` })

  // Cómo quedaría con esas acciones: primero el simulador; si falla, la suma simple.
  const base = falta ? -falta : enFecha.saldo
  const sim = simAcciones.length ? await settle(api.simular(simAcciones)) : null
  const quedaria = sim?.con_acciones?.saldo_minimo ?? base + pasos.reduce((s, p) => s + (p.monto || 0), 0)
  const n = pasos.filter((p) => p.monto).length
  const cuales = n === 2 ? 'Con 1 y 2' : n === 1 ? 'Con eso' : null
  const resultado =
    cuales && quedaria > base
      ? quedaria >= 0
        ? `${cuales}, el ${ddmm(fecha)} te quedarían unos **${soles(quedaria)}**` +
          (minimo != null && quedaria < minimo ? `, todavía menos que tu mínimo de ${soles(minimo)}.` : '.')
        : `${cuales}, el ${ddmm(fecha)} te faltarían ${soles(-quedaria)} en vez de ${soles(falta)}.`
      : null

  const acciones = []
  if (recordar) acciones.push({ tipo: 'recordar_fiado', texto: `Recordar a ${recordar.cliente}`, fiado: recordar })
  acciones.push({ tipo: 'abrir_simulador', texto: 'Probar opciones' })

  return {
    tone: falta ? 'danger' : 'warning',
    titulo: falta ? `Tu plan para el ${ddmm(fecha)}` : 'Llegas muy justo',
    problema,
    pasosTitulo: 'Lo que puedes hacer:',
    pasos,
    resultado,
    acciones,
    fecha,
  }
}
