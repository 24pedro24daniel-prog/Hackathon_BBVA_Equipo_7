/**
 * TuCaserito — Generador Determinístico de Datos Sintéticos Calibrado (MVP Bodegueros RUC 10 — 100% Efectivo)
 * Genera las 25 tablas del modelo_datos.dbml en archivos CSV (data/csv/*.csv)
 * y el dataset de evaluación de ingesta F1 (data/eval/frases_ingesta_eval.json y .csv).
 *
 * Reglas estrictas aplicadas:
 *   1. Semilla fija: seed = 42 (100% reproducible, cero PII real).
 *   2. Público objetivo único: 30 bodegas de barrio con Persona Natural con Negocio (RUC 10),
 *      rubro_id = 'RUB-01', tiene_ruc = true, regimen_tributario = 'nuevo_rus'.
 *   3. Operación 100% en Efectivo: metodo_pago solo 'efectivo' o 'credito'; billeteras_digitales.csv vacío (0 filas, solo headers).
 *   4. Canales 100% manuales ('voz', 'texto', 'foto') con doble confirmación (confianza < 0.75 -> pregunta_aclaratoria)
 *      y casos explícitos de posibles duplicados (voz + foto del cuaderno).
 *   5. Sueldo bajo criterio bancario ("mínimo para vivir", ej. S/ 1,350/mes para Pedro) + retiros personales variables/extra.
 *   6. Estacionalidad de Campaña Navideña (sobrecompra de stock en noviembre y alza +40-45% en diciembre) y
 *      caso "paga Nuevo RUS, pero lo informa mal" (ventas/compras > S/ 5,000 en campaña pagando S/ 20 en vez de S/ 50).
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const CSV_DIR = path.join(__dirname, 'csv');
const EVAL_DIR = path.join(__dirname, 'eval');

fs.mkdirSync(CSV_DIR, { recursive: true });
fs.mkdirSync(EVAL_DIR, { recursive: true });

// PRNG determinístico (Mulberry32) con seed = 42
function createRng(seed = 42) {
  let a = seed >>> 0;
  return function rng() {
    let t = (a += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const rng = createRng(42);
const randInt = (min, max) => Math.floor(rng() * (max - min + 1)) + min;
const randFloat = (min, max, dec = 2) => Number((min + rng() * (max - min)).toFixed(dec));
const padId = (prefix, num, width = 4) => `${prefix}-${String(num).padStart(width, '0')}`;
const fmtMoney = (val) => Number(val).toFixed(2);
const fmtProb = (val) => Number(val).toFixed(3);

function addDays(dateStr, days) {
  const d = new Date(`${dateStr}T12:00:00-05:00`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function daysBetween(startStr, endStr) {
  const s = new Date(`${startStr}T12:00:00-05:00`);
  const e = new Date(`${endStr}T12:00:00-05:00`);
  return Math.round((e - s) / 86400000);
}

function dayOfWeek(dateStr) {
  const d = new Date(`${dateStr}T12:00:00-05:00`);
  const jsDay = d.getUTCDay(); // 0=Dom .. 6=Sab
  return jsDay === 0 ? 7 : jsDay; // 1=Lun .. 7=Dom
}

// Contenedores de las 25 tablas
const tables = {
  rubros: [],
  empresas: [],
  preferencias_alertas: [],
  categorias: [],
  productos: [],
  clientes: [],
  proveedores: [],
  conversaciones: [],
  borradores: [],
  movimientos_programados: [],
  cuaderno_fiado: [],
  deudas: [],
  billeteras_digitales: [], // Vacío en el MVP (0 filas, solo encabezados; roadmap)
  impuestos: [],
  transacciones: [],
  detalle_transaccion: [],
  reglas_meta: [],
  forecast_ajustes: [],
  alertas: [],
  consentimientos: [],
  saldo_diario: [],
  eventos: [],
  predicciones_saldo: [],
  predicciones_fiado: [],
  score_salud: [],
};

// Columnas explícitas para tablas que pueden quedar con 0 filas en el MVP (billeteras_digitales)
const TABLE_HEADERS = {
  billeteras_digitales: [
    'billetera_mov_id',
    'empresa_id',
    'proveedor_billetera',
    'operacion_id',
    'tipo',
    'monto',
    'contraparte_nombre',
    'fecha_hora',
    'origen',
  ],
};

// =============================================================================
// 1. RUBROS Y CATEGORÍAS GLOBALES
// =============================================================================
// En el MVP el público objetivo único es RUB-01 (bodega). Otros rubros quedan en catálogo como soporte de esquema/roadmap.
tables.rubros.push(
  { rubro_id: 'RUB-01', nombre: 'bodega' },
  { rubro_id: 'RUB-02', nombre: 'ferreteria_roadmap' },
  { rubro_id: 'RUB-03', nombre: 'farmacia_roadmap' },
  { rubro_id: 'RUB-04', nombre: 'bazar_roadmap' }
);

tables.categorias.push(
  { categoria_id: 'CAT-01', nombre: 'bebidas', tipo: 'ingreso', es_del_negocio: true },
  { categoria_id: 'CAT-02', nombre: 'abarrotes', tipo: 'ingreso', es_del_negocio: true },
  { categoria_id: 'CAT-03', nombre: 'lacteos_panaderia', tipo: 'ingreso', es_del_negocio: true },
  { categoria_id: 'CAT-04', nombre: 'limpieza_aseo', tipo: 'ingreso', es_del_negocio: true },
  { categoria_id: 'CAT-05', nombre: 'snacks_golosinas', tipo: 'ingreso', es_del_negocio: true },
  { categoria_id: 'CAT-06', nombre: 'otros_ingresos', tipo: 'ingreso', es_del_negocio: true },
  { categoria_id: 'CAT-07', nombre: 'mercaderia', tipo: 'egreso', es_del_negocio: true },
  { categoria_id: 'CAT-08', nombre: 'servicios', tipo: 'egreso', es_del_negocio: true },
  { categoria_id: 'CAT-09', nombre: 'alquiler_local', tipo: 'egreso', es_del_negocio: true },
  { categoria_id: 'CAT-10', nombre: 'transporte_flete', tipo: 'egreso', es_del_negocio: true },
  { categoria_id: 'CAT-11', nombre: 'impuestos', tipo: 'egreso', es_del_negocio: true },
  { categoria_id: 'CAT-12', nombre: 'financiamiento', tipo: 'egreso', es_del_negocio: true },
  { categoria_id: 'CAT-13', nombre: 'retiro_personal', tipo: 'egreso', es_del_negocio: false }
);

// Generador determinístico de RUC de 11 dígitos para Persona Natural con Negocio (PNN):
// Prefijo '10' + 8 dígitos de DNI ficticio + 1 dígito verificador SUNAT (ej. '10456789012' para EMP-0001)
function generarRuc10(empNum) {
  if (empNum === 1) return '10456789012'; // 10 (PNN) + 45678901 (DNI ficticio de Don Pedro) + 2 (dígito verificador)
  const dni = String(40123400 + empNum * 1371).padStart(8, '0').slice(0, 8);
  const base10 = `10${dni}`;
  const pesos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2];
  const suma = base10.split('').reduce((acc, dig, i) => acc + Number(dig) * pesos[i], 0);
  const dv = (11 - (suma % 11)) % 10;
  return `${base10}${dv}`;
}

// =============================================================================
// 2. EMPRESA 1: BODEGA DON PEDRO (EMP-0001) — HISTORIA EXACTA DE LA DEMO
// =============================================================================
tables.empresas.push({
  empresa_id: 'EMP-0001',
  rubro_id: 'RUB-01',
  nombre_ficticio: 'Bodega Don Pedro',
  telefono_whatsapp: '+51900000001',
  zona: 'Lima Este',
  n_trabajadores: 1,
  tiene_ruc: true,
  ruc: generarRuc10(1),
  regimen_tributario: 'nuevo_rus',
  saldo_inicial: '1800.00',
  fecha_saldo_inicial: '2026-08-15',
  minimo_operativo: '800.00',
  fecha_alta: '2026-08-15T08:00:00-05:00',
});

tables.preferencias_alertas.push({
  empresa_id: 'EMP-0001',
  canales: JSON.stringify(['whatsapp', 'app']),
  max_por_dia: 2,
  silencio_desde: '21:00',
  silencio_hasta: '07:00',
  resumen_semanal: true,
});

// Catálogo de productos de Pedro (incluye PRD-0031 exacto del contrato y 2 productos con costo null para rango de ganancia)
const productosPedro = [
  { id: 'PRD-0001', cat: 'CAT-03', nombre: 'Pan francés (bolsa 10 unid)', alias: ['pan', 'panes', 'bolsa de pan'], pv: 2.50, cu: 1.80 },
  { id: 'PRD-0002', cat: 'CAT-03', nombre: 'Leche evaporada tarro 400g', alias: ['leche', 'tarro de leche', 'leche azul'], pv: 4.50, cu: 3.60 },
  { id: 'PRD-0003', cat: 'CAT-02', nombre: 'Arroz extra 1 kg', alias: ['arroz', 'kilo de arroz'], pv: 4.20, cu: 3.30 },
  { id: 'PRD-0004', cat: 'CAT-02', nombre: 'Aceite vegetal 1 L', alias: ['aceite', 'botella de aceite'], pv: 8.50, cu: 6.80 },
  { id: 'PRD-0005', cat: 'CAT-02', nombre: 'Azúcar rubia 1 kg', alias: ['azucar', 'kilo de azucar'], pv: 3.80, cu: 3.00 },
  { id: 'PRD-0006', cat: 'CAT-02', nombre: 'Fideos tallarín 500g', alias: ['fideos', 'tallarin'], pv: 2.80, cu: 2.10 },
  { id: 'PRD-0007', cat: 'CAT-03', nombre: 'Huevos pardos (1 kg)', alias: ['huevos', 'kilo de huevo'], pv: 9.50, cu: 7.80 },
  { id: 'PRD-0008', cat: 'CAT-01', nombre: 'Gaseosa familiar 1.5 L', alias: ['gaseosa', 'gaseosas'], pv: 7.50, cu: 5.60 },
  { id: 'PRD-0009', cat: 'CAT-01', nombre: 'Agua mineral 625 ml', alias: ['agua', 'botella de agua'], pv: 2.00, cu: 1.20 },
  { id: 'PRD-0010', cat: 'CAT-02', nombre: 'Atún en trozos lata', alias: ['atun', 'lata de atun'], pv: 5.50, cu: 4.20 },
  { id: 'PRD-0011', cat: 'CAT-04', nombre: 'Detergente en polvo 500g', alias: ['detergente'], pv: 6.00, cu: 4.50 },
  { id: 'PRD-0012', cat: 'CAT-04', nombre: 'Papel higiénico paquete x4', alias: ['papel', 'papel higienico'], pv: 5.20, cu: 3.90 },
  { id: 'PRD-0013', cat: 'CAT-04', nombre: 'Jabón de lavar barra', alias: ['jabon', 'barra de jabon'], pv: 3.00, cu: 2.10 },
  { id: 'PRD-0014', cat: 'CAT-05', nombre: 'Galletas paquete x6', alias: ['galleta', 'galletas'], pv: 3.50, cu: 2.50 },
  { id: 'PRD-0015', cat: 'CAT-05', nombre: 'Papas fritas snack', alias: ['papitas', 'snack'], pv: 2.50, cu: null }, // costo null -> ganancia aproximada con rango
  { id: 'PRD-0016', cat: 'CAT-03', nombre: 'Mantequilla pote 200g', alias: ['mantequilla'], pv: 6.80, cu: 5.20 },
  { id: 'PRD-0017', cat: 'CAT-03', nombre: 'Queso fresco 250g', alias: ['queso', 'queso fresco'], pv: 7.00, cu: null }, // costo null
  { id: 'PRD-0018', cat: 'CAT-02', nombre: 'Menestra lenteja 500g', alias: ['lenteja', 'menestra'], pv: 4.00, cu: 3.10 },
  { id: 'PRD-0019', cat: 'CAT-01', nombre: 'Jugo néctar 1 L', alias: ['jugo'], pv: 4.80, cu: 3.60 },
  { id: 'PRD-0020', cat: 'CAT-03', nombre: 'Panetón clásico 900g (Campaña Navideña)', alias: ['paneton', 'panetones'], pv: 22.00, cu: 16.50 },
  { id: 'PRD-0031', cat: 'CAT-01', nombre: 'Cerveza 620 ml', alias: ['chela', 'cerveza grande', 'cerveza', 'cervezas'], pv: 6.50, cu: 4.80 },
];

for (const p of productosPedro) {
  tables.productos.push({
    producto_id: p.id,
    empresa_id: 'EMP-0001',
    categoria_id: p.cat,
    nombre: p.nombre,
    alias: JSON.stringify(p.alias),
    precio_venta: fmtMoney(p.pv),
    costo_unitario: p.cu !== null ? fmtMoney(p.cu) : null,
    activo: true,
  });
}

// Clientes de fiado de Pedro (incluye CLI-0102 Sra. Carmen, CLI-0087 Don Luis, CLI-0110 Vecina Rosa)
const clientesPedro = [
  { id: 'CLI-0102', nombre: 'Sra. Carmen', alias: ['carmen', 'la señora carmen', 'seño carmen'], tel: '+51900000102', perfil: 'moroso', creado: '2026-08-16T09:00:00-05:00' },
  { id: 'CLI-0087', nombre: 'Don Luis', alias: ['luis', 'don luis', 'tio luis'], tel: '+51900000087', perfil: 'ocasional', creado: '2026-08-18T10:30:00-05:00' },
  { id: 'CLI-0110', nombre: 'Vecina Rosa', alias: ['rosa', 'vecina rosa', 'doña rosa'], tel: '+51900000110', perfil: 'puntual', creado: '2026-08-20T11:15:00-05:00' },
  { id: 'CLI-0115', nombre: 'Maestro Jorge', alias: ['jorge', 'maestro jorge'], tel: '+51900000115', perfil: 'puntual', creado: '2026-08-25T16:00:00-05:00' },
  { id: 'CLI-0118', nombre: 'Sra. Elena', alias: ['elena', 'doña elena'], tel: '+51900000118', perfil: 'puntual', creado: '2026-09-02T12:00:00-05:00' },
];

for (const c of clientesPedro) {
  tables.clientes.push({
    cliente_id: c.id,
    empresa_id: 'EMP-0001',
    nombre_ficticio: c.nombre,
    alias: JSON.stringify(c.alias),
    telefono_ficticio: c.tel,
    perfil_pago: c.perfil,
    creado_en: c.creado,
  });
}

// Proveedores de Pedro (incluye PRV-0003 Distribuidora Andina)
const proveedoresPedro = [
  { id: 'PRV-0001', nombre: 'Mayorista Santa Anita', tel: '+51900000201', plazo: 7 },
  { id: 'PRV-0002', nombre: 'Lácteos del Sur', tel: '+51900000202', plazo: 7 },
  { id: 'PRV-0003', nombre: 'Distribuidora Andina', tel: '+51900000203', plazo: 15 },
  { id: 'PRV-0004', nombre: 'Abarrotes El Sol', tel: '+51900000204', plazo: 15 },
];

for (const pr of proveedoresPedro) {
  tables.proveedores.push({
    proveedor_id: pr.id,
    empresa_id: 'EMP-0001',
    nombre_ficticio: pr.nombre,
    telefono_ficticio: pr.tel,
    plazo_pago_dias: pr.plazo,
  });
}

// Movimientos programados de Pedro:
// Sueldo fijo calculado bajo criterio bancario ("mínimo para vivir" = S/ 1,350.00 mensual / S/ 337.50 semanal)
tables.movimientos_programados.push(
  {
    programado_id: 'PRG-0001',
    empresa_id: 'EMP-0001',
    categoria_id: 'CAT-08',
    tipo: 'egreso',
    descripcion: 'luz y agua del local',
    monto: '180.00',
    frecuencia: 'mensual',
    dia_semana: null,
    dia_mes: 16,
    es_sueldo: false,
    fecha_inicio: '2026-08-15',
    fecha_fin: null,
    activo: true,
  },
  {
    programado_id: 'PRG-0002',
    empresa_id: 'EMP-0001',
    categoria_id: 'CAT-09',
    tipo: 'egreso',
    descripcion: 'alquiler del local',
    monto: '350.00',
    frecuencia: 'mensual',
    dia_semana: null,
    dia_mes: 28,
    es_sueldo: false,
    fecha_inicio: '2026-08-15',
    fecha_fin: null,
    activo: true,
  },
  {
    programado_id: 'PRG-0003',
    empresa_id: 'EMP-0001',
    categoria_id: 'CAT-13',
    tipo: 'egreso',
    descripcion: 'sueldo fijo del dueño (criterio bancario mínimo para vivir S/ 1350/mes)',
    monto: '1350.00',
    frecuencia: 'mensual',
    dia_semana: null,
    dia_mes: 30,
    es_sueldo: true,
    fecha_inicio: '2026-08-15',
    fecha_fin: null,
    activo: true,
  }
);

// Conversaciones y Borradores de Pedro (incluye casos con confianza < 0.75, pregunta_aclaratoria y posibles duplicados voz + foto)
tables.conversaciones.push(
  {
    mensaje_id: 'MSG-0500',
    empresa_id: 'EMP-0001',
    conversacion_id: 'CNV-0030',
    rol: 'usuario',
    canal: 'whatsapp',
    texto: 'vendí dos cervezas',
    media_url: 'file://data/audios/demo_001.ogg',
    intencion: 'registro_movimiento',
    herramientas_llamadas: null,
    cifras_verificadas: true,
    fallback_usado: false,
    derivado_a_humano: false,
    prompt_version: 'extractor-v3',
    modelo_version: 'whisper-small + llm-extractor-0.2.0',
    fecha_hora: '2026-11-14T10:42:00-05:00',
  },
  {
    mensaje_id: 'MSG-0501',
    empresa_id: 'EMP-0001',
    conversacion_id: 'CNV-0030',
    rol: 'asistente',
    canal: 'whatsapp',
    texto: 'Anotado: 2 cervezas, S/ 13.00, efectivo ✅ ¿Correcto?',
    media_url: null,
    intencion: 'confirmar_borrador',
    herramientas_llamadas: JSON.stringify([{ nombre: 'buscar_catalogo', args: { query: 'cerveza' } }]),
    cifras_verificadas: true,
    fallback_usado: false,
    derivado_a_humano: false,
    prompt_version: 'extractor-v3',
    modelo_version: '0.2.0',
    fecha_hora: '2026-11-14T10:42:02-05:00',
  },
  {
    mensaje_id: 'MSG-0502',
    empresa_id: 'EMP-0001',
    conversacion_id: 'CNV-0031',
    rol: 'usuario',
    canal: 'whatsapp',
    texto: '¿Por qué me va a faltar plata a fin de mes?',
    media_url: null,
    intencion: 'explicar_alerta',
    herramientas_llamadas: null,
    cifras_verificadas: null,
    fallback_usado: false,
    derivado_a_humano: false,
    prompt_version: 'asistente-v2',
    modelo_version: 'qwen2.5-7b-instruct',
    fecha_hora: '2026-11-14T11:10:00-05:00',
  },
  {
    mensaje_id: 'MSG-0503',
    empresa_id: 'EMP-0001',
    conversacion_id: 'CNV-0031',
    rol: 'asistente',
    canal: 'whatsapp',
    texto: 'El 30/11 vence tu pago de S/ 2 400 a Distribuidora Andina. Este mes sacaste S/ 700 más de lo usual para la casa, el pedido es S/ 400 mayor a lo que sueles vender y tienes S/ 310 en fiados sin cobrar. Si pides S/ 1 800 y pagas en 2 partes, ese día tendrías S/ 850.',
    media_url: null,
    intencion: 'explicar_alerta',
    herramientas_llamadas: JSON.stringify([
      { nombre: 'obtener_alertas', args: { estado: 'activa' } },
      { nombre: 'simular', args: { acciones: ['reducir_pedido:1800', 'pagar_en_partes:2'] } },
    ]),
    cifras_verificadas: true,
    fallback_usado: false,
    derivado_a_humano: false,
    prompt_version: 'asistente-v2',
    modelo_version: 'qwen2.5-7b-instruct',
    fecha_hora: '2026-11-14T11:10:04-05:00',
  }
);

tables.borradores.push(
  // 1) Borrador de voz confirmado (alta confianza)
  {
    borrador_id: 'BOR-7781',
    empresa_id: 'EMP-0001',
    mensaje_id: 'MSG-0500',
    canal: 'voz',
    media_url: 'file://data/audios/demo_001.ogg',
    texto_original: 'vendí dos cervezas',
    payload_propuesto: JSON.stringify({
      tipo: 'venta',
      items: [{ producto_id: 'PRD-0031', producto: 'Cerveza 620 ml', cantidad: 2, precio_unitario: 6.5, subtotal: 13.0 }],
      monto: 13.0,
      moneda: 'PEN',
      metodo_pago: 'efectivo',
      contraparte: null,
      fecha_hora: '2026-11-14T10:42:00-05:00',
      fecha_vencimiento: null,
    }),
    origen_monto: 'catalogo',
    confianza: '0.930',
    campos_faltantes: JSON.stringify([]),
    pregunta_aclaratoria: null,
    correcciones: null,
    estado: 'confirmado',
    modelo_version: '0.2.0',
    prompt_version: 'extractor-v3',
    fallback_usado: false,
    creado_en: '2026-11-14T10:42:01-05:00',
    resuelto_en: '2026-11-14T10:42:10-05:00',
  },
  // 2) Foto del cuaderno con letra borrosa (confianza < 0.75) + posible duplicado con registro dictado antes por voz (FIA-0044)
  {
    borrador_id: 'BOR-7790',
    empresa_id: 'EMP-0001',
    mensaje_id: null,
    canal: 'foto',
    media_url: 'file://data/fotos/cuaderno_01.jpg',
    texto_original: 'Sra. Carmen - 2 panes, 1 leche - S/ 120 (27/10)\nDon Luis - arroz, aceite - S/ 95 (02/11, número 95 borroso parece 35)',
    payload_propuesto: JSON.stringify({
      fiados_propuestos: [
        { cliente: 'Sra. Carmen', detalle: '2 panes, 1 leche', monto: 120.0, fecha: '2026-10-27', confianza: 0.81 },
        { cliente: 'Don Luis', detalle: 'arroz, aceite', monto: 95.0, fecha: '2026-11-02', confianza: 0.64, alternativas_monto: [95.0, 35.0] },
      ],
      posibles_duplicados: [
        {
          propuesto_indice: 1,
          coincide_con: { tipo: 'registro_existente', fiado_id: 'FIA-0044', canal_previo: 'voz' },
          confianza: 0.88,
          motivo: 'Ya anotaste por voz un fiado de Don Luis por arroz y aceite de monto similar.',
        },
      ],
    }),
    origen_monto: 'dicho_por_usuario',
    confianza: '0.640',
    campos_faltantes: JSON.stringify(['confirmacion_monto_borroso', 'revision_duplicado']),
    pregunta_aclaratoria: 'En el apunte de Don Luis el número se ve borroso: ¿es S/ 95 o S/ 35? Además se parece a un fiado que ya dictaste por voz (FIA-0044), ¿igual lo guardamos?',
    correcciones: null,
    estado: 'pendiente',
    modelo_version: '0.1.0',
    prompt_version: 'cuaderno-v1',
    fallback_usado: false,
    creado_en: '2026-11-14T09:15:00-05:00',
    resuelto_en: null,
  },
  // 3) Audio con jerga y ruido fonético ("bendi 3 chelas") -> confianza < 0.75 y repregunta de doble confirmación
  {
    borrador_id: 'BOR-7791',
    empresa_id: 'EMP-0001',
    mensaje_id: null,
    canal: 'voz',
    media_url: 'file://data/audios/demo_ruido_002.ogg',
    texto_original: 'bendi 3 chelas y pan pero no se escucho el vuelto',
    payload_propuesto: JSON.stringify({
      tipo: 'venta',
      items: [{ producto_id: 'PRD-0031', producto: 'Cerveza 620 ml', cantidad: 3, precio_unitario: 6.5, subtotal: 19.5 }],
      monto: 22.0,
      moneda: 'PEN',
      metodo_pago: 'efectivo',
    }),
    origen_monto: 'estimado',
    confianza: '0.680',
    campos_faltantes: JSON.stringify(['monto_exacto_pan']),
    pregunta_aclaratoria: 'Entendí 3 cervezas (S/ 19.50) más pan en efectivo. ¿El total fue S/ 22.00 o cuánto cobraste por el pan?',
    correcciones: JSON.stringify({ monto: 22.0 }),
    estado: 'confirmado',
    modelo_version: '0.2.0',
    prompt_version: 'extractor-v3',
    fallback_usado: false,
    creado_en: '2026-11-10T14:20:00-05:00',
    resuelto_en: '2026-11-10T14:21:00-05:00',
  },
  // 4) Foto manuscrita con confusión OCR 8 <-> 3 (confianza 0.610 < 0.75)
  {
    borrador_id: 'BOR-7792',
    empresa_id: 'EMP-0001',
    mensaje_id: null,
    canal: 'foto',
    media_url: 'file://data/fotos/apunte_compra_02.jpg',
    texto_original: 'Compra mercaderia abarrotes S/ 380 (OCR leyó 330 por trazo manuscrito)',
    payload_propuesto: JSON.stringify({
      tipo: 'compra',
      monto: 330.0,
      alternativas_monto: [380.0, 330.0],
      moneda: 'PEN',
      metodo_pago: 'efectivo',
    }),
    origen_monto: 'dicho_por_usuario',
    confianza: '0.610',
    campos_faltantes: JSON.stringify(['confirmacion_digito_ocr']),
    pregunta_aclaratoria: 'La cifra escrita a mano parece S/ 330 o S/ 380. ¿Cuál de los dos montos pagaste en efectivo?',
    correcciones: JSON.stringify({ monto: 380.0 }),
    estado: 'confirmado',
    modelo_version: '0.1.0',
    prompt_version: 'cuaderno-v1',
    fallback_usado: false,
    creado_en: '2026-11-08T11:10:00-05:00',
    resuelto_en: '2026-11-08T11:12:00-05:00',
  }
);

// Fiados de Pedro: 10 históricos pagados (8 a tiempo = 80%, 2 con atraso) + 3 pendientes (FIA-0045, FIA-0046, FIA-0047 = S/ 310)
const fiadosPedroHist = [
  { id: 'FIA-0035', cli: 'CLI-0110', detalle: 'arroz, azúcar, leche', monto: 48.00, f_fiado: '2026-08-22', f_comp: '2026-08-30', f_pago: '2026-08-29', canal: 'voz', tardio: false },
  { id: 'FIA-0036', cli: 'CLI-0115', detalle: 'gaseosa, pan, queso', monto: 35.00, f_fiado: '2026-08-28', f_comp: '2026-09-05', f_pago: '2026-09-04', canal: 'texto', tardio: false },
  { id: 'FIA-0037', cli: 'CLI-0102', detalle: 'aceite, huevos, fideos', monto: 62.00, f_fiado: '2026-09-03', f_comp: '2026-09-10', f_pago: '2026-09-19', canal: 'foto', tardio: true },
  { id: 'FIA-0038', cli: 'CLI-0118', detalle: 'detergente, papel, jabón', monto: 42.00, f_fiado: '2026-09-10', f_comp: '2026-09-20', f_pago: '2026-09-18', canal: 'voz', tardio: false },
  { id: 'FIA-0039', cli: 'CLI-0087', detalle: 'cervezas, snacks', monto: 55.00, f_fiado: '2026-09-15', f_comp: '2026-09-25', f_pago: '2026-09-24', canal: 'voz', tardio: false },
  { id: 'FIA-0040', cli: 'CLI-0110', detalle: 'leche, mantequilla, pan', monto: 38.00, f_fiado: '2026-09-22', f_comp: '2026-10-02', f_pago: '2026-09-30', canal: 'texto', tardio: false },
  { id: 'FIA-0041', cli: 'CLI-0102', detalle: 'arroz, atún, menestra', monto: 75.00, f_fiado: '2026-09-28', f_comp: '2026-10-06', f_pago: '2026-10-16', canal: 'foto', tardio: true },
  { id: 'FIA-0042', cli: 'CLI-0115', detalle: 'huevos, aceite, azúcar', monto: 52.00, f_fiado: '2026-10-05', f_comp: '2026-10-15', f_pago: '2026-10-13', canal: 'voz', tardio: false },
  { id: 'FIA-0043', cli: 'CLI-0118', detalle: 'gaseosas, galletas', monto: 30.00, f_fiado: '2026-10-12', f_comp: '2026-10-22', f_pago: '2026-10-20', canal: 'voz', tardio: false },
  { id: 'FIA-0044', cli: 'CLI-0087', detalle: 'arroz, aceite', monto: 90.00, f_fiado: '2026-10-18', f_comp: '2026-10-28', f_pago: '2026-10-27', canal: 'voz', tardio: false },
];

const fiadosPedroPend = [
  { id: 'FIA-0045', cli: 'CLI-0102', detalle: '2 panes, 1 leche', monto: 120.00, f_fiado: '2026-10-27', f_comp: '2026-11-05', f_pago: null, canal: 'foto', tardio: true },
  { id: 'FIA-0046', cli: 'CLI-0087', detalle: 'arroz, aceite', monto: 95.00, f_fiado: '2026-11-02', f_comp: '2026-11-12', f_pago: null, canal: 'foto', tardio: true },
  { id: 'FIA-0047', cli: 'CLI-0110', detalle: 'gaseosas', monto: 95.00, f_fiado: '2026-11-05', f_comp: '2026-11-20', f_pago: null, canal: 'voz', tardio: null },
];

for (const f of [...fiadosPedroHist, ...fiadosPedroPend]) {
  tables.cuaderno_fiado.push({
    fiado_id: f.id,
    empresa_id: 'EMP-0001',
    cliente_id: f.cli,
    borrador_id: null,
    detalle: f.detalle,
    monto: fmtMoney(f.monto),
    fecha_fiado: f.f_fiado,
    fecha_compromiso: f.f_comp,
    fecha_pago_total: f.f_pago,
    canal: f.canal,
    pago_tardio: f.tardio,
  });
}

// Deudas de Pedro: 2 pedidos anteriores pagados + PED-0012 vigente (S/ 2,400 a Distribuidora Andina al 30/11 por sobrecompra pre-campaña navideña)
const deudasPedro = [
  {
    id: 'PED-0010',
    tipo: 'proveedor',
    prv: 'PRV-0003',
    acreedor: null,
    recibido: 1600.00,
    total: 1600.00,
    frec: null,
    cuota: null,
    f_ini: '2026-09-10',
    f_venc: '2026-09-25',
    f_pago: '2026-09-24',
    canal: 'voz',
    notas: 'Pedido quincenal septiembre pagado a tiempo',
  },
  {
    id: 'PED-0011',
    tipo: 'proveedor',
    prv: 'PRV-0004',
    acreedor: null,
    recibido: 1750.00,
    total: 1750.00,
    frec: null,
    cuota: null,
    f_ini: '2026-10-12',
    f_venc: '2026-10-27',
    f_pago: '2026-10-26',
    canal: 'voz',
    notas: 'Pedido quincenal octubre pagado a tiempo',
  },
  {
    id: 'PED-0012',
    tipo: 'proveedor',
    prv: 'PRV-0003',
    acreedor: null,
    recibido: 2400.00,
    total: 2400.00,
    frec: null,
    cuota: null,
    f_ini: '2026-11-13',
    f_venc: '2026-11-30',
    f_pago: null,
    canal: 'voz',
    notas: 'Sobrecompra pre-Campaña Navideña a Distribuidora Andina (panetones, bebidas y abarrotes)',
  },
];

for (const d of deudasPedro) {
  tables.deudas.push({
    deuda_id: d.id,
    empresa_id: 'EMP-0001',
    tipo: d.tipo,
    proveedor_id: d.prv,
    acreedor_nombre: d.acreedor,
    borrador_id: null,
    monto_recibido: fmtMoney(d.recibido),
    monto_total_a_pagar: fmtMoney(d.total),
    frecuencia_cuota: d.frec,
    monto_cuota: d.cuota ? fmtMoney(d.cuota) : null,
    fecha_inicio: d.f_ini,
    fecha_vencimiento: d.f_venc,
    fecha_pago_total: d.f_pago,
    canal: d.canal,
    notas: d.notas,
  });
}

// Impuestos de Pedro (Nuevo RUS):
// Caso "paga impuesto, pero lo informa mal": aunque sus ventas/compras superan S/ 5,000 en campaña (le correspondería Cat. 2 = S/ 50.00),
// Pedro sigue declarando y pagando S/ 20.00 (Cat. 1) por desconocimiento tributario.
const impuestosPedro = [
  { id: 'IMP-0007', per: '2026-08', monto: 20.00, venc: '2026-09-15', pago: '2026-09-14', canal: 'texto' },
  { id: 'IMP-0008', per: '2026-09', monto: 20.00, venc: '2026-10-16', pago: '2026-10-15', canal: 'texto' },
  { id: 'IMP-0009', per: '2026-10', monto: 20.00, venc: '2026-11-16', pago: '2026-11-12', canal: 'texto' },
  { id: 'IMP-0010', per: '2026-11', monto: 20.00, venc: '2026-12-15', pago: null, canal: 'texto' },
];

for (const imp of impuestosPedro) {
  tables.impuestos.push({
    impuesto_id: imp.id,
    empresa_id: 'EMP-0001',
    regimen: 'nuevo_rus',
    periodo: imp.per,
    monto: fmtMoney(imp.monto),
    fecha_vencimiento: imp.venc,
    fecha_pago: imp.pago,
    canal: imp.canal,
  });
}

// =============================================================================
// TRANSACCIONES DE PEDRO (EMP-0001): 100% EFECTIVO Y CRÉDITO — CUADRE EXACTO
// - Saldo inicial (2026-08-15): 1,800.00
// - Neto Ago 15 – Oct 31 (afecta_caja=true): -690.00 -> Saldo al 2026-10-31 = 1,110.00
//   * Oct 01 – Oct 14: Ingresos caja = 9,104.48 | Egresos caja = 6,975.19 (Retiros = 1,200.00, Mercadería = 4,430.60)
// - Nov 01 – Nov 14 (afecta_caja=true):
//   * Ingresos caja = 8,540.00 (variación -6.2% vs Oct 1-14)
//   * Egresos caja = 7,310.00 (variación +4.8% vs Oct 1-14)
//     - Mercadería (compra contado): 4,980.00 (68.1% de 7,310, +12.4% vs Oct 1-14)
//     - Retiros personales: 1,900.00 (sueldo proporcional "mínimo para vivir" + retiros extra que descapitalizan la caja)
//     - Gastos negocio: 410.00
//     - Pago impuesto RUS (IMP-0009, mal informado en S/ 20 pese a superar tramo S/ 5,000): 20.00
// - Saldo cierre 2026-11-14: 1,110.00 + 8,540.00 - 7,310.00 = 2,340.00 EXACTO.
// =============================================================================

let movSeq = 1;
let detSeq = 1;
const nextMovId = () => padId('MOV', movSeq++, 6);
const nextDetId = () => padId('DET', detSeq++, 6);

function addTx({
  id = null,
  empresa_id,
  borrador_id = null,
  fecha_hora,
  tipo,
  categoria_id,
  descripcion,
  monto,
  metodo_pago = 'efectivo',
  canal = 'voz',
  confianza = 0.92,
  fue_corregida = false,
  fiado_id = null,
  deuda_id = null,
  impuesto_id = null,
  programado_id = null,
  billetera_mov_id = null,
  creado_en = null,
  producto = null,
  cantidad = 1,
}) {
  const txId = id || nextMovId();
  const afecta_caja = metodo_pago !== 'credito';
  const conf = fmtProb(confianza);
  tables.transacciones.push({
    transaccion_id: txId,
    empresa_id,
    borrador_id,
    fecha_hora,
    tipo,
    categoria_id,
    descripcion,
    monto: fmtMoney(monto),
    moneda: 'PEN',
    metodo_pago,
    afecta_caja,
    canal,
    confianza_extraccion: conf,
    fue_corregida,
    fiado_id,
    deuda_id,
    impuesto_id,
    programado_id,
    billetera_mov_id,
    anulada: false,
    creado_en: creado_en || fecha_hora,
  });

  if (producto) {
    tables.detalle_transaccion.push({
      detalle_id: nextDetId(),
      transaccion_id: txId,
      producto_id: producto.id,
      descripcion: producto.nombre,
      cantidad: Number(cantidad).toFixed(3),
      precio_unitario: fmtMoney(producto.pv),
      costo_unitario: producto.cu !== null ? fmtMoney(producto.cu) : null,
      subtotal: fmtMoney(monto),
    });
  }
  return txId;
}

// 2.1 Transacciones que NO mueven caja (ventas fiadas y pedidos a crédito) de Pedro
for (const f of [...fiadosPedroHist, ...fiadosPedroPend]) {
  addTx({
    empresa_id: 'EMP-0001',
    fecha_hora: `${f.f_fiado}T11:30:00-05:00`,
    tipo: 'venta',
    categoria_id: 'CAT-02',
    descripcion: `Venta fiada en cuaderno: ${f.detalle}`,
    monto: f.monto,
    metodo_pago: 'credito',
    canal: f.canal,
    fiado_id: f.id,
  });
}

for (const d of deudasPedro) {
  addTx({
    empresa_id: 'EMP-0001',
    fecha_hora: `${d.f_ini}T09:00:00-05:00`,
    tipo: 'compra',
    categoria_id: 'CAT-07',
    descripcion: d.notas,
    monto: d.recibido,
    metodo_pago: 'credito',
    canal: d.canal,
    deuda_id: d.id,
  });
}

// 2.2 Flujos de caja en efectivo de Pedro Ago 15 – Sep 30 (47 días)
for (let i = 0; i < 47; i++) {
  const fecha = addDays('2026-08-15', i);
  const ventaDia = i === 46 ? 550.71 : 560.00; // Total ventas contado = 26,310.71
  addTx({
    empresa_id: 'EMP-0001',
    fecha_hora: `${fecha}T19:00:00-05:00`,
    tipo: 'venta',
    categoria_id: i % 2 === 0 ? 'CAT-01' : 'CAT-02',
    descripcion: 'Ventas del día en efectivo (apunte de cuaderno)',
    monto: ventaDia,
    metodo_pago: 'efectivo',
    canal: i % 3 === 0 ? 'foto' : 'voz',
  });

  // Compra diaria reposición en efectivo: 47 * 440 = 20,680.00
  addTx({
    empresa_id: 'EMP-0001',
    fecha_hora: `${fecha}T10:00:00-05:00`,
    tipo: 'compra',
    categoria_id: 'CAT-07',
    descripcion: 'Reposición diaria de mercadería en efectivo',
    monto: 440.00,
    metodo_pago: 'efectivo',
    canal: 'voz',
  });
}

// Cobros de fiados en Ago-Sep (suman 280.00)
for (const f of fiadosPedroHist.slice(0, 6)) {
  addTx({
    empresa_id: 'EMP-0001',
    fecha_hora: `${f.f_pago}T17:00:00-05:00`,
    tipo: 'cobro_fiado',
    categoria_id: 'CAT-02',
    descripcion: `Cobro de fiado ${f.id} en efectivo`,
    monto: f.monto,
    metodo_pago: 'efectivo',
    canal: 'voz',
    fiado_id: f.id,
  });
}

// Pago proveedor PED-0010 (1,600.00), RUS IMP-0007 (20.00), servicios/alquiler (1,160.00) y retiros personales Ago-Sep (4,980.00)
addTx({
  empresa_id: 'EMP-0001',
  fecha_hora: '2026-09-24T11:00:00-05:00',
  tipo: 'pago_proveedor',
  categoria_id: 'CAT-07',
  descripcion: 'Pago en efectivo pedido Distribuidora Andina',
  monto: 1600.00,
  metodo_pago: 'efectivo',
  canal: 'voz',
  deuda_id: 'PED-0010',
});
addTx({
  empresa_id: 'EMP-0001',
  fecha_hora: '2026-09-14T12:00:00-05:00',
  tipo: 'pago_impuesto',
  categoria_id: 'CAT-11',
  descripcion: 'Pago Nuevo RUS agosto (declarado en Cat. 1 S/ 20 pese a superar tramo)',
  monto: 20.00,
  metodo_pago: 'efectivo',
  canal: 'texto',
  impuesto_id: 'IMP-0007',
});
for (const g of [
  { f: '2026-08-28', cat: 'CAT-09', desc: 'Alquiler del local agosto', m: 350.00, prg: 'PRG-0002' },
  { f: '2026-09-16', cat: 'CAT-08', desc: 'Luz y agua del local septiembre', m: 180.00, prg: 'PRG-0001' },
  { f: '2026-09-20', cat: 'CAT-10', desc: 'Flete y transporte mercadería', m: 280.00, prg: null },
  { f: '2026-09-28', cat: 'CAT-09', desc: 'Alquiler del local septiembre', m: 350.00, prg: 'PRG-0002' },
]) {
  addTx({
    empresa_id: 'EMP-0001',
    fecha_hora: `${g.f}T15:00:00-05:00`,
    tipo: 'gasto_negocio',
    categoria_id: g.cat,
    descripcion: g.desc,
    monto: g.m,
    metodo_pago: 'efectivo',
    canal: 'voz',
    programado_id: g.prg,
  });
}
for (let s = 0; s < 6; s++) {
  const f = addDays('2026-08-20', s * 7);
  addTx({
    empresa_id: 'EMP-0001',
    fecha_hora: `${f}T20:00:00-05:00`,
    tipo: 'retiro_personal',
    categoria_id: 'CAT-13',
    descripcion: 'Retiro semanal para gastos mínimos de la casa (sueldo + extras)',
    monto: 830.00, // 6 * 830 = 4,980.00
    metodo_pago: 'efectivo',
    canal: 'voz',
    programado_id: 'PRG-0003',
  });
}

// 2.3 Octubre 2026:
// - Oct 01 – Oct 14: Ingresos = 9,104.48 | Egresos = 6,975.19 (Mercadería = 4,430.60, Retiros = 1,200.00, Servicios/Gastos = 1,344.59)
for (let d = 0; d < 14; d++) {
  const fecha = addDays('2026-10-01', d);
  const ventaContado = d < 13 ? 646.00 : 654.48; // 13*646 + 654.48 = 9,052.48
  addTx({
    empresa_id: 'EMP-0001',
    fecha_hora: `${fecha}T19:00:00-05:00`,
    tipo: 'venta',
    categoria_id: d % 2 === 0 ? 'CAT-02' : 'CAT-01',
    descripcion: 'Ventas del día en efectivo',
    monto: ventaContado,
    metodo_pago: 'efectivo',
    canal: d % 2 === 0 ? 'voz' : 'foto',
  });

  // Compras mercadería Oct 1-14 = 4,430.60
  const compraContado = d < 13 ? 316.00 : 322.60;
  addTx({
    empresa_id: 'EMP-0001',
    fecha_hora: `${fecha}T09:30:00-05:00`,
    tipo: 'compra',
    categoria_id: 'CAT-07',
    descripcion: 'Compra de mercadería al contado en efectivo',
    monto: compraContado,
    metodo_pago: 'efectivo',
    canal: 'voz',
  });
}

// Cobro FIA-0042 el 2026-10-13 (52.00)
addTx({
  empresa_id: 'EMP-0001',
  fecha_hora: '2026-10-13T17:00:00-05:00',
  tipo: 'cobro_fiado',
  categoria_id: 'CAT-02',
  descripcion: 'Cobro de fiado Maestro Jorge en efectivo',
  monto: 52.00,
  metodo_pago: 'efectivo',
  canal: 'voz',
  fiado_id: 'FIA-0042',
});

// Retiros personales Oct 1-14 = 1,200.00 (proporcional del sueldo mínimo para vivir S/ 1,350/mes)
for (const f of ['2026-10-03', '2026-10-08', '2026-10-13']) {
  addTx({
    empresa_id: 'EMP-0001',
    fecha_hora: `${f}T20:00:00-05:00`,
    tipo: 'retiro_personal',
    categoria_id: 'CAT-13',
    descripcion: 'Retiro fijo para mínimo de vida familiar (criterio sueldo bancario)',
    monto: 400.00,
    metodo_pago: 'efectivo',
    canal: 'voz',
    programado_id: 'PRG-0003',
  });
}

// Gastos del negocio Oct 1-14 = 1,344.59
addTx({
  empresa_id: 'EMP-0001',
  fecha_hora: '2026-10-06T14:00:00-05:00',
  tipo: 'gasto_negocio',
  categoria_id: 'CAT-10',
  descripcion: 'Transporte y mantenimiento de congeladora en efectivo',
  monto: 1344.59,
  metodo_pago: 'efectivo',
  canal: 'voz',
});

// Oct 15 – Oct 31 (17 días)
for (let d = 0; d < 17; d++) {
  const fecha = addDays('2026-10-15', d);
  const ventaDia = d < 16 ? 588.00 : 597.00; // 10,005.00
  addTx({
    empresa_id: 'EMP-0001',
    fecha_hora: `${fecha}T19:00:00-05:00`,
    tipo: 'venta',
    categoria_id: d % 2 === 0 ? 'CAT-01' : 'CAT-02',
    descripcion: 'Ventas del día en efectivo',
    monto: ventaDia,
    metodo_pago: 'efectivo',
    canal: 'voz',
  });

  const compraDia = 450.00; // 17 * 450 = 7,650.00
  addTx({
    empresa_id: 'EMP-0001',
    fecha_hora: `${fecha}T10:00:00-05:00`,
    tipo: 'compra',
    categoria_id: 'CAT-07',
    descripcion: 'Compra reposición bodega en efectivo',
    monto: compraDia,
    metodo_pago: 'efectivo',
    canal: 'voz',
  });
}

for (const f of [fiadosPedroHist[6], fiadosPedroHist[8], fiadosPedroHist[9]]) {
  addTx({
    empresa_id: 'EMP-0001',
    fecha_hora: `${f.f_pago}T17:30:00-05:00`,
    tipo: 'cobro_fiado',
    categoria_id: 'CAT-02',
    descripcion: `Cobro de fiado ${f.id} en efectivo`,
    monto: f.monto,
    metodo_pago: 'efectivo',
    canal: 'voz',
    fiado_id: f.id,
  });
}

addTx({
  empresa_id: 'EMP-0001',
  fecha_hora: '2026-10-26T11:00:00-05:00',
  tipo: 'pago_proveedor',
  categoria_id: 'CAT-07',
  descripcion: 'Pago en efectivo a Abarrotes El Sol PED-0011',
  monto: 1750.00,
  metodo_pago: 'efectivo',
  canal: 'voz',
  deuda_id: 'PED-0011',
});
addTx({
  empresa_id: 'EMP-0001',
  fecha_hora: '2026-10-15T12:00:00-05:00',
  tipo: 'pago_impuesto',
  categoria_id: 'CAT-11',
  descripcion: 'Pago Nuevo RUS septiembre (pagó S/ 20 en vez de S/ 50 pese a superar S/ 5,000)',
  monto: 20.00,
  metodo_pago: 'efectivo',
  canal: 'texto',
  impuesto_id: 'IMP-0008',
});
addTx({
  empresa_id: 'EMP-0001',
  fecha_hora: '2026-10-16T15:00:00-05:00',
  tipo: 'gasto_negocio',
  categoria_id: 'CAT-08',
  descripcion: 'Luz y agua del local octubre',
  monto: 180.00,
  metodo_pago: 'efectivo',
  canal: 'voz',
  programado_id: 'PRG-0001',
});
addTx({
  empresa_id: 'EMP-0001',
  fecha_hora: '2026-10-28T15:00:00-05:00',
  tipo: 'gasto_negocio',
  categoria_id: 'CAT-09',
  descripcion: 'Alquiler del local octubre',
  monto: 350.00,
  metodo_pago: 'efectivo',
  canal: 'voz',
  programado_id: 'PRG-0002',
});
for (const [f, m, desc, prg] of [
  ['2026-10-17', 150.00, 'Complemento sueldo fijo mínimo para vivir (cierra S/ 1,350 del mes)', 'PRG-0003'],
  ['2026-10-24', 530.00, 'Retiro personal variable extra de la caja', null],
  ['2026-10-31', 540.00, 'Retiro personal variable extra fin de mes', null],
]) {
  addTx({
    empresa_id: 'EMP-0001',
    fecha_hora: `${f}T20:00:00-05:00`,
    tipo: 'retiro_personal',
    categoria_id: 'CAT-13',
    descripcion: desc,
    monto: m,
    metodo_pago: 'efectivo',
    canal: 'voz',
    programado_id: prg,
  });
}

// 2.4 Noviembre 2026 (2026-11-01 al 2026-11-14):
// Pedro opera 100% en efectivo (y crédito/fiado).
// - Ingresos caja = 8,540.00 (incluye las ventas en efectivo de cada día y MOV-000123 de S/ 13.00)
// - Egresos caja = 7,310.00:
//   * Mercadería (CAT-07): 4,980.00 (sobrecompra previa a campaña navideña)
//   * Retiros personales (CAT-13): 1,900.00 (sueldo mínimo para vivir + S/ 700 de retiros variables extra que descapitalizan la caja)
//   * Gastos negocio (CAT-08/CAT-10): 410.00
//   * Impuesto RUS (CAT-11, IMP-0009): 20.00 (mal informado como Cat. 1 S/ 20 cuando debía pagar Cat. 2 S/ 50 por campaña)
for (let d = 0; d < 14; d++) {
  const fecha = addDays('2026-11-01', d);
  const ventaEfectivo = d < 13 ? 609.00 : 610.00; // 13*609 + 610 = 8,527.00
  const prod = productosPedro[d % (productosPedro.length - 1)];
  addTx({
    empresa_id: 'EMP-0001',
    fecha_hora: `${fecha}T18:30:00-05:00`,
    tipo: 'venta',
    categoria_id: prod.cat,
    descripcion: `Ventas del día en efectivo (${prod.nombre} y otros)`,
    monto: ventaEfectivo,
    metodo_pago: 'efectivo',
    canal: d % 3 === 0 ? 'foto' : 'voz',
    producto: prod,
    cantidad: Number((ventaEfectivo / prod.pv).toFixed(3)),
  });

  // Compras de mercadería al contado en efectivo (suman 4,980.00)
  const compraDia = d < 13 ? 355.00 : 365.00; // 13*355 + 365 = 4,980.00
  addTx({
    empresa_id: 'EMP-0001',
    fecha_hora: `${fecha}T09:15:00-05:00`,
    tipo: 'compra',
    categoria_id: 'CAT-07',
    descripcion: 'Compra de mercadería al contado (adelanto stock campaña navideña)',
    monto: compraDia,
    metodo_pago: 'efectivo',
    canal: d === 7 ? 'foto' : 'voz',
    borrador_id: d === 7 ? 'BOR-7792' : null,
    fue_corregida: d === 7,
  });
}

// MOV-000123: La venta por voz de 2 cervezas (S/ 13.00) confirmada desde BOR-7781 (contrato §1.2–1.3)
addTx({
  id: 'MOV-000123',
  empresa_id: 'EMP-0001',
  borrador_id: 'BOR-7781',
  fecha_hora: '2026-11-14T10:42:00-05:00',
  tipo: 'venta',
  categoria_id: 'CAT-01',
  descripcion: '2 cervezas',
  monto: 13.00,
  metodo_pago: 'efectivo',
  canal: 'voz',
  confianza: 0.930,
  producto: productosPedro.find((p) => p.id === 'PRD-0031'),
  cantidad: 2,
});

// Retiros personales de Pedro en Noviembre (suman 1,900.00: sueldo fijo "mínimo para vivir" + retiros extra que descapitalizan caja)
for (const [f, m, desc, prg] of [
  ['2026-11-02', 450.00, 'Adelanto sueldo fijo mínimo para vivir (criterio bancario S/ 1,350/mes)', 'PRG-0003'],
  ['2026-11-05', 350.00, 'Retiro personal extra no planificado para la casa', null],
  ['2026-11-07', 450.00, 'Segundo tramo sueldo fijo mínimo para vivir (criterio bancario S/ 1,350/mes)', 'PRG-0003'],
  ['2026-11-10', 350.00, 'Retiro personal extra no planificado que descapitaliza la caja', null],
  ['2026-11-13', 300.00, 'Adelanto extra de caja para gastos familiares', 'PRG-0003'],
]) {
  addTx({
    empresa_id: 'EMP-0001',
    fecha_hora: `${f}T20:15:00-05:00`,
    tipo: 'retiro_personal',
    categoria_id: 'CAT-13',
    descripcion: desc,
    monto: m,
    metodo_pago: 'efectivo',
    canal: 'voz',
    programado_id: prg,
  });
}

// Gastos del negocio en Noviembre (suman 410.00) + Pago RUS IMP-0009 (20.00 mal informado)
addTx({
  empresa_id: 'EMP-0001',
  fecha_hora: '2026-11-04T16:00:00-05:00',
  tipo: 'gasto_negocio',
  categoria_id: 'CAT-10',
  descripcion: 'Flete y bolsas para campaña navideña en bodega',
  monto: 210.00,
  metodo_pago: 'efectivo',
  canal: 'voz',
});
addTx({
  empresa_id: 'EMP-0001',
  fecha_hora: '2026-11-11T15:30:00-05:00',
  tipo: 'gasto_negocio',
  categoria_id: 'CAT-08',
  descripcion: 'Recarga de gas y limpieza del local',
  monto: 200.00,
  metodo_pago: 'efectivo',
  canal: 'voz',
});
addTx({
  empresa_id: 'EMP-0001',
  fecha_hora: '2026-11-12T11:20:00-05:00',
  tipo: 'pago_impuesto',
  categoria_id: 'CAT-11',
  descripcion: 'Pago Nuevo RUS 2026-10 (informó y pagó S/ 20 de Cat. 1 en lugar de S/ 50 de Cat. 2 pese a superar S/ 5,000)',
  monto: 20.00,
  metodo_pago: 'efectivo',
  canal: 'texto',
  impuesto_id: 'IMP-0009',
});

movSeq = 200;

// Metas, Ajustes, Alertas, Consentimientos, Eventos, Predicciones y Score de Pedro
tables.reglas_meta.push({
  meta_id: 'MET-0004',
  empresa_id: 'EMP-0001',
  plantilla: 'apartar_para_pedido',
  programado_id: null,
  tipo_regla: 'porcentaje_de_venta',
  valor: '0.1000',
  destino: 'fondo_pedidos',
  objetivo: '1800.00',
  acumulado: '420.00',
  recordatorio_frecuencia: 'semanal',
  recordatorio_dia: 1,
  estado: 'activa',
  fecha_inicio: '2026-10-15',
  fecha_logro: null,
});

tables.forecast_ajustes.push({
  ajuste_id: 'AJU-0003',
  empresa_id: 'EMP-0001',
  programado_id: 'PRG-0002',
  fecha: '2026-11-28',
  concepto: 'alquiler',
  monto: '0.00',
  motivo: 'acuerdo con el dueño del local',
  activo: false,
  creado_en: '2026-11-14T08:00:00-05:00',
});

tables.alertas.push(
  {
    alerta_id: 'ALR-0007',
    empresa_id: 'EMP-0001',
    tipo: 'faltante_caja',
    prioridad: 1,
    fecha_evento: '2026-11-30',
    monto: '650.00',
    probabilidad: '0.740',
    nivel_riesgo: 'alto',
    causas: JSON.stringify([
      { descripcion: 'Retiraste más para la casa sobre tu mínimo para vivir', monto: 700.0 },
      { descripcion: 'Sobrecompra de campaña navideña mayor a tus ventas quincenales', monto: 400.0 },
      { descripcion: 'Fiados sin cobrar en el cuaderno', monto: 310.0 },
    ]),
    accion_sugerida: 'abrir_simulador',
    entidad_tipo: 'deudas',
    entidad_id: 'PED-0012',
    canal: 'whatsapp',
    estado: 'activa',
    accion_tomada: null,
    fecha_accion: null,
    creada_en: '2026-11-14T08:05:00-05:00',
    enviada_en: '2026-11-14T08:05:05-05:00',
    modelo_version: 'forecast-lgbm-quantile-0.3.1',
  },
  {
    alerta_id: 'ALR-0008',
    empresa_id: 'EMP-0001',
    tipo: 'fiado_vencido',
    prioridad: 6,
    fecha_evento: '2026-11-14',
    monto: '120.00',
    probabilidad: '0.720',
    nivel_riesgo: 'alto',
    causas: JSON.stringify([{ descripcion: 'Sra. Carmen lleva 18 días sin pagar', monto: 120.0 }]),
    accion_sugerida: 'recordar_cliente',
    entidad_tipo: 'cuaderno_fiado',
    entidad_id: 'FIA-0045',
    canal: 'app',
    estado: 'activa',
    accion_tomada: null,
    fecha_accion: null,
    creada_en: '2026-11-14T08:10:00-05:00',
    enviada_en: '2026-11-14T08:10:02-05:00',
    modelo_version: 'riesgo-atraso-clf-0.2.0',
  }
);

tables.consentimientos.push({
  consentimiento_id: 'CNS-0001',
  empresa_id: 'EMP-0001',
  alcance: JSON.stringify(['resumen_12_meses', 'score']),
  activo: false,
  fecha_otorgado: null,
  vigencia_hasta: null,
  fecha_revocado: null,
});

// Eventos (ground truth) de Pedro: incluye retiro_excesivo, sobrecompra navideña (alza_proveedor) y cliente_no_paga
tables.eventos.push(
  {
    evento_id: 'EVT-0001',
    empresa_id: 'EMP-0001',
    tipo_evento: 'retiro_excesivo',
    fecha_inicio: '2026-11-05',
    fecha_fin: '2026-11-13',
    descripcion: 'Retiro de S/ 700 extra para la casa por encima del sueldo mínimo para vivir (S/ 1,350/mes)',
  },
  {
    evento_id: 'EVT-0002',
    empresa_id: 'EMP-0001',
    tipo_evento: 'alza_proveedor',
    fecha_inicio: '2026-11-13',
    fecha_fin: '2026-11-30',
    descripcion: 'Sobrecompra de stock pre-Campaña Navideña a Distribuidora Andina (PED-0012 por S/ 2,400) y Nuevo RUS mal informado en S/ 20 en lugar de S/ 50',
  },
  {
    evento_id: 'EVT-0003',
    empresa_id: 'EMP-0001',
    tipo_evento: 'cliente_no_paga',
    fecha_inicio: '2026-11-05',
    fecha_fin: null,
    descripcion: 'Sra. Carmen (FIA-0045, S/ 120) y Don Luis (FIA-0046, S/ 95) se atrasaron en pagar',
  }
);

// Predicciones de saldo de Pedro (30 días: 2026-11-15 al 2026-12-14):
// Cae a -650.00 el 30/11 por el pago de PED-0012 (S/ 2,400) y en diciembre sube por el alza de ventas de Campaña Navideña (+42%)
const noisePedro = [40, -30, 55, 20, -45, 35, 60, -20, 25, -35, 50, 10, -25, 45, 0, 30, -40, 25, 55, -15, 40, 10, -30, 35, 20, -10, 45, -25, 30, 15];
let p50Pedro = 2340;
let predSaldoSeq = 1;
for (let i = 0; i < 30; i++) {
  const fechaObj = addDays('2026-11-15', i);
  const dow = dayOfWeek(fechaObj);
  const esDiciembreNavidad = fechaObj.startsWith('2026-12');
  let ingresos = Math.round((610 + (dow === 6 || dow === 7 ? 120 : 0)) * (esDiciembreNavidad ? 1.42 : 1.0));
  let egresos = 640;
  if (fechaObj === '2026-11-16') egresos += 180;
  if (fechaObj === '2026-11-20') ingresos += 190;
  if (fechaObj === '2026-11-30') egresos += 2400;
  if (esDiciembreNavidad) egresos = 680; // mayor reposición navideña pero con margen positivo
  p50Pedro = p50Pedro + ingresos - egresos + noisePedro[i];
  if (fechaObj === '2026-11-30') p50Pedro = -650;
  const spread = 90 + i * 14;
  const p10 = fechaObj === '2026-11-30' ? -1180 : Math.round(p50Pedro - spread);
  const p90 = fechaObj === '2026-11-30' ? -90 : Math.round(p50Pedro + spread * 0.85);

  tables.predicciones_saldo.push({
    prediccion_id: padId('PRS', predSaldoSeq++, 5),
    empresa_id: 'EMP-0001',
    fecha_corte: '2026-11-14',
    fecha_objetivo: fechaObj,
    p10: fmtMoney(p10),
    p50: fmtMoney(p50Pedro),
    p90: fmtMoney(p90),
    modelo_version: 'forecast-lgbm-quantile-0.3.1',
    creado_en: '2026-11-14T10:42:05-05:00',
  });

  tables.predicciones_saldo.push({
    prediccion_id: padId('PRS', predSaldoSeq++, 5),
    empresa_id: 'EMP-0001',
    fecha_corte: '2026-11-14',
    fecha_objetivo: fechaObj,
    p10: fmtMoney(p10 - 65),
    p50: fmtMoney(p50Pedro - 35),
    p90: fmtMoney(p90 + 65),
    modelo_version: 'naive_estacional-1.0',
    creado_en: '2026-11-14T10:42:05-05:00',
  });
}

// Predicciones de fiado de Pedro (FIA-0045, FIA-0046, FIA-0047 -> cobros esperados ponderados = 190.00)
let predFiadoSeq = 1;
for (const pf of [
  { fiado_id: 'FIA-0045', atraso: 0.720, pago14d: 0.350, nivel: 'alto', base: 0.600 },
  { fiado_id: 'FIA-0046', atraso: 0.450, pago14d: 0.650, nivel: 'medio', base: 0.600 },
  { fiado_id: 'FIA-0047', atraso: 0.180, pago14d: 0.908, nivel: 'bajo', base: 0.600 },
]) {
  tables.predicciones_fiado.push(
    {
      prediccion_id: padId('PRF', predFiadoSeq++, 5),
      fiado_id: pf.fiado_id,
      fecha_corte: '2026-11-14',
      prob_atraso: fmtProb(pf.atraso),
      prob_pago_14d: fmtProb(pf.pago14d),
      nivel_riesgo: pf.nivel,
      modelo_version: 'riesgo-atraso-clf-0.2.0',
      creado_en: '2026-11-14T10:42:05-05:00',
    },
    {
      prediccion_id: padId('PRF', predFiadoSeq++, 5),
      fiado_id: pf.fiado_id,
      fecha_corte: '2026-11-14',
      prob_atraso: fmtProb(pf.base),
      prob_pago_14d: fmtProb(1 - pf.base),
      nivel_riesgo: 'medio',
      modelo_version: 'baseline_historial-1.0',
      creado_en: '2026-11-14T10:42:05-05:00',
    }
  );
}

// Score de salud mensual de Pedro (agosto a noviembre 2026)
for (const sc of [
  { mes: '2026-08', score: 38, sub: { constancia_registro: 45, separacion_personal: 30, colchon_caja: 35, pedidos_acordes: 40, cobro_fiados: 40, impuestos_al_dia: 50, meses_sin_faltante: 30 } },
  { mes: '2026-09', score: 52, sub: { constancia_registro: 68, separacion_personal: 48, colchon_caja: 40, pedidos_acordes: 50, cobro_fiados: 60, impuestos_al_dia: 100, meses_sin_faltante: 50 } },
  { mes: '2026-10', score: 64, sub: { constancia_registro: 82, separacion_personal: 62, colchon_caja: 45, pedidos_acordes: 65, cobro_fiados: 75, impuestos_al_dia: 100, meses_sin_faltante: 50 } },
  { mes: '2026-11', score: 71, sub: { constancia_registro: 92, separacion_personal: 70, colchon_caja: 45, pedidos_acordes: 60, cobro_fiados: 80, impuestos_al_dia: 100, meses_sin_faltante: 50 } },
]) {
  tables.score_salud.push({
    empresa_id: 'EMP-0001',
    mes: sc.mes,
    score: sc.score,
    subindicadores: JSON.stringify(sc.sub),
    version_formula: 'score-v1',
  });
}

// =============================================================================
// 3. EMPRESA 2: ESCENARIO "USUARIO NUEVO — DÍA 3" (EMP-0002, Bodega Nueva Esperanza)
// Bodega RUC 10 en Nuevo RUS con 3 días de operación 100% en efectivo
// =============================================================================
tables.empresas.push({
  empresa_id: 'EMP-0002',
  rubro_id: 'RUB-01',
  nombre_ficticio: 'Bodega Nueva Esperanza',
  telefono_whatsapp: '+51900000002',
  zona: 'Lima Este',
  n_trabajadores: 1,
  tiene_ruc: true,
  ruc: generarRuc10(2),
  regimen_tributario: 'nuevo_rus',
  saldo_inicial: '850.00',
  fecha_saldo_inicial: '2026-11-12',
  minimo_operativo: '500.00',
  fecha_alta: '2026-11-12T08:30:00-05:00',
});

tables.preferencias_alertas.push({
  empresa_id: 'EMP-0002',
  canales: JSON.stringify(['whatsapp']),
  max_por_dia: 2,
  silencio_desde: '21:00',
  silencio_hasta: '07:00',
  resumen_semanal: true,
});

for (const [dIdx, f, ing, comp] of [
  [0, '2026-11-12', 610.00, 480.00],
  [1, '2026-11-13', 640.00, 500.00],
  [2, '2026-11-14', 620.00, 470.00],
]) {
  addTx({
    empresa_id: 'EMP-0002',
    fecha_hora: `${f}T18:30:00-05:00`,
    tipo: 'venta',
    categoria_id: 'CAT-02',
    descripcion: `Ventas día ${dIdx + 1} en efectivo`,
    monto: ing,
    metodo_pago: 'efectivo',
    canal: 'voz',
  });
  addTx({
    empresa_id: 'EMP-0002',
    fecha_hora: `${f}T09:30:00-05:00`,
    tipo: 'compra',
    categoria_id: 'CAT-07',
    descripcion: 'Compra mercadería del día en efectivo',
    monto: comp,
    metodo_pago: 'efectivo',
    canal: 'voz',
  });
}
addTx({
  empresa_id: 'EMP-0002',
  fecha_hora: '2026-11-13T20:00:00-05:00',
  tipo: 'retiro_personal',
  categoria_id: 'CAT-13',
  descripcion: 'Retiro en efectivo para gastos mínimos de la casa',
  monto: 150.00,
  metodo_pago: 'efectivo',
  canal: 'voz',
});

// =============================================================================
// 4. EMPRESAS PARES (EMP-0003 a EMP-0030): 28 BODEGAS RUC 10 (NUEVO RUS) — 100% EFECTIVO
// Todas tienen rubro_id = 'RUB-01', tiene_ruc = true, regimen_tributario = 'nuevo_rus'.
// Incluye bodegas pequeñas (ventas <= S/ 5,000/mes -> RUS S/ 20 bien pagado),
// bodegas medianas que pagan RUS Cat. 2 (S/ 50) correctamente, y bodegas que en campaña
// superan S/ 5,000 pero siguen pagando/informando mal S/ 20 (o lo anotan como gasto común).
// =============================================================================

const nombresBodegasPares = [
  { nombre: 'Bodega Mi Barrio', zona: 'Lima Este' },
  { nombre: 'Bodega San Martín', zona: 'Lima Este' },
  { nombre: 'Bodega El Progreso', zona: 'Lima Este' },
  { nombre: 'Bodega Los Olivos', zona: 'Lima Norte' },
  { nombre: 'Bodega Doña María', zona: 'Lima Este' },
  { nombre: 'Bodega Santa Rosa', zona: 'Lima Sur' },
  { nombre: 'Bodega El Vecino', zona: 'Lima Este' },
  { nombre: 'Bodega La Familia', zona: 'Lima Norte' },
  { nombre: 'Bodega Sol de Oro', zona: 'Lima Este' },
  { nombre: 'Bodega Las Flores', zona: 'Lima Este' },
  { nombre: 'Bodega Villa Sur', zona: 'Lima Sur' },
  { nombre: 'Bodega Central Huaycán', zona: 'Lima Este' },
  { nombre: 'Bodega San Juan', zona: 'Lima Este' },
  { nombre: 'Bodega El Trébol', zona: 'Callao' },
  { nombre: 'Bodega Los Andes', zona: 'Lima Este' },
  { nombre: 'Bodega La Esquina', zona: 'Lima Norte' },
  { nombre: 'Bodega Virgen del Carmen', zona: 'Lima Este' },
  { nombre: 'Bodega El Ahorro', zona: 'Lima Sur' },
  { nombre: 'Bodega Chosica Express', zona: 'Lima Este' },
  { nombre: 'Bodega Canto Grande', zona: 'Lima Este' },
  { nombre: 'Bodega Primavera', zona: 'Lima Norte' },
  { nombre: 'Bodega Ceres', zona: 'Lima Este' },
  { nombre: 'Bodega Los Pinos', zona: 'Lima Este' },
  { nombre: 'Bodega Horizonte', zona: 'Lima Norte' },
  { nombre: 'Bodega Doña Julia', zona: 'Lima Este' },
  { nombre: 'Bodega El Buen Vecino', zona: 'Lima Sur' },
  { nombre: 'Bodega Santa Clara', zona: 'Lima Este' },
  { nombre: 'Bodega SurAndina', zona: 'Lima Este' },
];

let prodSeq = 100;
let cliSeq = 200;
let prvSeq = 50;
let prgSeq = 10;
let fiaSeq = 100;
let deuSeq = 100;
let impSeq = 50;
let evtSeq = 10;
let alrSeq = 50;
let metSeq = 10;

const nombresClientesPool = [
  'Sra. Juana', 'Don Carlos', 'Vecino Miguel', 'Sra. Bertha', 'Don Alberto',
  'Joven Kevin', 'Sra. Gladis', 'Maestro Tito', 'Vecina Patricia', 'Don Héctor',
];

const nombresProveedoresPool = [
  'Distribuidora Unión', 'Mayorista Central', 'Comercial Pacífico', 'Alimentos del Valle', 'Bebidas Nacionales',
];

for (let idx = 0; idx < nombresBodegasPares.length; idx++) {
  const empNum = idx + 3;
  const empId = padId('EMP', empNum, 4);
  const info = nombresBodegasPares[idx];
  const fechaIni = '2026-07-18'; // 120 días hasta 2026-11-14
  const saldoIni = randInt(1200, 3200);
  const minOp = randInt(500, 900);
  // Algunas bodegas venden <= S/ 5,000/mes (~150/día) y otras > S/ 5,000/mes (~240 a 550/día)
  const esTramo1Real = idx % 4 === 0;
  const baseVentaDia = esTramo1Real ? randInt(135, 160) : randInt(240, 560);
  const ratioRetiro = randFloat(0.18, 0.26, 3);
  // Sueldo mensual calculado bajo criterio bancario ("mínimo para vivir")
  const sueldoMensualMinimoVivir = Math.round((baseVentaDia * 30 * 0.20) / 50) * 50;
  const sueldoSemanal = Math.round(sueldoMensualMinimoVivir / 4);

  tables.empresas.push({
    empresa_id: empId,
    rubro_id: 'RUB-01', // 100% bodegas RUC 10
    nombre_ficticio: info.nombre,
    telefono_whatsapp: `+5190000${String(empNum).padStart(4, '0')}`,
    zona: info.zona,
    n_trabajadores: randInt(1, 3),
    tiene_ruc: true, // 100% RUC 10
    ruc: generarRuc10(empNum),
    regimen_tributario: 'nuevo_rus', // 100% Nuevo RUS
    saldo_inicial: fmtMoney(saldoIni),
    fecha_saldo_inicial: fechaIni,
    minimo_operativo: fmtMoney(minOp),
    fecha_alta: `${fechaIni}T08:00:00-05:00`,
  });

  tables.preferencias_alertas.push({
    empresa_id: empId,
    canales: JSON.stringify(['whatsapp']),
    max_por_dia: 2,
    silencio_desde: '21:00',
    silencio_hasta: '07:00',
    resumen_semanal: true,
  });

  const empProds = [
    { id: padId('PRD', prodSeq++, 4), cat: 'CAT-01', nombre: 'Bebida gaseosa 1.5L', pv: 7.50, cu: 5.50 },
    { id: padId('PRD', prodSeq++, 4), cat: 'CAT-02', nombre: 'Arroz superior 1kg', pv: 4.20, cu: 3.20 },
    { id: padId('PRD', prodSeq++, 4), cat: 'CAT-03', nombre: 'Leche evaporada', pv: 4.50, cu: 3.50 },
    { id: padId('PRD', prodSeq++, 4), cat: 'CAT-04', nombre: 'Detergente multiusos', pv: 5.80, cu: 4.30 },
  ];
  for (const p of empProds) {
    tables.productos.push({
      producto_id: p.id,
      empresa_id: empId,
      categoria_id: p.cat,
      nombre: p.nombre,
      alias: JSON.stringify([p.nombre.toLowerCase().split(' ')[0]]),
      precio_venta: fmtMoney(p.pv),
      costo_unitario: fmtMoney(p.cu),
      activo: true,
    });
  }

  const perfiles = ['puntual', 'ocasional', 'moroso'];
  const empClis = [];
  for (let c = 0; c < 3; c++) {
    const cliId = padId('CLI', cliSeq++, 4);
    const cname = nombresClientesPool[(idx * 3 + c) % nombresClientesPool.length];
    const perfil = perfiles[c];
    tables.clientes.push({
      cliente_id: cliId,
      empresa_id: empId,
      nombre_ficticio: cname,
      alias: JSON.stringify([cname.toLowerCase()]),
      telefono_ficticio: `+5191000${String(cliSeq).padStart(4, '0')}`,
      perfil_pago: perfil,
      creado_en: `${fechaIni}T09:00:00-05:00`,
    });
    empClis.push({ id: cliId, nombre: cname, perfil });
  }

  const empPrvs = [];
  for (let p = 0; p < 2; p++) {
    const prvId = padId('PRV', prvSeq++, 4);
    const pname = nombresProveedoresPool[(idx * 2 + p) % nombresProveedoresPool.length];
    tables.proveedores.push({
      proveedor_id: prvId,
      empresa_id: empId,
      nombre_ficticio: pname,
      telefono_ficticio: `+5192000${String(prvSeq).padStart(4, '0')}`,
      plazo_pago_dias: p === 0 ? 15 : 7,
    });
    empPrvs.push({ id: prvId, nombre: pname, plazo: p === 0 ? 15 : 7 });
  }

  const prgSueldoId = padId('PRG', prgSeq++, 4);
  const prgAlqId = padId('PRG', prgSeq++, 4);
  tables.movimientos_programados.push(
    {
      programado_id: prgSueldoId,
      empresa_id: empId,
      categoria_id: 'CAT-13',
      tipo: 'egreso',
      descripcion: `sueldo fijo mensual del dueño (mínimo para vivir S/ ${sueldoMensualMinimoVivir}/mes)`,
      monto: fmtMoney(sueldoSemanal),
      frecuencia: 'semanal',
      dia_semana: 6,
      dia_mes: null,
      es_sueldo: true,
      fecha_inicio: fechaIni,
      fecha_fin: null,
      activo: true,
    },
    {
      programado_id: prgAlqId,
      empresa_id: empId,
      categoria_id: 'CAT-09',
      tipo: 'egreso',
      descripcion: 'alquiler del local',
      monto: '350.00',
      frecuencia: 'mensual',
      dia_semana: null,
      dia_mes: 28,
      es_sueldo: false,
      fecha_inicio: fechaIni,
      fecha_fin: null,
      activo: true,
    }
  );

  tables.reglas_meta.push({
    meta_id: padId('MET', metSeq++, 4),
    empresa_id: empId,
    plantilla: idx % 2 === 0 ? 'sueldo_fijo' : 'colchon_caja',
    programado_id: idx % 2 === 0 ? prgSueldoId : null,
    tipo_regla: 'porcentaje_de_venta',
    valor: '0.0500',
    destino: 'colchon',
    objetivo: fmtMoney(minOp),
    acumulado: fmtMoney(randInt(120, 600)),
    recordatorio_frecuencia: 'semanal',
    recordatorio_dia: 1,
    estado: 'activa',
    fecha_inicio: '2026-09-01',
    fecha_logro: null,
  });

  // Shocks de sobrecompra navideña, retiro excesivo o caída de ventas
  const tieneShock = idx % 3 === 0;
  const shockWindowStart = '2026-10-25';
  const shockWindowEnd = '2026-11-14';
  if (tieneShock) {
    const tipoEv = idx % 9 === 0 ? 'retiro_excesivo' : idx % 6 === 3 ? 'alza_proveedor' : 'mes_bajo';
    tables.eventos.push({
      evento_id: padId('EVT', evtSeq++, 4),
      empresa_id: empId,
      tipo_evento: tipoEv,
      fecha_inicio: shockWindowStart,
      fecha_fin: shockWindowEnd,
      descripcion:
        tipoEv === 'alza_proveedor'
          ? 'Sobrecompra de mercadería para Campaña Navideña y Nuevo RUS mal informado en S/ 20 en lugar de S/ 50'
          : tipoEv === 'retiro_excesivo'
          ? 'Retiros personales extraordinarios por encima del mínimo para vivir que descapitalizan la caja'
          : 'Caída temporal de ventas previa a campaña navideña',
    });
  }

  // Impuestos (Nuevo RUS: S/ 20 hasta S/ 5,000; S/ 50 si > S/ 5,000; simulación de mal informado en campaña)
  const informaMalRus = !esTramo1Real && idx % 2 === 0; // supera S/ 5,000 pero declara/paga S/ 20 en vez de S/ 50
  const cuotaDeclarada = esTramo1Real ? 20.00 : informaMalRus ? 20.00 : 50.00;
  for (const [per, venc, pag] of [
    ['2026-08', '2026-09-15', '2026-09-14'],
    ['2026-09', '2026-10-15', '2026-10-14'],
    ['2026-10', '2026-11-16', '2026-11-12'],
    ['2026-11', '2026-12-15', null],
  ]) {
    const impId = padId('IMP', impSeq++, 4);
    tables.impuestos.push({
      impuesto_id: impId,
      empresa_id: empId,
      regimen: 'nuevo_rus',
      periodo: per,
      monto: fmtMoney(cuotaDeclarada),
      fecha_vencimiento: venc,
      fecha_pago: pag,
      canal: 'texto',
    });
    if (pag) {
      addTx({
        empresa_id: empId,
        fecha_hora: `${pag}T11:00:00-05:00`,
        tipo: 'pago_impuesto',
        categoria_id: 'CAT-11',
        descripcion: informaMalRus
          ? `Pago Nuevo RUS ${per} (informó S/ 20 Cat. 1 en lugar de S/ 50 Cat. 2 pese a superar S/ 5,000 en campaña)`
          : `Pago Nuevo RUS ${per} (Cat. ${cuotaDeclarada === 50 ? '2 S/ 50' : '1 S/ 20'})`,
        monto: cuotaDeclarada,
        metodo_pago: 'efectivo',
        canal: 'texto',
        impuesto_id: impId,
      });
    }
  }

  // Fiados de la bodega par (100% efectivo al cobrar, crédito al fiar)
  for (let fIdx = 0; fIdx < 6; fIdx++) {
    const cli = empClis[fIdx % 3];
    const fId = padId('FIA', fiaSeq++, 4);
    const offset = 10 + fIdx * 18;
    const fFiado = addDays(fechaIni, offset);
    const fComp = addDays(fFiado, 10);
    const montoF = randInt(25, 140);
    const esReciente = fFiado >= '2026-11-01';
    const seAtraso = cli.perfil === 'moroso' ? true : cli.perfil === 'ocasional' ? fIdx % 2 === 1 : false;
    const delayDias = seAtraso ? randInt(4, 14) : -randInt(0, 2);
    const fPago = esReciente && seAtraso ? null : addDays(fComp, delayDias);
    const pagoFinal = fPago && fPago <= '2026-11-14' ? fPago : null;

    tables.cuaderno_fiado.push({
      fiado_id: fId,
      empresa_id: empId,
      cliente_id: cli.id,
      borrador_id: null,
      detalle: 'abarrotes y bebidas en cuaderno',
      monto: fmtMoney(montoF),
      fecha_fiado: fFiado,
      fecha_compromiso: fComp,
      fecha_pago_total: pagoFinal,
      canal: fIdx % 2 === 0 ? 'foto' : 'voz',
      pago_tardio: seAtraso,
    });

    addTx({
      empresa_id: empId,
      fecha_hora: `${fFiado}T12:00:00-05:00`,
      tipo: 'venta',
      categoria_id: 'CAT-02',
      descripcion: `Venta fiada a ${cli.nombre}`,
      monto: montoF,
      metodo_pago: 'credito',
      canal: fIdx % 2 === 0 ? 'foto' : 'voz',
      fiado_id: fId,
    });

    if (pagoFinal) {
      addTx({
        empresa_id: empId,
        fecha_hora: `${pagoFinal}T17:00:00-05:00`,
        tipo: 'cobro_fiado',
        categoria_id: 'CAT-02',
        descripcion: `Cobro fiado ${cli.nombre} en efectivo`,
        monto: montoF,
        metodo_pago: 'efectivo',
        canal: 'voz',
        fiado_id: fId,
      });
    } else {
      const probAtraso = cli.perfil === 'moroso' ? randFloat(0.68, 0.88, 3) : cli.perfil === 'ocasional' ? randFloat(0.38, 0.58, 3) : randFloat(0.10, 0.25, 3);
      const nivel = probAtraso >= 0.65 ? 'alto' : probAtraso >= 0.35 ? 'medio' : 'bajo';
      tables.predicciones_fiado.push({
        prediccion_id: padId('PRF', predFiadoSeq++, 5),
        fiado_id: fId,
        fecha_corte: '2026-11-14',
        prob_atraso: fmtProb(probAtraso),
        prob_pago_14d: fmtProb(1 - probAtraso * 0.8),
        nivel_riesgo: nivel,
        modelo_version: 'riesgo-atraso-clf-0.2.0',
        creado_en: '2026-11-14T10:42:05-05:00',
      });
    }
  }

  // Deudas de la bodega par (sobrecompra pre-campaña navideña en noviembre)
  const dProvId = padId('PED', deuSeq++, 4);
  const montoPedidoNavidad = Math.round(baseVentaDia * 3.2);
  tables.deudas.push({
    deuda_id: dProvId,
    empresa_id: empId,
    tipo: 'proveedor',
    proveedor_id: empPrvs[0].id,
    acreedor_nombre: null,
    borrador_id: null,
    monto_recibido: fmtMoney(montoPedidoNavidad),
    monto_total_a_pagar: fmtMoney(montoPedidoNavidad),
    frecuencia_cuota: null,
    monto_cuota: null,
    fecha_inicio: '2026-11-10',
    fecha_vencimiento: '2026-11-25',
    fecha_pago_total: null,
    canal: 'voz',
    notas: 'Pedido de mercadería pre-Campaña Navideña',
  });
  addTx({
    empresa_id: empId,
    fecha_hora: '2026-11-10T09:00:00-05:00',
    tipo: 'compra',
    categoria_id: 'CAT-07',
    descripcion: 'Pedido a crédito proveedor para campaña navideña',
    monto: montoPedidoNavidad,
    metodo_pago: 'credito',
    canal: 'voz',
    deuda_id: dProvId,
  });

  if (tieneShock && idx % 6 === 0) {
    const dInfId = padId('DEU', deuSeq++, 4);
    tables.deudas.push({
      deuda_id: dInfId,
      empresa_id: empId,
      tipo: 'prestamo_informal',
      proveedor_id: null,
      acreedor_nombre: 'Prestamista informal',
      borrador_id: null,
      monto_recibido: '1000.00',
      monto_total_a_pagar: '1200.00',
      frecuencia_cuota: 'diaria',
      monto_cuota: '40.00',
      fecha_inicio: '2026-11-01',
      fecha_vencimiento: '2026-11-30',
      fecha_pago_total: null,
      canal: 'voz',
      notas: 'Préstamo informal diario 20% mensual en efectivo',
    });
    addTx({
      empresa_id: empId,
      fecha_hora: '2026-11-01T10:00:00-05:00',
      tipo: 'prestamo_recibido',
      categoria_id: 'CAT-06',
      descripcion: 'Préstamo recibido en efectivo',
      monto: 1000.00,
      metodo_pago: 'efectivo',
      canal: 'voz',
      deuda_id: dInfId,
    });
    for (let cd = 1; cd <= 13; cd++) {
      const fCuota = addDays('2026-11-01', cd);
      addTx({
        empresa_id: empId,
        fecha_hora: `${fCuota}T19:30:00-05:00`,
        tipo: 'pago_prestamo',
        categoria_id: 'CAT-12',
        descripcion: 'Pago cuota diaria préstamo en efectivo',
        monto: 40.00,
        metodo_pago: 'efectivo',
        canal: 'voz',
        deuda_id: dInfId,
      });
    }
  }

  // Serie diaria 100% en efectivo (120 días: 2026-07-18 al 2026-11-14)
  for (let d = 0; d < 120; d++) {
    const fecha = addDays(fechaIni, d);
    const dow = dayOfWeek(fecha);
    const factorSemanal = dow === 6 || dow === 7 ? 1.22 : dow === 1 ? 0.90 : 1.0;
    const esNoviembreCampania = fecha.startsWith('2026-11');
    const enShock = tieneShock && fecha >= shockWindowStart && fecha <= shockWindowEnd;
    const factorShock = enShock && idx % 6 !== 0 ? 0.78 : 1.0;
    const ventaDia = Math.round(baseVentaDia * factorSemanal * factorShock * randFloat(0.92, 1.08, 2));
    const prod = empProds[d % empProds.length];

    addTx({
      empresa_id: empId,
      fecha_hora: `${fecha}T18:45:00-05:00`,
      tipo: 'venta',
      categoria_id: prod.cat,
      descripcion: 'Ventas del día en efectivo',
      monto: ventaDia,
      metodo_pago: 'efectivo', // 100% efectivo
      canal: d % 4 === 0 ? 'foto' : d % 3 === 0 ? 'texto' : 'voz',
      producto: prod,
      cantidad: Number((ventaDia / prod.pv).toFixed(3)),
    });

    // En noviembre sube la compra de stock por adelanto de Campaña Navideña (~74% vs ~62% habitual)
    const factorSobrecompraNavidad = esNoviembreCampania ? 0.74 : 0.62;
    const compraDia = Math.round(ventaDia * factorSobrecompraNavidad);
    addTx({
      empresa_id: empId,
      fecha_hora: `${fecha}T09:30:00-05:00`,
      tipo: 'compra',
      categoria_id: 'CAT-07',
      descripcion: esNoviembreCampania
        ? 'Compra de mercadería en efectivo (acumulación de stock pre-Campaña Navideña)'
        : 'Compra de mercadería en efectivo',
      monto: compraDia,
      metodo_pago: 'efectivo',
      canal: 'voz',
    });

    // Sueldo semanal los sábados (mínimo para vivir) + retiro variable extra si hay shock
    if (dow === 6) {
      addTx({
        empresa_id: empId,
        fecha_hora: `${fecha}T20:00:00-05:00`,
        tipo: 'retiro_personal',
        categoria_id: 'CAT-13',
        descripcion: 'Retiro semanal para gastos mínimos de vida (sueldo fijo)',
        monto: sueldoSemanal,
        metodo_pago: 'efectivo',
        canal: 'voz',
        programado_id: prgSueldoId,
      });

      if (enShock && idx % 6 === 0) {
        addTx({
          empresa_id: empId,
          fecha_hora: `${fecha}T20:30:00-05:00`,
          tipo: 'retiro_personal',
          categoria_id: 'CAT-13',
          descripcion: 'Retiro personal variable extra que descapitaliza la caja',
          monto: Math.round(sueldoSemanal * 0.75),
          metodo_pago: 'efectivo',
          canal: 'voz',
          programado_id: null,
        });
      }
    }

    if (fecha.endsWith('-28')) {
      addTx({
        empresa_id: empId,
        fecha_hora: `${fecha}T15:00:00-05:00`,
        tipo: 'gasto_negocio',
        categoria_id: 'CAT-09',
        descripcion: 'Alquiler del local en efectivo',
        monto: 350.00,
        metodo_pago: 'efectivo',
        canal: 'voz',
        programado_id: prgAlqId,
      });
    }
  }

  for (const mes of ['2026-08', '2026-09', '2026-10', '2026-11']) {
    const scVal = tieneShock && mes === '2026-11' ? randInt(48, 62) : randInt(64, 86);
    tables.score_salud.push({
      empresa_id: empId,
      mes,
      score: scVal,
      subindicadores: JSON.stringify({
        constancia_registro: randInt(75, 95),
        separacion_personal: Math.round((1 - Math.abs(ratioRetiro - 0.20)) * 85),
        colchon_caja: randInt(50, 85),
        pedidos_acordes: randInt(65, 90),
        cobro_fiados: randInt(60, 90),
        impuestos_al_dia: 100,
        meses_sin_faltante: tieneShock ? 50 : 100,
      }),
      version_formula: 'score-v1',
    });
  }

  if (tieneShock) {
    tables.alertas.push({
      alerta_id: padId('ALR', alrSeq++, 4),
      empresa_id: empId,
      tipo: idx % 6 === 0 ? 'retiro_excesivo' : 'pedido_excesivo',
      prioridad: idx % 6 === 0 ? 3 : 2,
      fecha_evento: '2026-11-25',
      monto: fmtMoney(baseVentaDia * 1.2),
      probabilidad: '0.710',
      nivel_riesgo: 'medio',
      causas: JSON.stringify([{ descripcion: 'Sobrecompra navideña y retiros por encima del mínimo para vivir', monto: Math.round(baseVentaDia * 1.2) }]),
      accion_sugerida: 'abrir_simulador',
      entidad_tipo: 'deudas',
      entidad_id: dProvId,
      canal: 'whatsapp',
      estado: 'activa',
      accion_tomada: null,
      fecha_accion: null,
      creada_en: '2026-11-14T08:30:00-05:00',
      enviada_en: '2026-11-14T08:30:05-05:00',
      modelo_version: 'forecast-lgbm-quantile-0.3.1',
    });
  }
}

// =============================================================================
// 5. MATERIALIZACIÓN DE SALDO_DIARIO Y ETIQUETA DEFICIT_14D PARA TODAS LAS EMPRESAS
// =============================================================================
const ingresosSet = new Set(['venta', 'cobro_fiado', 'prestamo_recibido', 'otro_ingreso']);

for (const emp of tables.empresas) {
  const empId = emp.empresa_id;
  const fStart = emp.fecha_saldo_inicial;
  const fEnd = '2026-11-14';
  const nDays = daysBetween(fStart, fEnd) + 1;

  const flujoPorFecha = new Map();
  for (const tx of tables.transacciones) {
    if (tx.empresa_id !== empId || !tx.afecta_caja || tx.anulada) continue;
    const f = tx.fecha_hora.slice(0, 10);
    const delta = ingresosSet.has(tx.tipo) ? Number(tx.monto) : -Number(tx.monto);
    flujoPorFecha.set(f, (flujoPorFecha.get(f) || 0) + delta);
  }

  const cierres = [];
  let saldo = Number(emp.saldo_inicial);
  for (let i = 0; i < nDays; i++) {
    const f = addDays(fStart, i);
    saldo = Number((saldo + (flujoPorFecha.get(f) || 0)).toFixed(2));
    cierres.push({ fecha: f, saldo });
  }

  const minOp = Number(emp.minimo_operativo);
  for (let i = 0; i < cierres.length; i++) {
    let deficit = false;
    for (let j = i + 1; j <= Math.min(cierres.length - 1, i + 14); j++) {
      if (cierres[j].saldo < minOp) {
        deficit = true;
        break;
      }
    }
    if (empId === 'EMP-0001' && cierres[i].fecha >= '2026-11-01') {
      deficit = true;
    }
    tables.saldo_diario.push({
      empresa_id: empId,
      fecha: cierres[i].fecha,
      saldo_cierre: fmtMoney(cierres[i].saldo),
      deficit_14d: deficit,
    });
  }
}

// =============================================================================
// 6. DATASET DE EVALUACIÓN DE INGESTA (F1): 150 FRASES Y APUNTES DE CUADERNO
// Solo canales manuales ('voz', 'texto', 'foto') y métodos 'efectivo' o 'credito'.
// Incluye baja confianza (< 0.75) por letra manuscrita borrosa / mala pronunciación
// que activa pregunta_aclaratoria (doble confirmación), y casos de posibles duplicados.
// =============================================================================
const frasesBase = [
  {
    frase: 'vendí dos cervezas',
    canal: 'voz',
    tipo: 'venta',
    metodo_pago: 'efectivo',
    monto: 13.00,
    producto_id: 'PRD-0031',
    cantidad: 2,
    origen_monto: 'catalogo',
    confianza_simulada: 0.93,
    requiere_doble_confirmacion: false,
    pregunta_aclaratoria: null,
    posible_duplicado: false,
    dentro_alcance: true,
  },
  {
    frase: 'bendi 3 chelas bien heladas pero no se oye bien el monto',
    canal: 'voz',
    tipo: 'venta',
    metodo_pago: 'efectivo',
    monto: 19.50,
    producto_id: 'PRD-0031',
    cantidad: 3,
    origen_monto: 'catalogo',
    confianza_simulada: 0.68,
    requiere_doble_confirmacion: true,
    pregunta_aclaratoria: 'Entendí 3 cervezas (S/ 19.50) en efectivo. ¿Es correcto ese monto?',
    posible_duplicado: false,
    dentro_alcance: true,
  },
  {
    frase: 'me compraron 2 kilos de arroz y un aceite en efectivo, fueron 16.90',
    canal: 'voz',
    tipo: 'venta',
    metodo_pago: 'efectivo',
    monto: 16.90,
    producto_id: 'PRD-0003',
    cantidad: 2,
    origen_monto: 'dicho_por_usuario',
    confianza_simulada: 0.91,
    requiere_doble_confirmacion: false,
    pregunta_aclaratoria: null,
    posible_duplicado: false,
    dentro_alcance: true,
  },
  {
    frase: 'saqué 50 para la casa',
    canal: 'voz',
    tipo: 'retiro_personal',
    metodo_pago: 'efectivo',
    monto: 50.00,
    producto_id: null,
    cantidad: null,
    origen_monto: 'dicho_por_usuario',
    confianza_simulada: 0.95,
    requiere_doble_confirmacion: false,
    pregunta_aclaratoria: null,
    posible_duplicado: false,
    dentro_alcance: true,
  },
  {
    frase: 'agarré 80 soles de la caja para el almuerzo familiar',
    canal: 'texto',
    tipo: 'retiro_personal',
    metodo_pago: 'efectivo',
    monto: 80.00,
    producto_id: null,
    cantidad: null,
    origen_monto: 'dicho_por_usuario',
    confianza_simulada: 0.90,
    requiere_doble_confirmacion: false,
    pregunta_aclaratoria: null,
    posible_duplicado: false,
    dentro_alcance: true,
  },
  {
    frase: 'pagué el colegio de mi hijo con mi plata',
    canal: 'voz',
    tipo: null,
    metodo_pago: null,
    monto: null,
    producto_id: null,
    cantidad: null,
    origen_monto: null,
    confianza_simulada: 0.89,
    requiere_doble_confirmacion: true,
    pregunta_aclaratoria: 'TuCaserito solo lleva las cuentas de la bodega. ¿Esa plata salió de la caja del negocio para anotarla como retiro personal?',
    posible_duplicado: false,
    dentro_alcance: false,
  },
  {
    frase: 'le fié a la señora Carmen 2 panes y una leche, son 9.50',
    canal: 'voz',
    tipo: 'venta',
    metodo_pago: 'credito',
    monto: 9.50,
    producto_id: 'PRD-0001',
    cantidad: 2,
    origen_monto: 'dicho_por_usuario',
    confianza_simulada: 0.92,
    requiere_doble_confirmacion: false,
    pregunta_aclaratoria: null,
    posible_duplicado: false,
    dentro_alcance: true,
  },
  {
    frase: '[Foto cuaderno borrosa] Don Luis - arroz, aceite - S/ 95 (parece 35 u 85, ya dictado antes por voz)',
    canal: 'foto',
    tipo: 'venta',
    metodo_pago: 'credito',
    monto: 95.00,
    producto_id: 'PRD-0003',
    cantidad: 1,
    origen_monto: 'dicho_por_usuario',
    confianza_simulada: 0.64,
    requiere_doble_confirmacion: true,
    pregunta_aclaratoria: 'El monto manuscrito se ve borroso (¿S/ 95 o S/ 35?) y coincide con un fiado de Don Luis ya dictado por voz. ¿Confirmas si es nuevo?',
    posible_duplicado: true,
    dentro_alcance: true,
  },
  {
    frase: 'la señora Carmen me pagó 50 en efectivo de su cuenta del cuaderno',
    canal: 'voz',
    tipo: 'cobro_fiado',
    metodo_pago: 'efectivo',
    monto: 50.00,
    producto_id: null,
    cantidad: null,
    origen_monto: 'dicho_por_usuario',
    confianza_simulada: 0.94,
    requiere_doble_confirmacion: false,
    pregunta_aclaratoria: null,
    posible_duplicado: false,
    dentro_alcance: true,
  },
  {
    frase: '[Foto cuaderno OCR 8 vs 3] Compra abarrotes mayorista S/ 380 (trazo parece 330)',
    canal: 'foto',
    tipo: 'compra',
    metodo_pago: 'efectivo',
    monto: 380.00,
    producto_id: null,
    cantidad: null,
    origen_monto: 'dicho_por_usuario',
    confianza_simulada: 0.61,
    requiere_doble_confirmacion: true,
    pregunta_aclaratoria: 'En la foto del cuaderno el número puede ser S/ 380 o S/ 330. ¿Cuál es el monto correcto?',
    posible_duplicado: false,
    dentro_alcance: true,
  },
  {
    frase: 'pedí 2400 a Andina por campaña navideña para pagar el 30',
    canal: 'voz',
    tipo: 'compra',
    metodo_pago: 'credito',
    monto: 2400.00,
    producto_id: null,
    cantidad: null,
    origen_monto: 'dicho_por_usuario',
    confianza_simulada: 0.90,
    requiere_doble_confirmacion: false,
    pregunta_aclaratoria: null,
    posible_duplicado: false,
    dentro_alcance: true,
  },
  {
    frase: 'le pagué 1200 a Distribuidora Andina en efectivo',
    canal: 'voz',
    tipo: 'pago_proveedor',
    metodo_pago: 'efectivo',
    monto: 1200.00,
    producto_id: null,
    cantidad: null,
    origen_monto: 'dicho_por_usuario',
    confianza_simulada: 0.93,
    requiere_doble_confirmacion: false,
    pregunta_aclaratoria: null,
    posible_duplicado: false,
    dentro_alcance: true,
  },
  {
    frase: 'me prestaron 1000 soles en efectivo, pago 40 diarios',
    canal: 'voz',
    tipo: 'prestamo_recibido',
    metodo_pago: 'efectivo',
    monto: 1000.00,
    producto_id: null,
    cantidad: null,
    origen_monto: 'dicho_por_usuario',
    confianza_simulada: 0.91,
    requiere_doble_confirmacion: false,
    pregunta_aclaratoria: null,
    posible_duplicado: false,
    dentro_alcance: true,
  },
  {
    frase: 'pagué la luz del local en efectivo, 180 soles',
    canal: 'texto',
    tipo: 'gasto_negocio',
    metodo_pago: 'efectivo',
    monto: 180.00,
    producto_id: null,
    cantidad: null,
    origen_monto: 'dicho_por_usuario',
    confianza_simulada: 0.95,
    requiere_doble_confirmacion: false,
    pregunta_aclaratoria: null,
    posible_duplicado: false,
    dentro_alcance: true,
  },
  {
    frase: 'pagué mi RUS en efectivo, 20 soles (aunque vendí más de 5000 por campaña)',
    canal: 'texto',
    tipo: 'pago_impuesto',
    metodo_pago: 'efectivo',
    monto: 20.00,
    producto_id: null,
    cantidad: null,
    origen_monto: 'dicho_por_usuario',
    confianza_simulada: 0.92,
    requiere_doble_confirmacion: false,
    pregunta_aclaratoria: null,
    posible_duplicado: false,
    dentro_alcance: true,
  },
];

const frasesEval = [];
for (let i = 0; i < 150; i++) {
  const b = frasesBase[i % frasesBase.length];
  const factor = Math.floor(i / frasesBase.length) + 1;
  const montoVar =
    b.monto && b.origen_monto === 'dicho_por_usuario' && b.tipo !== 'pago_impuesto'
      ? Number((b.monto + (factor - 1) * 5).toFixed(2))
      : b.monto;
  const fraseTexto = factor === 1 ? b.frase : `${b.frase} (muestra ${factor})`;
  frasesEval.push({
    caso_id: padId('EVF', i + 1, 3),
    canal: b.canal,
    frase: fraseTexto,
    tipo_esperado: b.tipo,
    metodo_pago_esperado: b.metodo_pago,
    monto_esperado: montoVar,
    producto_id_esperado: b.producto_id,
    origen_monto_esperado: b.origen_monto,
    confianza_simulada: b.confianza_simulada,
    requiere_doble_confirmacion: b.requiere_doble_confirmacion,
    pregunta_aclaratoria: b.pregunta_aclaratoria,
    posible_duplicado: b.posible_duplicado,
    dentro_alcance: b.dentro_alcance,
  });
}

fs.writeFileSync(path.join(EVAL_DIR, 'frases_ingesta_eval.json'), JSON.stringify(frasesEval, null, 2), 'utf8');

// =============================================================================
// 7. EXPORTACIÓN A CSV (incluye encabezados aun cuando la tabla tenga 0 filas)
// =============================================================================
function toCsvValue(val) {
  if (val === null || val === undefined) return '';
  const str = String(val);
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function writeCsv(filePath, rows, explicitHeaders = null) {
  const headers = rows.length > 0 ? Object.keys(rows[0]) : explicitHeaders || [];
  if (headers.length === 0) return;
  const lines = [headers.join(',')];
  for (const r of rows) {
    lines.push(headers.map((h) => toCsvValue(r[h])).join(','));
  }
  fs.writeFileSync(filePath, lines.join('\n') + '\n', 'utf8');
}

for (const [tableName, rows] of Object.entries(tables)) {
  writeCsv(path.join(CSV_DIR, `${tableName}.csv`), rows, TABLE_HEADERS[tableName]);
}
writeCsv(path.join(EVAL_DIR, 'frases_ingesta_eval.csv'), frasesEval);

// =============================================================================
// 8. VERIFICACIÓN DE INVARIANTES DE PEDRO (EMP-0001)
// =============================================================================
const txPedro = tables.transacciones.filter((t) => t.empresa_id === 'EMP-0001' && !t.anulada);
const txPedroCaja = txPedro.filter((t) => t.afecta_caja);
const saldoFinalPedro = txPedroCaja.reduce(
  (acc, t) => acc + (ingresosSet.has(t.tipo) ? Number(t.monto) : -Number(t.monto)),
  1800.0
);
const txNovPedro = txPedroCaja.filter((t) => t.fecha_hora.startsWith('2026-11'));
const ingNovPedro = txNovPedro.filter((t) => ingresosSet.has(t.tipo)).reduce((a, t) => a + Number(t.monto), 0);
const egrNovPedro = txNovPedro.filter((t) => !ingresosSet.has(t.tipo)).reduce((a, t) => a + Number(t.monto), 0);
const retNovPedro = txNovPedro.filter((t) => t.tipo === 'retiro_personal').reduce((a, t) => a + Number(t.monto), 0);
const mercNovPedro = txNovPedro.filter((t) => t.categoria_id === 'CAT-07').reduce((a, t) => a + Number(t.monto), 0);

console.log('=== RESUMEN DE GENERACIÓN SINTÉTICA CALIBRADA (SEED=42, RUC 10, 100% EFECTIVO) ===');
for (const [k, v] of Object.entries(tables)) {
  console.log(`  ${k.padEnd(26)}: ${String(v.length).padStart(6)} filas`);
}
console.log('--- Verificación Bodega Don Pedro (EMP-0001) al 2026-11-14 ---');
console.log(`  Saldo Caja Negocio      : S/ ${saldoFinalPedro.toFixed(2)} (esperado: 2340.00)`);
console.log(`  Ingresos Mes (Nov)      : S/ ${ingNovPedro.toFixed(2)} (esperado: 8540.00)`);
console.log(`  Egresos Mes (Nov)       : S/ ${egrNovPedro.toFixed(2)} (esperado: 7310.00)`);
console.log(`  Mercadería Mes (Nov)    : S/ ${mercNovPedro.toFixed(2)} (esperado: 4980.00)`);
console.log(`  Retiros Personales (Nov): S/ ${retNovPedro.toFixed(2)} (esperado: 1900.00)`);
