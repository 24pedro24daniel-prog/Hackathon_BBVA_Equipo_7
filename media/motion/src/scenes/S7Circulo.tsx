import React from 'react';
import {AbsoluteFill, useVideoConfig} from 'remotion';
import {Canvas} from '../components/Canvas';
import {Pedro} from '../components/Pedro';
import {Coin} from '../components/Props';
import {onRing, Ring} from '../components/Ring';
import {useSceneFrame} from '../lib/time';
import {Sfx} from '../components/Sfx';
import {ease, pop} from '../lib/anim';
import {dark} from '../theme';

const NODE_TIMES = [6, 18, 30, 42];
const SPIN_START = 50;
const SPIN_END = 150; // a partir de aquí todo se congela

/** Ángulo de la moneda que da vueltas cada vez más rápido. */
const markerAngle = (frame: number) => {
	const g = Math.max(0, Math.min(SPIN_END - SPIN_START, frame - SPIN_START));
	return -90 + 3 * g + 0.06 * g * g;
};

// Golpe sordo cada vez que la moneda vuelve a "No le alcanza"
const LAPS: number[] = [];
for (let f = SPIN_START + 1; f <= SPIN_END; f++) {
	if (Math.floor((markerAngle(f) + 90) / 360) > Math.floor((markerAngle(f - 1) + 90) / 360)) LAPS.push(f);
}

export const RING_END = {r: 275, flowEnd: ease(SPIN_END, [SPIN_START, SPIN_END], [0, 2.4], (x) => x * x), angle: markerAngle(SPIN_END)};
export const PEDRO_IN_RING = {x: 960, y: 690, scale: 0.42};

export const S7Circulo: React.FC = () => {
	const frame = useSceneFrame();
	const {fps} = useVideoConfig();

	const draw = ease(frame, [0, 46], [0, 1]);
	const r = ease(frame, [SPIN_START, SPIN_END], [330, RING_END.r]);
	const flow = ease(frame, [SPIN_START, SPIN_END], [0, 2.4], (x) => x * x);
	const nodes = NODE_TIMES.map((t) => pop(frame, t, fps));
	const angle = markerAngle(frame);
	const [mx, my] = onRing(r, angle);
	const vignette = ease(frame, [SPIN_START, SPIN_END], [0.35, 0.9]);
	const markerIn = ease(frame, [SPIN_START - 6, SPIN_START + 4], [0, 1]);

	return (
		<AbsoluteFill style={{background: `radial-gradient(circle at 50% 50%, #3A1418 0%, ${dark.bg} 70%)`}}>
			<Canvas>
				<Ring r={r} draw={draw} flow={flow} nodes={nodes} />
				<Pedro x={PEDRO_IN_RING.x} y={PEDRO_IN_RING.y} scale={PEDRO_IN_RING.scale} mood="sad" sweat seed={7} />
				<Coin x={mx} y={my} r={30 * markerIn} spin={frame * 0.4} />
			</Canvas>
			<AbsoluteFill style={{background: `radial-gradient(ellipse at 50% 50%, transparent 62%, rgba(0,0,0,${vignette}) 100%)`}} />

			<Sfx at={0} name="drone" volume={0.9} />
			{NODE_TIMES.map((t, i) => (
				<Sfx key={t} at={t} name="tick" volume={0.6} rate={0.8 + i * 0.1} />
			))}
			{LAPS.map((f) => (
				<Sfx key={f} at={f} name="thud" volume={0.35} />
			))}
		</AbsoluteFill>
	);
};

