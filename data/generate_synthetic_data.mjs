/**
 * TuCaserito — Generador determinístico de datos sintéticos (seed = 42)
 * Genera las 25 tablas del modelo de datos (modelo_datos.dbml = backend/app/db/models.py) en data/csv/*.csv
 * y el dataset de evaluación de ingesta (data/eval/frases_ingesta_eval.json y .csv).
 *
 * Uso:  node data/generate_synthetic_data.mjs        (dos corridas producen archivos idénticos)
 *
 * Principios:
 *   1. Semilla fija (42) y un generador pseudoaleatorio propio por empresa: reproducible y estable (cambiar una
 *      empresa no mueve a las demás). Cero PII real.
 *   2. 30 empresas: EMP-0001 (Bodega Don Pedro, historia calibrada de la demo), EMP-0002 (usuario nuevo, 3 días) y
 *      28 negocios con volumen, rubro (bodega, restaurante, taller, distribuidora), fiado, billetera digital,
 *      trabajadores, RUC y estacionalidad (quincena / fin de mes / fin de semana) distintos.
 *   3. "Hoy" de la demo = 2026-11-14 y la HORA DE CORTE es las 10:00 (Lima): nada del 14/11 es posterior a esa hora
 *      (la venta "vendí dos cervezas" se dice en vivo durante la demo y no debe estar ya registrada).
 *   4. Dinero siempre con 2 decimales; cantidades de detalle_transaccion enteras y subtotal = cantidad x precio.
 *   5. La caja de ninguna empresa es negativa: los gastos discrecionales se limitan al efectivo disponible.
 *   6. Las alertas pedido_excesivo / retiro_excesivo / obligacion_proxima, el riesgo de atraso de los fiados y el score
 *      de salud se calculan con las mismas fórmulas que el backend (services/alertas/reglas.py, finanzas/consultas.py,
 *      finanzas/riesgo.py, salud/score.py) sobre estos mismos datos.
 *   7. Pedro (EMP-0001): historia día por día calibrada contra el forecast LightGBM del backend (saldo 2 340, 30/11 en
 *      −650; ver 2.2). Sus filas de resultado que JavaScript no puede calcular (predicciones_saldo y sus alertas, incluida
 *      la de faltante) se leen de data/demo_pedro_backend.json (data/pipeline_python/exportar_demo_backend.py).
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { generarFrasesEval } from './eval_ingesta.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
// GEN_OUT_DIR (opcional) escribe <dir>/csv y <dir>/eval en otra carpeta (para probar cambios sin tocar data/csv).
const OUT_DIR = process.env.GEN_OUT_DIR ? path.resolve(process.env.GEN_OUT_DIR) : null;
const CSV_DIR = OUT_DIR ? path.join(OUT_DIR, 'csv') : path.join(__dirname, 'csv');
const EVAL_DIR = OUT_DIR ? path.join(OUT_DIR, 'eval') : path.join(__dirname, 'eval');

fs.mkdirSync(CSV_DIR, { recursive: true });
fs.mkdirSync(EVAL_DIR, { recursive: true });

export const FECHA_DEMO = '2026-11-14';
export const HORA_CORTE = '10:00'; // los datos del 14/11 terminan antes de esta hora (Lima)

// PRNG determinístico (Mulberry32). Cada empresa usa su propio flujo: useRng(seedEmpresa).
function createRng(seed = 42) {
  let a = seed >>> 0;
  return function rng() {
    let t = (a += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

let rng = createRng(42);
const useRng = (seed) => {
  rng = createRng(seed);
};
const randInt = (min, max) => Math.floor(rng() * (max - min + 1)) + min;
const randFloat = (min, max, dec = 2) => Number((min + rng() * (max - min)).toFixed(dec));
const pick = (arr) => arr[Math.floor(rng() * arr.length)];
const chance = (p) => rng() < p;
const shuffle = (arr) => {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
};
const padId = (prefix, num, width = 4) => `${prefix}-${String(num).padStart(width, '0')}`;
const fmtMoney = (val) => Number(val).toFixed(2);
const fmtProb = (val) => Number(val).toFixed(3);
const cents = (val) => Math.round(Number(val) * 100);
const fromCents = (c) => c / 100;
const sum = (arr, f = (x) => x) => arr.reduce((a, x) => a + f(x), 0);

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

const ultimoDiaMes = (anio, mes) => new Date(Date.UTC(anio, mes, 0)).getUTCDate();
const mesDe = (fecha) => fecha.slice(0, 7);
const primerDiaMes = (fecha) => `${fecha.slice(0, 7)}-01`;

// Fecha-hora en Lima. En el día de la demo ninguna hora puede pasar de la hora de corte.
function ts(fecha, hhmm, ss = '00') {
  let h = hhmm;
  if (fecha === FECHA_DEMO && hhmm >= HORA_CORTE) h = hhmm > '12:00' ? '09:40' : '09:20';
  return `${fecha}T${h}:${ss}-05:00`;
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
  billeteras_digitales: [],
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

// Columnas de las tablas que pueden quedar vacías (para escribir al menos el encabezado)
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
// 1. RUBROS Y CATEGORÍAS GLOBALES (los mismos de modelo_datos.dbml, models.py y los modelos de ML)
// =============================================================================
tables.rubros.push(
  { rubro_id: 'RUB-01', nombre: 'bodega' },
  { rubro_id: 'RUB-02', nombre: 'restaurante' },
  { rubro_id: 'RUB-03', nombre: 'taller' },
  { rubro_id: 'RUB-04', nombre: 'distribuidora' }
);

// 16 categorías en snake_case. El backend compara los nombres sin tildes, en minúsculas y con "_" = espacio.
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
  { categoria_id: 'CAT-13', nombre: 'retiro_personal', tipo: 'egreso', es_del_negocio: false },
  { categoria_id: 'CAT-14', nombre: 'cobro_fiados', tipo: 'ingreso', es_del_negocio: true },
  { categoria_id: 'CAT-15', nombre: 'prestamos_recibidos', tipo: 'ingreso', es_del_negocio: true },
  { categoria_id: 'CAT-16', nombre: 'otros_gastos', tipo: 'egreso', es_del_negocio: true }
);

// RUC de persona natural con negocio: '10' + 8 dígitos de un DNI ficticio + dígito verificador módulo 11 de SUNAT
// (pesos 5,4,3,2,7,6,5,4,3,2; dv = (11 - suma % 11) % 10). Todos los RUC generados pasan la validación.
const MODELO_FORECAST = 'lgbm_cuantiles-1.0'; // modelo/artifacts/prediccion_ingreso_egreso/metadata.json
const MODELO_REGLAS = 'reglas-alertas-0.2.0'; // alertas de reglas determinísticas: backend/app/services/alertas/motor.py (VERSION)
// Textos de las causas, iguales a los de backend/app/services/alertas/reglas.py
const CAUSA_RETIROS = 'Sacaste más de la caja de lo usual';
const CAUSA_PEDIDO = 'Pediste más de lo que vendes';
const CAUSA_FIADOS = 'Fiados sin cobrar';
// Niveles de riesgo de fiado: mismos umbrales que backend/app/services/finanzas/riesgo.py (>= 0.6 alto, >= 0.3 medio)
const nivelRiesgoFiado = (p) => (p >= 0.6 ? 'alto' : p >= 0.3 ? 'medio' : 'bajo');
const rucsUsados = new Set();
function digitoVerificadorRuc(base10) {
  const pesos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2];
  const suma = base10.split('').reduce((acc, dig, i) => acc + Number(dig) * pesos[i], 0);
  return (11 - (suma % 11)) % 10;
}
function generarRuc10(empNum) {
  let dniNum = empNum === 1 ? 45678901 : 40123400 + empNum * 1371;
  for (;;) {
    const base10 = `10${String(dniNum).padStart(8, '0').slice(0, 8)}`;
    const ruc = `${base10}${digitoVerificadorRuc(base10)}`;
    if (!rucsUsados.has(ruc)) {
      rucsUsados.add(ruc);
      return ruc;
    }
    dniNum += 1;
  }
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

// Recibo de luz y agua esperado para noviembre (PRG-0001): fija el p50 del 30/11 en −650.00 con el LightGBM del backend
// (los recibos pagados de agosto a octubre fueron de S/ 168.40, 176.90 y 183.30).
const PEDRO_LUZ_NOV = process.env.PEDRO_LUZ_NOV || '176.37';
// Movimientos programados de Pedro:
// Sueldo fijo calculado bajo criterio bancario ("mínimo para vivir" = S/ 1,350.00 mensual / S/ 337.50 semanal)
tables.movimientos_programados.push(
  {
    programado_id: 'PRG-0001',
    empresa_id: 'EMP-0001',
    categoria_id: 'CAT-08',
    tipo: 'egreso',
    descripcion: 'luz y agua del local',
    monto: PEDRO_LUZ_NOV, // perilla fina de la historia de la demo (ver 2.2)
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

// Conversaciones y borradores de Pedro (casos con confianza < 0.75, pregunta_aclaratoria y posibles duplicados voz + foto).
// La venta "vendí dos cervezas" (BOR-7781 / MOV-000123) ya NO está: se dice en vivo durante la demo (a las 10:42) y no
// debe estar registrada antes. Los valores de `conversaciones.intencion` son los de IntencionAsistente del backend.
tables.conversaciones.push(
  {
    mensaje_id: 'MSG-0500',
    empresa_id: 'EMP-0001',
    conversacion_id: 'CNV-0030',
    rol: 'usuario',
    canal: 'whatsapp',
    texto: 'bendi 3 chelas y pan pero no se escucho el vuelto',
    media_url: 'file://data/audios/demo_ruido_002.ogg',
    intencion: 'otro',
    herramientas_llamadas: null,
    cifras_verificadas: null,
    fallback_usado: false,
    derivado_a_humano: false,
    prompt_version: 'extractor-v3',
    modelo_version: 'whisper-small+extractor-0.2.0',
    fecha_hora: '2026-11-10T14:20:00-05:00',
  },
  {
    mensaje_id: 'MSG-0501',
    empresa_id: 'EMP-0001',
    conversacion_id: 'CNV-0030',
    rol: 'asistente',
    canal: 'whatsapp',
    texto: 'Entendí 3 cervezas (S/ 19.50) más pan en efectivo. ¿El total fue S/ 22.00 o cuánto cobraste por el pan?',
    media_url: null,
    intencion: 'otro',
    herramientas_llamadas: JSON.stringify([{ nombre: 'buscar_catalogo', args: { query: 'cerveza' } }]),
    cifras_verificadas: true,
    fallback_usado: false,
    derivado_a_humano: false,
    prompt_version: 'extractor-v3',
    modelo_version: '0.2.0',
    fecha_hora: '2026-11-10T14:20:04-05:00',
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
    fecha_hora: '2026-11-14T09:20:00-05:00',
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
    fecha_hora: '2026-11-14T09:20:04-05:00',
  }
);

tables.borradores.push(
  // 1) Foto del cuaderno con letra borrosa (confianza < 0.75) + posible duplicado de un fiado dictado antes por voz
  //    (FIA-0044). La clave del payload es `fiados` (la que lee backend/app/services/ingesta/servicio.py).
  {
    borrador_id: 'BOR-7790',
    empresa_id: 'EMP-0001',
    mensaje_id: null,
    canal: 'foto',
    media_url: 'file://data/fotos/cuaderno_01.jpg',
    texto_original: 'Sra. Carmen - 2 panes, 1 leche - S/ 120 (27/10)\nDon Luis - arroz, aceite - S/ 95 (02/11, número 95 borroso parece 35)',
    payload_propuesto: JSON.stringify({
      fiados: [
        { cliente: 'Sra. Carmen', detalle: '2 panes, 1 leche', monto: 120.0, fecha: '2026-10-27', confianza: 0.81 },
        { cliente: 'Don Luis', detalle: 'arroz, aceite', monto: 95.0, fecha: '2026-11-02', confianza: 0.64, alternativas_monto: [95.0, 35.0] },
      ],
      lineas_no_legibles: [],
      lineas_tachadas: [],
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
  // 2) Audio con jerga y ruido fonético ("bendi 3 chelas") -> confianza < 0.75, repregunta y corrección del monto.
  //    Su venta existe (10/11 14:21, S/ 22.00): 3 cervezas (19.50) + 1 pan francés (2.50).
  {
    borrador_id: 'BOR-7791',
    empresa_id: 'EMP-0001',
    mensaje_id: 'MSG-0500',
    canal: 'voz',
    media_url: 'file://data/audios/demo_ruido_002.ogg',
    texto_original: 'bendi 3 chelas y pan pero no se escucho el vuelto',
    payload_propuesto: JSON.stringify({
      tipo: 'venta',
      items: [{ producto_id: 'PRD-0031', producto: 'Cerveza 620 ml', cantidad: 3, precio_unitario: 6.5, subtotal: 19.5 }],
      monto: 19.5,
      moneda: 'PEN',
      metodo_pago: 'efectivo',
      fecha_hora: '2026-11-10T14:20:00-05:00',
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
  // 3) Foto manuscrita con confusión OCR 8 <-> 3 (confianza 0.610 < 0.75). El usuario corrigió 330 -> 380 y la compra
  //    registrada (08/11) es de S/ 380.00.
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
      fecha_hora: '2026-11-08T09:15:00-05:00',
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
// TRANSACCIONES DE PEDRO (EMP-0001): 100% EFECTIVO Y CRÉDITO
// - Saldo inicial (2026-08-15): 1 800.00. Saldo al 14/11 antes de las 10:00: 2 340.00 exacto (ver 2.2).
// - Ventas del día con detalle de productos (canasta exacta), reposición diaria al contado, pedidos grandes a crédito
//   (deudas con detalle a costo), sueldo fijo mensual y retiros sueltos. Ver 2.2 para la calibración de la demo.
// =============================================================================

// Los IDs definitivos (MOV-000001 ...) se asignan al final, ordenando por fecha y hora; mientras tanto cada transacción
// lleva un ID temporal ("~n") que comparten sus filas de detalle_transaccion.
let txTemp = 0;
let detTemp = 0;

/**
 * Registra una transacción y, si trae `lineas`, su detalle. Cada línea es {prod, cantidad, precio?, costo?} con cantidad
 * ENTERA; subtotal = cantidad x precio exacto (en céntimos). Si hay `lineas`, el monto es la suma de los subtotales
 * (si además se pasa `monto`, debe coincidir: un descuadre es un error del generador).
 */
function addTx({
  empresa_id,
  borrador_id = null,
  fecha_hora,
  tipo,
  categoria_id,
  descripcion,
  monto = null,
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
  lineas = [],
}) {
  const subtotales = lineas.map((l) => {
    if (!Number.isInteger(l.cantidad) || l.cantidad < 1) throw new Error(`cantidad no entera: ${l.cantidad}`);
    return l.cantidad * cents(l.precio ?? l.prod.pv);
  });
  const totalLineas = sum(subtotales);
  if (lineas.length > 0) {
    if (monto !== null && cents(monto) !== totalLineas) {
      throw new Error(`monto ${monto} != suma de líneas ${fromCents(totalLineas)} (${descripcion})`);
    }
    monto = fromCents(totalLineas);
  }
  if (monto === null || !(Number(monto) > 0)) throw new Error(`monto inválido en ${tipo} ${descripcion}`);
  const txId = `~${++txTemp}`;
  const tx = {
    transaccion_id: txId,
    empresa_id,
    borrador_id,
    fecha_hora,
    tipo,
    categoria_id,
    descripcion: descripcion === undefined ? null : descripcion.slice(0, 255),
    monto: fmtMoney(monto),
    moneda: 'PEN',
    metodo_pago,
    afecta_caja: metodo_pago !== 'credito',
    canal,
    confianza_extraccion: confianza === null ? null : fmtProb(confianza),
    fue_corregida,
    fiado_id,
    deuda_id,
    impuesto_id,
    programado_id,
    billetera_mov_id,
    anulada: false,
    creado_en: creado_en || fecha_hora,
  };
  tables.transacciones.push(tx);
  lineas.forEach((l, i) => {
    tables.detalle_transaccion.push({
      detalle_id: `~${++detTemp}`,
      transaccion_id: txId,
      producto_id: l.prod.id,
      descripcion: l.prod.nombre.slice(0, 100),
      cantidad: Number(l.cantidad).toFixed(3),
      precio_unitario: fmtMoney(fromCents(cents(l.precio ?? l.prod.pv))),
      costo_unitario: (l.costo ?? l.prod.cu) !== null && (l.costo ?? l.prod.cu) !== undefined ? fmtMoney(l.costo ?? l.prod.cu) : null,
      subtotal: fmtMoney(fromCents(subtotales[i])),
    });
  });
  return tx;
}

// Une líneas repetidas del mismo producto.
function fusionarLineas(lineas) {
  const m = new Map();
  for (const l of lineas) {
    const k = `${l.prod.id}|${l.precio ?? ''}`;
    if (m.has(k)) m.get(k).cantidad += l.cantidad;
    else m.set(k, { ...l });
  }
  return [...m.values()];
}

function textoLineas(lineas) {
  return lineas.map((l) => `${l.cantidad} ${l.prod.alias?.[0] ?? l.prod.nombre}`).join(', ');
}

/**
 * Arma una canasta cuyo total es EXACTAMENTE `objetivoCents`: líneas aleatorias de cantidad entera y, al final, un
 * resto exacto resuelto con las combinaciones de precios del catálogo (búsqueda sobre los precios baratos).
 */
