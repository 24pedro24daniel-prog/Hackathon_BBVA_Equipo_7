/**
 * TuCaserito — Dataset de evaluación de la ingesta (F1): frases y apuntes de cuaderno de Pedro (EMP-0001).
 *
 * Lo importa data/generate_synthetic_data.mjs, que pasa el catálogo REAL de Pedro (productos, clientes y proveedores
 * de data/csv). Cada caso es una frase distinta (sin duplicados ni "(muestra N)") con su verdad esperada:
 *   - origen_monto_esperado = 'catalogo'  -> monto = cantidad x precio del catálogo de Pedro (la frase no dice el monto);
 *   - origen_monto_esperado = 'dicho_por_usuario' -> el monto es el que dice la frase (a veces redondeado hacia arriba);
 *   - origen_monto_esperado = 'estimado' -> la frase no alcanza para fijar el monto.
 * Confianza simulada < 0.75 => requiere_doble_confirmacion (pregunta aclaratoria), como en el backend (UMBRAL_CONFIANZA).
 * Determinístico (seed propia 777).
 */

function mulberry(seed) {
  let a = seed >>> 0;
  return () => {
    let t = (a += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Cómo se dice cada producto del catálogo de Pedro: [singular con artículo, plural sin número, jerga opcional]
const FORMAS = {
  'PRD-0001': ['una bolsa de pan', 'bolsas de pan', 'panes'],
  'PRD-0002': ['un tarro de leche', 'tarros de leche', 'leches'],
  'PRD-0003': ['un kilo de arroz', 'kilos de arroz', null],
  'PRD-0004': ['una botella de aceite', 'botellas de aceite', null],
  'PRD-0005': ['un kilo de azúcar', 'kilos de azúcar', null],
  'PRD-0006': ['un paquete de fideos', 'paquetes de fideos', null],
  'PRD-0007': ['un kilo de huevos', 'kilos de huevos', null],
  'PRD-0008': ['una gaseosa familiar', 'gaseosas familiares', 'gaseosas'],
  'PRD-0009': ['una botella de agua', 'botellas de agua', 'aguas'],
  'PRD-0010': ['una lata de atún', 'latas de atún', null],
  'PRD-0011': ['un detergente', 'detergentes', null],
  'PRD-0012': ['un paquete de papel higiénico', 'paquetes de papel higiénico', null],
  'PRD-0013': ['una barra de jabón', 'barras de jabón', null],
  'PRD-0014': ['un paquete de galletas', 'paquetes de galletas', null],
  'PRD-0016': ['una mantequilla', 'mantequillas', null],
  'PRD-0017': ['un queso fresco', 'quesos frescos', null],
  'PRD-0018': ['una menestra de lenteja', 'menestras de lenteja', null],
  'PRD-0019': ['un jugo', 'jugos', null],
  'PRD-0031': ['una cerveza', 'cervezas', 'chelas'],
};
const PALABRAS = ['', 'un', 'dos', 'tres', 'cuatro', 'cinco', 'seis'];
const fmt = (x) => (Number.isInteger(x) ? String(x) : x.toFixed(2));
const cents = (x) => Math.round(x * 100);

export function generarFrasesEval({ productos, clientes, proveedores }) {
  const R = mulberry(777);
  const pick = (a) => a[Math.floor(R() * a.length)];
  const int = (a, b) => Math.floor(R() * (b - a + 1)) + a;
  const chance = (p) => R() < p;
  const catalogo = productos.filter((p) => FORMAS[p.id]);
  const porId = new Map(productos.map((p) => [p.id, p]));
  const casos = [];
  const vistos = new Set();

  const decir = (prod, cant, jerga = false) => {
    const [uno, varios, slang] = FORMAS[prod.id];
    if (cant === 1) return uno;
    const nombre = jerga && slang ? slang : varios;
    return `${cant <= 6 ? PALABRAS[cant] : cant} ${nombre}`;
  };
  const decirDigito = (prod, cant) => (cant === 1 ? FORMAS[prod.id][0] : `${cant} ${FORMAS[prod.id][1]}`);
  const juntar = (partes) => (partes.length === 1 ? partes[0] : `${partes.slice(0, -1).join(', ')} y ${partes[partes.length - 1]}`);
  const canasta = (nItems) => {
    const sel = [];
    while (sel.length < nItems) {
      const p = pick(catalogo);
      if (!sel.some((s) => s.prod.id === p.id)) sel.push({ prod: p, cant: int(1, p.pv > 6 ? 3 : 5) });
    }
    const totalC = sel.reduce((a, s) => a + s.cant * cents(s.prod.pv), 0);
    return { sel, total: totalC / 100 };
  };
  const itemsEsperados = (sel) => sel.map((s) => ({ producto_id: s.prod.id, cantidad: s.cant }));

  const agregar = (caso) => {
    const clave = caso.frase.trim().toLowerCase();
    if (vistos.has(clave)) return false;
    vistos.add(clave);
    casos.push({
      caso_id: '',
      canal: 'voz',
      frase: '',
      tipo_esperado: null,
      metodo_pago_esperado: null,
      monto_esperado: null,
      producto_id_esperado: null,
      items_esperados: [],
      contraparte_esperada: null,
      origen_monto_esperado: null,
      confianza_simulada: 0.92,
      requiere_doble_confirmacion: false,
      pregunta_aclaratoria: null,
      posible_duplicado: false,
      dentro_alcance: true,
      ...caso,
    });
    return true;
  };
  const repetir = (n, f) => {
    let hechos = 0;
    let guardia = 0;
    while (hechos < n && guardia++ < n * 60) if (f()) hechos++;
  };

  // ── 1. frases de la demo (siempre presentes) ──
  const cerveza = porId.get('PRD-0031');
  const pan = porId.get('PRD-0001');
  const leche = porId.get('PRD-0002');
  agregar({ frase: 'vendí dos cervezas', canal: 'voz', tipo_esperado: 'venta', metodo_pago_esperado: 'efectivo', monto_esperado: 13.0, producto_id_esperado: 'PRD-0031',
    items_esperados: [{ producto_id: 'PRD-0031', cantidad: 2 }], origen_monto_esperado: 'catalogo', confianza_simulada: 0.93 });
  agregar({ frase: 'le fié a la señora Carmen 2 panes y una leche, son 9.50', canal: 'voz', tipo_esperado: 'venta', metodo_pago_esperado: 'credito', monto_esperado: 9.5,
    producto_id_esperado: 'PRD-0001', items_esperados: [{ producto_id: 'PRD-0001', cantidad: 2 }, { producto_id: 'PRD-0002', cantidad: 1 }],
    contraparte_esperada: 'Sra. Carmen', origen_monto_esperado: 'dicho_por_usuario', confianza_simulada: 0.92 });
  agregar({ frase: 'la señora Carmen me pagó 50 en efectivo de su cuenta del cuaderno', canal: 'voz', tipo_esperado: 'cobro_fiado', metodo_pago_esperado: 'efectivo', monto_esperado: 50.0,
    contraparte_esperada: 'Sra. Carmen', origen_monto_esperado: 'dicho_por_usuario', confianza_simulada: 0.94 });
  agregar({ frase: 'saqué 50 para la casa', canal: 'voz', tipo_esperado: 'retiro_personal', metodo_pago_esperado: 'efectivo', monto_esperado: 50.0, origen_monto_esperado: 'dicho_por_usuario', confianza_simulada: 0.95 });
  agregar({ frase: 'pedí 2400 a Andina por campaña navideña para pagar el 30', canal: 'voz', tipo_esperado: 'compra', metodo_pago_esperado: 'credito', monto_esperado: 2400.0,
    contraparte_esperada: 'Distribuidora Andina', origen_monto_esperado: 'dicho_por_usuario', confianza_simulada: 0.9 });
  agregar({ frase: 'le pagué 1200 a Distribuidora Andina en efectivo', canal: 'voz', tipo_esperado: 'pago_proveedor', metodo_pago_esperado: 'efectivo', monto_esperado: 1200.0,
    contraparte_esperada: 'Distribuidora Andina', origen_monto_esperado: 'dicho_por_usuario', confianza_simulada: 0.93 });
  agregar({ frase: 'me prestaron 1000 soles en efectivo, pago 40 diarios', canal: 'voz', tipo_esperado: 'prestamo_recibido', metodo_pago_esperado: 'efectivo', monto_esperado: 1000.0,
    origen_monto_esperado: 'dicho_por_usuario', confianza_simulada: 0.91 });
  agregar({ frase: 'pagué la luz del local en efectivo, 180 soles', canal: 'texto', tipo_esperado: 'gasto_negocio', metodo_pago_esperado: 'efectivo', monto_esperado: 180.0,
    origen_monto_esperado: 'dicho_por_usuario', confianza_simulada: 0.95 });
  agregar({ frase: 'pagué mi RUS en efectivo, 20 soles', canal: 'texto', tipo_esperado: 'pago_impuesto', metodo_pago_esperado: 'efectivo', monto_esperado: 20.0,
    origen_monto_esperado: 'dicho_por_usuario', confianza_simulada: 0.92 });
  agregar({ frase: 'pagué el colegio de mi hijo con mi plata', canal: 'voz', tipo_esperado: null, dentro_alcance: false, requiere_doble_confirmacion: true, confianza_simulada: 0.89,
    pregunta_aclaratoria: 'TuCaserito solo lleva las cuentas de la bodega. ¿Esa plata salió de la caja del negocio para anotarla como retiro personal?' });
  // jerga y ruido de la demo (confianza < 0.75)
  agregar({ frase: 'bendi 3 chelas y pan pero no se escucho el vuelto', canal: 'voz', tipo_esperado: 'venta', metodo_pago_esperado: 'efectivo', monto_esperado: 22.0,
    producto_id_esperado: 'PRD-0031', items_esperados: [{ producto_id: 'PRD-0031', cantidad: 3 }, { producto_id: 'PRD-0001', cantidad: 1 }], origen_monto_esperado: 'estimado',
    confianza_simulada: 0.68, requiere_doble_confirmacion: true, pregunta_aclaratoria: 'Entendí 3 cervezas (S/ 19.50) más pan en efectivo. ¿El total fue S/ 22.00 o cuánto cobraste por el pan?' });

  // ── 2. ventas al contado con el catálogo (la frase no dice el monto) ──
  const verbosVenta = ['vendí', 'me compraron', 'salieron', 'despaché', 'se llevaron', 'acabo de vender', 'anota que vendí', 'hoy vendí'];
  repetir(26, () => {
    const { sel, total } = canasta(int(1, 3));
    const jerga = chance(0.3);
    const frase = `${pick(verbosVenta)} ${juntar(sel.map((s) => decir(s.prod, s.cant, jerga)))}${chance(0.3) ? ' en efectivo' : ''}`;
    return agregar({ frase, canal: chance(0.7) ? 'voz' : 'texto', tipo_esperado: 'venta', metodo_pago_esperado: 'efectivo', monto_esperado: total,
      producto_id_esperado: sel[0].prod.id, items_esperados: itemsEsperados(sel), origen_monto_esperado: 'catalogo', confianza_simulada: 0.88 + int(0, 8) / 100 });
  });
  // ── 3. ventas diciendo el monto ──
  repetir(12, () => {
    const { sel, total } = canasta(int(1, 3));
    const dicho = chance(0.5) ? total : Math.ceil(total);
    const cola = pick([`, fueron ${fmt(dicho)}`, `, me pagaron ${fmt(dicho)}`, `, ${fmt(dicho)} soles en total`, ` por ${fmt(dicho)} soles`]);
    const frase = `${pick(['vendí', 'me compraron', 'despaché'])} ${juntar(sel.map((s) => decirDigito(s.prod, s.cant)))}${cola}`;
    return agregar({ frase, canal: 'voz', tipo_esperado: 'venta', metodo_pago_esperado: 'efectivo', monto_esperado: dicho, producto_id_esperado: sel[0].prod.id,
      items_esperados: itemsEsperados(sel), origen_monto_esperado: 'dicho_por_usuario', confianza_simulada: 0.9 });
  });

  // ── 4. ventas fiadas a los clientes de Pedro ──
  const cli = clientes;
  const nombreVoz = (c) => pick({ 'Sra. Carmen': ['la señora Carmen', 'doña Carmen', 'Carmen'], 'Don Luis': ['don Luis', 'Luis'], 'Vecina Rosa': ['la vecina Rosa', 'Rosa', 'doña Rosa'],
    'Maestro Jorge': ['el maestro Jorge', 'Jorge'], 'Sra. Elena': ['la señora Elena', 'doña Elena'] }[c.nombre] || [c.nombre]);
  repetir(14, () => {
    const c = pick(cli);
    const { sel, total } = canasta(int(1, 3));
    const conMonto = chance(0.5);
    const base = `${pick(['le fié a', 'fíale a', 'anota en el cuaderno de', 'le dejé fiado a'])} ${nombreVoz(c)} ${juntar(sel.map((s) => decir(s.prod, s.cant)))}`;
    const frase = conMonto ? `${base}, son ${fmt(total)}` : base;
    return agregar({ frase, canal: chance(0.8) ? 'voz' : 'texto', tipo_esperado: 'venta', metodo_pago_esperado: 'credito', monto_esperado: total, producto_id_esperado: sel[0].prod.id,
      items_esperados: itemsEsperados(sel), contraparte_esperada: c.nombre, origen_monto_esperado: conMonto ? 'dicho_por_usuario' : 'catalogo', confianza_simulada: 0.9 });
  });
  // ── 5. cobros de fiado (solo clientes con fiados pendientes de Pedro: Carmen 120, Don Luis 95, Vecina Rosa 95) ──
  const pendientes = { 'Sra. Carmen': 120, 'Don Luis': 95, 'Vecina Rosa': 95 };
  repetir(10, () => {
    const nombreC = pick(Object.keys(pendientes));
    const c = cli.find((x) => x.nombre === nombreC);
    const monto = pick([20, 25, 30, 40, 45, 50, 60, 70, 80, 90]);
    if (monto > pendientes[c.nombre]) return false;
    const frase = pick([`${nombreVoz(c)} me pagó ${monto}`, `${nombreVoz(c)} me abonó ${monto} soles de su fiado`, `cobré ${monto} a ${nombreVoz(c)}`, `me canceló ${monto} ${nombreVoz(c)}`]);
    return agregar({ frase, canal: 'voz', tipo_esperado: 'cobro_fiado', metodo_pago_esperado: 'efectivo', monto_esperado: monto, contraparte_esperada: c.nombre, origen_monto_esperado: 'dicho_por_usuario', confianza_simulada: 0.93 });
  });

  // ── 6. compras y pedidos a proveedores ──
  const prv = proveedores;
  repetir(7, () => {
    const monto = pick([150, 200, 250, 300, 350, 380, 420, 480, 520, 600]);
    const frase = pick([`compré mercadería por ${monto} soles`, `traje ${monto} de abarrotes del mayorista`, `compré ${monto} en abarrotes, pagué en efectivo`, `repuse mercadería, ${monto} soles al contado`]);
    return agregar({ frase, canal: chance(0.6) ? 'voz' : 'texto', tipo_esperado: 'compra', metodo_pago_esperado: 'efectivo', monto_esperado: monto, origen_monto_esperado: 'dicho_por_usuario', confianza_simulada: 0.9 });
  });
  repetir(8, () => {
    const p = pick(prv);
    const monto = pick([800, 1000, 1200, 1500, 1800, 2000, 2400, 2800]);
    const dia = pick([20, 25, 28, 30]);
    const frase = pick([`pedí ${monto} a ${p.corto} para pagar el ${dia}`, `le hice un pedido de ${monto} a ${p.corto}, lo pago el ${dia}`, `compré a crédito ${monto} en ${p.corto}, vence el ${dia}`]);
    return agregar({ frase, canal: 'voz', tipo_esperado: 'compra', metodo_pago_esperado: 'credito', monto_esperado: monto, contraparte_esperada: p.nombre, origen_monto_esperado: 'dicho_por_usuario', confianza_simulada: 0.9 });
  });
  repetir(8, () => {
    const p = pick(prv);
    const monto = pick([300, 400, 500, 600, 800, 1000, 1200, 1600]);
    const frase = pick([`le pagué ${monto} a ${p.corto}`, `cancelé ${monto} a ${p.corto} en efectivo`, `abonó ${monto} a ${p.corto} por el pedido`, `a ${p.corto} le di ${monto} soles`]);
    return agregar({ frase, canal: 'voz', tipo_esperado: 'pago_proveedor', metodo_pago_esperado: 'efectivo', monto_esperado: monto, contraparte_esperada: p.nombre, origen_monto_esperado: 'dicho_por_usuario', confianza_simulada: 0.92 });
  });

  // ── 7. préstamos ──
  repetir(5, () => {
    const R1 = pick([500, 600, 800, 1000, 1500, 2000]);
    const cuota = Math.round(R1 * 0.04);
    const frase = pick([`me prestaron ${R1}, devuelvo ${cuota} cada día`, `recibí un préstamo de ${R1} soles, pago ${cuota} diarios`, `un prestamista me dio ${R1} en efectivo y le pago ${cuota} al día`]);
    return agregar({ frase, canal: 'voz', tipo_esperado: 'prestamo_recibido', metodo_pago_esperado: 'efectivo', monto_esperado: R1, origen_monto_esperado: 'dicho_por_usuario', confianza_simulada: 0.9 });
  });
  repetir(5, () => {
    const cuota = pick([20, 30, 36, 40, 48, 60, 80]);
    const frase = pick([`pagué la cuota del préstamo, ${cuota} soles`, `le di ${cuota} al prestamista de hoy`, `cuota diaria del préstamo: ${cuota}`, `pagué ${cuota} de la cuota del préstamo en efectivo`]);
    return agregar({ frase, canal: 'voz', tipo_esperado: 'pago_prestamo', metodo_pago_esperado: 'efectivo', monto_esperado: cuota, origen_monto_esperado: 'dicho_por_usuario', confianza_simulada: 0.9 });
  });

  // ── 8. retiros personales, gastos del negocio e impuestos ──
  repetir(10, () => {
    const monto = pick([20, 30, 40, 60, 80, 100, 120, 150, 200, 250, 300]);
    const motivo = pick(['la casa', 'el almuerzo familiar', 'el pasaje de mis hijos', 'las compras del hogar', 'el colegio', 'mis gastos personales', 'la medicina de mi mamá']);
    const frase = pick([`saqué ${monto} de la caja para ${motivo}`, `agarré ${monto} soles para ${motivo}`, `retiré ${monto} para ${motivo}`, `me llevé ${monto} de la caja para ${motivo}`]);
    return agregar({ frase, canal: chance(0.6) ? 'voz' : 'texto', tipo_esperado: 'retiro_personal', metodo_pago_esperado: 'efectivo', monto_esperado: monto, origen_monto_esperado: 'dicho_por_usuario', confianza_simulada: 0.93 });
  });
  const gastos = [['la luz del local', [150, 180, 195, 210]], ['el agua', [35, 48, 60]], ['el alquiler del local', [350]], ['el flete de la mercadería', [40, 60, 80, 120]],
    ['el gas del local', [58, 62, 65]], ['internet y celular del negocio', [89, 99]], ['bolsas y embalajes', [25, 35, 45]], ['la reparación de la congeladora', [90, 150, 280]]];
  repetir(8, () => {
    const [que, montos] = pick(gastos);
    const monto = pick(montos);
    const frase = pick([`pagué ${que}, ${monto} soles`, `gasté ${monto} en ${que.replace(/^(la|el) /, '')}`, `${que}: ${monto} en efectivo`, `pagué ${monto} por ${que}`]);
    return agregar({ frase, canal: chance(0.5) ? 'voz' : 'texto', tipo_esperado: 'gasto_negocio', metodo_pago_esperado: 'efectivo', monto_esperado: monto, origen_monto_esperado: 'dicho_por_usuario', confianza_simulada: 0.92 });
  });
  repetir(4, () => {
    const monto = pick([20, 20, 50]);
    const mes = pick(['septiembre', 'octubre', 'noviembre', 'agosto']);
    const frase = pick([`pagué mi RUS de ${mes}, ${monto} soles`, `pagué la cuota del Nuevo RUS, ${monto}`, `ya pagué el impuesto RUS de ${mes}: ${monto} soles`, `cancelé la SUNAT, ${monto} soles de RUS`]);
    return agregar({ frase, canal: 'texto', tipo_esperado: 'pago_impuesto', metodo_pago_esperado: 'efectivo', monto_esperado: monto, origen_monto_esperado: 'dicho_por_usuario', confianza_simulada: 0.92 });
  });

  // ── 9. fuera de alcance (gastos del hogar o preguntas ajenas a la caja de la bodega) ──
  const fuera = ['compré zapatillas para mi esposa', 'pagué la mensualidad del gimnasio', 'recargué mi celular personal con 20 soles', 'pagué la clínica de mi hijo', 'pagué la tarjeta de crédito de mi casa',
    'cuánto está el dólar hoy', 'qué hora es', 'compré un televisor para la sala', 'pagué el alquiler de mi casa'];
  for (const frase of fuera) {
    agregar({ frase, canal: chance(0.5) ? 'voz' : 'texto', tipo_esperado: null, dentro_alcance: false, requiere_doble_confirmacion: true, confianza_simulada: 0.7 + int(0, 18) / 100,
      pregunta_aclaratoria: 'TuCaserito solo lleva las cuentas de la bodega. ¿Esa plata salió de la caja del negocio para anotarla como retiro personal?' });
  }

  // ── 10. voz con ruido o jerga (confianza < 0.75: doble confirmación) ──
  const ruidosas = [
    ['bendi 2 serbesas', 'venta', 'efectivo', 13.0, 'PRD-0031', [['PRD-0031', 2]]],
    ['sake 80 pa la casa', 'retiro_personal', 'efectivo', 80.0, null, []],
    ['le fie a la seño carmen una leche y 2 panes', 'venta', 'credito', 9.5, 'PRD-0002', [['PRD-0002', 1], ['PRD-0001', 2]]],
    ['bendí 4 chelas bien heladas', 'venta', 'efectivo', 26.0, 'PRD-0031', [['PRD-0031', 4]]],
    ['pague la luz creo que 180 o 190', 'gasto_negocio', 'efectivo', null, null, []],
    ['me pago don luis cuarenta y algo', 'cobro_fiado', 'efectivo', null, null, []],
    ['pedi a andina mil doscientos para el treinta', 'compra', 'credito', 1200.0, null, []],
    ['vendi unas cosas al fiado a rosa', 'venta', 'credito', null, null, []],
  ];
  for (const [frase, tipo, metodo, monto, prodId, items] of ruidosas) {
    agregar({ frase, canal: 'voz', tipo_esperado: tipo, metodo_pago_esperado: metodo, monto_esperado: monto, producto_id_esperado: prodId,
      items_esperados: items.map(([producto_id, cantidad]) => ({ producto_id, cantidad })), origen_monto_esperado: monto === null ? null : prodId ? 'catalogo' : 'dicho_por_usuario',
      confianza_simulada: 0.5 + int(0, 22) / 100, requiere_doble_confirmacion: true,
      pregunta_aclaratoria: monto === null ? '¿Cuánto fue exactamente? No alcancé a entender el monto.' : `Entendí ${tipo.replace('_', ' ')} por S/ ${fmt(monto)}. ¿Es correcto?` });
  }

  // ── 11. fotos del cuaderno (letra manuscrita; confusión de dígitos 8/3, 5/6, 1/7; posibles duplicados) ──
  const cuaderno = [
    ['[Foto cuaderno] Sra. Carmen - 2 panes, 1 leche - S/ 120 (27/10)', 'venta', 'credito', 120.0, 'Sra. Carmen', 0.81, false, null],
    ['[Foto cuaderno borrosa] Don Luis - arroz, aceite - S/ 95 (parece 35 u 85; ya dictado antes por voz)', 'venta', 'credito', 95.0, 'Don Luis', 0.64, true,
      'El monto manuscrito se ve borroso (¿S/ 95 o S/ 35?) y coincide con un fiado de Don Luis ya dictado por voz. ¿Confirmas si es nuevo?'],
    ['[Foto cuaderno OCR 8 vs 3] Compra abarrotes mayorista S/ 380 (trazo parece 330)', 'compra', 'efectivo', 380.0, null, 0.61, false,
      'En la foto del cuaderno el número puede ser S/ 380 o S/ 330. ¿Cuál es el monto correcto?'],
    ['[Foto cuaderno] Vecina Rosa - gaseosas - S/ 95 (05/11)', 'venta', 'credito', 95.0, 'Vecina Rosa', 0.84, false, null],
    ['[Foto cuaderno] Maestro Jorge - huevos, aceite, azúcar - S/ 52 (05/10)', 'venta', 'credito', 52.0, 'Maestro Jorge', 0.86, false, null],
    ['[Foto cuaderno] Sra. Elena - gaseosas, galletas - S/ 30 (12/10)', 'venta', 'credito', 30.0, 'Sra. Elena', 0.83, false, null],
    ['[Foto cuaderno] Pago Luz del Sur S/ 180 (16/10) - número 180 con trazo dudoso', 'gasto_negocio', 'efectivo', 180.0, null, 0.7, false,
      'El número del recibo parece S/ 180 pero el trazo es dudoso (¿S/ 100?). ¿Cuál es el monto?'],
    ['[Foto cuaderno] Cobré a Sra. Carmen S/ 60 (tachado) y luego S/ 50', 'cobro_fiado', 'efectivo', 50.0, 'Sra. Carmen', 0.66, false,
      'Hay un monto tachado (S/ 60) y otro encima (S/ 50). ¿Cuánto te pagó la Sra. Carmen?'],
  ];
  for (const [frase, tipo, metodo, monto, contraparte, conf, dup, pregunta] of cuaderno) {
    agregar({ frase, canal: 'foto', tipo_esperado: tipo, metodo_pago_esperado: metodo, monto_esperado: monto, contraparte_esperada: contraparte,
      origen_monto_esperado: 'dicho_por_usuario', confianza_simulada: conf, requiere_doble_confirmacion: conf < 0.75, pregunta_aclaratoria: conf < 0.75 ? pregunta : null, posible_duplicado: dup });
  }

  casos.forEach((c, i) => {
    c.caso_id = `EVF-${String(i + 1).padStart(3, '0')}`;
  });
  return casos;
}
