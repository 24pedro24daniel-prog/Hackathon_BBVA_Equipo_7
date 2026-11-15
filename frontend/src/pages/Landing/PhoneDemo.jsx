import { Icon } from '../../components/ui/index.jsx'

// Vista de Inicio de la app dentro de un teléfono, hecha con HTML/CSS. Usa las mismas cifras ficticias que la demo
// de Pedro (mocks: saldo S/ 2 340, pago a Andina de S/ 2 400 el 30/11, faltan S/ 650).

const DESCRIPCION =
  'Ejemplo de la pantalla de inicio de TuCaserito con datos ficticios: saldo del negocio de 2 340 soles, ' +
  'aviso de que hoy no conviene gastar y, en el pago de 2 400 soles a Distribuidora Andina del 30/11, faltan 650 soles. ' +
  'Al lado, una nota de voz que dice «vendí dos cervezas» y la respuesta «Anotado: 2 cervezas, 13 soles, efectivo».'

const Soles = ({ children, signo }) => (
  <span className="ph-money">
    {signo}
    <span className="ph-money__cur">S/</span>
    {children}
  </span>
)

export default function PhoneDemo() {
  return (
    <figure className="ph" role="img" aria-label={DESCRIPCION}>
      <div className="ph__frame" aria-hidden="true">
        <div className="ph__screen">
          <div className="ph__status">
            <span>10:24</span>
            <span className="ph__notch" />
            <span className="ph__signal">
              <i /> <i /> <i />
            </span>
          </div>

          <div className="ph__top">
            <p className="ph__hola">¡Hola!</p>
            <p className="ph__negocio">Bodega Don Pedro</p>
          </div>

          <div className="ph__cuenta">
            <p className="ph__cuenta-label">Saldo del negocio</p>
            <p className="ph__cuenta-saldo">
              <Soles>2 340</Soles>
            </p>
            <div className="ph__cuenta-disp">
              <p className="ph__cuenta-row">Hoy no deberías gastar</p>
              <p className="ph__cuenta-msg">Arriesgas el pago del 30/11.</p>
            </div>
          </div>

          <div className="ph__btn">
            <Icon name="mic" size={15} />
            Registrar transacción
          </div>

          <p className="ph__section">Próximos movimientos</p>
          <div className="ph__card">
            <div className="ph__row">
              <span className="ph__lead">
                <Icon name="receipt" size={14} />
              </span>
              <span className="ph__row-text">
                <span className="ph__row-title">Planilla luz y agua</span>
                <span className="ph__row-sub">16/11 · en 2 días</span>
              </span>
              <Soles signo="−">180</Soles>
            </div>
            <div className="ph__row ph__row--alerta">
              <span className="ph__lead">
                <Icon name="store" size={14} />
              </span>
              <span className="ph__row-text">
                <span className="ph__row-title">Pago a Andina</span>
                <span className="ph__row-sub">30/11 · en 16 días</span>
              </span>
              <Soles signo="−">2 400</Soles>
              <span className="ph__cobertura">
                <span className="ph__cobertura-ok" />
              </span>
              <span className="ph__cobertura-txt">
                <span>Cubres S/ 1 750</span>
                <strong>Faltan S/ 650</strong>
              </span>
              <span className="ph__link">Ver qué puedo hacer</span>
            </div>
          </div>

          <div className="ph__nav">
            <span className="is-active">
              <Icon name="home" size={16} />
            </span>
            <span>
              <Icon name="chart" size={16} />
            </span>
            <span>
              <Icon name="list" size={16} />
            </span>
            <span>
              <Icon name="arrowUp" size={16} />
            </span>
            <span>
              <Icon name="chat" size={16} />
            </span>
          </div>
        </div>
      </div>

      <div className="ph__voz" aria-hidden="true">
        <div className="ph__burbuja ph__burbuja--out">
          <span className="ph__play">
            <Icon name="play" size={12} />
          </span>
          <svg className="ph__onda" viewBox="0 0 64 18" width="64" height="18">
            {[6, 10, 14, 8, 16, 11, 6, 13, 9, 15, 7, 12, 5, 10, 8, 4].map((h, i) => (
              <rect key={i} x={i * 4} y={(18 - h) / 2} width="2" height={h} rx="1" />
            ))}
          </svg>
          <span className="ph__dur">0:04</span>
        </div>
        <div className="ph__burbuja ph__burbuja--in">
          <Icon name="check" size={14} />
          <span>
            Anotado: 2 cervezas, <strong>S/ 13</strong>, efectivo
          </span>
        </div>
      </div>
    </figure>
  )
}
