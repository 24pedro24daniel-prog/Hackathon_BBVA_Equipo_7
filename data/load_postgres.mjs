/**
 * TuCaserito — Cargador de data/csv en PostgreSQL (Node, paquete `pg`). Equivalente a data/load_postgres.py.
 *
 * Crea el esquema desde data/schema.sql (GENERADO desde backend/app/db/models.py con
 * data/pipeline_python/generar_schema.py), carga los CSV en orden de llaves foráneas y valida los conteos.
 *
 *   node data/load_postgres.mjs                      # BD vacía: crea el esquema y carga
 *   node data/load_postgres.mjs --recrear            # borra SOLO las tablas y tipos del esquema y vuelve a crear
 *   node data/load_postgres.mjs --url postgresql://usuario:clave@localhost:5433/mi_bd
 *
 * La URL sale de --url, de DATABASE_URL (entorno) o de data/.env. Nunca se imprime.
 *
 * SALVAGUARDA DE PRODUCCIÓN: se rechaza cualquier host *.render.com o APP_ENV=produccion, salvo que se pase
 *     --produccion --confirmar <nombre_de_la_bd>
 * con el nombre exacto de la base de datos de destino.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import pg from 'pg';

const { Client } = pg;
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CSV_DIR = path.join(__dirname, 'csv');

function cargarEnv(ruta) {
  if (!fs.existsSync(ruta)) return;
  for (const linea of fs.readFileSync(ruta, 'utf8').split(/\r?\n/)) {
    const t = linea.trim();
    if (!t || t.startsWith('#') || !t.includes('=')) continue;
    const i = t.indexOf('=');
    const k = t.slice(0, i).trim();
    const v = t.slice(i + 1).trim().replace(/^["']|["']$/g, '');
    if (process.env[k] === undefined) process.env[k] = v;
  }
}

function argumento(nombre) {
  const i = process.argv.indexOf(nombre);
  return i >= 0 ? process.argv[i + 1] : undefined;
}

function parseCsv(contenido) {
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
  const encabezado = filas[0] || [];
  return { encabezado, registros: filas.slice(1).map((r) => encabezado.map((_, i) => (r[i] === undefined || r[i] === '' ? null : r[i]))) };
}

function verificarDestino(url, produccion, confirmar) {
  const u = new URL(url);
  const bd = decodeURIComponent(u.pathname.replace(/^\//, ''));
  const esProd = u.hostname.endsWith('.render.com') || u.hostname.startsWith('dpg-') || ['produccion', 'producción', 'production'].includes((process.env.APP_ENV || '').toLowerCase());
  if (!esProd) return { host: u.hostname, bd, remoto: !['localhost', '127.0.0.1'].includes(u.hostname) };
  if (!produccion || confirmar !== bd) {
    console.error(`RECHAZADO: el destino parece PRODUCCIÓN (host '${u.hostname}', base '${bd}', APP_ENV='${process.env.APP_ENV || ''}').\nPara cargar de verdad pasa --produccion --confirmar <nombre_exacto_de_la_bd>.`);
    process.exit(2);
  }
  console.log(`ATENCIÓN: cargando en PRODUCCIÓN (host '${u.hostname}', base '${bd}'), confirmado por el usuario.`);
  return { host: u.hostname, bd, remoto: true };
}

async function main() {
  cargarEnv(path.join(__dirname, '.env'));
  const url = (argumento('--url') || process.env.DATABASE_URL || '').replace('postgresql+psycopg://', 'postgresql://');
  if (!url) { console.error('No hay URL: usa --url, DATABASE_URL o data/.env'); process.exit(1); }
  const destino = verificarDestino(url, process.argv.includes('--produccion'), argumento('--confirmar'));
  const esquemaRuta = path.join(__dirname, 'schema_esquema.json');
  if (!fs.existsSync(esquemaRuta)) { console.error('Falta data/schema_esquema.json: ejecuta PYTHONPATH=backend python data/pipeline_python/generar_schema.py'); process.exit(1); }
  const esquema = JSON.parse(fs.readFileSync(esquemaRuta, 'utf8'));
  const tablas = Object.keys(esquema.tablas);
  const enums = Object.keys(esquema.enums);
  const sqlEsquema = fs.readFileSync(path.join(__dirname, 'schema.sql'), 'utf8');

  const client = new Client({ connectionString: url, ssl: destino.remoto ? { rejectUnauthorized: false } : false });
  console.log(`Destino: host '${destino.host}', base '${destino.bd}'`);
  await client.connect();
  try {
    await client.query('BEGIN');
    const existentes = (await client.query('SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = ANY($1)', [tablas])).rows;
    if (existentes.length) {
      if (!process.argv.includes('--recrear')) {
        console.error(`Ya existen ${existentes.length} tablas del esquema en '${destino.bd}'. Usa --recrear para borrarlas y volver a crear.`);
        await client.query('ROLLBACK');
        process.exit(1);
      }
      for (const t of tablas) await client.query(`DROP TABLE IF EXISTS "${t}" CASCADE`);
      for (const e of enums) await client.query(`DROP TYPE IF EXISTS "${e}" CASCADE`);
    }
    console.log('Creando el esquema desde schema.sql (idéntico a backend/app/db/models.py)...');
    await client.query(sqlEsquema);

    let total = 0;
    let nTablas = 0;
    for (const tabla of esquema.orden_carga) {
      const ruta = path.join(CSV_DIR, `${tabla}.csv`);
      if (!fs.existsSync(ruta)) continue; // tablas técnicas sin CSV (idempotency_keys, llm_llamadas)
      const { encabezado, registros } = parseCsv(fs.readFileSync(ruta, 'utf8'));
      const columnasBd = esquema.tablas[tabla].columnas.map((c) => c.nombre);
      const desconocidas = encabezado.filter((c) => !columnasBd.includes(c));
      if (desconocidas.length) throw new Error(`${tabla}.csv tiene columnas que no existen en el esquema: ${desconocidas}`);
      const obligatorias = esquema.tablas[tabla].columnas.filter((c) => !encabezado.includes(c.nombre) && !c.nullable && !c.tiene_default).map((c) => c.nombre);
      if (obligatorias.length) throw new Error(`${tabla}.csv no trae columnas obligatorias: ${obligatorias}`);
      const lote = Math.max(1, Math.floor(30000 / encabezado.length)); // máx. 65 535 parámetros por consulta
      for (let i = 0; i < registros.length; i += lote) {
        const grupo = registros.slice(i, i + lote);
        const valores = [];
        const marcas = grupo.map((fila, r) => `(${fila.map((v, c) => { valores.push(v); return `$${r * encabezado.length + c + 1}`; }).join(',')})`);
        await client.query(`INSERT INTO "${tabla}" (${encabezado.map((c) => `"${c}"`).join(',')}) VALUES ${marcas.join(',')}`, valores);
      }
      const n = Number((await client.query(`SELECT count(*) FROM "${tabla}"`)).rows[0].count);
      if (n !== registros.length) throw new Error(`${tabla}: el CSV tiene ${registros.length} filas y la BD ${n}`);
      total += n;
      nTablas++;
      console.log(`  OK ${tabla.padEnd(26)} ${String(n).padStart(6)} filas`);
    }
    await client.query('COMMIT');
    console.log(`\nCarga completada: ${total} filas en ${nTablas} tablas; conteos validados contra los CSV.`);
  } catch (err) {
    await client.query('ROLLBACK').catch(() => {});
    console.error('Error durante la carga:', err.message);
    process.exitCode = 1;
  } finally {
    await client.end();
  }
}

main();
