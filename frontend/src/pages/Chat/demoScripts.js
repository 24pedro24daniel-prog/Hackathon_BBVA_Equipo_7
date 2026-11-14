// Guiones para la presentación: /chat?demo=registro|pedido|alertas|fiados reproduce la conversación del mockup.
// Cada paso pasa por el mismo flujo que un toque real (api.* incluido). `pausa` en ms antes del paso.
export const DEMO_SCRIPTS = {
  registro: [{ voz: 'cervezas' }, { texto: 'Fue por billetera', pausa: 2200 }, { voz: 'rus', pausa: 2200 }],
  pedido: [{ texto: 'pedi 2400 a andina para el 30' }, { texto: '30/11', pausa: 2200 }, { texto: 'ver opciones', pausa: 2600 }],
  alertas: [{ texto: 'y si pido un prestamo?', pausa: 1800 }, { texto: 'como va mi caja', pausa: 3200 }],
  fiados: [{ foto: true }, { texto: '95', pausa: 2600 }],
}
