// F7: respuesta del asistente (incluye el ejemplo de préstamo informal y el "Modo básico").
import { Button, Status } from '../../components/ui/index.jsx'
import { soles } from '../../lib/format.js'
import { HowIKnow, InBubble, KVTable, RichText } from './ChatParts.jsx'

// Fuente técnica de una cifra → frase para Pedro. Si no la reconocemos, no se muestra.
const FUENTES = [
  [/^resumen\.saldo_caja/, 'tu caja de hoy'],
  [/^forecast\.dia_critico/, 'lo que calculo para tu día más justo'],
  [/^forecast/, 'lo que calculo que vas a vender'],
  [/^pedidos\./, 'tu pedido'],
  [/^simular/, 'cómo quedaría tu caja con ese cambio'],
  [/prestamo_informal/, 'un ejemplo de préstamo informal'],
  [/^fiados/, 'tus fiados'],
]
function fuenteTexto(fuente = '') {
  return FUENTES.find(([re]) => re.test(fuente))?.[1] || null
}

export function AssistantCard({ msg, onAccion }) {
  const { res, time } = msg
  const fallback = !!res.meta?.fallback_usado
  const ej = res.ejemplo_prestamo_informal
  const acciones = [...(res.acciones || [])]
  if (res.ofrecer_humano && !acciones.some((a) => a.tipo === 'hablar_humano')) {
    acciones.push({ tipo: 'hablar_humano', texto: 'Hablar con una persona' })
  }
  const usadas = (res.cifras_usadas || [])
    .map((c) => {
      const f = fuenteTexto(c.fuente)
      return f ? `${f} (${soles(c.valor)})` : null
    })
    .filter(Boolean)
  const extra = [
    ...(usadas.length ? [['Usé', usadas.join(' · ')]] : []),
    ...(res.verificacion_cifras
      ? [['Cifras', res.verificacion_cifras.ok ? 'Verificadas con tus registros' : 'Algunas no se pudieron verificar']]
      : []),
  ]
  return (
    <InBubble wide time={time} footer={res.disclaimer || 'Orientación educativa · no es asesoría'}>
      {fallback && (
        <p>
          <Status tone="warning">Modo básico</Status>
        </p>
      )}
      <RichText text={res.respuesta} />
      {ej && (
        <div className="chat-ejemplo">
          <p className="chat-ejemplo__k">Ejemplo de préstamo informal</p>
          <KVTable
            label="Ejemplo de préstamo informal"
            rows={[
              ['Recibes', soles(ej.recibes)],
              [`Devuelves en ${ej.dias} días`, soles(ej.devuelves), 'neg'],
              ...(ej.cuota_diaria ? [['Pagas cada día', soles(ej.cuota_diaria)]] : []),
            ]}
          />
          {ej.cuota_diaria && <p className="chat-note">La cuota diaria sale de la venta del día.</p>}
        </div>
      )}
      {res.respuesta_post && <RichText text={res.respuesta_post} />}
      {res.tabla?.length > 0 && (
        <KVTable label="Tus números" rows={res.tabla.map((r) => [r.etiqueta, typeof r.valor === 'number' ? soles(r.valor) : r.valor])} />
      )}
      {acciones.length > 0 && (
        <div className="chat-actions chat-actions--stack">
          {acciones.map((a, i) => (
            <Button key={a.tipo} block variant={i === 0 ? 'primary' : 'ghost'} onClick={() => onAccion(a)}>
              {a.texto}
            </Button>
          ))}
        </div>
      )}
      <HowIKnow extra={extra} meta={res.meta} />
    </InBubble>
  )
}
