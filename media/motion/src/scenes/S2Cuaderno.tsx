import React from 'react';
import {AbsoluteFill, random} from 'remotion';
import {Canvas} from '../components/Canvas';
import {Pedro} from '../components/Pedro';
import {Coin, Counter, Shelves} from '../components/Props';
import {useSceneFrame} from '../lib/time';
import {Sfx} from '../components/Sfx';
import {arc, ease, lerp} from '../lib/anim';
import {hand, sans, warm} from '../theme';

// Cuaderno
const NB = {x: 990, y: 95, w: 820, h: 900};
const LINE0 = 205;
const LINE_H = 72;

type Entry = {t: number; text: string; color?: string; size?: number};
const ENTRIES: Entry[] = [
	{t: 10, text: 'Ventas y fiados', size: 62},
	{t: 24, text: 'Gaseosas x6 ........ S/ 21'},
	{t: 40, text: 'Sra. Rosa fió ........ S/ 12'},
	{t: 56, text: 'Don Luis debe ....... S/ 35'},
	{t: 72, text: 'Pan y leche ........... S/ 9'},
	{t: 88, text: '¿Pagó Rosa???', color: warm.inkRed},
	{t: 104, text: 'Proveedor el 30 → S/ ???', color: warm.inkRed},
];

const MESSY = [
	['Fiado Doña Carmen S/ 18', 'Gas S/ 52', 'Recarga S/ 5', 'Don Luis ???', 'S/ 7 + S/ 12 = ?'],
	['Colegio S/ 40', 'Fiado vecino S/ 9', 'Proveedor ...', 'Luz ??', 'debe 15? 25?'],
	['Arroz x5', '¿cuánto quedó?', 'Rosa S/ 12 (otra vez)', 'Agua S/ 38', '???'],
];

const FLIPS = [128, 142, 156];
const FLIP_LEN = 11;

const DAYS = ['LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM'];
// Las semanas pasan cada vez más rápido
const DAY_TIMES = [...DAYS.map((_, i) => 6 + i * 13), ...DAYS.map((_, i) => 100 + i * 6), ...DAYS.map((_, i) => 144 + i * 4)];

const PaperBg: React.FC = () => (
	<g>
		<rect x={NB.x} y={NB.y} width={NB.w} height={NB.h} rx={14} fill={warm.paper} />
		{Array.from({length: 11}).map((_, i) => (
			<line key={i} x1={NB.x + 20} x2={NB.x + NB.w - 20} y1={LINE0 + LINE_H * i + 14} y2={LINE0 + LINE_H * i + 14} stroke={warm.paperLine} strokeWidth={3} />
		))}
		<line x1={NB.x + 115} x2={NB.x + 115} y1={NB.y} y2={NB.y + NB.h} stroke="#E8A0A0" strokeWidth={3} />
	</g>
);

const MessyPage: React.FC<{index: number}> = ({index}) => (
	<g>
		<PaperBg />
		{MESSY[index % MESSY.length].map((txt, i) => (
			<text
				key={i}
				x={NB.x + 140 + random(`m-x-${index}-${i}`) * 120}
				y={LINE0 + LINE_H * (i + 1) + 10}
				fontFamily={hand}
				fontSize={50}
				fill={random(`m-c-${index}-${i}`) > 0.7 ? warm.inkRed : warm.ink}
				transform={`rotate(${(random(`m-r-${index}-${i}`) - 0.5) * 8} ${NB.x + 300} ${LINE0 + LINE_H * (i + 1)})`}
			>
				{txt}
			</text>
		))}
		<path
			d={`M ${NB.x + 160} ${LINE0 + LINE_H * 6 + 30} q 40 -40 80 0 t 80 0 t 80 0 t 80 0 t 80 0`}
			stroke={warm.ink}
			strokeWidth={6}
			fill="none"
			opacity={0.7}
		/>
	</g>
);

