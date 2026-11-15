// Genera efectos de sonido suaves (WAV 16-bit mono) por síntesis, sin assets externos.
// Uso: node scripts/make-sfx.mjs
import {mkdirSync, writeFileSync} from 'node:fs';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';

const SR = 44100;
const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'sfx');
mkdirSync(OUT, {recursive: true});

let seed = 7;
const noise = () => {
	seed = (seed * 1664525 + 1013904223) >>> 0;
	return (seed / 4294967296) * 2 - 1;
};

const buf = (sec) => new Float32Array(Math.round(sec * SR));

const lowpass = (x, cutoff) => {
	const a = Math.exp((-2 * Math.PI * cutoff) / SR);
	let y = 0;
	return x.map((v) => (y = (1 - a) * v + a * y));
};
const highpass = (x, cutoff) => {
	const lp = lowpass(x, cutoff);
	return x.map((v, i) => v - lp[i]);
};

const write = (name, x, gain = 0.8) => {
	let peak = 0;
	for (const v of x) peak = Math.max(peak, Math.abs(v));
	const k = peak > 0 ? gain / peak : 0;
	const data = Buffer.alloc(44 + x.length * 2);
	data.write('RIFF', 0);
	data.writeUInt32LE(36 + x.length * 2, 4);
	data.write('WAVEfmt ', 8);
	data.writeUInt32LE(16, 16);
	data.writeUInt16LE(1, 20);
	data.writeUInt16LE(1, 22);
	data.writeUInt32LE(SR, 24);
	data.writeUInt32LE(SR * 2, 28);
	data.writeUInt16LE(2, 32);
	data.writeUInt16LE(16, 34);
	data.write('data', 36);
	data.writeUInt32LE(x.length * 2, 40);
	// Fade de 5 ms al final para evitar clics
	const fade = Math.round(0.005 * SR);
	x.forEach((v, i) => {
		const f = i > x.length - fade ? (x.length - i) / fade : 1;
		data.writeInt16LE(Math.round(Math.max(-1, Math.min(1, v * k * f)) * 32767), 44 + i * 2);
	});
	writeFileSync(join(OUT, `${name}.wav`), data);
};

// Moneda: parciales metálicos inarmónicos con decaimiento rápido
{
	const x = buf(0.45);
	const parts = [
		[2350, 1, 9],
		[3820, 0.6, 12],
		[5270, 0.35, 16],
		[6900, 0.2, 20],
	];
	x.forEach((_, i) => {
		const t = i / SR;
		let v = 0;
		for (const [f, a, d] of parts) v += a * Math.sin(2 * Math.PI * f * t) * Math.exp(-d * t);
		x[i] = v * Math.min(1, t / 0.002);
	});
	write('coin', x, 0.55);
}

// Pop: blip con subida de tono
{
	const x = buf(0.14);
	let ph = 0;
	x.forEach((_, i) => {
		const t = i / SR;
		const f = 520 + 700 * Math.min(1, t / 0.05);
		ph += (2 * Math.PI * f) / SR;
		x[i] = Math.sin(ph) * Math.exp(-28 * t) * Math.min(1, t / 0.003);
	});
	write('pop', x, 0.6);
}

// Whoosh: ruido filtrado con envolvente de campana
{
	const n = buf(0.6).map(noise);
	const lp = lowpass(n, 1800);
	const x = highpass(lp, 250).map((v, i) => {
		const t = i / (0.6 * SR);
		return v * Math.sin(Math.PI * t) ** 2;
	});
	write('whoosh', x, 0.6);
}

// Hoja de papel / calendario
{
	const n = buf(0.22).map(noise);
	const x = highpass(lowpass(n, 6000), 1200).map((v, i) => {
		const t = i / SR;
		return v * Math.min(1, t / 0.01) * Math.exp(-18 * t);
	});
	write('page', x, 0.5);
}

// Lápiz sobre papel
{
	const n = buf(0.5).map(noise);
	const x = highpass(lowpass(n, 5000), 2000).map((v, i) => {
		const t = i / SR;
		const stroke = 0.5 + 0.5 * Math.sin(2 * Math.PI * 9 * t);
		return v * stroke * Math.sin((Math.PI * i) / n.length);
	});
	write('write', x, 0.35);
}

