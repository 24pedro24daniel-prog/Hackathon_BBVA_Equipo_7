import { useEffect, useId } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from '../../components/ui/index.jsx'
import { LogoMark } from '../../components/layout/Logo.jsx'
import { despertarServidor } from '../../api/index.js'
import { useTitulo } from '../../lib/useTitulo.js'
import SiteBar from './SiteBar.jsx'
import DotFan from './DotFan.jsx'
import PhoneDemo from './PhoneDemo.jsx'
import './marca.css'
import './Landing.css'

const PASOS = [
  {
    icon: 'mic',
    titulo: 'Anota como hablas',
    texto: 'Manda una nota de voz, escribe o tómale foto a tu cuaderno de fiados. Antes de guardar, confirmas lo que entendimos.',
  },
  {
    icon: 'store',
    titulo: 'Separa la casa del negocio',
    texto: 'Lo que sacas para la casa queda anotado como retiro. Así ves cuánta plata es de verdad de tu bodega.',
  },
  {
    icon: 'chart',
    titulo: 'Mira tu caja a 30 días',
    texto: 'Ves lo que vas a cobrar y lo que tienes que pagar. Si un pago no te va a alcanzar, te avisamos con tiempo y con ideas para cubrirlo.',
  },
]

// Mismo desglose que "¿De dónde sale lo que puedes gastar hoy?" en Inicio, con las cifras ficticias de la demo de Pedro.
const DESGLOSE = [
  ['Tienes', '2 340', ''],
  ['Te pagarán', '190', '+'],
  ['Debes pagar', '2 955', '−'],
  ['Reserva', '820', '−'],
]

export default function Landing() {
  useTitulo('TuCaserito · Sabe hoy si te alcanza para el 30')
  // Render (plan free) duerme el backend: se despierta mientras la persona lee la landing.
  useEffect(() => despertarServidor(), [])
  const idHero = useId()
  const idPasos = useId()
  const idCuenta = useId()

  return (
    <div className="lp">
      <SiteBar
        accion={
          <Link to="/ingresar" className="lp-bar__ingresar">
            Ingresar
          </Link>
        }
      />

      <main>
        <section className="lp-hero" aria-labelledby={idHero}>
          <div className="lp-hero__panel lp-panel">
            <DotFan className="lp-fan" />
            <div className="lp-hero__texto">
              <h1 className="lp-hero__titulo" id={idHero}>
                Sabe hoy si te alcanza para el 30
              </h1>
              <p className="lp-hero__sub">
                Anota ventas, gastos y fiados con una nota de voz. TuCaserito ordena la caja de tu bodega y te avisa antes de que
                te falte para pagar.
              </p>
              <Link to="/ingresar" className="lp-cta">
                Probar la demo
                <Icon name="arrowRight" size={20} />
              </Link>
              <p className="lp-hero__nota">Demo con datos ficticios. Funciona en el navegador, sin instalar nada.</p>
            </div>
            <div className="lp-hero__visual">
              <PhoneDemo />
            </div>
          </div>
        </section>

        <section className="lp-pasos" aria-labelledby={idPasos}>
          <h2 className="lp-h2" id={idPasos}>
            Tres pasos, sin cambiar tu rutina
          </h2>
          <ol className="lp-pasos__lista">
            {PASOS.map((p) => (
              <li key={p.titulo} className="lp-paso">
                <span className="lp-paso__icono" aria-hidden="true">
                  <Icon name={p.icon} size={24} />
                </span>
                <h3 className="lp-paso__titulo">{p.titulo}</h3>
                <p className="lp-paso__texto">{p.texto}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="lp-cuenta" aria-labelledby={idCuenta}>
          <div className="lp-cuenta__texto">
            <h2 className="lp-h2" id={idCuenta}>
              Cada número te dice de dónde sale
            </h2>
            <p className="lp-cuenta__p">
              Si TuCaserito te dice que hoy no gastes, te enseña la cuenta: lo que tienes, lo que te van a pagar y lo que debes.
              Son cálculos aproximados con tus propios datos, y la decisión siempre es tuya.
            </p>
            <Link to="/ingresar" className="lp-cta lp-cta--claro">
              Probar la demo
              <Icon name="arrowRight" size={20} />
            </Link>
          </div>

          <figure className="lp-desglose">
            <figcaption className="lp-desglose__titulo">¿De dónde sale lo que puedes gastar hoy?</figcaption>
            <dl className="lp-desglose__lista">
              {DESGLOSE.map(([label, monto, signo]) => (
                <div key={label} className="lp-desglose__fila">
                  <dt>{label}</dt>
                  <dd className="num">
                    {signo}S/ {monto}
                  </dd>
                </div>
              ))}
              <div className="lp-desglose__fila lp-desglose__total">
                <dt>Puedes gastar hoy</dt>
                <dd className="num">S/ 0</dd>
              </div>
            </dl>
            <p className="lp-desglose__nota">No alcanza, por eso hoy es S/ 0.</p>
            <p className="lp-desglose__fuente">Ejemplo con datos ficticios de la demo.</p>
          </figure>
        </section>
      </main>

      <footer className="lp-pie">
        <div className="lp-pie__in">
          <p className="lp-pie__marca">
            <LogoMark size={28} className="lp-pie__logo" />
            TuCaserito
          </p>
          <p className="lp-pie__legal">
            Prototipo de hackathon con datos ficticios. No es un producto de ningún banco ni ofrece préstamos.
          </p>
          <Link to="/ingresar" className="lp-pie__link">
            Ingresar a la demo
          </Link>
        </div>
      </footer>
    </div>
  )
}
