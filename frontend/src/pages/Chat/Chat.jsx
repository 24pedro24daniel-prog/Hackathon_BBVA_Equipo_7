// Chat simulado de WhatsApp: superficie principal de registro (F1), alertas (F6) y asistente (F7).
// /chat?demo=registro|pedido|alertas|fiados reproduce la conversación del mockup para la presentación.
import { useSearchParams } from 'react-router-dom'
import ChatHeader from './ChatHeader.jsx'
import Composer from './Composer.jsx'
import MessageList from './MessageList.jsx'
import { useChat } from './useChat.js'
import './Chat.css'

export default function Chat() {
  const [params] = useSearchParams()
  const { messages, typing, busy, flujo, actions } = useChat({ demo: params.get('demo') })
  return (
    <div className="chat-page">
      <ChatHeader flujo={flujo} />
      <MessageList messages={messages} typing={typing} actions={actions} />
      <Composer busy={busy} onText={actions.enviarTexto} onVoice={actions.enviarVoz} onPhoto={actions.enviarFoto} />
    </div>
  )
}
