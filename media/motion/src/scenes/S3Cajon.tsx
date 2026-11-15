import React from 'react';
import {AbsoluteFill, useVideoConfig} from 'remotion';
import {Canvas, Card} from '../components/Canvas';
import {Bill, Cajon, Coin, HouseIcon, StoreIcon} from '../components/Props';
import {useSceneFrame} from '../lib/time';
import {Sfx} from '../components/Sfx';
import {arc, ease, lerp, pop} from '../lib/anim';
import {sans, serif, warm} from '../theme';

const CAJON = {x: 960, y: 760, w: 600};
const HOUSE: [number, number] = [430, 400];
const STORE: [number, number] = [1490, 400];

// Entra plata de los dos lados…
const IN = [
	...[0, 1, 2, 3, 4, 5].map((i) => ({start: 12 + i * 9, from: STORE, bill: false})),
	...[0, 1, 2].map((i) => ({start: 18 + i * 16, from: HOUSE, bill: true})),
];

// …y sale para todo
const OUT = [
	{start: 92, label: 'Gas', to: HOUSE, pos: [100, 640]},
	{start: 106, label: 'Colegio', to: HOUSE, pos: [360, 770]},
	{start: 120, label: 'Mercado', to: HOUSE, pos: [100, 260]},
	{start: 134, label: 'Luz', to: HOUSE, pos: [640, 260]},
	{start: 150, label: 'Proveedor', to: STORE, pos: [1520, 680]},
] as const;

export const S3Cajon: React.FC = () => {
	const frame = useSceneFrame();
	const {fps} = useVideoConfig();

	const landed = IN.filter((f) => frame >= f.start + 18).length;
	const left = OUT.filter((o) => frame >= o.start + 6).length;
	const fill = 0.15 + (landed / IN.length) * 0.85 - left * 0.16;
	const shake = frame > 150 && frame < 162 ? Math.sin(frame * 2.2) * 4 : 0;
	const titleIn = pop(frame, 4, fps);

	return (
		<AbsoluteFill style={{backgroundColor: warm.kraft}}>
			<Canvas>
				<rect x={0} y={0} width={960} height={1080} fill="#F1DDBA" />
				<rect x={960} y={0} width={960} height={1080} fill="#E6CDA2" />
				<line x1={960} y1={60} x2={960} y2={520} stroke={warm.muted} strokeWidth={4} strokeDasharray="14 14" opacity={0.5} />

				<HouseIcon x={HOUSE[0]} y={HOUSE[1]} s={1.15} />
				<StoreIcon x={STORE[0]} y={STORE[1]} s={1.15} />

				{IN.map((f, i) => {
					const t = lerp(frame, [f.start, f.start + 18], [0, 1]);
					if (t <= 0 || t >= 1) return null;
					const [x, y] = arc(t, [f.from[0], f.from[1] + 60], [CAJON.x + (f.bill ? -80 : 80), CAJON.y - 60], 220);
					return f.bill ? <Bill key={i} x={x} y={y} w={120} rot={t * 200} /> : <Coin key={i} x={x} y={y} r={28} spin={t * 10} />;
				})}

				{OUT.map((o, i) => {
					const t = lerp(frame, [o.start, o.start + 16], [0, 1]);
					if (t <= 0 || t >= 1) return null;
					const [x, y] = arc(t, [CAJON.x, CAJON.y - 80], [o.pos[0] + 60, o.pos[1]], 200);
					return i % 2 ? <Bill key={i} x={x} y={y} w={110} rot={-t * 220} /> : <Coin key={i} x={x} y={y} r={28} spin={t * 10} />;
				})}

				<g transform={`translate(${shake} 0)`}>
					<Cajon x={CAJON.x} y={CAJON.y} w={CAJON.w} fill={fill} label="UN SOLO CAJÓN" />
				</g>
			</Canvas>

			<Card x={HOUSE[0]} y={110} anchor="center" style={{opacity: titleIn, transform: `translate(-50%, ${-50 + (1 - titleIn) * 40}%)`}}>
				<div style={{fontFamily: serif, fontWeight: 700, fontSize: 64, color: warm.text}}>Casa</div>
			</Card>
			<Card x={STORE[0]} y={110} anchor="center" style={{opacity: titleIn, transform: `translate(-50%, ${-50 + (1 - titleIn) * 40}%)`}}>
				<div style={{fontFamily: serif, fontWeight: 700, fontSize: 64, color: warm.text}}>Bodega</div>
			</Card>

			{OUT.map((o) => {
				const p = pop(frame, o.start + 14, fps);
				const supplier = o.label === 'Proveedor';
				return (
					<Card key={o.label} x={o.pos[0]} y={o.pos[1]}>
						<div
							style={{
								fontFamily: sans,
								fontWeight: 700,
								fontSize: 40,
								padding: '14px 28px',
								borderRadius: 999,
								background: supplier ? '#FFF4DE' : '#FFFFFF',
								color: supplier ? warm.inkRed : warm.text,
								border: supplier ? `3px dashed ${warm.inkRed}` : 'none',
								boxShadow: '0 10px 24px rgba(80,45,10,0.18)',
								transform: `scale(${p})`,
								opacity: Math.min(1, p * 2),
								whiteSpace: 'nowrap',
							}}
						>
							{supplier ? 'Proveedor: ¿?' : `− ${o.label}`}
						</div>
					</Card>
				);
			})}

			{IN.filter((f) => !f.bill).map((f) => (
				<Sfx key={`c${f.start}`} at={f.start + 17} name="coin" volume={0.35} />
			))}
			{IN.filter((f) => f.bill).map((f) => (
				<Sfx key={`b${f.start}`} at={f.start} name="whoosh" volume={0.3} rate={1.4} />
			))}
			{OUT.map((o) => (
				<Sfx key={o.label} at={o.start + 14} name="pop" volume={0.55} rate={o.label === 'Proveedor' ? 0.7 : 1} />
			))}
		</AbsoluteFill>
	);
};
