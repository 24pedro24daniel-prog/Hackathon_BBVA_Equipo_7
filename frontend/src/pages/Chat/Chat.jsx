// Chat simulado de WhatsApp: superficie principal de registro (F1), alertas (F6) y asistente (F7).
// /chat?demo=registro|pedido|alertas|fiados reproduce la conversación del mockup para la presentación.
// navigate('/chat', { state: { intent: 'plan_caja' } }) abre el chat con el plan para el próximo pago ("Probar qué hacer").
import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import ChatHeader from './ChatHeader.jsx'
import Composer from './Composer.jsx'
import MessageList from './MessageList.jsx'
import { useChat } from './useChat.js'
import './Chat.css'

export default function Chat() {
  const [params] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  // La intención se lee una sola vez al montar; luego se borra del historial para que
  // volver atrás o recargar no la repita.
  const [intent] = useState(() => location.state?.intent || null)
  useEffect(() => {
    if (location.state?.intent) navigate(`${location.pathname}${location.search}`, { replace: true, state: null })
  }, [location, navigate])

  const { messages, typing, busy, flujo, actions } = useChat({ demo: params.get('demo'), intent })
  return (
    <div className="chat-page">
      <ChatHeader flujo={flujo} />
      <MessageList messages={messages} typing={typing} actions={actions} />
      <Composer busy={busy} onText={actions.enviarTexto} onVoice={actions.enviarVoz} onPhoto={actions.enviarFoto} />
    </div>
  )
}
