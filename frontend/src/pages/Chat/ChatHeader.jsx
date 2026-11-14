import { useNavigate } from 'react-router-dom'
import { Icon } from '../../components/ui/index.jsx'

export default function ChatHeader({ flujo }) {
  const navigate = useNavigate()
  return (
    <header className="chat-header">
      <button type="button" className="chat-iconbtn chat-iconbtn--plain" onClick={() => navigate('/')} aria-label="Volver a Inicio">
        <Icon name="back" size={24} />
      </button>
      <span className="chat-avatar" aria-hidden="true">
        CC
      </span>
      <div className="chat-header__text">
        <h1 className="chat-header__title">CajaClara</h1>
        <p className="chat-header__sub">{flujo} · chat simulado</p>
      </div>
    </header>
  )
}