export const S2Cuaderno: React.FC = () => {
	const frame = useSceneFrame();

	const page = FLIPS.filter((t) => frame >= t).length;
	const flipping = FLIPS.findIndex((t) => frame >= t && frame < t + FLIP_LEN);

	const day = DAY_TIMES.filter((t) => frame >= t).length - 1;

	// Monedas que entran (clientes pagan) y productos que salen
	const flights = Array.from({length: 10}).map((_, i) => ({start: 6 + i * 12, coin: i % 2 === 0, i}));

	return (
		<AbsoluteFill style={{backgroundColor: warm.kraft}}>
			<Canvas>
				<defs>
					<clipPath id="s2-left">
						<rect x={0} y={0} width={930} height={1080} />
					</clipPath>
					{ENTRIES.map((e, i) => (
						<clipPath key={i} id={`s2-line-${i}`}>
							<rect x={NB.x + 120} y={LINE0 + LINE_H * i - 70} width={ease(frame, [e.t, e.t + 14], [0, 700], (x) => x)} height={100} />
						</clipPath>
					))}
				</defs>

				{/* Bodega por dentro */}
				<g clipPath="url(#s2-left)">
					<rect width={930} height={1080} fill="#F3DDB5" />
					<Shelves seed="s2" x={20} width={890} top={10} gap={185} />
					<Pedro x={465} y={920} scale={1.1} mood={frame > 112 ? 'worried' : 'neutral'} seed={2} />
					<Counter y={790} width={930} />
					{flights.map(({start, coin, i}) => {
						const t = lerp(frame, [start, start + 16], [0, 1]);
						if (t <= 0 || t >= 1) return null;
						if (coin) {
							const [x, y] = arc(t, [-40, 1020], [420 + (i % 3) * 40, 790], 260);
							return <Coin key={i} x={x} y={y} r={26} spin={t * 9} />;
						}
						const [x, y] = arc(t, [250 + (i % 4) * 120, 420], [-80, 820], 180);
						return (
							<g key={i} transform={`translate(${x} ${y}) rotate(${t * 140})`}>
								<rect x={-26} y={-38} width={52} height={76} rx={5} fill={['#D9483B', '#3E8E5E', '#2F6DB5', '#E77F3C'][i % 4]} />
								<rect x={-18} y={-22} width={36} height={22} fill="#FFF7E6" opacity={0.8} />
							</g>
						);
					})}
					{/* Días de la semana */}
					{DAYS.map((d, i) => {
						const active = day >= 0 && day % 7 === i;
						return (
							<g key={d} transform={`translate(${78 + i * 112} 960)`}>
								<rect x={-48} y={-34} width={96} height={68} rx={34} fill={active ? '#FFF4DE' : '#000'} opacity={active ? 1 : 0.18} />
								<text y={11} textAnchor="middle" fontFamily={sans} fontWeight={700} fontSize={28} fill={active ? warm.inkRed : '#FBE7C8'}>
									{d}
								</text>
							</g>
						);
					})}
				</g>
				<rect x={926} y={0} width={8} height={1080} fill={warm.woodDark} opacity={0.35} />

				{/* Cuaderno */}
				<g transform={`rotate(-3 ${NB.x + NB.w / 2} ${NB.y + NB.h / 2})`}>
					<rect x={NB.x + 14} y={NB.y + 18} width={NB.w} height={NB.h} rx={14} fill="#000" opacity={0.18} />
					{page === 0 ? (
						<g>
							<PaperBg />
							{ENTRIES.map((e, i) => (
								<text
									key={i}
									clipPath={`url(#s2-line-${i})`}
									x={NB.x + 140}
									y={LINE0 + LINE_H * i + 4}
									fontFamily={hand}
									fontWeight={i === 0 ? 700 : 500}
									fontSize={e.size ?? 52}
									fill={e.color ?? warm.ink}
								>
									{e.text}
								</text>
							))}
							{/* Tachón y corrección */}
							<line
								x1={NB.x + 140}
								y1={LINE0 + LINE_H * 3 - 12}
								x2={NB.x + 140 + ease(frame, [96, 104], [0, 560])}
								y2={LINE0 + LINE_H * 3 - 18}
								stroke={warm.inkRed}
								strokeWidth={6}
								strokeLinecap="round"
							/>
							<text
								x={NB.x + 700}
								y={LINE0 + LINE_H * 3 - 36}
								fontFamily={hand}
								fontWeight={700}
								fontSize={56}
								fill={warm.inkRed}
								opacity={lerp(frame, [104, 108], [0, 1])}
								transform={`rotate(-10 ${NB.x + 700} ${LINE0 + LINE_H * 3})`}
							>
								53?
							</text>
							{/* Mancha de tinta */}
							<path
								transform={`translate(${NB.x + 640} ${LINE0 + LINE_H * 7}) scale(${ease(frame, [116, 122], [0, 1])})`}
								d="M 0 -40 C 30 -46 52 -20 44 6 C 60 22 36 50 10 40 C -14 58 -50 40 -40 14 C -62 -6 -34 -40 0 -40 Z"
								fill={warm.ink}
								opacity={0.85}
							/>
						</g>
					) : (
						<MessyPage index={page - 1} />
					)}
					{/* Hoja que se pasa */}
					{flipping >= 0 ? (
						<g transform={`translate(0 ${NB.y}) scale(1 ${1 - ease(frame - FLIPS[flipping], [0, FLIP_LEN], [0, 1])}) translate(0 ${-NB.y})`}>
							<rect x={NB.x} y={NB.y} width={NB.w} height={NB.h} rx={14} fill="#EADBC0" />
							<rect x={NB.x} y={NB.y} width={NB.w} height={NB.h} rx={14} fill="#000" opacity={0.08} />
						</g>
					) : null}
					{/* Espiral */}
					{Array.from({length: 14}).map((_, i) => (
						<g key={i}>
							<circle cx={NB.x + 50 + i * 56} cy={NB.y + 16} r={10} fill={warm.kraft} />
							<rect x={NB.x + 44 + i * 56} y={NB.y - 22} width={12} height={40} rx={6} fill="#8E949C" />
						</g>
					))}
				</g>
			</Canvas>

			{ENTRIES.slice(1).map((e) => (
				<Sfx key={e.t} at={e.t} name="write" volume={0.55} />
			))}
			{flights
				.filter((f) => f.coin)
				.map((f) => (
					<Sfx key={f.start} at={f.start + 15} name="coin" volume={0.3} />
				))}
			{DAY_TIMES.slice(0, 14).map((t) => (
				<Sfx key={t} at={t} name="tick" volume={0.35} />
			))}
			{FLIPS.map((t) => (
				<Sfx key={t} at={t} name="page" volume={0.7} />
			))}
		</AbsoluteFill>
	);
};
