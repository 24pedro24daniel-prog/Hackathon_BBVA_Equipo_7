import React from 'react';
import {AbsoluteFill, useVideoConfig} from 'remotion';
import {Canvas} from '../components/Canvas';
import {Pedro} from '../components/Pedro';
import {BoxIcon, HouseIcon} from '../components/Props';
import {useSceneFrame} from '../lib/time';
import {Sfx} from '../components/Sfx';
import {ease, lerp, pop} from '../lib/anim';
import {hand, sans, serif, warm} from '../theme';

const CAL = {x: 150, y: 110, w: 420, h: 450};
const FLIPS = [6, 15, 24, 33];
const INVOICES = [
	{t: 62, amount: 'S/ 480', y: 770, rot: -6},
	{t: 74, amount: 'S/ 420', y: 815, rot: 4},
	{t: 86, amount: 'S/ 300', y: 860, rot: -2},
];
const BASE = 900;
const MAX_H = 600;
const BARS = [
	{x: 900, value: 450, label: 'En caja', color: '#C9A54A', t: 100},
	{x: 1210, value: 1200, label: 'Por pagar', color: '#B8322A', t: 110},
];

const CalendarPage: React.FC<{day: number}> = ({day}) => (
	<g>
		<rect x={CAL.x} y={CAL.y} width={CAL.w} height={CAL.h} rx={16} fill="#FFFBF2" />
		<text x={CAL.x + CAL.w / 2} y={CAL.y + 330} textAnchor="middle" fontFamily={serif} fontWeight={700} fontSize={230} fill={warm.text}>
			{day}
		</text>
	</g>
);

