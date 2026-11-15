/**
 * TuCaserito — Auditor de calidad de datos: valida data/csv/*.csv CONTRA EL ESQUEMA REAL.
 *
 * El esquema sale de data/schema_esquema.json (exportado desde backend/app/db/models.py por
 * data/pipeline_python/generar_schema.py). Se valida:
 *   A. Estructura: los 25 CSV existen y sus columnas coinciden con las de la tabla.
 *   B. Por columna: NOT NULL, tipo (boolean, fecha, fecha-hora, número con su precisión/escala, entero, JSON), largo
 *      de varchar(n)/char(n) y valores de cada enum.
 *   C. Llaves: PK únicas (simples y compuestas), TODAS las FK, UNIQUE e índices únicos (parcial de sueldo activo).
 *   D. CHECK: se interpretan TODOS los CHECK de models.py (lógica de tres valores como PostgreSQL).
 *   E. Reglas de negocio de los datos: cuadre del saldo diario y de deficit_14d, caja nunca negativa, detalle con
 *      cantidades enteras y subtotal = cantidad x precio, hora de corte del 14/11, fuga de datos, categorías por tipo de
 *      movimiento, borradores confirmados con su transacción, alertas (causas/entidad), score de salud con la fórmula del
 *      backend, RUC con dígito verificador SUNAT, y el dataset de evaluación de ingesta.
 *
 * Uso:  node data/audit_quality.mjs [--csv <carpeta>] [--no-escribir]
 * Escribe data/AUDITORIA_CALIDAD_DATOS.md y .json con la fecha real de la auditoría y sale con código 1 si algo FALLA.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const FECHA_CORTE = '2026-11-14';
export const HORA_CORTE = '10:00';

// ── CSV ─────────────────────────────────────────────────────────────────────────────────────────
export function parseCsv(contenido) {
  const filas = [];
  let fila = [];
  let campo = '';
  let comillas = false;
  for (let i = 0; i < contenido.length; i++) {
    const ch = contenido[i];
    if (comillas) {
      if (ch === '"' && contenido[i + 1] === '"') { campo += '"'; i++; }
      else if (ch === '"') comillas = false;
      else campo += ch;
    } else if (ch === '"') comillas = true;
    else if (ch === ',') { fila.push(campo); campo = ''; }
    else if (ch === '\n') {
      fila.push(campo.replace(/\r$/, ''));
      campo = '';
      if (fila.length > 1 || fila[0] !== '') filas.push(fila);
      fila = [];
    } else campo += ch;
  }
  if (campo !== '' || fila.length) { fila.push(campo); filas.push(fila); }
  return filas;
}

function leerTabla(ruta) {
  const filas = parseCsv(fs.readFileSync(ruta, 'utf8'));
  const encabezado = filas[0] || [];
  return { encabezado, filas: filas.slice(1).map((f) => Object.fromEntries(encabezado.map((h, i) => [h, f[i] === undefined || f[i] === '' ? null : f[i]]))) };
}

// ── intérprete de CHECK (subconjunto de SQL, lógica de tres valores) ───────────────────────────
function tokenizar(sql) {
  const re = /\s*(?:(\d+(?:\.\d+)?)|'((?:[^']|'')*)'|([A-Za-z_][A-Za-z0-9_]*)|(<>|<=|>=|=|<|>|~|\(|\)|,))/y;
  const out = [];
  let m;
  while (re.lastIndex < sql.length && (m = re.exec(sql))) {
    if (m[1] !== undefined) out.push({ t: 'num', v: Number(m[1]) });
    else if (m[2] !== undefined) out.push({ t: 'str', v: m[2].replace(/''/g, "'") });
    else if (m[3] !== undefined) out.push({ t: 'id', v: m[3] });
    else out.push({ t: 'op', v: m[4] });
  }
  if (re.lastIndex < sql.trimEnd().length) throw new Error(`CHECK no interpretable: ${sql}`);
  return out;
}

export function compilarCheck(sql) {
  const toks = tokenizar(sql);
  let p = 0;
  const kw = (v) => toks[p] && toks[p].t === 'id' && toks[p].v.toUpperCase() === v;
  const op = (v) => toks[p] && toks[p].t === 'op' && toks[p].v === v;
  const and3 = (xs) => (xs.includes(false) ? false : xs.includes(null) ? null : true);
  const or3 = (xs) => (xs.includes(true) ? true : xs.includes(null) ? null : false);

  function orExpr() {
    const partes = [andExpr()];
    while (kw('OR')) { p++; partes.push(andExpr()); }
    return partes.length === 1 ? partes[0] : (r) => or3(partes.map((f) => f(r)));
  }
  function andExpr() {
    const partes = [notExpr()];
    while (kw('AND')) { p++; partes.push(notExpr()); }
    return partes.length === 1 ? partes[0] : (r) => and3(partes.map((f) => f(r)));
  }
  function notExpr() {
    if (kw('NOT')) { p++; const f = notExpr(); return (r) => { const v = f(r); return v === null ? null : !v; }; }
    return cmpExpr();
  }
  function cmpExpr() {
    const izq = primario();
    if (kw('IS')) {
      p++;
      const negado = kw('NOT');
      if (negado) p++;
      if (!kw('NULL')) throw new Error(`IS esperado NULL en ${sql}`);
      p++;
      return (r) => (izq(r) === null) !== negado;
    }
    let negado = false;
    if (kw('NOT') && toks[p + 1] && toks[p + 1].v.toUpperCase() === 'IN') { negado = true; p++; }
    if (kw('IN')) {
      p++;
      if (!op('(')) throw new Error('IN espera (');
      p++;
      const lista = [];
      while (!op(')')) { if (op(',')) p++; else lista.push(toks[p++].v); }
      p++;
      return (r) => { const v = izq(r); return v === null ? null : lista.includes(v) !== negado; };
    }
    if (kw('BETWEEN')) {
      p++;
      const a = primario();
      if (!kw('AND')) throw new Error('BETWEEN espera AND');
      p++;
      const b = primario();
      return (r) => { const v = izq(r); return v === null ? null : v >= a(r) && v <= b(r); };
    }
    if (toks[p] && toks[p].t === 'op' && ['=', '<>', '<', '<=', '>', '>=', '~'].includes(toks[p].v)) {
      const o = toks[p++].v;
      const der = primario();
      return (r) => {
        const a = izq(r);
        const b = der(r);
        if (a === null || b === null) return null;
        switch (o) {
          case '=': return a === b;
          case '<>': return a !== b;
          case '<': return a < b;
          case '<=': return a <= b;
          case '>': return a > b;
          case '>=': return a >= b;
          default: return new RegExp(b).test(String(a));
        }
      };
    }
    return izq;
  }
  function primario() {
    const tk = toks[p++];
    if (tk.t === 'num' || tk.t === 'str') return () => tk.v;
    if (tk.t === 'op' && tk.v === '(') { const f = orExpr(); p++; return f; }
    if (tk.t === 'id') {
      if (op('(')) { // función: num_nonnulls(a, b, ...)
        p++;
        const args = [];
        while (!op(')')) { if (op(',')) p++; else args.push(primario()); }
        p++;
        if (tk.v === 'num_nonnulls') return (r) => args.filter((f) => f(r) !== null).length;
        throw new Error(`función no soportada: ${tk.v}`);
      }
      if (tk.v.toUpperCase() === 'TRUE') return () => true;
      if (tk.v.toUpperCase() === 'FALSE') return () => false;
      return (r) => (r[tk.v] === undefined ? null : r[tk.v]);
    }
    throw new Error(`token inesperado en CHECK: ${sql}`);
  }
  const f = orExpr();
  if (p < toks.length) throw new Error(`CHECK con texto sobrante: ${sql}`);
  return f;
}

// ── tipos de columna ───────────────────────────────────────────────────────────────────────────
const RE_FECHA = /^\d{4}-\d{2}-\d{2}$/;
const RE_TS = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;
const fechaValida = (s) => RE_FECHA.test(s) && !Number.isNaN(Date.parse(`${s}T00:00:00Z`)) && new Date(`${s}T00:00:00Z`).toISOString().slice(0, 10) === s;

function validarValor(col, v, enums) {
  const t = col.tipo;
  const b = t.base;
  if (t.enum) return enums[t.enum].includes(v) ? null : `valor '${v}' no pertenece al enum ${t.enum}`;
  if (b === 'varchar' || b === 'char') return v.length <= t.largo ? null : `largo ${v.length} > ${b}(${t.largo})`;
  if (b === 'boolean') return v === 'true' || v === 'false' ? null : `booleano inválido '${v}'`;
  if (b === 'date') return fechaValida(v) ? null : `fecha inválida '${v}'`;
  if (b === 'timestamp') return RE_TS.test(v) && !Number.isNaN(Date.parse(v)) ? null : `fecha-hora inválida '${v}'`;
  if (b === 'time') return /^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$/.test(v) ? null : `hora inválida '${v}'`;
  if (b === 'numeric') {
    if (!/^-?\d+(\.\d+)?$/.test(v)) return `número inválido '${v}'`;
    const [ent, dec = ''] = v.replace('-', '').split('.');
    if (dec.length > t.escala) return `más de ${t.escala} decimales (${v})`;
    if (ent.replace(/^0+(?=\d)/, '').length > t.precision - t.escala) return `excede numeric(${t.precision},${t.escala}) (${v})`;
    return null;
  }
  if (b === 'smallint') return /^-?\d+$/.test(v) && Math.abs(Number(v)) <= 32767 ? null : `smallint inválido '${v}'`;
  if (b === 'integer') return /^-?\d+$/.test(v) && Math.abs(Number(v)) <= 2147483647 ? null : `integer inválido '${v}'`;
  if (b === 'json') { try { JSON.parse(v); return null; } catch { return `JSON inválido`; } }
  return null; // text
}

function tipar(col, v) {
  if (v === null) return null;
  const b = col.tipo.base;
  if (b === 'numeric' || b === 'smallint' || b === 'integer') return Number(v);
  if (b === 'boolean') return v === 'true';
  return v;
}

// ── RUC SUNAT ──────────────────────────────────────────────────────────────────────────────────
export function rucValido(ruc) {
  if (!/^\d{11}$/.test(ruc)) return false;
  const pesos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2];
  const suma = pesos.reduce((a, p, i) => a + p * Number(ruc[i]), 0);
  return (11 - (suma % 11)) % 10 === Number(ruc[10]);
}

// ── auditoría ──────────────────────────────────────────────────────────────────────────────────
export function auditar(csvDir, opciones = {}) {
  const esquema = JSON.parse(fs.readFileSync(path.join(__dirname, 'schema_esquema.json'), 'utf8'));
  const evalDir = opciones.evalDir || path.join(__dirname, 'eval');
  const checks = [];
  const fallos = (nombre) => checks.filter((c) => c.categoria === nombre && c.estado === 'FAIL').length;
  const registrar = (categoria, regla, violaciones, evidencia, severidad = 'FAIL') =>
    checks.push({ categoria, regla, estado: violaciones.length === 0 ? 'PASS' : severidad, violaciones: violaciones.length, evidencia: violaciones.length === 0 ? evidencia : `${violaciones.length} violaciones. Ejemplos: ${violaciones.slice(0, 4).join(' | ')}` });

  const tablasDbml = esquema.tablas_dbml;
  const db = {};
  const encabezados = {};
  // A. estructura
  const faltantes = [];
  const columnasMal = [];
  for (const t of tablasDbml) {
    const ruta = path.join(csvDir, `${t}.csv`);
    if (!fs.existsSync(ruta)) { faltantes.push(`${t}.csv`); continue; }
    const { encabezado, filas } = leerTabla(ruta);
    db[t] = filas;
    encabezados[t] = encabezado;
    const esperadas = esquema.tablas[t].columnas.map((c) => c.nombre);
    const sobran = encabezado.filter((c) => !esperadas.includes(c));
    const faltan = esperadas.filter((c) => !encabezado.includes(c) && !esquema.tablas[t].columnas.find((x) => x.nombre === c).nullable && !esquema.tablas[t].columnas.find((x) => x.nombre === c).tiene_default);
    if (sobran.length || faltan.length) columnasMal.push(`${t}: sobran [${sobran}] faltan [${faltan}]`);
  }
  registrar('A. Estructura', `Los ${tablasDbml.length} CSV del modelo existen`, faltantes, `${tablasDbml.length - faltantes.length}/${tablasDbml.length} archivos`);
  registrar('A. Estructura', 'Las columnas de cada CSV coinciden con las de la tabla (ninguna extra, ninguna obligatoria faltante)', columnasMal, 'columnas coinciden con schema_esquema.json');
  for (const t of tablasDbml) if (!db[t]) db[t] = [];

  // B. columnas: NOT NULL, tipo, largo, enum
  const nn = [], tipos = [], enumsMal = [], largos = [];
  for (const t of tablasDbml) {
    for (const col of esquema.tablas[t].columnas) {
      if (!encabezados[t] || !encabezados[t].includes(col.nombre)) continue;
      db[t].forEach((fila, i) => {
        const v = fila[col.nombre];
        const ref = `${t}[${i + 2}].${col.nombre}`;
        if (v === null) { if (!col.nullable) nn.push(`${ref} es NULL`); return; }
        const err = validarValor(col, v, esquema.enums);
        if (err) (col.tipo.enum ? enumsMal : err.startsWith('largo') ? largos : tipos).push(`${ref}: ${err}`);
      });
    }
  }
  const nFilas = Object.values(db).reduce((a, x) => a + x.length, 0);
  registrar('B. Columnas', 'NOT NULL: ninguna columna obligatoria vacía', nn, `${nFilas} filas revisadas`);
  registrar('B. Columnas', 'Largo máximo de varchar(n)/char(n) (p. ej. IDs de 20 caracteres)', largos, 'todos los textos caben en su columna');
  registrar('B. Columnas', 'Tipos: boolean, date, timestamptz, time, numeric(p,s), smallint/integer, JSON válidos', tipos, 'todos los valores tienen el formato de su columna');
  registrar('B. Columnas', 'Enums: cada valor pertenece a su tipo enumerado', enumsMal, 'todos los valores están en su enum');

  // C. llaves
  const tipado = {};
  for (const t of tablasDbml) {
    tipado[t] = db[t].map((f) => {
      const r = {};
      for (const col of esquema.tablas[t].columnas) r[col.nombre] = tipar(col, f[col.nombre] === undefined ? null : f[col.nombre]);
      return r;
    });
  }
  const pkDup = [];
  for (const t of tablasDbml) {
    const vistos = new Set();
    for (const f of db[t]) {
      const k = esquema.tablas[t].pk.map((c) => f[c]).join('¦');
      if (vistos.has(k)) pkDup.push(`${t}: PK repetida ${k}`); else vistos.add(k);
    }
  }
  registrar('C. Llaves', 'PK únicas (simples y compuestas) en las 25 tablas', pkDup, `${nFilas} filas`);
  const pkSet = {};
  for (const t of tablasDbml) pkSet[t] = new Set(db[t].map((f) => f[esquema.tablas[t].pk[0]]));
  const fkRotas = [];
  let nFk = 0;
  for (const t of tablasDbml) {
    for (const fk of esquema.tablas[t].fks) {
      nFk++;
      const destino = pkSet[fk.tabla] || new Set((db[fk.tabla] || []).map((f) => f[fk.destino]));
      for (const f of db[t]) if (f[fk.columna] !== null && !destino.has(f[fk.columna])) fkRotas.push(`${t}.${fk.columna}='${f[fk.columna]}' no existe en ${fk.tabla}`);
    }
  }
  registrar('C. Llaves', `Todas las FK (${nFk} relaciones del esquema) apuntan a un registro existente`, fkRotas, `${nFk} FK sin huérfanos`);
  const unicos = [];
  for (const t of tablasDbml) {
    const defs = [...esquema.tablas[t].unicos, ...esquema.tablas[t].indices_unicos.filter((i) => !i.parcial)];
    for (const u of defs) {
      const vistos = new Set();
      for (const f of db[t]) {
        const vals = u.columnas.map((c) => f[c]);
        if (vals.some((v) => v === null)) continue;
        const k = vals.join('¦');
        if (vistos.has(k)) unicos.push(`${t}: ${u.nombre} repetido (${k})`); else vistos.add(k);
      }
    }
  }
  const sueldos = new Map();
  for (const f of tipado.movimientos_programados) if (f.es_sueldo && f.activo) sueldos.set(f.empresa_id, (sueldos.get(f.empresa_id) || 0) + 1);
  for (const [e, n] of sueldos) if (n > 1) unicos.push(`movimientos_programados: ${e} tiene ${n} sueldos activos`);
  registrar('C. Llaves', 'UNIQUE e índices únicos (ruc, teléfono, nombre de rubro/categoría, un sueldo activo por empresa, impuesto y billetera 1-1…)', unicos, 'sin repetidos');

  // D. CHECK
  const checkMal = [];
  let nChecks = 0;
  for (const t of tablasDbml) {
    for (const ck of esquema.tablas[t].checks) {
      let f;
      try { f = compilarCheck(ck.sql); } catch (e) { checkMal.push(`${t}.${ck.nombre}: ${e.message}`); continue; }
      nChecks++;
      tipado[t].forEach((r, i) => { if (f(r) === false) checkMal.push(`${t}[${i + 2}] viola ${ck.nombre} (${ck.sql})`); });
    }
  }
  registrar('D. CHECK', `Los ${nChecks} CHECK de models.py se cumplen (afecta_caja, un solo vínculo, cobro/pago con su vínculo, moneda PEN, 0-1, RUC, periodos AAAA-MM…)`, checkMal, `${nChecks} CHECK evaluados sobre todas las filas`);

  // E. reglas de negocio
  const corteFin = `${FECHA_CORTE}T${HORA_CORTE}:00-05:00`;
  const tx = tipado.transacciones;
  const empresas = tipado.empresas;
  const dia = (s) => s.slice(0, 10);
  const lima = (s) => new Date(s).getTime();
  const corteMs = lima(corteFin);
  const enDemo = tx.filter((t) => lima(t.fecha_hora) > corteMs || lima(t.creado_en) > corteMs);
  registrar('E. Negocio', `Nada posterior a la hora de corte (${HORA_CORTE} del ${FECHA_CORTE}, Lima): transacciones, fiados, pagos, predicciones, conversaciones, borradores`, [
    ...enDemo.map((t) => `${t.transaccion_id} ${t.fecha_hora}`),
    ...tipado.predicciones_saldo.filter((p) => lima(p.creado_en) > corteMs).map((p) => `${p.prediccion_id} creado_en ${p.creado_en}`),
    ...tipado.predicciones_fiado.filter((p) => lima(p.creado_en) > corteMs).map((p) => `${p.prediccion_id} creado_en ${p.creado_en}`),
    ...tipado.conversaciones.filter((c) => lima(c.fecha_hora) > corteMs).map((c) => `${c.mensaje_id} ${c.fecha_hora}`),
    ...tipado.borradores.filter((b) => lima(b.creado_en) > corteMs || (b.resuelto_en && lima(b.resuelto_en) > corteMs)).map((b) => `${b.borrador_id}`),
    ...tipado.alertas.filter((a) => lima(a.creada_en) > corteMs || (a.enviada_en && lima(a.enviada_en) > corteMs)).map((a) => `${a.alerta_id}`),
    ...tipado.cuaderno_fiado.filter((f) => f.fecha_fiado > FECHA_CORTE || (f.fecha_pago_total && f.fecha_pago_total > FECHA_CORTE)).map((f) => `${f.fiado_id} fechas futuras`),
    ...tipado.deudas.filter((d) => d.fecha_inicio > FECHA_CORTE || (d.fecha_pago_total && d.fecha_pago_total > FECHA_CORTE)).map((d) => `${d.deuda_id} fechas futuras`),
    ...tipado.impuestos.filter((i) => i.fecha_pago && i.fecha_pago > FECHA_CORTE).map((i) => `${i.impuesto_id} pagado en el futuro`),
    ...tipado.saldo_diario.filter((s) => s.fecha > FECHA_CORTE).map((s) => `saldo_diario ${s.empresa_id} ${s.fecha}`),
  ], 'cero registros posteriores al corte; la venta "2 cervezas" y los movimientos de la demo no están cargados');
  registrar('E. Negocio', 'Cero fuga de datos: creado_en nunca es anterior a la fecha del hecho que registra salvo registro tardío explícito, y los pagos no preceden a su origen', [
    ...tx.filter((t) => lima(t.creado_en) < lima(t.fecha_hora) - 60000).map((t) => `${t.transaccion_id} creado_en < fecha_hora`),
    ...tipado.cuaderno_fiado.filter((f) => f.fecha_pago_total && f.fecha_pago_total < f.fecha_fiado).map((f) => `${f.fiado_id} pagado antes de fiarse`),
    ...tipado.deudas.filter((d) => d.fecha_pago_total && d.fecha_pago_total < d.fecha_inicio).map((d) => `${d.deuda_id} pagada antes de empezar`),
  ], 'orden temporal coherente');

  // saldo diario y etiqueta
  const txPorEmp = new Map();
  for (const t of tx) { if (!txPorEmp.has(t.empresa_id)) txPorEmp.set(t.empresa_id, []); txPorEmp.get(t.empresa_id).push(t); }
  const INGRESOS = new Set(['venta', 'cobro_fiado', 'prestamo_recibido', 'otro_ingreso']);
  const sdMal = [], negativos = [], etiquetaMal = [];
  const sdPorEmp = new Map();
  for (const s of tipado.saldo_diario) { if (!sdPorEmp.has(s.empresa_id)) sdPorEmp.set(s.empresa_id, []); sdPorEmp.get(s.empresa_id).push(s); }
  const sumaDia = (e) => {
    const m = new Map();
    for (const t of txPorEmp.get(e.empresa_id) || []) {
      if (!t.afecta_caja || t.anulada) continue;
      const d = dia(t.fecha_hora);
      m.set(d, (m.get(d) || 0) + Math.round(t.monto * 100) * (INGRESOS.has(t.tipo) ? 1 : -1));
    }
    return m;
  };
  const sumarDias = (f, n) => { const d = new Date(`${f}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
  for (const e of empresas) {
    const filas = (sdPorEmp.get(e.empresa_id) || []).sort((a, b) => (a.fecha < b.fecha ? -1 : 1));
    const flujo = sumaDia(e);
    let saldo = Math.round(e.saldo_inicial * 100);
    const esperado = [];
    for (let f = e.fecha_saldo_inicial; f <= FECHA_CORTE; f = sumarDias(f, 1)) { saldo += flujo.get(f) || 0; esperado.push({ f, saldo }); }
    if (filas.length !== esperado.length) { sdMal.push(`${e.empresa_id}: ${filas.length} filas y se esperaban ${esperado.length}`); continue; }
    esperado.forEach((x, i) => {
      if (filas[i].fecha !== x.f || Math.round(filas[i].saldo_cierre * 100) !== x.saldo) sdMal.push(`${e.empresa_id} ${x.f}: saldo ${filas[i].saldo_cierre} vs ${x.saldo / 100}`);
      if (x.saldo < 0) negativos.push(`${e.empresa_id} ${x.f}: ${x.saldo / 100}`);
      const min = Math.round(e.minimo_operativo * 100);
      let esp = null;
      if (i + 14 <= esperado.length - 1) esp = esperado.slice(i + 1, i + 15).some((y) => y.saldo < min);
      if (filas[i].deficit_14d !== esp) etiquetaMal.push(`${e.empresa_id} ${x.f}: deficit_14d=${filas[i].deficit_14d} esperado=${esp}`);
    });
  }
  registrar('E. Negocio', 'saldo_diario = saldo inicial + Σ movimientos que afectan caja (todas las empresas, todos los días)', sdMal, `${tipado.saldo_diario.length} filas recalculadas`);
  registrar('E. Negocio', 'Ninguna empresa tiene saldo de caja negativo', negativos, 'mínimo de cada empresa >= 0');
  registrar('E. Negocio', 'deficit_14d recalculado (saldo < mínimo operativo en los 14 días siguientes); null si la ventana pasa del corte', etiquetaMal, 'etiqueta consistente');
  const conDeficit = new Set(tipado.saldo_diario.filter((s) => s.deficit_14d === true).map((s) => s.empresa_id));
  registrar('E. Negocio', 'Hay episodios reales de déficit en varias bodegas para medir recall (>= 5 empresas con deficit_14d = true)', conDeficit.size >= 5 ? [] : [`solo ${conDeficit.size}`], `${conDeficit.size} empresas con episodios`, 'WARN');

  // detalle
  const detMal = [];
  const detPorTx = new Map();
  for (const d of tipado.detalle_transaccion) {
    if (!Number.isInteger(d.cantidad)) detMal.push(`${d.detalle_id} cantidad fraccionaria ${d.cantidad}`);
    if (Math.round(d.cantidad * d.precio_unitario * 100) !== Math.round(d.subtotal * 100)) detMal.push(`${d.detalle_id} subtotal ${d.subtotal} != ${d.cantidad} x ${d.precio_unitario}`);
    detPorTx.set(d.transaccion_id, (detPorTx.get(d.transaccion_id) || 0) + Math.round(d.subtotal * 100));
  }
  const porId = new Map(tx.map((t) => [t.transaccion_id, t]));
  for (const [id, c] of detPorTx) { const t = porId.get(id); if (t && Math.round(t.monto * 100) !== c) detMal.push(`${id}: monto ${t.monto} != Σ detalle ${c / 100}`); }
  registrar('E. Negocio', 'detalle_transaccion: cantidades enteras, subtotal = cantidad x precio y Σ subtotales = monto de la transacción', detMal, `${tipado.detalle_transaccion.length} líneas`);

  // categorías por tipo de movimiento
  const catPorId = new Map(tipado.categorias.map((c) => [c.categoria_id, c]));
  const CAT_TIPO = { cobro_fiado: 'cobro_fiados', prestamo_recibido: 'prestamos_recibidos', retiro_personal: 'retiro_personal', pago_impuesto: 'impuestos', pago_prestamo: 'financiamiento' };
  const catMal = [];
  for (const t of tx) {
    const c = catPorId.get(t.categoria_id);
    if (!c) continue;
    if (CAT_TIPO[t.tipo] && c.nombre !== CAT_TIPO[t.tipo]) catMal.push(`${t.transaccion_id} ${t.tipo} en categoría '${c.nombre}' (debe ser '${CAT_TIPO[t.tipo]}')`);
    if (c.tipo !== (INGRESOS.has(t.tipo) ? 'ingreso' : 'egreso')) catMal.push(`${t.transaccion_id} ${t.tipo} en categoría de tipo ${c.tipo}`);
  }
  registrar('E. Negocio', 'Categorías: cobros de fiado, préstamos, retiros, impuestos y cuotas en su categoría; ingresos en categorías de ingreso y egresos en categorías de egreso', catMal, 'categorías coherentes con el tipo');
  const nombresCat = tipado.categorias.map((c) => c.nombre);
  registrar('E. Negocio', 'Catálogo de categorías snake_case con cobro_fiados, prestamos_recibidos y otros_gastos; rubros bodega/restaurante/taller/distribuidora', [
    ...['cobro_fiados', 'prestamos_recibidos', 'otros_gastos', 'retiro_personal', 'mercaderia'].filter((n) => !nombresCat.includes(n)).map((n) => `falta categoría ${n}`),
    ...nombresCat.filter((n) => !/^[a-z]+(_[a-z]+)*$/.test(n)).map((n) => `categoría no snake_case: ${n}`),
    ...tipado.rubros.map((r) => r.nombre).filter((n) => !['bodega', 'restaurante', 'taller', 'distribuidora'].includes(n)).map((n) => `rubro inesperado ${n}`),
  ], `${nombresCat.length} categorías y ${tipado.rubros.length} rubros`);

  // borradores
  const borMal = [];
  const conTx = new Set([...tx.map((t) => t.borrador_id), ...tipado.cuaderno_fiado.map((f) => f.borrador_id), ...tipado.deudas.map((d) => d.borrador_id)].filter(Boolean));
  for (const b of tipado.borradores) {
    let payload;
    try { payload = JSON.parse(b.payload_propuesto); } catch { borMal.push(`${b.borrador_id} payload ilegible`); continue; }
    if (b.estado === 'confirmado' && !conTx.has(b.borrador_id)) borMal.push(`${b.borrador_id} confirmado sin transacción`);
    if (b.confianza !== null && b.confianza < 0.75 && !b.pregunta_aclaratoria) borMal.push(`${b.borrador_id} confianza < 0.75 sin pregunta aclaratoria`);
    if (b.canal === 'foto' && payload.fiados === undefined && payload.tipo === undefined) borMal.push(`${b.borrador_id} foto sin clave 'fiados' ni 'tipo'`);
    if (payload.fiados_propuestos !== undefined) borMal.push(`${b.borrador_id} usa la clave 'fiados_propuestos' (el backend lee 'fiados')`);
    if (b.estado === 'confirmado' && b.correcciones && payload.monto !== undefined) {
      const corr = JSON.parse(b.correcciones);
      const t = tx.find((x) => x.borrador_id === b.borrador_id);
      if (corr.monto !== undefined && t && Math.abs(t.monto - corr.monto) > 0.001) borMal.push(`${b.borrador_id}: corrección ${corr.monto} pero la transacción es ${t.monto}`);
    }
  }
  registrar('E. Negocio', 'Borradores: payload legible con clave del backend, confirmados con su transacción y monto corregido coherente, confianza < 0.75 con pregunta aclaratoria', borMal, `${tipado.borradores.length} borradores`);

  // alertas
  const ENTIDAD = { deudas: 'deuda_id', impuestos: 'impuesto_id', cuaderno_fiado: 'fiado_id', transacciones: 'transaccion_id', reglas_meta: 'meta_id' };
  const alMal = [];
  for (const a of tipado.alertas) {
    let causas = null;
    try { causas = a.causas === null ? null : JSON.parse(a.causas); } catch { alMal.push(`${a.alerta_id} causas ilegibles`); continue; }
    if (causas && (!Array.isArray(causas) || causas.some((c) => typeof c.descripcion !== 'string' || typeof c.monto !== 'number'))) alMal.push(`${a.alerta_id} causas sin la forma {descripcion, monto}`);
    if (a.entidad_tipo === 'mes') { if (!/^\d{4}-\d{2}$/.test(a.entidad_id || '')) alMal.push(`${a.alerta_id} entidad mes con id '${a.entidad_id}'`); }
    else if (a.entidad_tipo !== null) {
      if (!ENTIDAD[a.entidad_tipo]) { alMal.push(`${a.alerta_id} entidad_tipo '${a.entidad_tipo}' no es una tabla en plural ni 'mes'`); continue; }
      const existe = (tipado[a.entidad_tipo] || []).some((r) => r[ENTIDAD[a.entidad_tipo]] === a.entidad_id);
      if (!existe) alMal.push(`${a.alerta_id} entidad ${a.entidad_tipo}/${a.entidad_id} no existe`);
    }
    if (a.tipo === 'pedido_excesivo' && (!causas || causas.length < 2)) alMal.push(`${a.alerta_id} pedido_excesivo con ${causas ? causas.length : 0} causas (el backend arma 2)`);
    if (a.tipo === 'retiro_excesivo' && (a.entidad_tipo !== 'mes' || !causas || causas.length < 2)) alMal.push(`${a.alerta_id} retiro_excesivo mal formado`);
    if (a.tipo === 'faltante_caja' && (!causas || causas.length < 1)) alMal.push(`${a.alerta_id} faltante_caja sin causas`);
    if (a.prioridad !== { faltante_caja: 1, pedido_excesivo: 2, retiro_excesivo: 3, obligacion_proxima: 4, gasto_inusual: 5, caida_ventas: 5, fiado_vencido: 6, meta_lograda: 7, resumen_semanal: 8 }[a.tipo]) alMal.push(`${a.alerta_id} prioridad ${a.prioridad} no corresponde al tipo ${a.tipo}`);
    if (a.estado !== 'activa' && a.accion_tomada === null) alMal.push(`${a.alerta_id} ${a.estado} sin accion_tomada`);
  }
  registrar('E. Negocio', 'Alertas: causas {descripcion, monto}, entidad existente (plural) o `mes`, prioridad según el tipo, causas de pedido/retiro como las arma el backend', alMal, `${tipado.alertas.length} alertas`);

  // score de salud
  const PESOS = { constancia_registro: 0.35, separacion_personal: 0.4, impuestos_al_dia: 0.25 };
  const scMal = [];
  for (const s of tipado.score_salud) {
    const sub = JSON.parse(s.subindicadores);
    if (Object.keys(sub).sort().join() !== Object.keys(PESOS).sort().join()) { scMal.push(`${s.empresa_id} ${s.mes}: subindicadores ${Object.keys(sub)}`); continue; }
    const calc = Math.round(Object.keys(PESOS).reduce((a, k) => a + PESOS[k] * sub[k], 0));
    if (Math.abs(calc - s.score) > 1) scMal.push(`${s.empresa_id} ${s.mes}: score ${s.score} vs fórmula ${calc}`);
    if (s.version_formula !== 'score-v1') scMal.push(`${s.empresa_id} ${s.mes}: version_formula ${s.version_formula}`);
  }
  registrar('E. Negocio', 'score_salud: 3 subindicadores con los pesos del backend (0.35 / 0.40 / 0.25) y score = suma ponderada', scMal, `${tipado.score_salud.length} scores`);

  // predicciones y modelo
  const predMal = [];
  for (const p of tipado.predicciones_fiado) { const n = p.prob_atraso >= 0.6 ? 'alto' : p.prob_atraso >= 0.3 ? 'medio' : 'bajo'; if (n !== p.nivel_riesgo) predMal.push(`${p.prediccion_id} prob ${p.prob_atraso} es '${n}' y dice '${p.nivel_riesgo}'`); }
  for (const p of tipado.predicciones_saldo) if (!(p.p10 <= p.p50 && p.p50 <= p.p90)) predMal.push(`${p.prediccion_id} cuantiles desordenados`);
  for (const p of tipado.predicciones_saldo) if (p.fecha_objetivo <= p.fecha_corte) predMal.push(`${p.prediccion_id} objetivo no es futuro`);
  registrar('E. Negocio', 'Predicciones: nivel de riesgo con los umbrales del backend (>= 0.6 alto, >= 0.3 medio) y p10 <= p50 <= p90', predMal, `${tipado.predicciones_fiado.length} de fiado y ${tipado.predicciones_saldo.length} de saldo`);
  const versiones = new Set([...tipado.predicciones_saldo.map((p) => p.modelo_version), ...tipado.alertas.map((a) => a.modelo_version).filter(Boolean)]);
  registrar('E. Negocio', "Ninguna versión del forecast apunta a 'forecast-lgbm-quantile-0.3.1' (la del artefacto es lgbm_cuantiles-1.0)", [...versiones].filter((v) => v.includes('forecast-lgbm-quantile')), `versiones: ${[...versiones].join(', ')}`);

  // empresas
  const emMal = [];
  for (const e of empresas) {
    if (e.tiene_ruc !== (e.ruc !== null)) emMal.push(`${e.empresa_id}: tiene_ruc=${e.tiene_ruc} y ruc=${e.ruc}`);
    if (e.ruc !== null && !rucValido(e.ruc)) emMal.push(`${e.empresa_id}: RUC ${e.ruc} con dígito verificador inválido`);
    if (e.tiene_ruc && e.regimen_tributario === null) emMal.push(`${e.empresa_id}: con RUC y sin régimen`);
    if (!e.tiene_ruc && tipado.impuestos.some((i) => i.empresa_id === e.empresa_id)) emMal.push(`${e.empresa_id}: sin RUC pero con impuestos`);
  }
  registrar('E. Negocio', 'Empresas: tiene_ruc ⇔ ruc presente, dígito verificador SUNAT (módulo 11) válido y régimen/impuestos coherentes', emMal, `${empresas.filter((e) => e.ruc).length}/${empresas.length} con RUC válido`);
  const nTrab = new Set(empresas.map((e) => e.n_trabajadores));
  const txPorBodega = empresas.map((e) => (txPorEmp.get(e.empresa_id) || []).length);
  const heteroMal = [];
  if (nTrab.size < 4) heteroMal.push(`solo ${nTrab.size} valores distintos de n_trabajadores`);
  if (new Set(txPorBodega).size < 20) heteroMal.push('el número de transacciones por empresa casi no varía');
  if (!tx.some((t) => t.metodo_pago === 'billetera_digital') || tipado.billeteras_digitales.length === 0) heteroMal.push('no hay uso de billetera digital');
  if (new Set(tipado.empresas.map((e) => e.rubro_id)).size < 3) heteroMal.push('menos de 3 rubros distintos');
  registrar('E. Negocio', 'Heterogeneidad: volúmenes, rubros, trabajadores (1-5), billetera digital y empresas sin RUC distintos entre sí', heteroMal, `${nTrab.size} valores de n_trabajadores; ${new Set(txPorBodega).size} volúmenes distintos; ${tipado.billeteras_digitales.length} movimientos de billetera`);

  // billeteras ↔ transacciones
  const bilMal = [];
  const bilIds = new Set(tipado.billeteras_digitales.map((b) => b.billetera_mov_id));
  const usadas = new Set(tx.map((t) => t.billetera_mov_id).filter(Boolean));
  for (const t of tx) if (t.metodo_pago === 'billetera_digital' && !t.billetera_mov_id) bilMal.push(`${t.transaccion_id} billetera sin billetera_mov_id`);
  for (const b of bilIds) if (!usadas.has(b)) bilMal.push(`${b} sin transacción`);
  registrar('E. Negocio', 'Billeteras: cada pago por billetera_digital tiene su movimiento en billeteras_digitales (1-1)', bilMal, `${bilIds.size} movimientos enlazados`);

  // cobros / pagos totales
  const cobMal = [];
  const cobrado = new Map();
  for (const t of tx) if (t.tipo === 'cobro_fiado') cobrado.set(t.fiado_id, (cobrado.get(t.fiado_id) || 0) + Math.round(t.monto * 100));
  for (const f of tipado.cuaderno_fiado) {
    const c = cobrado.get(f.fiado_id) || 0;
    const m = Math.round(f.monto * 100);
    if (c > m) cobMal.push(`${f.fiado_id} cobrado ${c / 100} > monto ${f.monto}`);
    if ((c >= m) !== (f.fecha_pago_total !== null)) cobMal.push(`${f.fiado_id}: cobrado ${c / 100}/${f.monto} y fecha_pago_total=${f.fecha_pago_total}`);
  }
  const pagado = new Map();
  for (const t of tx) if (t.tipo === 'pago_proveedor' || t.tipo === 'pago_prestamo') pagado.set(t.deuda_id, (pagado.get(t.deuda_id) || 0) + Math.round(t.monto * 100));
  for (const d of tipado.deudas) {
    const c = pagado.get(d.deuda_id) || 0;
    const m = Math.round(d.monto_total_a_pagar * 100);
    if (c > m) cobMal.push(`${d.deuda_id} pagado ${c / 100} > total ${d.monto_total_a_pagar}`);
    if ((c >= m) !== (d.fecha_pago_total !== null)) cobMal.push(`${d.deuda_id}: pagado ${c / 100}/${d.monto_total_a_pagar} y fecha_pago_total=${d.fecha_pago_total}`);
  }
  const conPagoImp = new Set(tx.filter((t) => t.tipo === 'pago_impuesto').map((t) => t.impuesto_id));
  for (const i of tipado.impuestos) if ((i.fecha_pago !== null) !== conPagoImp.has(i.impuesto_id)) cobMal.push(`${i.impuesto_id}: fecha_pago=${i.fecha_pago} y pago registrado=${conPagoImp.has(i.impuesto_id)}`);
  registrar('E. Negocio', 'Fiados, deudas e impuestos: fecha de pago total ⇔ pagos registrados que cubren el monto; nunca se cobra o paga de más', cobMal, `${tipado.cuaderno_fiado.length} fiados, ${tipado.deudas.length} deudas, ${tipado.impuestos.length} impuestos`);

  // evaluación de ingesta
  const evalMal = [];
  let frases = [];
  const rutaEval = path.join(evalDir, 'frases_ingesta_eval.json');
  if (fs.existsSync(rutaEval)) {
    const crudo = fs.readFileSync(rutaEval, 'utf8');
    if (crudo.includes('�')) evalMal.push('el JSON contiene caracteres de reemplazo U+FFFD (mala codificación)');
    frases = JSON.parse(crudo);
    const vistos = new Set();
    const prods = new Map(tipado.productos.filter((p) => p.empresa_id === 'EMP-0001').map((p) => [p.producto_id, p]));
    for (const f of frases) {
      const k = f.frase.trim().toLowerCase();
      if (vistos.has(k)) evalMal.push(`frase repetida: ${f.caso_id}`); vistos.add(k);
      if (/\(muestra \d+\)/i.test(f.frase)) evalMal.push(`${f.caso_id} tiene sufijo "(muestra N)"`);
      if (f.origen_monto_esperado === 'catalogo') {
        const total = (f.items_esperados || []).reduce((a, it) => a + Math.round(it.cantidad * (prods.get(it.producto_id)?.precio_venta ?? NaN) * 100), 0) / 100;
        if (!(Math.abs(total - f.monto_esperado) < 0.005)) evalMal.push(`${f.caso_id}: monto ${f.monto_esperado} != catálogo de EMP-0001 (${total})`);
      }
      for (const it of f.items_esperados || []) if (!prods.has(it.producto_id)) evalMal.push(`${f.caso_id}: producto ${it.producto_id} no está en el catálogo de EMP-0001`);
      if (f.requiere_doble_confirmacion !== (f.confianza_simulada < 0.75) && f.dentro_alcance) evalMal.push(`${f.caso_id}: doble confirmación inconsistente con la confianza`);
    }
    if (frases.length < 100 || frases.length > 160) evalMal.push(`${frases.length} frases (se esperan 100-150)`);
  } else evalMal.push('falta frases_ingesta_eval.json');
  registrar('F. Evaluación de ingesta', 'Frases distintas y sin "(muestra N)", UTF-8 correcto, monto coherente con el catálogo de EMP-0001 y doble confirmación según la confianza', evalMal, `${frases.length} frases distintas`);

  // calibración de la demo (informativa; la historia de Pedro se calibra después)
  const pedro = empresas.find((e) => e.empresa_id === 'EMP-0001');
  if (pedro) {
    const filas = (sdPorEmp.get('EMP-0001') || []).sort((a, b) => (a.fecha < b.fecha ? -1 : 1));
    const ult = filas[filas.length - 1];
    registrar('G. Demo (informativo)', `EMP-0001: saldo de caja al ${FECHA_CORTE} = S/ 2 340 (cifra de context.md §9)`, ult && Math.abs(ult.saldo_cierre - 2340) < 0.005 ? [] : [`saldo ${ult ? ult.saldo_cierre : 'n/d'}`], `saldo ${ult ? ult.saldo_cierre : 'n/d'}`, 'WARN');
  }

  const resumen = { pass: checks.filter((c) => c.estado === 'PASS').length, fail: checks.filter((c) => c.estado === 'FAIL').length, warn: checks.filter((c) => c.estado === 'WARN').length };
  return { checks, resumen, volumenes: Object.fromEntries(tablasDbml.map((t) => [t, db[t].length])), totalFilas: nFilas, frases: frases.length, nChecks, nFk };
}

function escribirInformes(r, csvDir) {
  const fecha = new Date().toISOString();
  const json = { fecha_auditoria: fecha, esquema: 'backend/app/db/models.py (vía data/schema_esquema.json)', csv: path.relative(path.join(__dirname, '..'), csvDir), ...r };
  fs.writeFileSync(path.join(__dirname, 'AUDITORIA_CALIDAD_DATOS.json'), JSON.stringify(json, null, 2) + '\n', 'utf8');
  const estado = r.resumen.fail === 0 ? `**APROBADO** (${r.resumen.pass} controles superados${r.resumen.warn ? `, ${r.resumen.warn} advertencias` : ''})` : `**FALLA** (${r.resumen.fail} controles fallidos)`;
  const lineas = [
    '# Reporte de auditoría de calidad de datos',
    '',
    `> Generado por [\`data/audit_quality.mjs\`](./audit_quality.mjs) el **${fecha}** sobre \`data/csv\`, contra el esquema real de \`backend/app/db/models.py\` (exportado en \`data/schema_esquema.json\`).`,
    `> Estado: ${estado} sobre **${r.totalFilas.toLocaleString('es-PE')} filas** de las 25 tablas, **${r.nFk} FK**, **${r.nChecks} CHECK** y **${r.frases} frases** de evaluación de ingesta.`,
    '> La capacidad de detección se demuestra con `node data/audit_mutations.mjs` (copias descartables con errores inyectados).',
    '',
    '## 1. Controles',
    '',
    '| # | Categoría | Regla | Estado | Evidencia |',
    '|---:|---|---|:---:|---|',
    ...r.checks.map((c, i) => `| ${i + 1} | ${c.categoria} | ${c.regla.replace(/\|/g, '\\|')} | **${c.estado}** | ${c.evidencia.replace(/\|/g, '\\|')} |`),
    '',
    '## 2. Filas por tabla',
    '',
    '| Tabla | Filas |',
    '|---|---:|',
    ...Object.entries(r.volumenes).map(([t, n]) => `| \`${t}\` | ${n.toLocaleString('es-PE')} |`),
    '',
  ];
  fs.writeFileSync(path.join(__dirname, 'AUDITORIA_CALIDAD_DATOS.md'), lineas.join('\n'), 'utf8');
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const i = process.argv.indexOf('--csv');
  const csvDir = i >= 0 ? path.resolve(process.argv[i + 1]) : path.join(__dirname, 'csv');
  const r = auditar(csvDir);
  for (const c of r.checks) console.log(`${c.estado.padEnd(4)} | ${c.categoria} | ${c.regla.slice(0, 110)} | ${c.evidencia.slice(0, 160)}`);
  console.log(`\n${r.resumen.pass} PASS, ${r.resumen.warn} WARN, ${r.resumen.fail} FAIL`);
  if (!process.argv.includes('--no-escribir')) escribirInformes(r, csvDir);
  process.exit(r.resumen.fail === 0 ? 0 : 1);
}
