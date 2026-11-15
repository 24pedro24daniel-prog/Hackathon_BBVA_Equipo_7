import React from 'react';
import {AbsoluteFill, useVideoConfig} from 'remotion';
import {Canvas, Card} from '../components/Canvas';
import {Pedro} from '../components/Pedro';
import {Bill, Cajon} from '../components/Props';
import {useSceneFrame} from '../lib/time';
import {Sfx} from '../components/Sfx';
import {arc, ease, lerp, pop} from '../lib/anim';
import {sans, serif} from '../theme';

const CAJON = {x: 960, y: 470, w: 460};
const LEAK_Y = CAJON.y + CAJON.w * 0.42 + 8;
const PUDDLE_Y = 965;
const FALL = 14;
const DROP_RED = '#E0523F';
const DROP_BLUE = '#4FA8E8';
const DAYS = 30;
const CUOTA = 40;
// Las cuotas diarias caen cada vez más seguido
const DROPS = Array.from({length: DAYS}).map((_, i) => Math.round(66 + 80 * (i / (DAYS - 1)) ** 0.6));

const money = (n: number) => (n >= 1000 ? `S/ ${Math.floor(n / 1000)} ${String(n % 1000).padStart(3, '0')}` : `S/ ${n}`);

const Stat: React.FC<{label: string; value: string; color?: string; scale?: number}> = ({label, value, color = '#F6EDE6', scale = 1}) => (
	<div style={{textAlign: 'center'}}>
		<div style={{fontFamily: sans, fontWeight: 600, fontSize: 34, color: '#C7B8B0'}}>{label}</div>
		<div style={{fontFamily: serif, fontWeight: 700, fontSize: 96, color, lineHeight: 1.05, transform: `scale(${scale})`}}>{value}</div>
	</div>
);