export const S4FinDeMes: React.FC = () => {
	const frame = useSceneFrame();
	const {fps} = useVideoConfig();

	const flipped = FLIPS.filter((t) => frame >= t).length;
	const day = 26 + flipped;
	const flipping = FLIPS.findIndex((t) => frame >= t && frame < t + 8);
	const circle = ease(frame, [42, 60], [1, 0]);
	const gap = pop(frame, 142, fps);
	const mood = frame >= 142 && frame < 158 ? 'shock' : 'worried';
	const thought = pop(frame, 146, fps, 14);

	return (
		<AbsoluteFill style={{backgroundColor: '#E5D8C2'}}>
			<Canvas>
				<defs>
					<pattern id="s4-hatch" width={18} height={18} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
						<rect width={18} height={18} fill="#B8322A" opacity={0.12} />
						<line x1={0} y1={0} x2={0} y2={18} stroke="#B8322A" strokeWidth={6} opacity={0.5} />
					</pattern>
				</defs>

				{/* Calendario */}
				<rect x={CAL.x + 12} y={CAL.y + 16} width={CAL.w} height={CAL.h} rx={16} fill="#000" opacity={0.15} />
				<CalendarPage day={day} />
				{flipping >= 0 ? (
					<g transform={`translate(0 ${CAL.y + 90}) scale(1 ${1 - ease(frame - FLIPS[flipping], [0, 8], [0, 1])}) translate(0 ${-(CAL.y + 90)})`}>
						<CalendarPage day={day - 1} />
					</g>
				) : null}
				<rect x={CAL.x} y={CAL.y} width={CAL.w} height={90} rx={16} fill={warm.inkRed} />
				<rect x={CAL.x} y={CAL.y + 60} width={CAL.w} height={30} fill={warm.inkRed} />
				<text x={CAL.x + CAL.w / 2} y={CAL.y + 60} textAnchor="middle" fontFamily={sans} fontWeight={800} fontSize={40} fill="#FFFBF2" letterSpacing={4}>
					FIN DE MES
				</text>
				{[0, 1].map((i) => (
					<rect key={i} x={CAL.x + 110 + i * 170} y={CAL.y - 20} width={30} height={50} rx={10} fill="#5B4A3A" />
				))}
				<ellipse
					cx={CAL.x + CAL.w / 2}
					cy={CAL.y + 255}
					rx={165}
					ry={125}
					fill="none"
					stroke={warm.inkRed}
					strokeWidth={10}
					strokeLinecap="round"
					pathLength={1}
					strokeDasharray={1}
					strokeDashoffset={circle}
					transform={`rotate(-8 ${CAL.x + CAL.w / 2} ${CAL.y + 255})`}
				/>
				<text x={CAL.x + CAL.w / 2} y={CAL.y + 425} textAnchor="middle" fontFamily={hand} fontWeight={700} fontSize={48} fill={warm.inkRed} opacity={lerp(frame, [56, 64], [0, 1])}>
					¡Pagar proveedores!
				</text>

				{/* Facturas que caen */}
				{INVOICES.map((inv, i) => {
					const p = pop(frame, inv.t, fps, 14, 160);
					const y = -200 + (inv.y + 200) * p;
					return (
						<g key={i} transform={`translate(${CAL.x + CAL.w / 2} ${y}) rotate(${inv.rot})`} opacity={frame >= inv.t ? 1 : 0}>
							<rect x={-200} y={-80} width={400} height={160} rx={10} fill="#FFFFFF" stroke="#D5CBB8" strokeWidth={3} />
							<text x={-176} y={-34} fontFamily={sans} fontWeight={800} fontSize={30} fill={warm.text} letterSpacing={2}>
								FACTURA
							</text>
							<rect x={-176} y={-10} width={180} height={12} rx={6} fill="#E3DACB" />
							<rect x={-176} y={18} width={130} height={12} rx={6} fill="#E3DACB" />
							<text x={176} y={34} textAnchor="end" fontFamily={sans} fontWeight={800} fontSize={48} fill={warm.inkRed}>
								{inv.amount}
							</text>
						</g>
					);
				})}

				{/* Tengo vs. debo */}
				{BARS.map((b) => {
					const h = ease(frame, [b.t, b.t + 28], [0, (b.value / 1200) * MAX_H], (x) => 1 - (1 - x) ** 3);
					const shown = Math.round((h / MAX_H) * 1200 / 10) * 10;
					return (
						<g key={b.label}>
							<rect x={b.x - 105} y={BASE - h} width={210} height={h} rx={12} fill={b.color} />
							<text x={b.x} y={BASE - h + 66} textAnchor="middle" fontFamily={sans} fontWeight={800} fontSize={50} fill="#FFFFFF" opacity={h > 80 ? 1 : 0}>
								S/ {shown >= 1000 ? `${Math.floor(shown / 1000)} ${String(shown % 1000).padStart(3, '0')}` : shown}
							</text>
							<text x={b.x} y={BASE + 56} textAnchor="middle" fontFamily={sans} fontWeight={600} fontSize={38} fill={warm.muted}>
								{b.label}
							</text>
						</g>
					);
				})}
				<line x1={760} y1={BASE} x2={1350} y2={BASE} stroke={warm.muted} strokeWidth={4} />
				{/* Faltante */}
				<g opacity={Math.min(1, gap * 1.4)}>
					<rect x={795} y={BASE - MAX_H} width={210} height={MAX_H - (450 / 1200) * MAX_H - 6} rx={12} fill="url(#s4-hatch)" stroke="#B8322A" strokeWidth={4} strokeDasharray="14 10" />
				</g>
				<g transform={`translate(900 ${BASE - MAX_H - 60}) scale(${gap})`}>
					<rect x={-165} y={-40} width={330} height={80} rx={40} fill="#B8322A" />
					<text y={16} textAnchor="middle" fontFamily={sans} fontWeight={800} fontSize={42} fill="#FFFFFF">
						Faltan S/ 750
					</text>
				</g>

				{/* Pedro y lo que piensa */}
				<Pedro x={1650} y={1150} scale={1} mood={mood} sweat seed={4} />
				<g opacity={thought} transform={`translate(1630 330) scale(${0.7 + 0.3 * thought})`}>
					<circle cx={-40} cy={300} r={16} fill="#FFFFFF" />
					<circle cx={-10} cy={250} r={24} fill="#FFFFFF" />
					<rect x={-250} y={-150} width={500} height={360} rx={70} fill="#FFFFFF" />
					<g opacity={lerp(frame, [150, 158], [0, 1])}>
						<HouseIcon x={-185} y={-50} s={0.32} />
						<text x={-125} y={-40} fontFamily={sans} fontWeight={700} fontSize={36} fill={warm.text}>
							Gastos de la casa
						</text>
					</g>
					<g opacity={lerp(frame, [170, 178], [0, 1])}>
						<BoxIcon x={-195} y={110} s={0.42} />
						<BoxIcon x={-170} y={78} s={0.38} rot={6} />
						<text x={-125} y={92} fontFamily={sans} fontWeight={700} fontSize={36} fill={warm.text}>
							Pidió mercadería
						</text>
						<text x={-125} y={136} fontFamily={sans} fontWeight={700} fontSize={36} fill={warm.text}>
							de más
						</text>
					</g>
				</g>
			</Canvas>

			{FLIPS.map((t) => (
				<Sfx key={t} at={t} name="page" volume={0.55} />
			))}
			<Sfx at={44} name="write" volume={0.6} />
			{INVOICES.map((inv) => (
				<Sfx key={inv.t} at={inv.t + 6} name="thud" volume={0.25} rate={1.6} />
			))}
			<Sfx at={142} name="nope" volume={0.7} />
			<Sfx at={150} name="pop" volume={0.4} />
			<Sfx at={170} name="pop" volume={0.4} />
		</AbsoluteFill>
	);
};
