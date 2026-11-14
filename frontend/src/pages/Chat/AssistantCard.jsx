// F7: respuesta del asistente (incluye el ejemplo de préstamo informal y el "Modo básico").
import { Badge, Button } from '../../components/ui/index.jsx'
import { soles } from '../../lib/format.js'
import { HowIKnow, InBubble, KVTable, RichText } from './ChatParts.jsx'

export function AssistantCard({ msg, onAccion }) {
  const { res, time } = msg
  const fallback = !!res.meta?.fallback_usado
  const ej = res.ejemplo_prestamo_informal
  const acciones = [...(res.acciones || [])]
  if (res.ofrecer_humano && !acciones.some((a) => a.tipo === 'hablar_humano')) {
    acciones.push({ tipo: 'hablar_humano', texto: 'Hablar con una persona' })
  }
  const extra = [
    ...(res.cifras_usadas || []).map((c) => [soles(c.valor), `de ${c.fuente}`]),
    ...(res.herramientas_llamadas?.length
      ? [['Consultas que hizo', res.herramientas_llamadas.map((h) => h.nombre.replace(/_/g, ' ')).join(', ')]]
      : []),
    ...(res.verificacion_cifras
      ? [['Cifras', res.verificacion_cifras.ok ? 'Verificadas con tus registros' : 'Algunas no se pudieron verificar']]
      : []),
  ]
  return (
    <InBubble wide time={time} footer={res.disclaimer || 'Orientación educativa · no es asesoría'}>
      {fallback && (
        <p>
          <Badge tone="warning">Modo básico</Badge>
        </p>
      )}
      <RichText text={res.respuesta} />
      {ej && (
        <div className="chat-ejemplo">
          <p className="chat-ejemplo__k">Ejemplo de préstamo informal</p>
          <RichText
            className="chat-ejemplo__v num"
            text={`Recibes **${soles(ej.recibes)}** → devuelves **${soles(ej.devuelves)}** en ${ej.dias} días`}
          />
          {ej.cuota_diaria && <p className="chat-ejemplo__s">{soles(ej.cuota_diaria)} diarios que salen de la venta del día.</p>}
        </div>
      )}
      {res.respuesta_post && <RichText text={res.respuesta_post} />}
      {res.tabla?.length > 0 && (
        <KVTable label="Tus números" rows={res.tabla.map((r) => [r.etiqueta, typeof r.valor === 'number' ? soles(r.valor) : r.valor])} />
      )}
      {acciones.length > 0 && (
        <div className="chat-actions">
          {acciones.map((a, i) => (
            <Button key={a.tipo} variant={i === 0 ? 'primary' : 'secondary'} onClick={() => onAccion(a)}>
              {a.texto}
            </Button>
          ))}
        </div>
      )}
      <HowIKnow extra={extra} meta={res.meta} />
    </InBubble>
  )
}
