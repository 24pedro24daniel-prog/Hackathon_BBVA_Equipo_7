// Guiones para la presentación: /chat?demo=registro|pedido|alertas|fiados reproduce la conversación del mockup.
// Cada paso pasa por el mismo flujo que un mensaje o toque real (api.* incluido). `pausa` en ms antes del paso.
// `tap` toca un botón de la última tarjeta de tipo `kind` (p. ej. "Ver opciones").
export const DEMO_SCRIPTS = {
  registro: [{ voz: 'cervezas' }, { texto: 'fue por billetera', pausa: 2200 }, { texto: 'sí', pausa: 2000 }, { voz: 'rus', pausa: 2200 }],
  pedido: [
    { texto: 'pedí 2400 a andina para el 30' },
    { texto: 'el 30 de noviembre', pausa: 2200 },
    { tap: 'verOpciones', kind: 'warning', pausa: 2600 },
  ],
  alertas: [{ texto: 'y si pido un préstamo?', pausa: 1800 }, { texto: '¿cómo va mi caja?', pausa: 3200 }],
  fiados: [{ foto: true }, { texto: '95', pausa: 2600 }],
}
