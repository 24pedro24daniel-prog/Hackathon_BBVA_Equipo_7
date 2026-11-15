/**
 * TuCaserito — Cargador y Verificador en PostgreSQL (Render / Local)
 * Lee DATABASE_URL desde data/.env, ejecuta data/schema.sql (25 tablas + 19 enums + 6 vistas),
 * inserta por lotes todas las tablas desde data/csv/*.csv y verifica los indicadores de EMP-0001.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import pg from 'pg';

const { Client } = pg;
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Leer variables de data/.env sin dependencias adicionales
function loadEnv(envPath) {
  if (!fs.existsSync(envPath)) return;
  const content = fs.readFileSync(envPath, 'utf8');
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIdx = trimmed.indexOf('=');
    if (eqIdx === -1) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    const val = trimmed.slice(eqIdx + 1).trim().replace(/^["']|["']$/g, '');
    if (!process.env[key]) process.env[key] = val;
  }
}

loadEnv(path.join(__dirname, '.env'));

const DATABASE_URL = process.env.DATABASE_URL;
if (!DATABASE_URL) {
  console.error('ERROR: No se encontró DATABASE_URL en data/.env ni en las variables de entorno.');
  process.exit(1);
}

// Parser CSV simple que soporta comillas escapadas ("")
function parseCsv(content) {
  const rows = [];
  let row = [];
  let field = '';
  let inQuotes = false;

  for (let i = 0; i < content.length; i++) {
    const ch = content[i];
    const next = content[i + 1];

    if (inQuotes) {
      if (ch === '"' && next === '"') {
        field += '"';
        i++;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        field += ch;
      }
    } else {
      if (ch === '"') {
        inQuotes = true;
      } else if (ch === ',') {
        row.push(field);
        field = '';
      } else if (ch === '\n') {
        row.push(field.replace(/\r$/, ''));
        field = '';
        if (row.length > 1 || row[0] !== '') rows.push(row);
        row = [];
      } else {
        field += ch;
      }
    }
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field.replace(/\r$/, ''));
    if (row.length > 1 || row[0] !== '') rows.push(row);
  }

  if (rows.length === 0) return { headers: [], records: [] };
  const headers = rows[0];
  const records = rows.slice(1).map((r) =>
    headers.map((_, idx) => {
      const v = r[idx];
      return v === '' || v === undefined ? null : v;
    })
  );
  return { headers, records };
}

// Orden topológico de inserción según Foreign Keys
const ORDERED_TABLES = [
  'rubros',
  'empresas',
  'preferencias_alertas',
  'categorias',
  'productos',
  'clientes',
  'proveedores',
  'conversaciones',
  'borradores',
  'movimientos_programados',
  'cuaderno_fiado',
  'deudas',
  'billeteras_digitales',
  'impuestos',
  'transacciones',
  'detalle_transaccion',
  'reglas_meta',
  'forecast_ajustes',
  'alertas',
  'consentimientos',
  'saldo_diario',
  'eventos',
  'predicciones_saldo',
  'predicciones_fiado',
  'score_salud',
];

async function main() {
  const isRemote = !DATABASE_URL.includes('localhost') && !DATABASE_URL.includes('127.0.0.1');
  const client = new Client({
    connectionString: DATABASE_URL,
    ssl: isRemote ? { rejectUnauthorized: false } : false,
  });

  console.log('Conectando a PostgreSQL...');
  await client.connect();

  try {
    console.log('Ejecutando schema.sql (creación limpia de 19 ENUMs, 25 tablas y 6 vistas)...');
    const schemaSql = fs.readFileSync(path.join(__dirname, 'schema.sql'), 'utf8');
    await client.query(schemaSql);

    await client.query('BEGIN');
    const csvDir = path.join(__dirname, 'csv');

    for (const table of ORDERED_TABLES) {
      const csvPath = path.join(csvDir, `${table}.csv`);
      const content = fs.readFileSync(csvPath, 'utf8');
      const { headers, records } = parseCsv(content);
      if (records.length === 0) continue;

      const batchSize = 250;
      for (let i = 0; i < records.length; i += batchSize) {
        const batch = records.slice(i, i + batchSize);
        const values = [];
        const placeholders = batch.map((row, rIdx) => {
          const rowPh = row.map((val, cIdx) => {
            values.push(val);
            return `$${rIdx * headers.length + cIdx + 1}`;
          });
          return `(${rowPh.join(',')})`;
        });
        const sql = `INSERT INTO ${table} (${headers.join(',')}) VALUES ${placeholders.join(',')}`;
        await client.query(sql, values);
      }
      console.log(`  ✔ ${table.padEnd(26)} -> ${String(records.length).padStart(5)} registros insertados`);
    }

    await client.query('COMMIT');
    console.log('\n¡Carga completada con éxito! Verificando vistas derivadas para EMP-0001 (Bodega Don Pedro):');

    const resSaldo = await client.query(`SELECT * FROM v_saldo_caja WHERE empresa_id = 'EMP-0001'`);
    console.log('  • v_saldo_caja        :', resSaldo.rows[0]);

    const resResumen = await client.query(`SELECT * FROM v_resumen_mes WHERE empresa_id = 'EMP-0001' AND periodo = '2026-11'`);
    console.log('  • v_resumen_mes (Nov) :', resResumen.rows[0]);

    const resFiados = await client.query(`SELECT fiado_id, cliente, monto_pendiente, dias_transcurridos, estado FROM v_fiados WHERE empresa_id = 'EMP-0001' AND estado <> 'pagado' ORDER BY fiado_id`);
    console.log('  • v_fiados pendientes :', resFiados.rows);

    const resDeudas = await client.query(`SELECT deuda_id, acreedor, monto_pendiente, fecha_vencimiento, dias_para_vencer, estado FROM v_deudas WHERE empresa_id = 'EMP-0001' AND estado <> 'pagado'`);
    console.log('  • v_deudas pendientes :', resDeudas.rows);

    const resDisp = await client.query(`SELECT * FROM v_disponible_gastar WHERE empresa_id = 'EMP-0001'`);
    console.log('  • v_disponible_gastar :', resDisp.rows[0]);
  } catch (err) {
    await client.query('ROLLBACK');
    console.error('Error durante la carga:', err);
    process.exitCode = 1;
  } finally {
    await client.end();
  }
}

main();