function canastaExacta(objetivoCents, prods) {
  for (let intento = 0; intento < 30; intento++) {
    const lineas = [];
    let resto = objetivoCents;
    while (resto > 4000) {
      const p = pick(prods);
      const pc = cents(p.pv);
      const qmax = Math.min(8, Math.floor((resto - 2000) / pc));
      if (qmax < 1) continue;
      const cantidad = randInt(1, qmax);
      lineas.push({ prod: p, cantidad });
      resto -= cantidad * pc;
    }
    // Resto exacto: combinación de a lo más 5 productos baratos
    const baratos = prods.filter((p) => cents(p.pv) <= 1000);
    const alcanzable = new Map([[0, []]]);
    let frontera = [0];
    for (let n = 0; n < 5 && !alcanzable.has(resto); n++) {
      const nueva = [];
      for (const base of shuffle(frontera)) {
        for (const p of shuffle(baratos)) {
          const t = base + cents(p.pv);
          if (t <= resto && !alcanzable.has(t)) {
            alcanzable.set(t, [...alcanzable.get(base), p]);
            nueva.push(t);
          }
        }
      }
      frontera = nueva;
    }
    if (alcanzable.has(resto)) {
      for (const p of alcanzable.get(resto)) lineas.push({ prod: p, cantidad: 1 });
      const fus = fusionarLineas(lineas);
      if (sum(fus, (l) => l.cantidad * cents(l.prod.pv)) === objetivoCents) return fus;
    }
  }
  throw new Error(`no se pudo armar una canasta exacta de ${fromCents(objetivoCents)}`);
}

function categoriaDominante(lineas) {
  const porCat = new Map();
  for (const l of lineas) porCat.set(l.prod.cat, (porCat.get(l.prod.cat) || 0) + l.cantidad * cents(l.precio ?? l.prod.pv));
  return [...porCat.entries()].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))[0][0];
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

// Detalle de los pedidos a crédito, a precio de costo (así el backend sabe qué trae cada proveedor: chequeo.py)
function lineasCosto(objetivo, base, libres) {
  // base: [[id, cantidad]]; libres: [idA, idB] cuyas cantidades se resuelven para cerrar el monto exacto
  const lineas = base.map(([id, cantidad]) => ({ prod: productosPedro.find((p) => p.id === id), cantidad }));
  lineas.forEach((l) => { l.precio = l.prod.cu; });
  const restoC = cents(objetivo) - sum(lineas, (l) => l.cantidad * cents(l.precio));
  const [a, b] = libres.map((id) => productosPedro.find((p) => p.id === id));
  for (let qa = 1; qa * cents(a.cu) < restoC; qa++) {
    const r = restoC - qa * cents(a.cu);
    if (r > 0 && r % cents(b.cu) === 0) return [...lineas, { prod: a, cantidad: qa, precio: a.cu }, { prod: b, cantidad: r / cents(b.cu), precio: b.cu }];
  }
  throw new Error(`no se pudo cerrar el detalle del pedido de ${objetivo}`);
}
const DETALLE_PEDIDOS_PEDRO = {
  'PED-0010': lineasCosto(1600, [['PRD-0008', 104], ['PRD-0031', 120]], ['PRD-0009', 'PRD-0019']), // Andina: bebidas
  'PED-0011': lineasCosto(1750, [['PRD-0003', 150], ['PRD-0004', 60], ['PRD-0005', 100], ['PRD-0006', 120]], ['PRD-0010', 'PRD-0018']), // El Sol: abarrotes
  'PED-0012': lineasCosto(2400, [['PRD-0020', 60], ['PRD-0008', 120], ['PRD-0031', 144]], ['PRD-0009', 'PRD-0019']), // Andina: panetones y bebidas
};
for (const d of deudasPedro) {
  addTx({
    empresa_id: 'EMP-0001',
    fecha_hora: `${d.f_ini}T09:00:00-05:00`,
    tipo: 'compra',
    categoria_id: 'CAT-07',
    descripcion: d.notas,
    metodo_pago: 'credito',
    canal: d.canal,
    deuda_id: d.id,
    lineas: DETALLE_PEDIDOS_PEDRO[d.id],
  });
}

// 2.2 Flujo de caja de Pedro día por día (2026-08-15 al 14/11 antes de las 10:00), con su propio flujo del PRNG (no
//     mueve a las demás empresas). Bodega de barrio que vende ~S/ 600 al día. Cómo compra:
//     - cada mañana repone al contado (pan, lácteos, abarrotes chicos) ~47 % de lo que vendió el día anterior;
//     - una vez al mes (día 5, cuando cobra el barrio) hace la compra grande del mes en el mercado mayorista, al contado;
//     - el resto le llega a crédito (deudas): Mayorista Santa Anita cada viernes y Lácteos del Sur cada jueves (7 días),
//       Abarrotes El Sol y Distribuidora Andina una vez al mes (15 días). Paga a tiempo.
//     Retiros: el sueldo fijo (S/ 1 350 el día 30, vinculado a PRG-0003 como lo vincula el registrador: un retiro por el
//     monto exacto del sueldo) y retiros sueltos "para la casa" sin vínculo.
//     Por qué esta forma: el LightGBM del backend se entrenó con bodegas cuyo egreso diario es ~55 % del ingreso con un
//     pago grande al mes (día 5); con un flujo ordinario así su error a 1 día en Pedro es bajo (ver README §ML). Si la
//     historia no tiene ese pago mensual, el modelo predice un pago "fantasma" de ~S/ 1 200 todos los días.
//     Historia de la demo (context.md §9), calibrada contra el forecast LightGBM (FORECAST_MOTOR=lightgbm):
//     - En noviembre saca S/ 700 más que lo usual al 14 (promedio del 1 al 14 de septiembre y octubre).
//     - Lo que vende de lo que trae Andina en las últimas 4 semanas da una venta esperada de S/ 2 000 hasta el 30/11:
//       el pedido PED-0012 (S/ 2 400, el doble de su pedido de octubre) es S/ 400 más.
//     - El 30/11 coinciden el pago a Andina y su sueldo, después de pagar a Santa Anita, Lácteos del Sur, El Sol (su
//       pedido grande de la campaña), la luz y el alquiler: la caja no alcanza.
//     - El recibo de luz y agua esperado de noviembre (PRG-0001) es la perilla fina del p50 del 30/11 (PEDRO_LUZ_NOV).
//     - El saldo del 14/11 cierra en S/ 2 340.00 exacto: el residuo se reparte en la reposición de agosto (fuera de
//       todas las ventanas que usan el forecast, sus backtests y las alertas).
useRng(20261114);
const PEDRO_FIN = FECHA_DEMO;
const valorPedro = (lineas) => fromCents(sum(lineas, (l) => l.cantidad * cents(l.precio ?? l.prod.pv)));
const PEDRO_SIN_REGISTRO = new Set(['2026-08-19', '2026-08-24', '2026-08-26', '2026-09-02', '2026-09-06', '2026-09-09']); // aún no anotaba todo
const PEDRO_SEMANA = { 1: 0.92, 2: 0.96, 3: 0.98, 4: 1.0, 5: 1.08, 6: 1.22, 7: 1.1 }; // = FACTOR_SEMANA.bodega
const PEDRO_VENTA_BASE = 560;
const PEDRO_RATIO = (f) => (f >= '2026-09-13' ? Number(process.env.PEDRO_RATIO || 0.47) : 0.4);
const PEDRO_COMPRA_MES = { '2026-09-05': 1240, '2026-10-05': 1310, '2026-11-05': 1380 }; // mercado mayorista, al contado
const PEDRO_EL_SOL_NOV = Number(process.env.PEDRO_EL_SOL_NOV || 2340); // pedido grande de abarrotes para la campaña
const VENTANA_VENTA_ESPERADA = ['2026-10-17', '2026-11-13']; // chequeo.py: 28 días antes del corte
const ANDINA_VENDIDO_OBJETIVO = 3500; // -> 3500 / 28 x 16 = 2000 de venta esperada hasta el 30/11
const ANDINA = ['PRD-0008', 'PRD-0009', 'PRD-0019', 'PRD-0031', 'PRD-0020']; // gaseosa, agua, jugo, cerveza, panetón
const NOMBRE_MES_PEDRO = { 8: 'agosto', 9: 'septiembre', 10: 'octubre', 11: 'noviembre' };
const prodPedro = (id) => productosPedro.find((p) => p.id === id);
const prodAndina = productosPedro.filter((p) => ANDINA.includes(p.id));
const prodAndinaSinPaneton = prodAndina.filter((p) => p.id !== 'PRD-0020');
const prodResto = productosPedro.filter((p) => !ANDINA.includes(p.id));
const aCosto = (ids) => ids.map((id) => { const p = prodPedro(id); return { ...p, pv: p.cu }; });
const diaRegistrado = (f) => { let d = f; while (PEDRO_SIN_REGISTRO.has(d)) d = addDays(d, 1); return d; };

// Líneas aleatorias (cantidad entera) hasta acercarse a `objetivo` (soles) sin pasarse más de un producto.
function lineasHasta(objetivo, prods, qtope = 4) {
  const lineas = [];
  let valor = 0;
  for (let guardia = 0; valor < objetivo - 2 && guardia < 60; guardia++) {
    const p = pick(prods);
    const qmax = Math.floor((objetivo - valor) / p.pv);
    if (qmax < 1) continue;
    const cantidad = randInt(1, Math.min(qtope, qmax));
    lineas.push({ prod: p, cantidad, precio: p.pv });
    valor += cantidad * p.pv;
  }
  return fusionarLineas(lineas);
}

// ── pedidos a crédito (deudas) con su detalle a costo y su pago ──
const pagosDeudaPedro = []; // {fecha, hora, monto, deuda, desc}
const NOMBRE_PRV_PEDRO = Object.fromEntries(proveedoresPedro.map((p) => [p.id, p.nombre]));
for (const d of deudasPedro) { // PED-0010/0011 pagados; PED-0012 vence el 30/11
  if (d.f_pago) pagosDeudaPedro.push({ fecha: d.f_pago, hora: '11:00', monto: d.total, deuda: d.id, desc: `Pago del pedido a ${NOMBRE_PRV_PEDRO[d.prv]}` });
}
let pedSeqPedro = 13;
function pedidoCredito({ id, prv, fecha, plazo, lineas, notas, pagoAntes = 0 }) {
  const monto = valorPedro(lineas);
  const venc = addDays(fecha, plazo);
  const fPago = venc <= PEDRO_FIN ? diaRegistrado(addDays(venc, -pagoAntes)) : null;
  const deudaId = id || padId('PED', pedSeqPedro++, 4);
  tables.deudas.push({
    deuda_id: deudaId, empresa_id: 'EMP-0001', tipo: 'proveedor', proveedor_id: prv, acreedor_nombre: null, borrador_id: null,
    monto_recibido: fmtMoney(monto), monto_total_a_pagar: fmtMoney(monto), frecuencia_cuota: null, monto_cuota: null,
    fecha_inicio: fecha, fecha_vencimiento: venc, fecha_pago_total: fPago && fPago < PEDRO_FIN ? fPago : null, canal: pick(['voz', 'voz', 'texto']), notas,
  });
  addTx({ empresa_id: 'EMP-0001', fecha_hora: ts(fecha, '08:40'), tipo: 'compra', categoria_id: 'CAT-07',
    descripcion: `${notas} (a crédito, vence el ${venc.slice(8, 10)}/${venc.slice(5, 7)})`, metodo_pago: 'credito', canal: 'voz',
    deuda_id: deudaId, lineas });
  if (fPago && fPago < PEDRO_FIN) pagosDeudaPedro.push({ fecha: fPago, hora: '11:00', monto, deuda: deudaId, desc: `Pago del pedido a ${NOMBRE_PRV_PEDRO[prv]}` });
  return deudaId;
}
// mensuales (15 días): Andina en octubre y El Sol cada mes (en noviembre, el pedido grande de la campaña)
pedidoCredito({ prv: 'PRV-0003', fecha: '2026-10-09', plazo: 15, notas: 'Pedido de bebidas a Distribuidora Andina',
  lineas: lineasHasta(1200, aCosto(['PRD-0008', 'PRD-0009', 'PRD-0019', 'PRD-0031']), 40), pagoAntes: 1 });
for (const [f, obj] of [['2026-08-17', 700], ['2026-09-14', 900]]) {
  pedidoCredito({ prv: 'PRV-0004', fecha: f, plazo: 15, notas: 'Pedido de abarrotes a Abarrotes El Sol',
    lineas: lineasHasta(obj, aCosto(['PRD-0003', 'PRD-0004', 'PRD-0005', 'PRD-0006', 'PRD-0010', 'PRD-0018']), 60) });
}
// semanales (7 días): Santa Anita los viernes y Lácteos del Sur los jueves
for (let f = '2026-08-15'; f < PEDRO_FIN; f = addDays(f, 1)) {
  if (PEDRO_SIN_REGISTRO.has(f)) continue;
  if (dayOfWeek(f) === 5) {
    pedidoCredito({ prv: 'PRV-0001', fecha: f, plazo: 7, notas: 'Pedido semanal al Mayorista Santa Anita', pagoAntes: chance(0.3) ? 1 : 0,
      lineas: lineasHasta(470 * (1 + (rng() - 0.5) * 0.2), aCosto(['PRD-0003', 'PRD-0005', 'PRD-0006', 'PRD-0010', 'PRD-0018', 'PRD-0011', 'PRD-0012', 'PRD-0013', 'PRD-0014']), 24) });
  }
  if (dayOfWeek(f) === 4) {
    pedidoCredito({ prv: 'PRV-0002', fecha: f, plazo: 7, notas: 'Pedido semanal a Lácteos del Sur', pagoAntes: 0,
      lineas: lineasHasta(230 * (1 + (rng() - 0.5) * 0.2), aCosto(['PRD-0002', 'PRD-0007', 'PRD-0016']), 24) });
  }
}

// el pedido grande de la campaña a El Sol: detalle exacto (sin azar, para poder ajustar su monto sin mover lo demás)
pedidoCredito({ prv: 'PRV-0004', fecha: '2026-11-12', plazo: 15, notas: 'Pedido grande de abarrotes para la campaña a Abarrotes El Sol',
  lineas: lineasCosto(PEDRO_EL_SOL_NOV, [['PRD-0003', 150], ['PRD-0004', 80], ['PRD-0005', 120], ['PRD-0006', 150], ['PRD-0011', 40], ['PRD-0012', 40]], ['PRD-0010', 'PRD-0018']) });

// ── plan del día (se agrega al final, después de cuadrar el saldo); flujo del PRNG propio ──
useRng(20261115);
const planPedro = []; // {fecha, hora, tipo, monto, desc, cat, lineas?, programado_id?, ajustable?}
let andinaVentana = 0;
let ventaAyer = PEDRO_VENTA_BASE;
for (let f = '2026-08-15'; f <= PEDRO_FIN; f = addDays(f, 1)) {
  if (PEDRO_SIN_REGISTRO.has(f)) continue;
  const dd = Number(f.slice(8, 10));
  const hoy = f === PEDRO_FIN;
  // venta al contado del día (el 14/11 solo la mañana)
  let factor = PEDRO_SEMANA[dayOfWeek(f)] * ((dd >= 14 && dd <= 16) || dd >= 28 || dd === 1 ? 1.06 : 1);
  if (f >= '2026-11-01') factor *= 1.04;
  let venta = Math.round(PEDRO_VENTA_BASE * factor * (1 + (rng() - 0.5) * 0.16) * 10) / 10;
  if (hoy) venta = Math.round(venta * 0.22 * 10) / 10;
  // parte de lo que trae Andina (bebidas; panetón desde la quincena de octubre)
  const enVentana = f >= VENTANA_VENTA_ESPERADA[0] && f <= VENTANA_VENTA_ESPERADA[1];
  let objetivoAndina = venta * (f >= '2026-10-15' ? 0.205 : 0.19) * (1 + (rng() - 0.5) * 0.3);
  if (f === VENTANA_VENTA_ESPERADA[1]) objetivoAndina = ANDINA_VENDIDO_OBJETIVO - andinaVentana - 19.5; // 19.50 = 3 cervezas de BOR-7791
  objetivoAndina = Math.min(Math.max(objetivoAndina, venta * 0.1), venta * 0.6);
  const lineasAndina = lineasHasta(objetivoAndina, f >= '2026-10-15' ? prodAndina : prodAndinaSinPaneton);
  const valorAndina = valorPedro(lineasAndina);
  if (enVentana) andinaVentana += valorAndina;
  const lineasResto = canastaExacta(cents(venta) - cents(valorAndina), prodResto);
  const lineas = fusionarLineas([...lineasAndina.map((l) => ({ prod: l.prod, cantidad: l.cantidad })), ...lineasResto]);
  planPedro.push({ fecha: f, hora: hoy ? '09:35' : '20:30', tipo: 'venta', cat: categoriaDominante(lineas), lineas,
    desc: `${hoy ? 'Ventas de la mañana' : 'Ventas del día'} en efectivo (${textoLineas(lineas.slice(0, 4))}…)` });
  // reposición al contado (mañana): ~47 % de lo vendido ayer; el 14/11 solo pan y lácteos
  let compra = Math.round(ventaAyer * PEDRO_RATIO(f) * (1 + (rng() - 0.5) * 0.24) * 10) / 10;
  if (f === '2026-11-08') compra = 380.0; // BOR-7792: la foto decía 330 y Pedro corrigió a 380
  if (hoy) compra = Math.round(ventaAyer * 0.14 * 10) / 10;
  planPedro.push({ fecha: f, hora: hoy ? '07:10' : '09:15', tipo: 'compra', cat: 'CAT-07', monto: compra, ajustable: f < '2026-09-13',
    desc: hoy ? 'Pan y lácteos del día al contado' : f === '2026-11-08' ? 'Compra de mercadería al contado (abarrotes)' : 'Reposición del día al contado' });
  if (PEDRO_COMPRA_MES[f]) {
    planPedro.push({ fecha: f, hora: '10:30', tipo: 'compra', cat: 'CAT-07', monto: PEDRO_COMPRA_MES[f],
      desc: 'Compra grande del mes en el mercado mayorista, al contado' });
  }
  if (!hoy) ventaAyer = venta;
  // retiros sueltos para la casa (sin vínculo al sueldo). Noviembre se arma aparte (+700 sobre lo usual).
  if (f < '2026-11-01' && chance(0.27)) {
    planPedro.push({ fecha: f, hora: '20:15', tipo: 'retiro_personal', cat: 'CAT-13', monto: pick([40, 50, 50, 60, 80, 100, 120]),
      desc: pick(['Saqué para la casa', 'Retiro para gastos de la casa', 'Saqué para el mercado de la casa', 'Retiro para pasajes y colegio']) });
  }
  // gastos chicos del negocio (bolsas, gas, mototaxi)
  if (dayOfWeek(f) === 1 && !hoy) planPedro.push({ fecha: f, hora: '15:00', tipo: 'gasto_negocio', cat: 'CAT-16', monto: pick([18, 22, 25, 28, 32]), desc: 'Bolsas y útiles de limpieza' });
  if (dd === 20 && !hoy) planPedro.push({ fecha: f, hora: '15:20', tipo: 'gasto_negocio', cat: 'CAT-16', monto: 48, desc: 'Balón de gas para el local' });
  if (dayOfWeek(f) === 4 && chance(0.5)) planPedro.push({ fecha: f, hora: '16:00', tipo: 'gasto_negocio', cat: 'CAT-10', monto: pick([10, 12, 15]), desc: 'Mototaxi para traer mercadería' });
}
// gastos puntuales
planPedro.push({ fecha: '2026-09-08', hora: '14:00', tipo: 'gasto_negocio', cat: 'CAT-16', monto: 420, desc: 'Mantenimiento de la congeladora' });
planPedro.push({ fecha: '2026-11-04', hora: '16:00', tipo: 'gasto_negocio', cat: 'CAT-10', monto: 65, desc: 'Flete y bolsas para la campaña navideña' });