export const S6GotaAGota: React.FC = () => {
	const frame = useSceneFrame();
	const {fps} = useVideoConfig();

	const flyer = pop(frame, 4, fps, 12, 180);
	const toCorner = ease(frame, [32, 52], [0, 1]);
	const flyerX = 960 + (330 - 960) * toCorner;
	const flyerY = 470 + (215 - 470) * toCorner;
	const flyerS = (1.35 - 0.35 * flyer) * (1 - 0.5 * toCorner);

	const loanIn = frame >= 64;
	const started = DROPS.filter((t) => frame >= t).length;
	const landed = DROPS.filter((t) => frame >= t + FALL).length;
	const paid = landed * CUOTA;
	const fill = loanIn ? 1 - 0.92 * (started / DAYS) : 0.08;
	const stats = ease(frame, [60, 72], [0, 1]);
	const over = paid > 1000;
	const extra = pop(frame, DROPS[DAYS - 1] + FALL, fps);

	return (
		<AbsoluteFill style={{background: 'radial-gradient(circle at 50% 45%, #4A3D40 0%, #2B2225 75%)'}}>
			<Canvas>
				{/* Billetes del préstamo */}
				{[0, 1, 2].map((i) => {
					const t = lerp(frame, [44 + i * 5, 62 + i * 5], [0, 1]);
					if (t <= 0 || t >= 1) return null;
					const [x, y] = arc(t, [330, 260], [CAJON.x + (i - 1) * 60, CAJON.y - 40], 160);
					return <Bill key={i} x={x} y={y} w={130} rot={t * 180} />;
				})}

				<Cajon x={CAJON.x} y={CAJON.y} w={CAJON.w} fill={fill} />

				{/* Charco que crece */}
				<ellipse cx={CAJON.x} cy={PUDDLE_Y} rx={40 + landed * 9} ry={12 + landed * 1.6} fill="#2C6FA8" opacity={landed > 0 ? 0.9 : 0} />

				{/* Gotas */}
				{DROPS.map((t, i) => {
					const p = lerp(frame, [t, t + FALL], [0, 1]);
					if (p <= 0 || p >= 1) return null;
					const y = LEAK_Y + (PUDDLE_Y - LEAK_Y) * p * p;
					const s = i < 3 ? 1.5 : 1;
					return (
						<g key={i} transform={`translate(${CAJON.x} ${y}) scale(${s})`}>
							<path d="M 0 -22 C 10 -6 14 2 14 8 A 14 14 0 0 1 -14 8 C -14 2 -10 -6 0 -22 Z" fill={DROP_BLUE} />
							{i < 3 ? (
								<text x={26} y={10} fontFamily={sans} fontWeight={800} fontSize={24} fill="#BFE2FA">
									S/ {CUOTA}
								</text>
							) : null}
						</g>
					);
				})}

				<Pedro x={1560} y={1190} scale={0.72} mood={landed > 18 ? 'sad' : 'worried'} sweat seed={6} />
			</Canvas>

			{/* Volante del prestamista */}
			<Card x={flyerX} y={flyerY} anchor="center" style={{opacity: Math.min(1, flyer * 1.6)}}>
				<div
					style={{
						position: 'relative',
						width: 720,
						padding: '40px 46px',
						background: '#FFF3B8',
						boxShadow: '0 22px 50px rgba(0,0,0,0.45)',
						transform: `rotate(-4deg) scale(${flyerS})`,
						textAlign: 'center',
					}}
				>
					{[-1, 1].map((s) => (
						<div key={s} style={{position: 'absolute', top: -18, [s < 0 ? 'left' : 'right']: 40, width: 120, height: 40, background: 'rgba(230,220,200,0.75)', transform: `rotate(${s * 8}deg)`}} />
					))}
					<div style={{fontFamily: sans, fontWeight: 800, fontSize: 64, color: '#C30A0A', lineHeight: 1}}>PRÉSTAMOS</div>
					<div style={{fontFamily: sans, fontWeight: 800, fontSize: 64, color: '#C30A0A', lineHeight: 1.1}}>AL TOQUE</div>
					<div style={{fontFamily: sans, fontWeight: 600, fontSize: 40, color: '#2B2225', marginTop: 18}}>Sin papeles · Sin aval</div>
					<div style={{fontFamily: sans, fontWeight: 600, fontSize: 40, color: '#2B2225'}}>Pagas diario</div>
					<div style={{fontFamily: sans, fontWeight: 800, fontSize: 46, color: '#2B2225', marginTop: 14, letterSpacing: 2}}>☎ 9•• ••• •••</div>
				</div>
			</Card>

			{/* Cifras del préstamo */}
			<Card x={330} y={560} anchor="center" style={{opacity: stats}}>
				<Stat label="Le prestaron" value="S/ 1 000" />
				<div style={{height: 36}} />
				<Stat label="Cuota diaria" value={`S/ ${CUOTA}`} color="#FFB4A8" />
			</Card>
			<Card x={1560} y={380} anchor="center" style={{opacity: stats}}>
				<Stat label="Día" value={String(Math.max(1, landed))} />
				<div style={{height: 36}} />
				<Stat label="Ya pagó" value={money(paid)} color={over ? DROP_RED : '#F6EDE6'} />
			</Card>
			<Card x={960} y={800} anchor="center" style={{opacity: Math.min(1, extra * 1.5)}}>
				<div
					style={{
						padding: '18px 36px',
						borderRadius: 999,
						background: DROP_RED,
						color: '#FFFFFF',
						fontFamily: sans,
						fontWeight: 800,
						fontSize: 46,
						transform: `scale(${extra})`,
						whiteSpace: 'nowrap',
					}}
				>
					S/ 200 más de lo que pidió… en un mes
				</div>
			</Card>

			<Sfx at={4} name="thud" volume={0.45} rate={1.3} />
			<Sfx at={44} name="whoosh" volume={0.45} />
			<Sfx at={62} name="coin" volume={0.4} />
			{DROPS.map((t, i) => (
				<Sfx key={i} at={t + FALL - 1} name="drip" volume={i < 3 ? 0.65 : 0.3} rate={0.9 + (i % 4) * 0.08} />
			))}
			<Sfx at={DROPS[DAYS - 1] + FALL} name="nope" volume={0.6} />
		</AbsoluteFill>
	);
};
