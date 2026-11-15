// Renderiza fotogramas sueltos para revisar el video sin hacer el render completo.
// Uso: node scripts/stills.mjs <carpeta-salida> <frame> [frame...]
import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';
import {mkdirSync} from 'node:fs';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const [outDir, ...frames] = process.argv.slice(2);
mkdirSync(outDir, {recursive: true});

const serveUrl = await bundle({entryPoint: join(root, 'src', 'index.ts')});
const composition = await selectComposition({serveUrl, id: process.env.COMP ?? 'Storytelling'});

for (const f of frames.map(Number)) {
	const output = resolve(outDir, `frame-${String(f).padStart(4, '0')}.png`);
	await renderStill({serveUrl, composition, frame: f, output, scale: 0.5});
	console.log(output);
}