// Retiros de noviembre: lo usual al 14 (promedio del 1 al 14 de sep. y oct.) + S/ 700
const retirosPlan = (desde, hasta) => sum(planPedro.filter((x) => x.tipo === 'retiro_personal' && x.fecha >= desde && x.fecha <= hasta), (x) => cents(x.monto)) / 100;
const usualPedro = (retirosPlan('2026-09-01', '2026-09-14') + retirosPlan('2026-10-01', '2026-10-14')) / 2;
const retirosNov = [['2026-11-02', 150, 'Saqué para la casa'], ['2026-11-04', 80, 'Retiro para gastos de la casa'],
  ['2026-11-06', 250, 'Retiro personal extra no planificado'], ['2026-11-09', 120, 'Saqué para el mercado de la casa'],
  ['2026-11-11', 200, 'Retiro extra para un gasto familiar'], ['2026-11-13', null, 'Saqué para la casa']];
const fijoNov = sum(retirosNov.filter((r) => r[1] !== null), (r) => r[1]);
retirosNov[retirosNov.length - 1][1] = Math.round((usualPedro + 700 - fijoNov) * 100) / 100;
if (!(retirosNov[retirosNov.length - 1][1] > 0)) throw new Error(`Pedro: retiro de cierre de noviembre no positivo (${usualPedro})`);
for (const [f, m, desc] of retirosNov) planPedro.push({ fecha: f, hora: '20:15', tipo: 'retiro_personal', cat: 'CAT-13', monto: m, desc });

// Pagos con fecha (vinculados): sueldo fijo, luz y agua, alquiler
for (const f of ['2026-08-30', '2026-09-30', '2026-10-30']) {
  planPedro.push({ fecha: f, hora: '20:00', tipo: 'retiro_personal', cat: 'CAT-13', monto: 1350, programado_id: 'PRG-0003',
    desc: `Sueldo fijo de ${NOMBRE_MES_PEDRO[Number(f.slice(5, 7))]}` });
}
for (const [f, m] of [['2026-08-16', 168.4], ['2026-09-16', 176.9], ['2026-10-16', 183.3]]) {
  planPedro.push({ fecha: f, hora: '15:00', tipo: 'gasto_negocio', cat: 'CAT-08', monto: m, programado_id: 'PRG-0001',
    desc: `Luz y agua del local (${NOMBRE_MES_PEDRO[Number(f.slice(5, 7))]})` });
}
for (const f of ['2026-08-28', '2026-09-28', '2026-10-28']) {
  planPedro.push({ fecha: f, hora: '15:30', tipo: 'gasto_negocio', cat: 'CAT-09', monto: 350, programado_id: 'PRG-0002',
    desc: `Alquiler del local (${NOMBRE_MES_PEDRO[Number(f.slice(5, 7))]})` });
}

// Cuadre: el saldo del 14/11 (antes de las 10:00) es S/ 2 340.00. El residuo se reparte en la reposición de agosto y
// del 1 al 12 de septiembre (días anteriores al 13/09: no entran al forecast, a su backtest ni a las alertas).
const signoPedro = (x) => (['venta', 'cobro_fiado', 'prestamo_recibido', 'otro_ingreso'].includes(x.tipo) ? 1 : -1);
const montoPlan = (x) => (x.lineas ? valorPedro(x.lineas) : x.monto);
const fijosPedroC = -sum(pagosDeudaPedro, (p) => cents(p.monto)) - cents(20 * 3) + sum(fiadosPedroHist, (f) => cents(f.monto)) + cents(22); // pedidos, RUS, cobros y BOR-7791
const saldoPlanC = cents(1800) + sum(planPedro, (x) => signoPedro(x) * cents(montoPlan(x))) + fijosPedroC;
const ajustables = planPedro.filter((x) => x.ajustable);
let residuoC = saldoPlanC - cents(2340);
const residuoInicialPedro = residuoC / 100;
for (let k = 0; k < ajustables.length; k++) {
  const parte = Math.round(residuoC / (ajustables.length - k) / 10) * 10;
  ajustables[k].monto = fromCents(cents(ajustables[k].monto) + parte);
  residuoC -= parte;
}
if (residuoC !== 0) throw new Error(`Pedro: no cuadra el saldo (residuo ${residuoC})`);
if (ajustables.some((x) => !(x.monto > 50))) throw new Error(`Pedro: la reposición de agosto quedó muy baja (residuo ${residuoInicialPedro})`);

for (const x of planPedro) {
  const esBor7792 = x.fecha === '2026-11-08' && x.tipo === 'compra' && x.hora === '09:15';
  addTx({
    empresa_id: 'EMP-0001',
    fecha_hora: ts(x.fecha, x.hora),
    tipo: x.tipo,
    categoria_id: x.cat,
    descripcion: x.desc,
    monto: x.lineas ? null : x.monto,
    metodo_pago: 'efectivo',
    canal: esBor7792 ? 'foto' : x.tipo === 'venta' && Number(x.fecha.slice(8, 10)) % 3 === 0 ? 'foto' : x.tipo === 'gasto_negocio' && x.programado_id ? 'texto' : 'voz',
    borrador_id: esBor7792 ? 'BOR-7792' : null,
    fue_corregida: esBor7792,
    creado_en: esBor7792 ? ts(x.fecha, '11:12') : null,
    programado_id: x.programado_id || null,
    lineas: x.lineas || [],
  });
}

// Pagos de los pedidos a crédito (a su vencimiento o un día antes)
for (const p of pagosDeudaPedro) {
  addTx({ empresa_id: 'EMP-0001', fecha_hora: `${p.fecha}T${p.hora}:00-05:00`, tipo: 'pago_proveedor', categoria_id: 'CAT-07',
    descripcion: p.desc, monto: p.monto, metodo_pago: 'efectivo', canal: 'voz', deuda_id: p.deuda });
}

// Cobros de fiados históricos (los 10 pagados)
for (const f of fiadosPedroHist) {
  addTx({
    empresa_id: 'EMP-0001',
    fecha_hora: `${f.f_pago}T17:00:00-05:00`,
    tipo: 'cobro_fiado',
    categoria_id: 'CAT-14',
    descripcion: `Cobro de fiado de ${clientesPedro.find((c) => c.id === f.cli).nombre} en efectivo`,
    monto: f.monto,
    metodo_pago: 'efectivo',
    canal: 'voz',
    fiado_id: f.id,
  });
}

// Nuevo RUS: paga S/ 20 de Cat. 1 aunque, por sus ventas, le tocaría S/ 50
for (const [f, imp, per] of [['2026-09-14T12:00:00-05:00', 'IMP-0007', 'agosto'], ['2026-10-15T12:00:00-05:00', 'IMP-0008', 'septiembre'],
  ['2026-11-12T11:20:00-05:00', 'IMP-0009', 'octubre']]) {
  addTx({ empresa_id: 'EMP-0001', fecha_hora: f, tipo: 'pago_impuesto', categoria_id: 'CAT-11',
    descripcion: `Pago Nuevo RUS ${per} (declaró Cat. 1 S/ 20 aunque sus ventas pasan de S/ 5 000)`, monto: 20.0,
    metodo_pago: 'efectivo', canal: 'texto', impuesto_id: imp });
}

// BOR-7791 (10/11): "bendi 3 chelas y pan", corregido a S/ 22.00 = 3 cervezas (19.50) + 1 pan francés (2.50)
addTx({
  empresa_id: 'EMP-0001',
  borrador_id: 'BOR-7791',
  fecha_hora: ts('2026-11-10', '14:20'),
  tipo: 'venta',
  categoria_id: 'CAT-01',
  descripcion: '3 cervezas y pan',
  metodo_pago: 'efectivo',
  canal: 'voz',
  confianza: 0.68,
  fue_corregida: true,
  creado_en: ts('2026-11-10', '14:21'),
  lineas: [
    { prod: prodPedro('PRD-0031'), cantidad: 3 },
    { prod: prodPedro('PRD-0001'), cantidad: 1 },
  ],
});
// (No hay venta de "2 cervezas" el 14/11: la dice Pedro en vivo durante la demo, a las 10:42.)

// Verificación de la venta esperada de lo que trae Andina (misma cuenta que chequeo.venta_esperada del backend)
{
  const ventaProdDia = new Map();
  const txIds = new Set(tables.transacciones.filter((t) => t.empresa_id === 'EMP-0001' && t.tipo === 'venta').map((t) => t.transaccion_id));
  const fechaTx = new Map(tables.transacciones.map((t) => [t.transaccion_id, t.fecha_hora.slice(0, 10)]));
  for (const det of tables.detalle_transaccion) {
    if (!txIds.has(det.transaccion_id)) continue;
    const f = fechaTx.get(det.transaccion_id);
    if (!ventaProdDia.has(f)) ventaProdDia.set(f, new Map());
    const m = ventaProdDia.get(f);
    m.set(det.producto_id, (m.get(det.producto_id) || 0) + cents(det.subtotal));
  }
  const ve = ventaEsperadaBackend(ventaProdDia, ANDINA, '2026-08-15', FECHA_DEMO, '2026-11-30');
  if (ve !== 2000) throw new Error(`Pedro: venta esperada de Andina = ${ve} (debe ser 2000: exceso del pedido S/ 400)`);
  if (process.env.DEBUG_PEDRO) console.error('Pedro: residuo repartido en agosto', residuoInicialPedro, 'usual retiros', usualPedro, 'venta esperada Andina', ve);
}

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

// Alertas de Pedro: las que calcula el backend sobre estos mismos datos (data/demo_pedro_backend.json, ver
// data/pipeline_python/exportar_demo_backend.py), guardadas como si la evaluación de las 08:05 las hubiera persistido.
// Máximo 2 notificadas al día (preferencias_alertas): las demás quedan con enviada_en = null.
const DEMO_BACKEND_PATH = path.join(__dirname, 'demo_pedro_backend.json');
if (!fs.existsSync(DEMO_BACKEND_PATH)) {
  throw new Error('Falta data/demo_pedro_backend.json: corre data/pipeline_python/exportar_demo_backend.py (ver su docstring) y vuelve a generar.');
}
const DEMO_BACKEND = JSON.parse(fs.readFileSync(DEMO_BACKEND_PATH, 'utf8'));
const MODELO_RIESGO = 'riesgo-atraso-baseline-0.1.0'; // backend/app/services/finanzas/riesgo.py (MODELO + VERSION), /health
const ID_ALERTA_PEDRO = { faltante_caja: 'ALR-0007', fiado_vencido: 'ALR-0008', pedido_excesivo: 'ALR-0009', retiro_excesivo: 'ALR-0010',
  obligacion_proxima: 'ALR-0011', gasto_inusual: 'ALR-0012', meta_lograda: 'ALR-0013' };
const PRIORIDAD_TIPO = { faltante_caja: 1, pedido_excesivo: 2, retiro_excesivo: 3, obligacion_proxima: 4, gasto_inusual: 5, fiado_vencido: 6, meta_lograda: 7 };
{
  const usados = new Set();
  [...DEMO_BACKEND.alertas].sort((a, b) => PRIORIDAD_TIPO[a.tipo] - PRIORIDAD_TIPO[b.tipo]).forEach((a, k) => {
    const id = ID_ALERTA_PEDRO[a.tipo] && !usados.has(ID_ALERTA_PEDRO[a.tipo]) ? ID_ALERTA_PEDRO[a.tipo] : padId('ALR', 20 + k, 4);
    usados.add(id);
    const creada = ts(FECHA_DEMO, '08:05', String(10 * k).padStart(2, '0'));
    tables.alertas.push({
      alerta_id: id, empresa_id: 'EMP-0001', tipo: a.tipo, prioridad: PRIORIDAD_TIPO[a.tipo], fecha_evento: a.fecha_evento,
      monto: a.monto === null ? null : fmtMoney(a.monto), probabilidad: a.probabilidad === null ? null : fmtProb(a.probabilidad),
      nivel_riesgo: a.nivel_riesgo, causas: JSON.stringify(a.causas), accion_sugerida: a.accion_sugerida, entidad_tipo: a.entidad_tipo,
      entidad_id: a.entidad_id, canal: k < 2 ? 'whatsapp' : 'app', estado: 'activa', accion_tomada: null, fecha_accion: null,
      creada_en: creada, enviada_en: k < 2 ? ts(FECHA_DEMO, '08:05', String(10 * k + 5).padStart(2, '0')) : null,
      modelo_version: a.tipo === 'faltante_caja' ? MODELO_FORECAST : a.tipo === 'fiado_vencido' ? MODELO_RIESGO : MODELO_REGLAS,
    });
  });
}

tables.consentimientos.push({
  consentimiento_id: 'CNS-0001',
  empresa_id: 'EMP-0001',
  alcance: JSON.stringify(['resumen_12_meses', 'score']),
  activo: false,
  fecha_otorgado: null,
  vigencia_hasta: null,
  fecha_revocado: null,
});