// Reja metálica subiendo
{
	const n = buf(1.3).map(noise);
	const body = lowpass(highpass(n, 400), 3500);
	const x = body.map((v, i) => {
		const t = i / SR;
		const rattle = 0.45 + 0.55 * Math.abs(Math.sin(2 * Math.PI * 14 * t));
		const env = Math.min(1, t / 0.08) * Math.min(1, (1.3 - t) / 0.35);
		return v * rattle * env;
	});
	write('shutter', x, 0.45);
}

// Sello: golpe grave + clic
{
	const x = buf(0.5);
	let ph = 0;
	x.forEach((_, i) => {
		const t = i / SR;
		const f = 45 + 110 * Math.exp(-30 * t);
		ph += (2 * Math.PI * f) / SR;
		const click = t < 0.012 ? noise() * (1 - t / 0.012) * 0.6 : 0;
		x[i] = Math.sin(ph) * Math.exp(-9 * t) + click;
	});
	write('thud', x, 0.85);
}

// Gota
{
	const x = buf(0.22);
	let ph = 0;
	x.forEach((_, i) => {
		const t = i / SR;
		const f = 700 + 1100 * Math.min(1, t / 0.035);
		ph += (2 * Math.PI * f) / SR;
		x[i] = Math.sin(ph) * Math.exp(-30 * t) * Math.min(1, t / 0.002);
	});
	write('drip', x, 0.5);
}

// "No": dos tonos graves suaves
{
	const x = buf(0.32);
	x.forEach((_, i) => {
		const t = i / SR;
		const f = t < 0.15 ? 330 : 247;
		const lt = t < 0.15 ? t : t - 0.16;
		const env = lt < 0 ? 0 : Math.min(1, lt / 0.01) * Math.exp(-14 * lt);
		x[i] = (Math.sin(2 * Math.PI * f * t) + 0.3 * Math.sin(4 * Math.PI * f * t)) * env;
	});
	write('nope', x, 0.45);
}

// Tic de reloj / día
{
	const n = buf(0.06).map(noise);
	const x = highpass(n, 2500).map((v, i) => v * Math.exp(-90 * (i / SR)));
	write('tick', x, 0.4);
}

// Dron de tensión que sube (6 s)
{
	const dur = 6;
	const x = buf(dur);
	const n = lowpass(buf(dur).map(noise), 400);
	let p1 = 0,
		p2 = 0,
		p3 = 0;
	x.forEach((_, i) => {
		const t = i / SR;
		const rise = t / dur;
		const f = 55 * (1 + 0.12 * rise);
		p1 += (2 * Math.PI * f) / SR;
		p2 += (2 * Math.PI * f * 1.498) / SR;
		p3 += (2 * Math.PI * f * 2.01) / SR;
		const pulse = 0.65 + 0.35 * Math.sin(2 * Math.PI * (1.2 + 2.2 * rise) * t);
		const env = Math.min(1, t / 1.2) * Math.min(1, (dur - t) / 0.3);
		x[i] = (Math.sin(p1) + 0.5 * Math.sin(p2) + 0.25 * Math.sin(p3) * rise + n[i] * 2 * rise) * pulse * env;
	});
	write('drone', x, 0.6);
}

// Ruptura: destello brillante con cola
{
	const dur = 1.2;
	const n = buf(dur).map(noise);
	const shimmer = highpass(n, 3000);
	const x = shimmer.map((v, i) => {
		const t = i / SR;
		let ring = 0;
		for (const f of [1760, 2637, 3520]) ring += Math.sin(2 * Math.PI * f * t) * 0.15;
		return (v * 0.8 + ring) * Math.exp(-5 * t) * Math.min(1, t / 0.004);
	});
	write('break', x, 0.5);
}

// Campana de marca: arpegio mayor ascendente
{
	const dur = 2.4;
	const x = buf(dur);
	const notes = [523.25, 659.25, 783.99, 1046.5];
	x.forEach((_, i) => {
		const t = i / SR;
		let v = 0;
		notes.forEach((f, k) => {
			const lt = t - k * 0.11;
			if (lt < 0) return;
			const env = Math.min(1, lt / 0.004) * Math.exp(-2.6 * lt);
			v += (Math.sin(2 * Math.PI * f * lt) + 0.35 * Math.sin(2 * Math.PI * f * 2.76 * lt) * Math.exp(-6 * lt)) * env;
		});
		x[i] = v;
	});
	write('chime', x, 0.6);
}

console.log('SFX generados en', OUT);
