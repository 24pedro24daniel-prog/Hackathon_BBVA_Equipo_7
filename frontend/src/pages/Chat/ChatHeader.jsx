import { useNavigate } from 'react-router-dom'
import { Icon } from '../../components/ui/index.jsx'

/** Barra blanca: volver circular a la izquierda, título centrado de 17px y línea de contexto apagada (Nu / Monzo). */
export default function ChatHeader({ flujo }) {
  const navigate = useNavigate()
  return (
    <header className="chat-header">
      <button type="button" className="cc-iconbtn" onClick={() => navigate('/')} aria-label="Volver a Inicio">
        <Icon name="back" size={22} />
      </button>
      <div className="chat-header__text">
        <h1 className="chat-header__title">TuCaserito</h1>
        <p className="chat-header__sub">{flujo}</p>
      </div>
      <span aria-hidden="true" />
    </header>
  )
}