// Eventos (ground truth) de Pedro: retiros de más, sobrecompra pre-campaña y clientes que no pagan
tables.eventos.push(
  {
    evento_id: 'EVT-0001',
    empresa_id: 'EMP-0001',
    tipo_evento: 'retiro_excesivo',
    fecha_inicio: '2026-11-02',
    fecha_fin: '2026-11-13',
    descripcion: `Del 1 al 13/11 sacó S/ ${fmtMoney(usualPedro + 700)} para la casa: S/ 700 más que lo usual a esa altura del mes (S/ ${fmtMoney(usualPedro)}), además de su sueldo fijo de S/ 1 350 a fin de mes`,
  },
  {
    evento_id: 'EVT-0002',
    empresa_id: 'EMP-0001',
    tipo_evento: 'alza_proveedor',
    fecha_inicio: '2026-11-12',
    fecha_fin: null, // en curso: los pagos vencen el 27/11 (El Sol) y el 30/11 (Andina), después de "hoy"
    descripcion: `Sobrecompra pre-Campaña Navideña a crédito: PED-0012 a Distribuidora Andina (S/ 2 400, el doble de su pedido de octubre) y S/ ${fmtMoney(PEDRO_EL_SOL_NOV)} a Abarrotes El Sol; además paga el Nuevo RUS de S/ 20 aunque le tocaría S/ 50`,
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

// Predicciones de saldo de Pedro (30 días: 2026-11-15 al 2026-12-14): la salida real del backend al 14/11 con los dos
// motores (LightGBM y baseline naive estacional), leída de data/demo_pedro_backend.json.
let predSaldoSeq = 1;
for (const motor of ['lightgbm', 'baseline']) {
  const fc = DEMO_BACKEND.forecast[motor];
  for (const p of fc.serie) {
    tables.predicciones_saldo.push({
      prediccion_id: padId('PRS', predSaldoSeq++, 5),
      empresa_id: 'EMP-0001',
      fecha_corte: DEMO_BACKEND.fecha_corte,
      fecha_objetivo: p.fecha,
      p10: fmtMoney(p.p10),
      p50: fmtMoney(p.p50),
      p90: fmtMoney(p.p90),
      modelo_version: motor === 'lightgbm' ? fc.modelo_version : `${fc.modelo.replace(/^forecast-/, '')}-${fc.modelo_version}`,
      creado_en: ts(FECHA_DEMO, '09:00', '05'),
    });
  }
}
// Las predicciones de fiado de Pedro salen con el mismo baseline que las demás empresas (sección 7).

// El score de salud de todas las empresas (Pedro incluido) se calcula al final con la fórmula del backend.

// =============================================================================
// 3. CATÁLOGOS POR RUBRO. Cada fila: [nombre, categoría, precio de venta, costo (o null), alias].
//    Los precios son múltiplos de 0.10: el subtotal (cantidad entera x precio) es siempre exacto al céntimo.
// =============================================================================
const CATALOGOS = {
  bodega: [
    ['Pan francés (bolsa 10 unid)', 'CAT-03', 2.5, 1.8, ['pan', 'bolsa de pan']],
    ['Leche evaporada tarro 400g', 'CAT-03', 4.5, 3.6, ['leche', 'tarro de leche']],
    ['Arroz extra 1 kg', 'CAT-02', 4.2, 3.3, ['arroz', 'kilo de arroz']],
    ['Aceite vegetal 1 L', 'CAT-02', 8.5, 6.8, ['aceite', 'botella de aceite']],
    ['Azúcar rubia 1 kg', 'CAT-02', 3.8, 3.0, ['azucar', 'kilo de azucar']],
    ['Fideos tallarín 500g', 'CAT-02', 2.8, 2.1, ['fideos', 'tallarin']],
    ['Huevos pardos (1 kg)', 'CAT-03', 9.5, 7.8, ['huevos', 'kilo de huevo']],
    ['Gaseosa familiar 1.5 L', 'CAT-01', 7.5, 5.6, ['gaseosa', 'gaseosas']],
    ['Agua mineral 625 ml', 'CAT-01', 2.0, 1.2, ['agua', 'botella de agua']],
    ['Atún en trozos lata', 'CAT-02', 5.5, 4.2, ['atun', 'lata de atun']],
    ['Detergente en polvo 500g', 'CAT-04', 6.0, 4.5, ['detergente']],
    ['Papel higiénico paquete x4', 'CAT-04', 5.2, 3.9, ['papel', 'papel higienico']],
    ['Jabón de lavar barra', 'CAT-04', 3.0, 2.1, ['jabon', 'barra de jabon']],
    ['Galletas paquete x6', 'CAT-05', 3.5, 2.5, ['galleta', 'galletas']],
    ['Papas fritas snack', 'CAT-05', 2.5, 1.7, ['papitas', 'snack']],
    ['Mantequilla pote 200g', 'CAT-03', 6.8, 5.2, ['mantequilla']],
    ['Queso fresco 250g', 'CAT-03', 7.0, 5.4, ['queso', 'queso fresco']],
    ['Menestra lenteja 500g', 'CAT-02', 4.0, 3.1, ['lenteja', 'menestra']],
    ['Jugo néctar 1 L', 'CAT-01', 4.8, 3.6, ['jugo']],
    ['Cerveza 620 ml', 'CAT-01', 6.5, 4.8, ['chela', 'cerveza', 'cervezas']],
    ['Gaseosa personal 500 ml', 'CAT-01', 2.5, 1.7, ['gaseosita', 'personal']],
    ['Chocolate barra', 'CAT-05', 1.5, 1.0, ['chocolate', 'barrita']],
    ['Yogurt botella 1 L', 'CAT-03', 7.5, 6.0, ['yogurt']],
    ['Sal yodada 1 kg', 'CAT-02', 1.8, 1.3, ['sal']],
    ['Harina preparada 1 kg', 'CAT-02', 4.0, 3.0, ['harina']],
    ['Lavavajilla 500 ml', 'CAT-04', 6.5, 4.8, ['lavavajilla', 'lava platos']],
  ],
  restaurante: [
    ['Menú del día (entrada y segundo)', 'CAT-06', 9.0, 4.5, ['menu', 'menú del día']],
    ['Almuerzo ejecutivo', 'CAT-06', 12.0, 6.0, ['ejecutivo', 'almuerzo']],
    ['Pollo a la brasa 1/4', 'CAT-06', 14.0, 8.0, ['pollo', 'cuarto de pollo']],
    ['Ají de gallina', 'CAT-06', 13.0, 7.0, ['aji de gallina']],
    ['Caldo de gallina', 'CAT-06', 8.0, 4.0, ['caldo']],
    ['Desayuno pan con café', 'CAT-03', 6.0, 3.0, ['desayuno']],
    ['Sándwich de pollo', 'CAT-03', 5.0, 2.8, ['sandwich']],
    ['Postre del día', 'CAT-03', 4.0, 1.8, ['postre']],
    ['Jugo de fruta', 'CAT-01', 5.0, 2.0, ['jugo']],
    ['Gaseosa 500 ml', 'CAT-01', 3.5, 2.2, ['gaseosa']],
    ['Chicha morada vaso', 'CAT-01', 2.5, 0.8, ['chicha']],
    ['Cerveza 620 ml', 'CAT-01', 8.0, 5.5, ['chela', 'cerveza']],
  ],
  taller: [
    ['Cambio de aceite y filtro', 'CAT-06', 45.0, 28.0, ['cambio de aceite']],
    ['Alineamiento y balanceo', 'CAT-06', 60.0, 30.0, ['alineamiento']],
    ['Revisión de frenos', 'CAT-06', 35.0, 12.0, ['frenos']],
    ['Cambio de filtro de aire', 'CAT-06', 25.0, 15.0, ['filtro']],
    ['Mano de obra (hora)', 'CAT-06', 30.0, null, ['mano de obra']],
    ['Batería con instalación', 'CAT-06', 220.0, 170.0, ['bateria']],
    ['Lavado y engrase', 'CAT-06', 20.0, 8.0, ['engrase', 'lavado']],
    ['Cambio de llanta', 'CAT-06', 15.0, null, ['llanta']],
    ['Líquido de frenos', 'CAT-04', 12.0, 8.0, ['liquido de frenos']],
    ['Escobilla y limpiaparabrisas', 'CAT-04', 18.0, 11.0, ['escobilla']],
  ],
  distribuidora: [
    ['Arroz saco 50 kg', 'CAT-02', 160.0, 138.0, ['arroz saco', 'saco de arroz']],
    ['Azúcar saco 50 kg', 'CAT-02', 170.0, 150.0, ['azucar saco']],
    ['Aceite vegetal caja 12 L', 'CAT-02', 98.0, 84.0, ['aceite caja']],
    ['Fideos caja 20 paquetes', 'CAT-02', 58.0, 48.0, ['fideos caja']],
    ['Gaseosa caja 12 x 1.5 L', 'CAT-01', 72.0, 60.0, ['gaseosa caja']],
    ['Agua mineral caja 24 u', 'CAT-01', 36.0, 28.0, ['agua caja']],
    ['Leche evaporada caja 48 u', 'CAT-03', 190.0, 168.0, ['leche caja']],
    ['Detergente caja 12 u', 'CAT-04', 54.0, 44.0, ['detergente caja']],
    ['Galletas caja 24 paquetes', 'CAT-05', 62.0, 50.0, ['galletas caja']],
  ],
};

// Parámetros de cada rubro: venta diaria base, canastas por día, tamaño máximo de línea, % de costo, % de sueldo
const PERFIL_RUBRO = {
  bodega: { base: [150, 560], canastas: [2, 4], costo: [0.58, 0.7], sueldo: 0.13, nProd: [12, 16], fiados: [0, 14] },
  restaurante: { base: [380, 900], canastas: [4, 7], costo: [0.45, 0.56], sueldo: 0.16, nProd: [9, 12], fiados: [0, 4] },
  taller: { base: [300, 1000], canastas: [1, 3], costo: [0.34, 0.5], sueldo: 0.2, nProd: [7, 10], fiados: [3, 8] },
  distribuidora: { base: [900, 2300], canastas: [1, 3], costo: [0.82, 0.88], sueldo: 0.045, nProd: [7, 9], fiados: [6, 14] },
};

// Ponderación semanal por rubro (índice 1 = lunes … 7 = domingo)
const FACTOR_SEMANA = {
  bodega: { 1: 0.92, 2: 0.96, 3: 0.98, 4: 1.0, 5: 1.08, 6: 1.22, 7: 1.1 },
  restaurante: { 1: 0.78, 2: 0.9, 3: 0.95, 4: 1.0, 5: 1.12, 6: 1.3, 7: 1.4 },
  taller: { 1: 1.1, 2: 1.05, 3: 1.05, 4: 1.0, 5: 1.0, 6: 0.85, 7: 0.15 },
  distribuidora: { 1: 1.2, 2: 1.05, 3: 1.0, 4: 1.0, 5: 1.05, 6: 0.85, 7: 0.2 },
};

const PROVEEDORES_POOL = [
  'Distribuidora Unión', 'Mayorista Central', 'Comercial Pacífico', 'Alimentos del Valle', 'Bebidas Nacionales',
  'Abarrotes Santa Rosa', 'Lácteos Andinos', 'Importaciones Lima Sur', 'Distribuidora Los Pinos', 'Panificadora La Espiga',
  'Comercial El Sol', 'Repuestos Autoparts', 'Insumos Don Beto', 'Mayorista Villa María',
];
const CLIENTES_POOL = [
  'Sra. Juana', 'Don Carlos', 'Vecino Miguel', 'Sra. Bertha', 'Don Alberto', 'Joven Kevin', 'Sra. Gladis', 'Maestro Tito',
  'Vecina Patricia', 'Don Héctor', 'Sra. Rosario', 'Don Ernesto', 'Doña Pilar', 'Sr. Walter', 'Sra. Mery', 'Don Teófilo',
  'Vecino Jhon', 'Sra. Lidia', 'Don Fermín', 'Srta. Karina', 'Maestro Ramiro', 'Sra. Olga', 'Don Segundo', 'Doña Nelly',
  'Sr. Percy', 'Sra. Yesenia', 'Don Mauro', 'Vecina Flor', 'Joven Brayan', 'Sra. Amparo',
];
const BILLETERAS = ['billetera_a', 'billetera_b'];
const CONTRAPARTES_BILLETERA = [
  'Cliente Rosa M.', 'Cliente Juan P.', 'Cliente Lucía T.', 'Cliente Mario Q.', 'Cliente Ana R.', 'Cliente Pedro S.',
  'Cliente Carla V.', 'Cliente Luis H.', 'Cliente Elena C.', 'Cliente Diego A.',
];

// Empresas EMP-0003 a EMP-0030 (28 negocios). idx = número de empresa - 3.
const NEGOCIOS = [
  ['Bodega Mi Barrio', 'Lima Este', 'bodega'], ['Restaurante Sabor Criollo', 'Lima Este', 'restaurante'],
  ['Bodega El Progreso', 'Lima Este', 'bodega'], ['Bodega Los Olivos', 'Lima Norte', 'bodega'],
  ['Bodega Doña María', 'Lima Este', 'bodega'], ['Taller Mecánico El Pistón', 'Lima Sur', 'taller'],
  ['Bodega El Vecino', 'Lima Este', 'bodega'], ['Bodega La Familia', 'Lima Norte', 'bodega'],
  ['Pollería Sazón Norteño', 'Lima Este', 'restaurante'], ['Bodega Las Flores', 'Lima Este', 'bodega'],
  ['Distribuidora Villa Sur', 'Lima Sur', 'distribuidora'], ['Bodega Central Huaycán', 'Lima Este', 'bodega'],
  ['Taller Automotriz San Juan', 'Lima Este', 'taller'], ['Bodega El Trébol', 'Callao', 'bodega'],
  ['Bodega Los Andes', 'Lima Este', 'bodega'], ['Comedor La Esquina', 'Lima Norte', 'restaurante'],
  ['Bodega Virgen del Carmen', 'Lima Este', 'bodega'], ['Bodega El Ahorro', 'Lima Sur', 'bodega'],
  ['Bodega Chosica Express', 'Lima Este', 'bodega'], ['Taller Mecánico Canto Grande', 'Lima Este', 'taller'],
  ['Bodega Primavera', 'Lima Norte', 'bodega'], ['Bodega Ceres', 'Lima Este', 'bodega'],
  ['Restaurante Los Pinos', 'Lima Este', 'restaurante'], ['Bodega Horizonte', 'Lima Norte', 'bodega'],
  ['Distribuidora Doña Julia', 'Lima Este', 'distribuidora'], ['Bodega El Buen Vecino', 'Lima Sur', 'bodega'],
  ['Bodega Santa Clara', 'Lima Este', 'bodega'], ['Bodega SurAndina', 'Lima Este', 'bodega'],
];
const RUBRO_ID = { bodega: 'RUB-01', restaurante: 'RUB-02', taller: 'RUB-03', distribuidora: 'RUB-04' };

const redondeaA = (x, paso) => Math.round(x / paso) * paso;
const precio10 = (x) => Math.max(0.5, Math.round(x * 10) / 10);

// Catálogo de una empresa: subconjunto del catálogo del rubro con precios y costos algo distintos
let prodSeq = 100;
function construirCatalogo(rubro, n) {
  const pool = shuffle(CATALOGOS[rubro]).slice(0, n);
  return pool.map(([nombre, cat, pv, cu, alias]) => {
    const f = rubro === 'distribuidora' || rubro === 'taller' ? randFloat(0.96, 1.06, 3) : randFloat(0.95, 1.1, 3);
    const precio = rubro === 'distribuidora' ? Math.round(pv * f) : precio10(pv * f);
    let costo = cu === null ? null : rubro === 'distribuidora' ? Math.round(cu * f) : precio10(cu * f);
    if (costo !== null && costo >= precio) costo = precio10(precio * 0.85);
    return { id: padId('PRD', prodSeq++, 4), cat, nombre, alias, pv: precio, cu: costo };
  });
}

// Canasta aleatoria de cantidad entera (no exacta): líneas hasta llegar al valor objetivo
function canastaAleatoria(prods, pesos, objetivo, rubro) {
  const lineas = [];
  let valor = 0;
  let guardia = 0;
  while (valor < objetivo * 0.85 && guardia++ < 25) {
    const p = elegirPonderado(prods, pesos);
    const faltante = objetivo - valor;
    const qmax = Math.max(1, Math.min(rubro === 'distribuidora' ? 6 : 8, Math.round(faltante / p.pv)));
    const topeLinea = p.pv >= 100 ? 3 : p.pv >= 30 ? 4 : p.pv >= 10 ? 6 : 8;
    const cantidad = randInt(1, Math.max(1, Math.min(qmax, topeLinea)));
    lineas.push({ prod: p, cantidad });
    valor += cantidad * p.pv;
  }
  return fusionarLineas(lineas);
}

function elegirPonderado(items, pesos) {
  const total = sum(pesos);
  let r = rng() * total;
  for (let i = 0; i < items.length; i++) {
    r -= pesos[i];
    if (r <= 0) return items[i];
  }
  return items[items.length - 1];
}

const valorLineas = (lineas) => fromCents(sum(lineas, (l) => l.cantidad * cents(l.precio ?? l.prod.pv)));

// Ocurrencia de un movimiento programado (misma lógica que backend/app/services/finanzas/consultas.py)
function ocurreProg(p, fecha) {
  if (!p.activo && p.fecha_fin === null) return false;
  if (fecha < p.fecha_inicio || (p.fecha_fin !== null && fecha > p.fecha_fin)) return false;
  if (p.frecuencia === 'diaria') return true;
  if (p.frecuencia === 'semanal') return dayOfWeek(fecha) === (p.dia_semana || 6);
  const [anio, mes, dia] = fecha.split('-').map(Number);
  const ult = ultimoDiaMes(anio, mes);
  const base = p.dia_mes || 1;
  if (p.frecuencia === 'mensual') return dia === Math.min(base, ult);
  return dia === Math.min(base, ult) || dia === Math.min(base + 15, ult); // quincenal
}

function fechasEntre(desde, hasta) {
  const out = [];
  for (let d = desde; d <= hasta; d = addDays(d, 1)) out.push(d);
  return out;
}

// =============================================================================
// 4. ESPECIFICACIÓN DE CADA NEGOCIO (EMP-0002 a EMP-0030): volumen, rubro, fiado, billetera, sueldo, shocks…
// =============================================================================
let cliSeq = 200;
let prvSeq = 50;
let prgSeq = 10;
let fiaSeq = 100;
let deuSeq = 100;
let impSeq = 50;
let evtSeq = 10;
let alrSeq = 50;
let metSeq = 10;
let bilSeq = 200;
let cnsSeq = 2;
let ajuSeq = 4;

const SIN_RUC = new Set([2, 7, 11, 16, 20, 23]); // idx de negocios informales (sin RUC)
const AJUSTADOS = new Set([1, 5, 9, 13, 17, 21, 25]); // caja ajustada: compras altas, más episodios bajo el mínimo
const SHOCK_POR_IDX = (idx) =>
  idx % 6 === 0 ? 'retiro_excesivo'
  : idx % 6 === 3 ? 'alza_proveedor'
  : [1, 7, 13, 19, 25].includes(idx) ? 'mes_bajo'
  : [2, 14, 26].includes(idx) ? 'gasto_extra'
  : [4, 16].includes(idx) ? 'cliente_no_paga'
  : null;
const PRESTAMO_POR_IDX = (idx) =>
  idx % 6 === 0 ? 'gota_a_gota' : [9, 20].includes(idx) ? 'familiar' : [11, 22].includes(idx) ? 'entidad_financiera' : null;
const INGRESO_FIJO_IDX = new Set([4, 22]); // venta fija semanal a un comedor / institución

function construirSpec(empNum) {
  const seed = 42 * 100003 + empNum * 7919;
  useRng(seed);
  if (empNum === 2) {
    return {
      empNum, empId: 'EMP-0002', idx: -1, seed, nombre: 'Bodega Nueva Esperanza', zona: 'Lima Este', rubro: 'bodega',
      nTrab: 1, tieneRuc: true, fechaIni: '2026-11-12', saldoIni: 850, minOp: 500, base: 620, canastas: 3, nProd: 12,
      ratioCompra: 0.78, pCompra: 1, billeteraShare: 0, nFiados: 0, sueldo: null, luz: null, alquiler: null,
      shock: null, prestamo: null, ingresoFijo: false, ajustada: false, nuevo: true,
      retirosFijos: [{ fecha: '2026-11-13', monto: 150, desc: 'Retiro en efectivo para gastos mínimos de la casa' }],
      canalPesos: { voz: 0.7, texto: 0.1, foto: 0.1, manual: 0.1 }, consentimiento: false,
    };
  }
  const idx = empNum - 3;
  const [nombre, zona, rubro] = NEGOCIOS[idx];
  const perf = PERFIL_RUBRO[rubro];
  const base = redondeaA(perf.base[0] * Math.exp(rng() * Math.log(perf.base[1] / perf.base[0])), 10);
  const nTrab =
    rubro === 'restaurante' ? randInt(3, 5) : rubro === 'taller' ? randInt(2, 5)
    : rubro === 'distribuidora' ? randInt(3, 5) : base < 250 ? 1 : base < 380 ? randInt(1, 3) : randInt(2, 4);
  const ajustada = AJUSTADOS.has(idx);
  const ratioCompra = ajustada ? Math.min(0.9, perf.costo[1] + randFloat(-0.02, 0.01, 3)) : randFloat(perf.costo[0] - 0.04, perf.costo[1] - 0.04, 3);
  const usaBilletera = rubro === 'taller' || rubro === 'distribuidora' ? chance(0.25) : chance(0.5);
  const sinSueldo = chance(0.17) && SHOCK_POR_IDX(idx) !== 'retiro_excesivo'; // el shock de retiros necesita un sueldo fijo contra el cual compararse
  const mensualDeseado = Math.min(2800, Math.max(700, redondeaA(perf.sueldo * base * 30, 50)));
  const freq = pick(['semanal', 'semanal', 'semanal', 'quincenal', 'mensual']);
  let sueldo = null;
  if (!sinSueldo) {
    sueldo = freq === 'semanal'
      ? { frecuencia: 'semanal', monto: redondeaA(mensualDeseado / 4.33, 10), dia_semana: 6, dia_mes: null }
      : freq === 'quincenal'
      ? { frecuencia: 'quincenal', monto: redondeaA(mensualDeseado / 2, 10), dia_semana: null, dia_mes: pick([1, 5]) }
      : { frecuencia: 'mensual', monto: mensualDeseado, dia_semana: null, dia_mes: pick([28, 30]) };
    sueldo.mensualEquiv = mensualDeseado;
  }
  const nFiados = chance(0.15) ? 0 : randInt(Math.max(1, perf.fiados[0]), perf.fiados[1]);
  const spec = {
    empNum, empId: padId('EMP', empNum, 4), idx, seed, nombre, zona, rubro, nTrab,
    tieneRuc: !SIN_RUC.has(idx),
    fechaIni: addDays('2026-05-04', randInt(0, 96)),
    base, canastas: randInt(perf.canastas[0], perf.canastas[1]), nProd: randInt(perf.nProd[0], perf.nProd[1]),
    ratioCompra, ajustada,
    pCompra: rubro === 'restaurante' ? 0.85 : rubro === 'bodega' ? 0.55 : 0.35,
    billeteraShare: usaBilletera ? randFloat(0.06, 0.35, 3) : 0,
    nFiados, sueldo,
    luz: { monto: Math.max(60, redondeaA(randFloat(0.008, 0.02) * base * 30, 10)), dia_mes: randInt(5, 25) },
    alquiler: chance(0.7) ? { monto: Math.max(150, redondeaA(base * 30 * randFloat(0.02, 0.045), 50)), dia_mes: pick([1, 5, 10, 28]) } : null,
    internet: chance(0.3) ? { monto: randInt(6, 14) * 10, dia_mes: 12 } : null,
    shock: SHOCK_POR_IDX(idx), prestamo: PRESTAMO_POR_IDX(idx), ingresoFijo: INGRESO_FIJO_IDX.has(idx), nuevo: false,
    retirosFijos: [],
    canalPesos: { voz: randFloat(0.3, 0.5, 2), texto: randFloat(0.15, 0.3, 2), foto: randFloat(0.05, 0.2, 2), manual: randFloat(0.1, 0.3, 2) },
    consentimiento: chance(0.3),
  };
  spec.saldoIni = redondeaA(base * randFloat(2, 6), 50);
  spec.minOp = Math.max(400, redondeaA(base * (rubro === 'distribuidora' ? randFloat(0.5, 0.9) : randFloat(1.0, 1.8)), 50));
  return spec;
}

function canalAleatorio(spec) {
  const entries = Object.entries(spec.canalPesos);
  const canal = elegirPonderado(entries.map((e) => e[0]), entries.map((e) => e[1]));
  return { canal, confianza: canal === 'manual' ? null : randFloat(0.72, 0.98, 3) };
}

function horaAleatoria(rubro) {
  const tramos =
    rubro === 'restaurante' ? [[7, 10, 0.2], [11.5, 15.5, 0.65], [18, 21, 0.15]]
    : rubro === 'bodega' ? [[7.5, 10, 0.3], [12, 14.5, 0.2], [17, 21, 0.5]]
    : rubro === 'taller' ? [[8, 18, 1]]
    : [[7, 17, 1]];
  const [a, b] = elegirPonderado(tramos, tramos.map((t) => t[2]));
  const h = a + rng() * (b - a);
  return `${String(Math.floor(h)).padStart(2, '0')}:${String(Math.floor((h % 1) * 60)).padStart(2, '0')}`;
}
const hhmm = (h) => `${String(Math.floor(h)).padStart(2, '0')}:${String(Math.round((h % 1) * 60) % 60).padStart(2, '0')}`;

// Venta esperada hasta un vencimiento: misma fórmula que backend/app/services/finanzas/chequeo.py (venta_esperada)
function ventaEsperadaBackend(ventaProdDia, productosIds, primer, corte, vencimiento) {
  const diasHist = Math.min(28, daysBetween(primer, corte));
  const dias = Math.max(1, daysBetween(corte, vencimiento > corte ? vencimiento : addDays(corte, 1)));
  if (diasHist <= 0) return 0;
  let vendidoC = 0;
  for (let d = addDays(corte, -diasHist); d <= addDays(corte, -1); d = addDays(d, 1)) {
    const dia = ventaProdDia.get(d);
    if (!dia) continue;
    for (const id of productosIds) vendidoC += dia.get(id) || 0;
  }
  const x = (vendidoC / 100 / diasHist) * dias;
  const paso = x >= 1000 ? 100 : x >= 100 ? 10 : 1;
  return Math.round(x / paso) * paso;
}

function sumarMeses(fecha, k) {
  const [y, m, d] = fecha.split('-').map(Number);
  const total = y * 12 + (m - 1) + k;
  const anio = Math.floor(total / 12);
  const mes = (total % 12) + 1;
  return `${anio}-${String(mes).padStart(2, '0')}-${String(Math.min(d, ultimoDiaMes(anio, mes))).padStart(2, '0')}`;
}

const negociosSim = []; // resumen de cada empresa simulada (para alertas, score y saldo)
const saldoPorEmpresa = new Map(); // empId -> [{fecha, saldoC}]


const horaManana = () => hhmm(7.5 + rng() * 2.4); // 07:30 – 09:54: todo el 14/11 queda antes de la hora de corte
// =============================================================================
// 5. SIMULACIÓN DE UN NEGOCIO (ventas -> fiados y pedidos -> caja día por día)
// =============================================================================
function factorDia(spec, fecha, i) {
  const dow = dayOfWeek(fecha);
  const dd = Number(fecha.slice(8, 10));
  let f = FACTOR_SEMANA[spec.rubro][dow];
  if (spec.rubro === 'distribuidora') {
    if (dd <= 3 || (dd >= 15 && dd <= 17)) f *= 1.15; // los bodegueros reponen a inicio de mes y en quincena
  } else if (dd === 15 || dd === 16 || dd >= 30 || dd <= 2) {
    f *= 1.15; // quincena y fin de mes: cobran sueldos
  }
  f *= 1 + 0.0005 * i; // crecimiento suave
  if (fecha >= '2026-11-01') f *= 1.04; // arranque de la campaña navideña
  if (spec.shock === 'mes_bajo' && fecha >= '2026-10-25') f *= 0.78;
  return f * randFloat(0.9, 1.1, 3);
}

function simularNegocio(spec) {
  useRng(spec.seed + 1);
  if (process.env.DEBUG_SPEC) console.error(spec.empId, spec.rubro, 'base', spec.base, 'ratio', spec.ratioCompra.toFixed(2), 'ajust', spec.ajustada, 'sueldo', spec.sueldo && spec.sueldo.frecuencia + ':' + spec.sueldo.monto, 'minOp', spec.minOp, 'saldoIni', spec.saldoIni, 'shock', spec.shock, 'ini', spec.fechaIni);
  const E = spec.empId;
  const perf = PERFIL_RUBRO[spec.rubro];
  const fechas = fechasEntre(spec.fechaIni, FECHA_DEMO);
  const nuevo = spec.nuevo;

  // ── empresa y preferencias ──
  tables.empresas.push({
    empresa_id: E,
    rubro_id: RUBRO_ID[spec.rubro],
    nombre_ficticio: spec.nombre,
    telefono_whatsapp: `+5190000${String(spec.empNum).padStart(4, '0')}`,
    zona: spec.zona,
    n_trabajadores: spec.nTrab,
    tiene_ruc: spec.tieneRuc,
    ruc: spec.tieneRuc ? generarRuc10(spec.empNum) : null,
    regimen_tributario: spec.tieneRuc ? 'nuevo_rus' : null,
    saldo_inicial: fmtMoney(spec.saldoIni),
    fecha_saldo_inicial: spec.fechaIni,
    minimo_operativo: fmtMoney(spec.minOp),
    fecha_alta: ts(spec.fechaIni, '08:00'),
  });
  const canalesPref = pick([['whatsapp'], ['whatsapp'], ['whatsapp', 'app'], ['app'], ['whatsapp', 'email']]);
  const prefs = {
    empresa_id: E,
    canales: JSON.stringify(canalesPref),
    max_por_dia: pick([1, 2, 2, 2, 3]),
    silencio_desde: pick(['21:00', '21:00', '22:00']),
    silencio_hasta: pick(['07:00', '07:00', '06:30', '08:00']),
    resumen_semanal: chance(0.8),
  };
  tables.preferencias_alertas.push(prefs);

  // ── catálogo, clientes y proveedores ──
  const prods = nuevo ? construirCatalogo('bodega', 12) : construirCatalogo(spec.rubro, spec.nProd);
  const pesos = prods.map((_, i) => 1 / Math.pow(i + 1, 0.8));
  for (const p of prods) {
    tables.productos.push({
      producto_id: p.id, empresa_id: E, categoria_id: p.cat, nombre: p.nombre, alias: JSON.stringify(p.alias),
      precio_venta: fmtMoney(p.pv), costo_unitario: p.cu !== null ? fmtMoney(p.cu) : null, activo: true,
    });
  }
  const nCli = spec.nFiados > 0 ? randInt(3, 6) : randInt(2, 3);
  const nombresCli = shuffle(CLIENTES_POOL).slice(0, nCli);
  const clientes = nombresCli.map((nombre, c) => {
    const perfil = elegirPonderado(['puntual', 'ocasional', 'moroso'], [0.5, 0.3, 0.2]);
    const cli = { id: padId('CLI', cliSeq++, 4), nombre, perfil };
    tables.clientes.push({
      cliente_id: cli.id, empresa_id: E, nombre_ficticio: nombre,
      alias: JSON.stringify([...new Set([nombre.toLowerCase(), nombre.split(' ').slice(-1)[0].toLowerCase()])]),
      telefono_ficticio: `+5191${String(cliSeq).padStart(6, '0')}`, perfil_pago: perfil,
      creado_en: ts(addDays(spec.fechaIni, c), '09:00'),
    });
    return cli;
  });
  const nPrv = Math.max(2, Math.min(3, Math.floor(prods.length / 4)));
  const repartoProd = shuffle(prods);
  const proveedores = [];
  for (let k = 0; k < nPrv; k++) {
    const nombre = PROVEEDORES_POOL[(spec.empNum * 3 + k * 5) % PROVEEDORES_POOL.length];
    const plazo = k === 0 ? 15 : pick([7, 15, 30]);
    const prv = { id: padId('PRV', prvSeq++, 4), nombre, plazo, prods: repartoProd.filter((_, i) => i % nPrv === k) };
    tables.proveedores.push({
      proveedor_id: prv.id, empresa_id: E, nombre_ficticio: nombre,
      telefono_ficticio: `+5192${String(prvSeq).padStart(6, '0')}`, plazo_pago_dias: plazo,
    });
    proveedores.push(prv);
  }

  // ── movimientos programados ──
  const progs = [];
  const nuevoProg = (desc, cat, tipo, monto, frecuencia, dia_semana, dia_mes, es_sueldo) => {
    const p = {
      programado_id: padId('PRG', prgSeq++, 4), empresa_id: E, categoria_id: cat, tipo, descripcion: desc,
      monto: fmtMoney(monto), frecuencia, dia_semana, dia_mes, es_sueldo, fecha_inicio: spec.fechaIni, fecha_fin: null, activo: true,
    };
    tables.movimientos_programados.push(p);
    progs.push(p);
    return p;
  };
  const prgSueldo = spec.sueldo
    ? nuevoProg(`sueldo fijo del dueño (S/ ${spec.sueldo.mensualEquiv} al mes)`, 'CAT-13', 'egreso', spec.sueldo.monto,
        spec.sueldo.frecuencia, spec.sueldo.dia_semana, spec.sueldo.dia_mes, true)
    : null;
  const prgLuz = spec.luz ? nuevoProg('luz y agua del local', 'CAT-08', 'egreso', spec.luz.monto, 'mensual', null, spec.luz.dia_mes, false) : null;
  const prgAlq = spec.alquiler ? nuevoProg('alquiler del local', 'CAT-09', 'egreso', spec.alquiler.monto, 'mensual', null, spec.alquiler.dia_mes, false) : null;
  const prgNet = spec.internet ? nuevoProg('internet y celular', 'CAT-08', 'egreso', spec.internet.monto, 'mensual', null, spec.internet.dia_mes, false) : null;
  const prgIng = spec.ingresoFijo
    ? nuevoProg('venta fija semanal a un comedor', 'CAT-06', 'ingreso', redondeaA(spec.base * 0.8, 10), 'semanal', 2, null, false)
    : null;
  const gastosFijos = [prgLuz, prgAlq, prgNet].filter(Boolean);

  // ── fiados planificados (venta a crédito + cobros) ──
  const fiados = [];
  const rangoFiado = { bodega: [20, 120], restaurante: [40, 150], taller: [120, 600], distribuidora: [150, 900] }[spec.rubro];
  const planFiado = (cli, fFiado, valor, forzarImpago = false) => {
    const lineas = canastaAleatoria(prods, pesos, valor, spec.rubro);
    const monto = valorLineas(lineas);
    const compromiso = addDays(fFiado, pick([7, 10, 14, 15, 21]));
    const fia = {
      id: padId('FIA', fiaSeq++, 4), cli, fecha: fFiado, lineas, montoC: cents(monto), compromiso,
      canal: pick(['voz', 'foto', 'texto']), pagos: [], hora: horaAleatoria(spec.rubro),
    };
    let ultima = null;
    let partes = 1;
    if (cli.perfil === 'puntual') { ultima = addDays(compromiso, -randInt(0, 2)); partes = chance(0.2) ? 2 : 1; }
    else if (cli.perfil === 'ocasional') { ultima = addDays(compromiso, randInt(-1, 9)); partes = chance(0.4) ? 2 : 1; }
    else if (!chance(0.35)) { ultima = addDays(compromiso, randInt(5, 22)); partes = randInt(1, 3); }
    if (fia.montoC < 300 * partes) partes = 1;
    if (forzarImpago) ultima = null;
    if (ultima !== null) {
      if (ultima <= fFiado) ultima = addDays(fFiado, 1);
      let acumC = 0;
      for (let k = 1; k <= partes; k++) {
        const fecha = k === partes ? ultima : addDays(fFiado, randInt(1, Math.max(1, daysBetween(fFiado, ultima) - 1)));
        const montoC = k === partes ? fia.montoC - acumC : Math.min(Math.max(100, Math.round((fia.montoC * randFloat(0.35, 0.6, 2)) / 50) * 50), fia.montoC - acumC - 100 * (partes - k));
        if (montoC <= 0) continue;
        acumC += montoC;
        fia.pagos.push({ fecha, montoC });
      }
      fia.pagos.sort((a, b) => (a.fecha < b.fecha ? -1 : 1));
    }
    fiados.push(fia);
  };
  for (let k = 0; k < spec.nFiados; k++) {
    const cli = pick(clientes);
    const fFiado = fechas[randInt(8, Math.max(9, fechas.length - 3))];
    planFiado(cli, fFiado, randFloat(rangoFiado[0], rangoFiado[1], 0));
  }
  if (spec.shock === 'cliente_no_paga') {
    const moroso = clientes.find((c) => c.perfil === 'moroso') || clientes[0];
    planFiado(moroso, '2026-10-24', spec.base * 1.3, true);
    planFiado(moroso, '2026-11-03', spec.base * 0.9, true);
  }
  fiados.sort((a, b) => (a.fecha < b.fecha ? -1 : a.fecha > b.fecha ? 1 : a.id < b.id ? -1 : 1));

  // ── ventas por día (cada venta es una canasta de varios productos de cantidad entera) ──
  const constancia = nuevo ? 1 : randFloat(0.55, 0.98, 3);
  const ventasDia = new Map();
  const ventaProdDia = new Map(); // fecha -> Map(producto -> céntimos)
  const acumularProd = (fecha, lineas) => {
    if (!ventaProdDia.has(fecha)) ventaProdDia.set(fecha, new Map());
    const m = ventaProdDia.get(fecha);
    for (const l of lineas) m.set(l.prod.id, (m.get(l.prod.id) || 0) + l.cantidad * cents(l.prod.pv));
  };
  const ventaMesC = new Map();
  fechas.forEach((fecha, i) => {
    const f = factorDia(spec, fecha, i);
    const dow = dayOfWeek(fecha);
    const noRegistra = !nuevo && fecha !== FECHA_DEMO && !chance(dow === 7 ? constancia * 0.85 : constancia);
    const baskets = [];
    if (!noRegistra) {
      const K = Math.max(1, Math.min(spec.canastas * 2, Math.round(spec.canastas * Math.sqrt(f))));
      for (let j = 0; j < K; j++) {
        const objetivo = ((spec.base * f) / K) * randFloat(0.8, 1.2, 2);
        const lineas = canastaAleatoria(prods, pesos, objetivo, spec.rubro);
        const total = valorLineas(lineas);
        const metodo = total <= 400 && chance(spec.billeteraShare) ? 'billetera_digital' : 'efectivo';
        baskets.push({ hora: fecha === FECHA_DEMO ? horaManana() : horaAleatoria(spec.rubro), lineas, total, metodo });
        acumularProd(fecha, lineas);
        ventaMesC.set(mesDe(fecha), (ventaMesC.get(mesDe(fecha)) || 0) + cents(total));
      }
    }
    ventasDia.set(fecha, baskets);
  });
  for (const fia of fiados) {
    acumularProd(fia.fecha, fia.lineas);
    ventaMesC.set(mesDe(fia.fecha), (ventaMesC.get(mesDe(fia.fecha)) || 0) + fia.montoC);
  }
  const ventaProv = (prodIds, desde, hasta) => {
    let c = 0;
    for (let d = desde; d <= hasta; d = addDays(d, 1)) {
      const dia = ventaProdDia.get(d);
      if (dia) for (const id of prodIds) c += dia.get(id) || 0;
    }
    return c / 100;
  };

  // ── pedidos a proveedores (deudas a crédito) ──
  const deudas = []; // {id, tipo, ..., obligaciones:[{fecha,montoC}], pagos:[], pagadoC}
  const lineasPedido = (prodsProv, objetivo, todos) => {
    const sel = todos ? prodsProv : shuffle(prodsProv).slice(0, Math.max(2, Math.ceil(prodsProv.length * 0.6)));
    const shares = sel.map(() => randFloat(0.5, 1.5, 2));
    const totalShare = sum(shares);
    return sel.map((p, i) => {
      const unit = p.cu !== null ? p.cu : precio10(p.pv * 0.76);
      return { prod: p, cantidad: Math.max(1, Math.round((objetivo * shares[i]) / totalShare / unit)), precio: unit, costo: p.cu };
    });
  };
  const nuevoPedido = (prv, fecha, lineas, hora) => {
    const monto = fromCents(sum(lineas, (l) => l.cantidad * cents(l.precio)));
    const venc = addDays(fecha, prv.plazo);
    const d = {
      id: padId('PED', deuSeq++, 4), tipo: 'proveedor', prv, fecha, hora, lineas, montoC: cents(monto), venc,
      recibidoC: cents(monto), obligaciones: [], pagos: [], pagadoC: 0, canal: pick(['voz', 'texto', 'foto']),
    };
    deudas.push(d);
    return d;
  };
  if (!nuevo) {
    for (const prv of proveedores) {
      const nHist = chance(0.25) ? 0 : spec.rubro === 'bodega' ? randInt(1, 2) : randInt(1, 2);
      for (let k = 0; k < nHist; k++) {
        const fecha = addDays(spec.fechaIni, randInt(14, Math.max(15, daysBetween(spec.fechaIni, '2026-10-20'))));
        if (addDays(fecha, prv.plazo) > '2026-11-05' || fecha < addDays(spec.fechaIni, 12)) continue;
        const previo = ventaProv(prv.prods.map((p) => p.id), addDays(fecha, -14), addDays(fecha, -1));
        const objetivo = previo * randFloat(0.6, 1.0, 2) * (prv.plazo / 14);
        if (objetivo < 120) continue;
        const d = nuevoPedido(prv, fecha, lineasPedido(prv.prods, objetivo, false), '09:00');
        const demora = spec.ajustada ? pick([0, 1, 2, 4, 8]) : pick([-1, 0, 0, 0, 1, 2]);
        d.obligaciones.push({ fecha: addDays(d.venc, demora), montoC: d.montoC });
      }
    }
    // Pedido abierto reciente (10/11): el de los negocios con shock `alza_proveedor` es mayor a lo que venden hasta el vencimiento
    if (spec.shock === 'alza_proveedor' || chance(0.6)) {
      const prv = proveedores[0];
      const venc = addDays('2026-11-10', prv.plazo);
      const ve = ventaEsperadaBackend(ventaProdDia, prv.prods.map((p) => p.id), spec.fechaIni, FECHA_DEMO, venc);
      const factor = spec.shock === 'alza_proveedor' ? randFloat(1.4, 1.8, 2) : randFloat(0.4, 0.75, 2);
      const objetivo = Math.max(150, ve * factor);
      const d = nuevoPedido(prv, '2026-11-10', lineasPedido(prv.prods, objetivo, true), '09:00');
      d.abierto = true;
      d.obligaciones.push({ fecha: d.venc, montoC: d.montoC });
      d.ventaEsperada = ve;
    }
  }

  // ── préstamos de dinero (gota a gota, familiar, entidad financiera) ──
  const prestamos = [];
  const deudasPrestamo = [];
  if (spec.prestamo === 'gota_a_gota') {
    const R = Math.min(2000, Math.max(500, redondeaA(spec.base * 3, 100)));
    const total = R * 1.2;
    const cuota = total / 30;
    deudasPrestamo.push({ id: padId('DEU', deuSeq++, 4), tipo: 'prestamo_informal', acreedor: 'Prestamista informal', recibido: R, total, frecuencia: 'diaria',
      cuota, inicio: '2026-11-01', venc: '2026-11-30', notas: 'Préstamo informal diario (20 % por 30 días) en efectivo' });
  } else if (spec.prestamo === 'familiar') {
    const R = redondeaA(spec.base * randFloat(3, 6), 100);
    const n = 4;
    const inicio = addDays(spec.fechaIni, 30);
    deudasPrestamo.push({ id: padId('DEU', deuSeq++, 4), tipo: 'familiar', acreedor: pick(['mi hermano', 'mi tío', 'mi cuñado']), recibido: R, total: R, frecuencia: 'mensual',
      cuota: R / n, inicio, venc: sumarMeses(inicio, n), notas: 'Préstamo familiar sin intereses, 4 cuotas mensuales' });
  } else if (spec.prestamo === 'entidad_financiera') {
    const R = redondeaA(spec.base * randFloat(8, 14), 100);
    const n = 12;
    const inicio = addDays(spec.fechaIni, 25);
    const total = redondeaA(R * 1.18, 10);
    deudasPrestamo.push({ id: padId('DEU', deuSeq++, 4), tipo: 'entidad_financiera', acreedor: 'Caja municipal (ficticia)', recibido: R, total, frecuencia: 'mensual',
      cuota: total / n, inicio, venc: sumarMeses(inicio, n), notas: 'Crédito de capital de trabajo a 12 cuotas mensuales' });
  }
  for (const p of deudasPrestamo) {
    const cuotaC = Math.round(p.cuota * 100);
    const fechasCuota = [];
    for (let k = 1; k < 400; k++) {
      const f = p.frecuencia === 'mensual' ? sumarMeses(p.inicio, k) : addDays(p.inicio, k);
      if (f > p.venc || f > FECHA_DEMO) break;
      fechasCuota.push(f);
    }
    p.obligaciones = fechasCuota.map((fecha) => ({ fecha, montoC: cuotaC }));
    p.montoC = cents(p.total);
    p.recibidoC = cents(p.recibido);
    p.pagos = [];
    p.pagadoC = 0;
    p.canal = 'voz';
    p.prestamo = true;
    deudas.push(p);
  }

  // ── impuestos (Nuevo RUS) ──
  const impuestos = [];
  if (spec.tieneRuc) {
    const informaMal = chance(0.4);
    let mes = mesDe(spec.fechaIni);
    for (; mes <= '2026-11'; mes = sumarMeses(`${mes}-01`, 1).slice(0, 7)) {
      const ventas = (ventaMesC.get(mes) || 0) / 100;
      const cuota = !informaMal && ventas > 5000 ? 50 : 20;
      const venc = `${sumarMeses(`${mes}-01`, 1).slice(0, 7)}-15`;
      let pago = null;
      if (mes < '2026-10') pago = (spec.idx === 4 || spec.idx === 17) && mes === '2026-09' ? null : addDays(venc, -randInt(0, 5));
      else if (mes === '2026-10') pago = chance(0.65) ? addDays('2026-11-13', -randInt(0, 8)) : null;
      if (pago !== null && pago < addDays(`${mes}-28`, 3)) pago = addDays(`${mes}-28`, 3); // no se paga antes de terminar el mes
      impuestos.push({ id: padId('IMP', impSeq++, 4), mes, cuota, venc, pago, informaMal, canal: pick(['texto', 'texto', 'voz']) });
    }
  }

  // ── eventos de tipo shock: retiros extra y gasto extraordinario ──
  const extras = [...spec.retirosFijos.map((r) => ({ ...r, montoC: cents(r.monto) }))];
  const gastosEx = [];
  if (spec.shock === 'retiro_excesivo' && spec.sueldo) {
    const unidad = spec.sueldo.frecuencia === 'semanal' ? spec.sueldo.monto : spec.sueldo.mensualEquiv / 4;
    for (const f of ['2026-10-28', '2026-11-03', '2026-11-07', '2026-11-11']) {
      extras.push({ fecha: f, montoC: cents(redondeaA(unidad * randFloat(0.6, 1.1, 2), 10)), desc: 'Retiro personal extra de la caja (por encima del sueldo fijo)' });
    }
  }
  if (spec.shock === 'gasto_extra') {
    gastosEx.push({ fecha: '2026-10-30', montoC: cents(redondeaA(spec.base * randFloat(2, 3.2, 2), 10)), desc: 'Reparación urgente del local y equipos', cat: 'CAT-16' });
  }

  // ── caja día por día ──
  const sinSueldo = spec.sueldo === null && !nuevo;
  let saldoC = cents(spec.saldoIni);
  const saldoPath = [];
  const ventasRecientes = []; // totales diarios recientes para dimensionar las compras
  const retirosTx = []; // {fecha, montoC}
  const diasConRegistro = new Set();
  const cola = []; // gastos fijos atrasados: {fecha, prog, montoC}
  const nuevoCanal = () => canalAleatorio(spec);
  const finDemoAntes = (fecha, hora) => !(fecha === FECHA_DEMO && hora >= HORA_CORTE);

  const emitir = (f) => {
    const c = nuevoCanal();
    const tx = addTx({ empresa_id: E, canal: c.canal, confianza: c.confianza, fue_corregida: c.canal !== 'manual' && chance(0.05), ...f });
    diasConRegistro.add(f.fecha_hora.slice(0, 10));
    return tx;
  };

  fechas.forEach((fecha, i) => {
    const demo = fecha === FECHA_DEMO;
    let cajaC = saldoC;

    // 1) ventas del día (contado y billetera)
    let ventaDiaC = 0;
    for (const b of ventasDia.get(fecha) || []) {
      ventaDiaC += cents(b.total);
      const desc = `Venta: ${textoLineas(b.lineas.slice(0, 4))}${b.lineas.length > 4 ? '…' : ''}`;
      if (b.metodo === 'billetera_digital') {
        const origen = chance(0.85) ? 'api' : 'captura';
        const bil = {
          billetera_mov_id: padId('BIL', bilSeq++, 4), empresa_id: E, proveedor_billetera: pick(BILLETERAS),
          operacion_id: `OP-${randInt(10000000, 99999999)}`, tipo: 'ingreso', monto: fmtMoney(b.total),
          contraparte_nombre: pick(CONTRAPARTES_BILLETERA), fecha_hora: ts(fecha, b.hora), origen,
        };
        tables.billeteras_digitales.push(bil);
        const tx = addTx({
          empresa_id: E, fecha_hora: ts(fecha, b.hora), tipo: 'venta', categoria_id: categoriaDominante(b.lineas), descripcion: desc,
          metodo_pago: 'billetera_digital', canal: origen === 'api' ? 'billetera_api' : 'foto', confianza: origen === 'api' ? null : 0.85,
          billetera_mov_id: bil.billetera_mov_id, lineas: b.lineas,
        });
        diasConRegistro.add(fecha);
        cajaC += cents(tx.monto);
      } else {
        const tx = emitir({ fecha_hora: ts(fecha, b.hora), tipo: 'venta', categoria_id: categoriaDominante(b.lineas), descripcion: desc, metodo_pago: 'efectivo', lineas: b.lineas });
        cajaC += cents(tx.monto);
      }
    }
    if (ventaDiaC > 0) ventasRecientes.push(ventaDiaC);
    if (ventasRecientes.length > 7) ventasRecientes.shift();

    // 2) ventas fiadas del día
    for (const fia of fiados.filter((x) => x.fecha === fecha)) {
      emitir({
        fecha_hora: ts(fecha, demo ? horaManana() : fia.hora), tipo: 'venta', categoria_id: categoriaDominante(fia.lineas),
        descripcion: `Venta fiada a ${fia.cli.nombre}: ${textoLineas(fia.lineas.slice(0, 4))}`, metodo_pago: 'credito', canal: fia.canal,
        fiado_id: fia.id, lineas: fia.lineas,
      });
    }

    // 3) pedidos a crédito del día
    for (const d of deudas.filter((x) => !x.prestamo && x.fecha === fecha)) {
      emitir({
        fecha_hora: ts(fecha, d.hora), tipo: 'compra', categoria_id: 'CAT-07', descripcion: `Pedido a crédito a ${d.prv.nombre}`,
        metodo_pago: 'credito', canal: d.canal, deuda_id: d.id, lineas: d.lineas,
      });
    }
    // 4) préstamos recibidos
    for (const p of deudasPrestamo.filter((x) => x.inicio === fecha)) {
      const tx = emitir({
        fecha_hora: ts(fecha, '10:00'), tipo: 'prestamo_recibido', categoria_id: 'CAT-15', descripcion: `Préstamo recibido: ${p.acreedor}`,
        monto: p.recibido, metodo_pago: 'efectivo', canal: 'voz', deuda_id: p.id,
      });
      cajaC += cents(tx.monto);
    }

    // 5) cobros de fiado (después de la hora de corte del 14/11 no se anota nada)
    for (const fia of fiados) {
      for (const pg of fia.pagos) {
        if (pg.fecha !== fecha || !finDemoAntes(fecha, '17:00')) continue;
        emitir({
          fecha_hora: ts(fecha, '17:00'), tipo: 'cobro_fiado', categoria_id: 'CAT-14', descripcion: `Cobro de fiado a ${fia.cli.nombre}`,
          monto: fromCents(pg.montoC), metodo_pago: 'efectivo', fiado_id: fia.id,
        });
        fia.cobradoC = (fia.cobradoC || 0) + pg.montoC;
        fia.ultimoCobro = fecha;
        if (fia.cobradoC >= fia.montoC && !fia.fechaPagoTotal) fia.fechaPagoTotal = fecha;
        cajaC += pg.montoC;
      }
    }
    // 6) ingreso fijo semanal (venta a un comedor)
    if (prgIng && ocurreProg(prgIng, fecha) && finDemoAntes(fecha, '16:00')) {
      emitir({ fecha_hora: ts(fecha, '16:00'), tipo: 'otro_ingreso', categoria_id: 'CAT-06', descripcion: prgIng.descripcion, monto: Number(prgIng.monto), metodo_pago: 'efectivo', programado_id: prgIng.programado_id });
      cajaC += cents(prgIng.monto);
    }

    // 7) pagos obligatorios (nunca dejan la caja en negativo; si no alcanza, se pagan después)
    const reservaForzada = 500; // 5.00 de colchón mínimo
    if (!demo) {
      for (const d of deudas) {
        const vencidoC = sum(d.obligaciones.filter((o) => o.fecha <= fecha), (o) => o.montoC) - d.pagadoC;
        if (vencidoC <= 0) continue;
        const reservaPago = d.prestamo ? Math.round(cents(spec.minOp) * 0.1) : Math.round(cents(spec.minOp) * 0.3);
        const pagoC = Math.min(vencidoC, Math.max(0, cajaC - reservaPago));
        if (pagoC < 500 && pagoC < vencidoC) continue;
        const prestamo = d.prestamo;
        emitir({
          fecha_hora: ts(fecha, prestamo ? '19:30' : '11:00'), tipo: prestamo ? 'pago_prestamo' : 'pago_proveedor',
          categoria_id: prestamo ? 'CAT-12' : 'CAT-07',
          descripcion: prestamo ? `Pago de cuota: ${d.acreedor}` : `Pago a ${d.prv.nombre}${pagoC < vencidoC ? ' (pago parcial)' : ''}`,
          monto: fromCents(pagoC), metodo_pago: 'efectivo', deuda_id: d.id,
        });
        d.pagadoC += pagoC;
        d.ultimoPago = fecha;
        if (d.pagadoC >= d.montoC && !d.fechaPagoTotal) d.fechaPagoTotal = fecha;
        cajaC -= pagoC;
      }
      for (const imp of impuestos) {
        if (imp.pago === fecha && !imp.pagado && cajaC - reservaForzada < cents(imp.cuota)) imp.pago = addDays(fecha, 1); // sin caja: se paga al día siguiente
        if (imp.pago === fecha && !imp.pagado) {
          emitir({
            fecha_hora: ts(fecha, '11:30'), tipo: 'pago_impuesto', categoria_id: 'CAT-11',
            descripcion: `Pago Nuevo RUS ${imp.mes} (Cat. ${imp.cuota === 50 ? '2 S/ 50' : '1 S/ 20'})`, monto: imp.cuota, metodo_pago: 'efectivo',
            impuesto_id: imp.id, canal: imp.canal, confianza: 0.9,
          });
          imp.pagado = true;
          cajaC -= cents(imp.cuota);
        }
      }
      // gastos fijos (luz, alquiler, internet) y gastos extraordinarios
      for (const p of gastosFijos) if (ocurreProg(p, fecha)) cola.push({ fecha, prog: p, montoC: cents(p.monto) });
      for (let k = cola.length - 1; k >= 0; k--) {
        const g = cola[k];
        if (Math.max(0, cajaC - reservaForzada) < g.montoC) continue;
        emitir({
          fecha_hora: ts(fecha, '15:00'), tipo: 'gasto_negocio', categoria_id: g.prog.categoria_id,
          descripcion: `${g.prog.descripcion} (${mesDe(g.fecha)})`, monto: fromCents(g.montoC), metodo_pago: 'efectivo', programado_id: g.prog.programado_id,
        });
        cajaC -= g.montoC;
        cola.splice(k, 1);
      }
      for (const g of gastosEx.filter((x) => x.fecha === fecha)) {
        const c = Math.min(g.montoC, Math.max(0, cajaC - cents(spec.minOp) * 0.3));
        if (c < 500) continue;
        emitir({ fecha_hora: ts(fecha, '14:00'), tipo: 'gasto_negocio', categoria_id: g.cat, descripcion: g.desc, monto: fromCents(c), metodo_pago: 'efectivo' });
        cajaC -= c;
      }
    }

    // 8) retiros personales: sueldo fijo y extras (limitados al efectivo disponible)
    if (!demo) {
      const reservaRetiro = Math.round(cents(spec.minOp) * 0.3);
      if (prgSueldo && ocurreProg(prgSueldo, fecha)) {
        const montoC = Math.min(cents(prgSueldo.monto), Math.max(0, cajaC - reservaRetiro));
        if (montoC >= cents(prgSueldo.monto) * 0.3 && montoC >= 500) {
          emitir({ fecha_hora: ts(fecha, '20:00'), tipo: 'retiro_personal', categoria_id: 'CAT-13', descripcion: `Sueldo fijo del dueño (${spec.sueldo.frecuencia})`, monto: fromCents(montoC), metodo_pago: 'efectivo', programado_id: prgSueldo.programado_id });
          retirosTx.push({ fecha, montoC });
          cajaC -= montoC;
        }
      }
      for (const r of extras.filter((x) => x.fecha === fecha)) {
        const montoC = Math.min(r.montoC, Math.max(0, cajaC - reservaRetiro));
        if (montoC < 500) continue;
        emitir({ fecha_hora: ts(fecha, '20:30'), tipo: 'retiro_personal', categoria_id: 'CAT-13', descripcion: r.desc, monto: fromCents(montoC), metodo_pago: 'efectivo' });
        retirosTx.push({ fecha, montoC });
        cajaC -= montoC;
      }
      if (sinSueldo && chance(0.14)) {
        const montoC = Math.min(cents(redondeaA(spec.base * randFloat(0.15, 0.5, 2), 10)), Math.max(0, cajaC - reservaRetiro));
        if (montoC >= 500) {
          emitir({ fecha_hora: ts(fecha, '20:00'), tipo: 'retiro_personal', categoria_id: 'CAT-13', descripcion: 'Retiro para gastos de la casa', monto: fromCents(montoC), metodo_pago: 'efectivo' });
          retirosTx.push({ fecha, montoC });
          cajaC -= montoC;
        }
      }
    }

    // 9) gastos menores, inversión del excedente y compras de mercadería al contado
    const registrado = (ventasDia.get(fecha) || []).length > 0;
    const tope = cents(spec.base) * 14;
    if (!demo && registrado && cajaC > tope && chance(0.12)) {
      const montoC = Math.round((cajaC - tope) * randFloat(0.3, 0.6, 2) / 1000) * 1000;
      if (montoC >= 5000) {
        emitir({
          fecha_hora: ts(fecha, '15:30'), tipo: 'gasto_negocio', categoria_id: 'CAT-16',
          descripcion: pick(['Compra de equipos para el negocio', 'Mejoras y refacción del local', 'Compra de mobiliario y vitrinas']),
          monto: fromCents(montoC), metodo_pago: 'efectivo',
        });
        cajaC -= montoC;
      }
    }
    if (!demo && registrado && chance(0.07)) {
      const montoC = Math.min(cents(redondeaA(spec.base * randFloat(0.05, 0.22, 2), 5)), Math.max(0, cajaC - cents(spec.minOp) * 0.3));
      if (montoC >= 500) {
        const transporte = chance(0.45);
        emitir({
          fecha_hora: ts(fecha, '13:00'), tipo: 'gasto_negocio', categoria_id: transporte ? 'CAT-10' : 'CAT-16',
          descripcion: transporte ? 'Flete y movilidad de mercadería' : pick(['Bolsas y embalajes', 'Mantenimiento menor del local', 'Útiles de limpieza del local', 'Reparación pequeña']),
          monto: fromCents(montoC), metodo_pago: 'efectivo',
        });
        cajaC -= montoC;
      }
    }
    if (registrado && chance(spec.pCompra)) {
      const ref = ventasRecientes.length ? sum(ventasRecientes) / ventasRecientes.length : cents(spec.base);
      const holgura = Math.min(0.12, Math.max(0, (cajaC - cents(spec.base) * 5) / (cents(spec.base) * 20)));
      const objetivoC = (ref * (spec.ratioCompra + (spec.ajustada ? 0 : holgura)) * randFloat(0.7, 1.3, 2)) / spec.pCompra;
      const montoC = Math.min(Math.round(objetivoC / 100) * 100, Math.max(0, cajaC - Math.round(cents(spec.minOp) * 0.35)));
      if (montoC >= 500) {
        emitir({
          fecha_hora: ts(fecha, demo ? '09:15' : pick(['07:30', '08:30', '09:30', '10:30', '11:30'])), tipo: 'compra', categoria_id: 'CAT-07',
          descripcion: pick(['Compra de mercadería al contado', 'Reposición de stock al contado', 'Compra en mayorista (efectivo)']), monto: fromCents(montoC), metodo_pago: 'efectivo',
        });
        cajaC -= montoC;
      }
    }
    saldoC = cajaC;
    saldoPath.push({ fecha, saldoC });
  });
  saldoPorEmpresa.set(E, saldoPath);

  // ── filas de las tablas satélite (con lo que realmente se emitió) ──
  for (const fia of fiados) {
    const pagado = (fia.cobradoC || 0) >= fia.montoC;
    const tardio = pagado ? fia.fechaPagoTotal > fia.compromiso : fia.compromiso < FECHA_DEMO ? true : null;
    tables.cuaderno_fiado.push({
      fiado_id: fia.id, empresa_id: E, cliente_id: fia.cli.id, borrador_id: null, detalle: textoLineas(fia.lineas).slice(0, 255),
      monto: fmtMoney(fromCents(fia.montoC)), fecha_fiado: fia.fecha, fecha_compromiso: fia.compromiso,
      fecha_pago_total: pagado ? fia.fechaPagoTotal : null, canal: fia.canal, pago_tardio: tardio,
    });
    fia.pagado = pagado;
  }
  for (const d of deudas) {
    const pagado = d.pagadoC >= d.montoC;
    tables.deudas.push({
      deuda_id: d.id, empresa_id: E, tipo: d.tipo, proveedor_id: d.prv ? d.prv.id : null, acreedor_nombre: d.prv ? null : d.acreedor, borrador_id: null,
      monto_recibido: fmtMoney(fromCents(d.recibidoC)), monto_total_a_pagar: fmtMoney(fromCents(d.montoC)),
      frecuencia_cuota: d.prestamo ? d.frecuencia : null, monto_cuota: d.prestamo ? fmtMoney(d.cuota) : null,
      fecha_inicio: d.prestamo ? d.inicio : d.fecha, fecha_vencimiento: d.venc, fecha_pago_total: pagado ? d.fechaPagoTotal : null, canal: d.canal,
      notas: d.prestamo ? d.notas : d.abierto ? 'Pedido de mercadería pre-Campaña Navideña' : 'Pedido de mercadería a crédito',
    });
  }
  for (const imp of impuestos) {
    tables.impuestos.push({
      impuesto_id: imp.id, empresa_id: E, regimen: 'nuevo_rus', periodo: imp.mes, monto: fmtMoney(imp.cuota), fecha_vencimiento: imp.venc,
      fecha_pago: imp.pagado ? imp.pago : null, canal: imp.canal,
    });
  }

  negociosSim.push({ spec, prefs, canalesPref, prods, clientes, proveedores, progs, prgSueldo, prgAlq, prgLuz, fiados, deudas, impuestos, saldoPath, retirosTx, ventaProdDia, ventaMesC, diasConRegistro, extras });
}

// =============================================================================
// 6. EMPRESA 2 (usuario nuevo, día 3) Y NEGOCIOS EMP-0003 a EMP-0030
// =============================================================================
simularNegocio(construirSpec(2));
for (let empNum = 3; empNum <= 30; empNum++) simularNegocio(construirSpec(empNum));
useRng(4242);

// =============================================================================
// 7. FUNCIONES DEL BACKEND REPLICADAS SOBRE LOS DATOS GENERADOS (alertas y score de salud)
// =============================================================================
const pyRound = (x) => {
  // round() de Python: mitades al par
  const f = Math.floor(x);
  const d = x - f;
  if (Math.abs(d - 0.5) < 1e-9) return f % 2 === 0 ? f : f + 1;
  return Math.round(x);
};
const NOMBRE_MES = ['', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const txPorEmpresa = new Map();
for (const t of tables.transacciones) {
  if (!txPorEmpresa.has(t.empresa_id)) txPorEmpresa.set(t.empresa_id, []);
  txPorEmpresa.get(t.empresa_id).push(t);
}
const progsPorEmpresa = (empId) => tables.movimientos_programados.filter((p) => p.empresa_id === empId);
const retirosEntre = (empId, desde, hasta) =>
  sum(
    (txPorEmpresa.get(empId) || []).filter((t) => t.tipo === 'retiro_personal' && t.afecta_caja && t.fecha_hora.slice(0, 10) >= desde && t.fecha_hora.slice(0, 10) <= hasta),
    (t) => cents(t.monto)
  ) / 100;

// services/finanzas/consultas.py: sueldo_esperado / sueldo_a_la_fecha. Diario y semanal: las veces que cae en el rango;
// mensual y quincenal: se prorratea por día dentro de cada periodo, pero un sueldo que ya cayó en el periodo cuenta
// completo (max(prorrateo, sueldo ya vencido)): cobrarse el sueldo al inicio del periodo no es un retiro excesivo.
// None si nunca hubo sueldo fijo en el rango.
const vigenteProg = (p, d) => !(!p.activo && p.fecha_fin === null) && p.fecha_inicio <= d && (p.fecha_fin === null || d <= p.fecha_fin);
function periodoProg(p, d) {
  const [y, m, dd] = d.split('-').map(Number);
  const ult = ultimoDiaMes(y, m);
  const mm = `${d.slice(0, 8)}`;
  if (p.frecuencia === 'mensual') return [`${mm}01`, `${mm}${String(ult).padStart(2, '0')}`];
  return dd <= 15 ? [`${mm}01`, `${mm}15`] : [`${mm}16`, `${mm}${String(ult).padStart(2, '0')}`];
}
function sueldoALaFecha(p, desde, hasta) {
  if (p.frecuencia === 'diaria' || p.frecuencia === 'semanal') {
    return Number(p.monto) * fechasEntre(desde, hasta).filter((d) => ocurreProg(p, d)).length;
  }
  const prorrateo = new Map(); // "ini|fin" -> parte
  const fin = p.fecha_fin !== null && p.fecha_fin < hasta ? p.fecha_fin : hasta;
  for (let d = desde > p.fecha_inicio ? desde : p.fecha_inicio; d <= fin; d = addDays(d, 1)) {
    if (!vigenteProg(p, d)) continue;
    const [y, m, dd] = d.split('-').map(Number);
    const ult = ultimoDiaMes(y, m);
    const k = periodoProg(p, d).join('|');
    prorrateo.set(k, (prorrateo.get(k) || 0) + Number(p.monto) / (p.frecuencia === 'mensual' ? ult : dd <= 15 ? 15 : ult - 15));
  }
  let total = 0;
  for (const [k, parte] of prorrateo) {
    const [ini, finPer] = k.split('|');
    const a = [ini, desde, p.fecha_inicio].sort().at(-1);
    const b = finPer < fin ? finPer : fin;
    const vencido = Number(p.monto) * (a <= b ? fechasEntre(a, b).filter((d) => ocurreProg(p, d)).length : 0);
    total += Math.max(parte, vencido);
  }
  return total;
}
function sueldoEsperado(empId, desde, hasta) {
  const sueldos = progsPorEmpresa(empId).filter((p) => p.es_sueldo);
  let total = 0;
  let alguno = false;
  for (const p of sueldos) {
    const parte = sueldoALaFecha(p, desde, hasta);
    if (parte || vigenteProg(p, desde) || vigenteProg(p, hasta)) alguno = true;
    total += parte;
  }
  return alguno ? Math.round(total * 100) / 100 : null;
}
// consultas.py: retiros_del_mes -> promedio de los 3 meses previos al mismo día del mes
function promedioHistoricoRetiros(empId, fechaIni, corte) {
  const previos = [];
  for (let k = 1; k <= 3; k++) {
    const inicio = sumarMeses(primerDiaMes(corte), -k);
    if (inicio < fechaIni) continue;
    const [y, m] = inicio.split('-').map(Number);
    const fin = `${inicio.slice(0, 8)}${String(Math.min(Number(corte.slice(8, 10)), ultimoDiaMes(y, m))).padStart(2, '0')}`;
    previos.push(retirosEntre(empId, inicio, fin));
  }
  return previos.length ? Math.round((sum(previos) / previos.length) * 100) / 100 : null;
}
const nivelPorProporcion = (parte, total) => {
  const r = total ? parte / total : 0;
  return r >= 0.25 ? 'alto' : r >= 0.1 ? 'medio' : 'bajo';
};

// ── alertas de los negocios (reglas.py: retiro_excesivo, pedido_excesivo, obligacion_proxima) ──
const horaAlerta = {};
for (const neg of negociosSim) {
  const { spec } = neg;
  const E = spec.empId;
  const corte = FECHA_DEMO;
  const candidatas = [];
  // retiro_excesivo
  const retMes = retirosEntre(E, primerDiaMes(corte), corte);
  const sueldo = sueldoEsperado(E, primerDiaMes(corte), corte);
  let referencia = null;
  let etiqueta = null;
  if (sueldo !== null) { referencia = sueldo; etiqueta = 'Tu sueldo fijo hasta hoy'; }
  else {
    const prom = promedioHistoricoRetiros(E, spec.fechaIni, corte);
    if (prom !== null) { referencia = prom; etiqueta = 'Lo que sueles sacar a esta altura del mes'; }
  }
  if (referencia !== null) {
    const exceso = Math.round((retMes - referencia) * 100) / 100;
    if (exceso > 0) {
      candidatas.push({
        tipo: 'retiro_excesivo', prioridad: 3, fecha_evento: corte, monto: exceso, probabilidad: null, nivel: nivelPorProporcion(exceso, retMes),
        causas: [{ descripcion: 'Lo que sacaste de la caja este mes', monto: retMes }, { descripcion: etiqueta, monto: referencia }],
        accion: 'ver_retiros', entidad_tipo: 'mes', entidad_id: corte.slice(0, 7), modelo: MODELO_REGLAS,
      });
    }
  }
  // pedido_excesivo: pedido a proveedor impago iniciado en los últimos 7 días que supera lo que se vende hasta su vencimiento
  for (const d of neg.deudas.filter((x) => !x.prestamo && x.abierto && x.pagadoC < x.montoC && x.fecha >= addDays(corte, -7))) {
    const monto = fromCents(d.montoC);
    const exceso = Math.max(0, Math.round((monto - d.ventaEsperada) * 100) / 100);
    if (exceso <= 0) continue;
    candidatas.push({
      tipo: 'pedido_excesivo', prioridad: 2, fecha_evento: d.venc, monto: exceso, probabilidad: null, nivel: nivelPorProporcion(exceso, monto),
      causas: [
        { descripcion: 'Lo que pediste', monto },
        { descripcion: `Lo que sueles vender de eso hasta el ${d.venc.slice(8, 10)}/${d.venc.slice(5, 7)}`, monto: d.ventaEsperada },
      ],
      accion: 'abrir_simulador', entidad_tipo: 'deudas', entidad_id: d.id, modelo: MODELO_REGLAS,
    });
  }
  // obligacion_proxima: vence en los próximos 3 días y sigue impaga
  const saldoHoy = neg.saldoPath[neg.saldoPath.length - 1].saldoC / 100;
  const nivelCaja = saldoHoy < 0 ? 'alto' : saldoHoy < spec.minOp ? 'medio' : 'bajo';
  for (const d of neg.deudas.filter((x) => x.pagadoC < x.montoC && x.venc >= corte && x.venc <= addDays(corte, 3))) {
    candidatas.push({
      tipo: 'obligacion_proxima', prioridad: 4, fecha_evento: d.venc, monto: fromCents(d.montoC - d.pagadoC), probabilidad: null, nivel: nivelCaja,
      causas: [{ descripcion: `Pago a ${d.prv ? d.prv.nombre : d.acreedor}`, monto: fromCents(d.montoC - d.pagadoC) }],
      accion: 'ver_cuentas', entidad_tipo: 'deudas', entidad_id: d.id, modelo: MODELO_REGLAS,
    });
  }
  for (const imp of neg.impuestos.filter((x) => !x.pagado && x.venc >= corte && x.venc <= addDays(corte, 3))) {
    candidatas.push({
      tipo: 'obligacion_proxima', prioridad: 4, fecha_evento: imp.venc, monto: imp.cuota, probabilidad: null, nivel: nivelCaja,
      causas: [{ descripcion: `RUS de ${NOMBRE_MES[Number(imp.mes.slice(5, 7))]}`, monto: imp.cuota }],
      accion: 'ver_cuentas', entidad_tipo: 'impuestos', entidad_id: imp.id, modelo: MODELO_REGLAS,
    });
  }
  candidatas.sort((a, b) => a.prioridad - b.prioridad);
  let enviadas = 0;
  candidatas.forEach((c, k) => {
    const creada = ts(FECHA_DEMO, '08:30', String(10 * k).padStart(2, '0'));
    const envia = enviadas < neg.prefs.max_por_dia;
    if (envia) enviadas++;
    const estadoSorteo = rng();
    const estado = c.tipo !== 'retiro_excesivo' || estadoSorteo < 0.7 ? 'activa' : estadoSorteo < 0.85 ? 'atendida' : 'descartada'; // solo el aviso de retiros se descarta o se atiende en los datos
    const accion = estado === 'atendida' ? 'ejecutada' : estado === 'descartada' ? 'descartada' : null;
    tables.alertas.push({
      alerta_id: padId('ALR', alrSeq++, 4), empresa_id: E, tipo: c.tipo, prioridad: c.prioridad, fecha_evento: c.fecha_evento,
      monto: fmtMoney(c.monto), probabilidad: c.probabilidad === null ? null : fmtProb(c.probabilidad), nivel_riesgo: c.nivel,
      causas: JSON.stringify(c.causas), accion_sugerida: c.accion, entidad_tipo: c.entidad_tipo, entidad_id: c.entidad_id,
      canal: neg.canalesPref[0], estado, accion_tomada: accion, fecha_accion: accion ? ts(FECHA_DEMO, '09:10') : null,
      creada_en: creada, enviada_en: envia ? ts(FECHA_DEMO, '08:30', String(10 * k + 5).padStart(2, '0')) : null, modelo_version: c.modelo,
    });
  });
}

// ── riesgo de atraso de fiados (baseline del backend: tasa del cliente suavizada hacia la global, m = 2) ──
// Pedro (EMP-0001) entra con la misma regla: sus fiados en el formato de los negocios simulados.
const fiadosPedroSim = [...fiadosPedroHist, ...fiadosPedroPend].map((f) => ({
  id: f.id, cli: { id: f.cli }, compromiso: f.f_comp, pagado: f.f_pago !== null, fechaPagoTotal: f.f_pago,
}));
for (const neg of [{ fiados: fiadosPedroSim }, ...negociosSim]) {
  const corte = FECHA_DEMO;
  const info = neg.fiados.map((f) => {
    const pagado = f.pagado;
    const atrasado = pagado ? f.fechaPagoTotal > f.compromiso : f.compromiso < corte ? true : null;
    return { f, atrasado };
  });
  const conocidos = info.filter((x) => x.atrasado !== null);
  const global = (conocidos.filter((x) => x.atrasado).length + 1) / (conocidos.length + 2);
  for (const { f } of info.filter((x) => !x.f.pagado)) {
    const propios = conocidos.filter((x) => x.f.cli.id === f.cli.id && x.f.id !== f.id);
    const p = (propios.filter((x) => x.atrasado).length + 2 * global) / (propios.length + 2);
    const pr = pyRound(p * 100) / 100;
    tables.predicciones_fiado.push({
      prediccion_id: padId('PRF', tables.predicciones_fiado.length + 1, 5), fiado_id: f.id, fecha_corte: corte, prob_atraso: fmtProb(pr),
      prob_pago_14d: fmtProb(Math.max(0, 1 - pr * 0.8)), nivel_riesgo: nivelRiesgoFiado(p), modelo_version: MODELO_RIESGO,
      creado_en: ts(FECHA_DEMO, '09:00', '05'),
    });
  }
}

// ── eventos (ground truth de los shocks) ──
for (const neg of negociosSim) {
  const { spec } = neg;
  const ev = {
    retiro_excesivo: ['2026-10-28', '2026-11-12', 'Retiros personales extraordinarios por encima del sueldo fijo que descapitalizan la caja'],
    alza_proveedor: ['2026-11-10', null, 'Pedido a crédito de mercadería pre-Campaña Navideña mayor a lo que se vende hasta su vencimiento'],
    mes_bajo: ['2026-10-25', null, 'Caída temporal de ventas previa a la campaña navideña (en curso)'],
    gasto_extra: ['2026-10-30', '2026-10-30', 'Gasto extraordinario de reparación del local y equipos'],
    cliente_no_paga: ['2026-10-24', null, 'Un cliente con fiados grandes dejó de pagar'],
  }[spec.shock];
  if (!ev) continue;
  tables.eventos.push({ evento_id: padId('EVT', evtSeq++, 4), empresa_id: spec.empId, tipo_evento: spec.shock, fecha_inicio: ev[0], fecha_fin: ev[1], descripcion: ev[2] });
}

// ── metas, ajustes del forecast y consentimientos ──
for (const neg of negociosSim) {
  const { spec } = neg;
  const E = spec.empId;
  const nuevaMeta = (m) => tables.reglas_meta.push({ meta_id: padId('MET', metSeq++, 4), empresa_id: E, programado_id: null, tipo_regla: null, valor: null, destino: null,
    objetivo: null, acumulado: '0.00', recordatorio_frecuencia: null, recordatorio_dia: null, estado: 'activa', fecha_logro: null, ...m });
  if (spec.nuevo) {
    nuevaMeta({ plantilla: 'registrar_30_dias', objetivo: '30.00', acumulado: '3.00', recordatorio_frecuencia: 'diaria', fecha_inicio: spec.fechaIni });
    continue;
  }
  const ini = addDays(spec.fechaIni, randInt(5, 40));
  if (neg.prgSueldo && chance(0.6)) {
    nuevaMeta({ plantilla: 'sueldo_fijo', programado_id: neg.prgSueldo.programado_id, tipo_regla: 'monto_fijo', valor: Number(neg.prgSueldo.monto).toFixed(4),
      recordatorio_frecuencia: neg.prgSueldo.frecuencia, recordatorio_dia: neg.prgSueldo.dia_semana || neg.prgSueldo.dia_mes, fecha_inicio: ini });
  }
  const otra = pick(['colchon_caja', 'apartar_para_pedido', 'reservar_impuestos', 'registrar_30_dias']);
  if (otra === 'colchon_caja') {
    const acum = randInt(60, spec.minOp);
    const lograda = chance(0.15);
    nuevaMeta({ plantilla: 'colchon_caja', tipo_regla: 'porcentaje_de_venta', valor: '0.0500', destino: 'colchon', objetivo: fmtMoney(spec.minOp),
      acumulado: fmtMoney(lograda ? spec.minOp : acum), recordatorio_frecuencia: 'semanal', recordatorio_dia: 1, estado: lograda ? 'lograda' : 'activa',
      fecha_inicio: ini, fecha_logro: lograda ? addDays(ini, randInt(30, 60)) : null });
  } else if (otra === 'apartar_para_pedido') {
    nuevaMeta({ plantilla: 'apartar_para_pedido', tipo_regla: 'porcentaje_de_venta', valor: '0.1000', destino: 'fondo_pedidos', objetivo: fmtMoney(redondeaA(spec.base * 5, 100)),
      acumulado: fmtMoney(randInt(50, Math.round(spec.base * 3))), recordatorio_frecuencia: 'semanal', recordatorio_dia: pick([1, 5]), fecha_inicio: ini });
  } else if (otra === 'reservar_impuestos' && spec.tieneRuc) {
    nuevaMeta({ plantilla: 'reservar_impuestos', tipo_regla: 'monto_fijo', valor: '5.0000', destino: 'fondo_impuestos', objetivo: '50.00', acumulado: fmtMoney(randInt(5, 40)),
      recordatorio_frecuencia: 'mensual', recordatorio_dia: 10, fecha_inicio: ini });
  } else {
    nuevaMeta({ plantilla: 'registrar_30_dias', objetivo: '30.00', acumulado: fmtMoney(randInt(4, 28)), recordatorio_frecuencia: 'diaria', fecha_inicio: addDays(FECHA_DEMO, -randInt(5, 28)) });
  }
  if (neg.prgAlq && chance(0.25)) {
    tables.forecast_ajustes.push({
      ajuste_id: padId('AJU', ajuSeq++, 4), empresa_id: E, programado_id: neg.prgAlq.programado_id, fecha: addDays('2026-11-15', randInt(1, 14)), concepto: 'alquiler',
      monto: fmtMoney(chance(0.5) ? 0 : Number(neg.prgAlq.monto) / 2), motivo: pick(['acuerdo con el dueño del local', 'adelanto del mes pasado', 'descuento por mantenimiento']),
      activo: chance(0.7), creado_en: ts(addDays(FECHA_DEMO, -randInt(1, 4)), '17:30'),
    });
  }
  if (spec.consentimiento) {
    const otorgado = addDays(FECHA_DEMO, -randInt(2, 40));
    const revocado = chance(0.2);
    tables.consentimientos.push({
      consentimiento_id: padId('CNS', cnsSeq++, 4), empresa_id: E, alcance: JSON.stringify(chance(0.5) ? ['resumen_12_meses', 'score'] : ['score']), activo: !revocado,
      fecha_otorgado: ts(otorgado, '16:00'), vigencia_hasta: addDays(otorgado, 365), fecha_revocado: revocado ? ts(addDays(otorgado, randInt(1, 20)), '18:00') : null,
    });
  }
}

// ── score de salud: misma fórmula que backend/app/services/salud/score.py (3 subindicadores, pesos 0.35/0.40/0.25) ──
const PESOS_SCORE = { constancia_registro: 0.35, separacion_personal: 0.4, impuestos_al_dia: 0.25 };
function calcularScore(empId, mes, corte) {
  const inicio = `${mes}-01`;
  const txs = (txPorEmpresa.get(empId) || []).filter((t) => !t.anulada);
  const dias = new Set(txs.map((t) => t.fecha_hora.slice(0, 10)).filter((d) => d >= inicio && d <= corte));
  let evaluados = daysBetween(inicio, corte) + 1;
  if (!dias.has(corte) && evaluados > 1) evaluados -= 1;
  const constancia = Math.min(100, evaluados ? pyRound((100 * dias.size) / evaluados) : 0);
  const retiros = retirosEntre(empId, inicio, corte);
  const sueldos = progsPorEmpresa(empId).filter((p) => p.es_sueldo);
  let separacion;
  if (!sueldos.some((p) => p.activo)) separacion = 30;
  else {
    const esperado = sueldoEsperado(empId, inicio, corte) || 0; // score.py usa consultas.sueldo_esperado
    separacion = retiros <= esperado ? 100 : pyRound(40 + 60 * (esperado / retiros));
  }
  const imps = tables.impuestos.filter((i) => i.empresa_id === empId);
  const conPago = new Set(txs.filter((t) => t.tipo === 'pago_impuesto' && t.fecha_hora.slice(0, 10) <= corte).map((t) => t.impuesto_id));
  const vencido = imps.some((i) => !(conPago.has(i.impuesto_id) || (i.fecha_pago !== null && i.fecha_pago <= corte)) && i.fecha_vencimiento < corte);
  const impuestos = vencido ? 0 : 100;
  const sub = { constancia_registro: constancia, separacion_personal: separacion, impuestos_al_dia: impuestos };
  const score = pyRound(sum(Object.keys(PESOS_SCORE), (k) => PESOS_SCORE[k] * sub[k]));
  return { score, sub };
}
for (const emp of tables.empresas) {
  const primerMes = emp.fecha_saldo_inicial.slice(0, 7);
  for (let mes = primerMes; mes <= '2026-11'; mes = sumarMeses(`${mes}-01`, 1).slice(0, 7)) {
    const [y, m] = mes.split('-').map(Number);
    const corte = mes === '2026-11' ? FECHA_DEMO : `${mes}-${String(ultimoDiaMes(y, m)).padStart(2, '0')}`;
    const { score, sub } = calcularScore(emp.empresa_id, mes, corte);
    tables.score_salud.push({ empresa_id: emp.empresa_id, mes, score, subindicadores: JSON.stringify(sub), version_formula: 'score-v1' });
  }
}

// =============================================================================
// 8. SALDO_DIARIO Y ETIQUETA DEFICIT_14D (null cuando la ventana de 14 días pasa del 14/11)
// =============================================================================
const ingresosSet = new Set(['venta', 'cobro_fiado', 'prestamo_recibido', 'otro_ingreso']);
for (const emp of tables.empresas) {
  const empId = emp.empresa_id;
  const fStart = emp.fecha_saldo_inicial;
  const nDays = daysBetween(fStart, FECHA_DEMO) + 1;
  const flujoPorFecha = new Map();
  for (const tx of txPorEmpresa.get(empId) || []) {
    if (!tx.afecta_caja || tx.anulada) continue;
    const f = tx.fecha_hora.slice(0, 10);
    const delta = ingresosSet.has(tx.tipo) ? cents(tx.monto) : -cents(tx.monto);
    flujoPorFecha.set(f, (flujoPorFecha.get(f) || 0) + delta);
  }
  const cierres = [];
  let saldo = cents(emp.saldo_inicial);
  for (let i = 0; i < nDays; i++) {
    const f = addDays(fStart, i);
    saldo += flujoPorFecha.get(f) || 0;
    cierres.push({ fecha: f, saldo });
  }
  const minOp = cents(emp.minimo_operativo);
  for (let i = 0; i < cierres.length; i++) {
    let deficit = null;
    if (i + 14 <= cierres.length - 1) {
      deficit = false;
      for (let j = i + 1; j <= i + 14; j++) {
        if (cierres[j].saldo < minOp) { deficit = true; break; }
      }
    }
    tables.saldo_diario.push({ empresa_id: empId, fecha: cierres[i].fecha, saldo_cierre: fmtMoney(fromCents(cierres[i].saldo)), deficit_14d: deficit });
  }
}

// =============================================================================
// 9. IDs DEFINITIVOS DE TRANSACCIONES Y DETALLE (ordenados por fecha y hora)
// =============================================================================
const ordenadas = [...tables.transacciones].sort((a, b) =>
  a.fecha_hora < b.fecha_hora ? -1 : a.fecha_hora > b.fecha_hora ? 1 : Number(a.transaccion_id.slice(1)) - Number(b.transaccion_id.slice(1))
);
const nuevoId = new Map();
ordenadas.forEach((t, i) => nuevoId.set(t.transaccion_id, padId('MOV', i + 1, 6)));
for (const t of tables.transacciones) t.transaccion_id = nuevoId.get(t.transaccion_id);
tables.transacciones = ordenadas;
for (const d of tables.detalle_transaccion) d.transaccion_id = nuevoId.get(d.transaccion_id);
tables.detalle_transaccion.sort((a, b) => (a.transaccion_id < b.transaccion_id ? -1 : a.transaccion_id > b.transaccion_id ? 1 : Number(a.detalle_id.slice(1)) - Number(b.detalle_id.slice(1))));
tables.detalle_transaccion.forEach((d, i) => { d.detalle_id = padId('DET', i + 1, 6); });

// =============================================================================
// 10. EXPORTACIÓN A CSV (siempre con encabezados, aunque la tabla quede vacía)
// =============================================================================
function toCsvValue(val) {
  if (val === null || val === undefined) return '';
  const str = String(val);
  if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function writeCsv(filePath, rows, explicitHeaders = null) {
  const headers = rows.length > 0 ? Object.keys(rows[0]) : explicitHeaders || [];
  if (headers.length === 0) return;
  const clave = [...headers].sort().join('|');
  for (const r of rows) {
    if (Object.keys(r).sort().join('|') !== clave) throw new Error(`${path.basename(filePath)}: fila con columnas distintas a las del encabezado: ${JSON.stringify(r).slice(0, 120)}`);
  }
  const lines = [headers.join(',')];
  for (const r of rows) lines.push(headers.map((h) => toCsvValue(r[h])).join(','));
  fs.writeFileSync(filePath, lines.join('\n') + '\n', 'utf8');
}

for (const [tableName, rows] of Object.entries(tables)) {
  writeCsv(path.join(CSV_DIR, `${tableName}.csv`), rows, TABLE_HEADERS[tableName]);
}

// Evaluación de la ingesta: frases distintas con el catálogo, los clientes y los proveedores REALES de Pedro (EMP-0001)
const CORTO_PROVEEDOR = { 'Mayorista Santa Anita': 'Santa Anita', 'Lácteos del Sur': 'Lácteos del Sur', 'Distribuidora Andina': 'Andina', 'Abarrotes El Sol': 'El Sol' };
const frasesEval = generarFrasesEval({
  productos: productosPedro.map((p) => ({ id: p.id, nombre: p.nombre, pv: p.pv })),
  clientes: clientesPedro.map((c) => ({ id: c.id, nombre: c.nombre })),
  proveedores: proveedoresPedro.map((p) => ({ nombre: p.nombre, corto: CORTO_PROVEEDOR[p.nombre] || p.nombre })),
});
fs.writeFileSync(path.join(EVAL_DIR, 'frases_ingesta_eval.json'), JSON.stringify(frasesEval, null, 2) + '\n', 'utf8');
writeCsv(path.join(EVAL_DIR, 'frases_ingesta_eval.csv'), frasesEval.map((f) => ({ ...f, items_esperados: JSON.stringify(f.items_esperados) })));

// =============================================================================
// 11. VERIFICACIÓN DE INVARIANTES (se imprime; el auditor completo es data/audit_quality.mjs)
// =============================================================================
const txPedro = tables.transacciones.filter((t) => t.empresa_id === 'EMP-0001' && !t.anulada);
const txPedroCaja = txPedro.filter((t) => t.afecta_caja);
const saldoFinalPedro = txPedroCaja.reduce((acc, t) => acc + (ingresosSet.has(t.tipo) ? cents(t.monto) : -cents(t.monto)), cents(1800)) / 100;
const sumaC = (arr) => sum(arr, (t) => cents(t.monto)) / 100;
const retNovPedro = sumaC(txPedroCaja.filter((t) => t.tipo === 'retiro_personal' && t.fecha_hora.startsWith('2026-11')));
const pendientesPedro = tables.deudas.filter((d) => d.empresa_id === 'EMP-0001' && d.fecha_pago_total === null);
const minSaldo = (empId) => Math.min(...tables.saldo_diario.filter((s) => s.empresa_id === empId).map((s) => Number(s.saldo_cierre)));
const negativas = tables.empresas.filter((e) => minSaldo(e.empresa_id) < 0).map((e) => `${e.empresa_id}(${minSaldo(e.empresa_id)})`);
const posterioresCorte = tables.transacciones.filter((t) => t.fecha_hora > `${FECHA_DEMO}T${HORA_CORTE}:00-05:00` || t.creado_en > `${FECHA_DEMO}T${HORA_CORTE}:00-05:00`).length;
const empConDeficit = new Set(tables.saldo_diario.filter((s) => s.deficit_14d === true).map((s) => s.empresa_id));

console.log('=== RESUMEN DE GENERACIÓN SINTÉTICA (SEED=42) ===');
for (const [k, v] of Object.entries(tables)) {
  console.log(`  ${k.padEnd(26)}: ${String(v.length).padStart(6)} filas`);
}
console.log('--- Verificación Bodega Don Pedro (EMP-0001) al 2026-11-14 ---');
console.log(`  Saldo Caja Negocio      : S/ ${saldoFinalPedro.toFixed(2)} (esperado: 2340.00)`);
console.log(`  Retiros Personales (Nov): S/ ${retNovPedro.toFixed(2)} (usual al 14: S/ ${usualPedro.toFixed(2)}; +700 = S/ ${(usualPedro + 700).toFixed(2)})`);
console.log(`  Pedidos pendientes      : ${pendientesPedro.map((d) => `${d.deuda_id} ${d.monto_total_a_pagar} vence ${d.fecha_vencimiento}`).join(' | ')}`);
console.log(`  Forecast del backend (data/demo_pedro_backend.json): 30/11 p50 = ${DEMO_BACKEND.forecast.lightgbm.serie.find((p) => p.fecha === '2026-11-30').p50} (LightGBM), ${DEMO_BACKEND.forecast.baseline.serie.find((p) => p.fecha === '2026-11-30').p50} (baseline)`);
console.log(`  Frases de evaluación de ingesta: ${frasesEval.length} (todas distintas: ${new Set(frasesEval.map((f) => f.frase.toLowerCase())).size})`);
console.log('--- Verificación global ---');
console.log(`  Empresas con saldo negativo : ${negativas.length ? negativas.join(', ') : 'ninguna'}`);
console.log(`  Movimientos posteriores a las ${HORA_CORTE} del ${FECHA_DEMO}: ${posterioresCorte}`);
console.log(`  Empresas con episodios de déficit (deficit_14d = true): ${empConDeficit.size} -> ${[...empConDeficit].join(' ')}`);
