/**
 * TuCaserito — Prueba del auditor con mutaciones: copia data/csv y data/eval a una carpeta temporal, inyecta UN error
 * conocido por vez y comprueba que data/audit_quality.mjs lo detecta (alguna comprobación pasa a FAIL).
 * No toca data/csv. Uso:  node data/audit_mutations.mjs
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { auditar, parseCsv } from './audit_quality.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CSV = path.join(__dirname, 'csv');
const EVAL = path.join(__dirname, 'eval');

const esc = (v) => (v === null || v === undefined ? '' : /[",\n\r]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
function editar(dir, tabla, fn) {
  const ruta = path.join(dir, `${tabla}.csv`);
  const filas = parseCsv(fs.readFileSync(ruta, 'utf8'));
  const enc = filas[0];
  const objs = filas.slice(1).map((f) => Object.fromEntries(enc.map((h, i) => [h, f[i]])));
  const salida = fn(objs) || objs;
  fs.writeFileSync(ruta, [enc.join(','), ...salida.map((o) => enc.map((h) => esc(o[h])).join(','))].join('\n') + '\n', 'utf8');
}

const MUTACIONES = [
  ['PK duplicada', (d) => editar(d, 'transacciones', (r) => [...r, { ...r[0] }])],
  ['FK huérfana (transacciones.categoria_id = CAT-99)', (d) => editar(d, 'transacciones', (r) => { r[4].categoria_id = 'CAT-99'; })],
  ['FK huérfana (cuaderno_fiado.cliente_id inexistente)', (d) => editar(d, 'cuaderno_fiado', (r) => { r[3].cliente_id = 'CLI-9999'; })],
  ['FK huérfana en una tabla que el auditor viejo no miraba (alertas.empresa_id)', (d) => editar(d, 'alertas', (r) => { r[0].empresa_id = 'EMP-0099'; })],
  ['ID de 34 caracteres', (d) => editar(d, 'transacciones', (r) => { r[2].transaccion_id = `MOV-${'X'.repeat(30)}`; })],
  ['Enum inválido (transacciones.tipo = venta_fiada)', (d) => editar(d, 'transacciones', (r) => { r[10].tipo = 'venta_fiada'; })],
  ['Categoría inexistente (nombre de categoría que no es snake_case del catálogo)', (d) => editar(d, 'categorias', (r) => { r[0].nombre = 'Bebidas Frías'; })],
  ['Cobro de fiado en la categoría equivocada (abarrotes)', (d) => editar(d, 'transacciones', (r) => { const t = r.find((x) => x.tipo === 'cobro_fiado'); t.categoria_id = 'CAT-02'; })],
  ['NOT NULL vacío (empresas.nombre_ficticio)', (d) => editar(d, 'empresas', (r) => { r[3].nombre_ficticio = ''; })],
  ['CHECK violado (afecta_caja = true en una venta a crédito)', (d) => editar(d, 'transacciones', (r) => { const t = r.find((x) => x.metodo_pago === 'credito'); t.afecta_caja = 'true'; })],
  ['CHECK violado (monto <= 0)', (d) => editar(d, 'transacciones', (r) => { r[7].monto = '-5.00'; })],
  ['Cantidad fraccionaria en detalle_transaccion', (d) => editar(d, 'detalle_transaccion', (r) => { r[0].cantidad = '243.600'; })],
  ['RUC con dígito verificador inválido (EMP-0001 = 10456789012)', (d) => editar(d, 'empresas', (r) => { r[0].ruc = '10456789012'; })],
  ['Registro posterior a la hora de corte (14/11 18:30)', (d) => editar(d, 'transacciones', (r) => { r[20].fecha_hora = '2026-11-14T18:30:00-05:00'; r[20].creado_en = '2026-11-14T18:30:00-05:00'; })],
  ['saldo_diario alterado', (d) => editar(d, 'saldo_diario', (r) => { r[40].saldo_cierre = '999999.00'; })],
  ['deficit_14d forzado a true', (d) => editar(d, 'saldo_diario', (r) => { const x = r.find((s) => s.empresa_id === 'EMP-0001' && s.fecha === '2026-11-10'); x.deficit_14d = 'true'; })],
  ['Alerta con entidad_tipo en singular', (d) => editar(d, 'alertas', (r) => { r[0].entidad_tipo = 'deuda'; })],
  ['Alerta con causas {causa, impacto}', (d) => editar(d, 'alertas', (r) => { r[0].causas = '[{"causa":"retiro","impacto":700}]'; })],
  ['Borrador con la clave fiados_propuestos', (d) => editar(d, 'borradores', (r) => { r[0].payload_propuesto = r[0].payload_propuesto.replace('"fiados"', '"fiados_propuestos"'); })],
  ['score_salud con 7 subindicadores', (d) => editar(d, 'score_salud', (r) => { r[0].subindicadores = '{"a":1,"b":2,"c":3,"d":4,"e":5,"f":6,"g":7}'; })],
  ['predicciones_fiado 0.600 marcado como medio', (d) => editar(d, 'predicciones_fiado', (r) => { r[0].prob_atraso = '0.600'; r[0].nivel_riesgo = 'medio'; })],
  ['Frase repetida con sufijo "(muestra 2)" en la evaluación', (d, ev) => {
    const j = JSON.parse(fs.readFileSync(path.join(ev, 'frases_ingesta_eval.json'), 'utf8'));
    j.push({ ...j[0], caso_id: 'EVF-999', frase: `${j[0].frase} (muestra 2)` });
    fs.writeFileSync(path.join(ev, 'frases_ingesta_eval.json'), JSON.stringify(j), 'utf8');
  }],
];

const base = auditar(CSV);
console.log(`Línea base (data/csv real): ${base.resumen.pass} PASS, ${base.resumen.warn} WARN, ${base.resumen.fail} FAIL\n`);
let sinDetectar = 0;
const filas = [];
for (const [nombre, aplicar] of MUTACIONES) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'tucaserito-mut-'));
  const csv = path.join(tmp, 'csv');
  const ev = path.join(tmp, 'eval');
  fs.cpSync(CSV, csv, { recursive: true });
  fs.cpSync(EVAL, ev, { recursive: true });
  try {
    aplicar(csv, ev);
    const r = auditar(csv, { evalDir: ev });
    const falla = r.checks.filter((c) => c.estado === 'FAIL');
    const detectada = falla.length > 0;
    if (!detectada) sinDetectar++;
    filas.push([detectada ? 'DETECTADA' : 'NO DETECTADA', nombre, falla.map((c) => c.regla.split(':')[0].slice(0, 60)).slice(0, 2).join(' / ')]);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}
for (const f of filas) console.log(`${f[0].padEnd(13)} | ${f[1]}\n${' '.repeat(16)}-> ${f[2]}`);
console.log(`\n${MUTACIONES.length - sinDetectar}/${MUTACIONES.length} mutaciones detectadas`);
process.exit(sinDetectar === 0 && base.resumen.fail === 0 ? 0 : 1);
