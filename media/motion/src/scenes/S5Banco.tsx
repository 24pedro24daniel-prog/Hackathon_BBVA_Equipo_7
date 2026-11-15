import React from 'react';
import {AbsoluteFill, interpolateColors, useVideoConfig} from 'remotion';
import {Canvas, Card} from '../components/Canvas';
import {Pedro} from '../components/Pedro';
import {useSceneFrame} from '../lib/time';
import {Sfx} from '../components/Sfx';
import {ease, pop} from '../lib/anim';
import {hand, sans, serif, warm} from '../theme';

const REQS = [
	{t: 40, label: 'Registro de ventas'},
	{t: 54, label: 'Historial crediticio'},
	{t: 68, label: 'Estados financieros'},
];
const STAMP_AT = 86;
const PHASE_B = 114;

const RUMORS = [
	{t: 128, x: 80, y: 230, anchor: 'left', text: 'Si te formalizas, la SUNAT te cierra la tienda'},
	{t: 146, x: 1840, y: 210, anchor: 'right', text: 'Formalizarse sale carísimo'},
	{t: 164, x: 60, y: 560, anchor: 'left', text: 'A los bodegueros los bancos no les prestan'},
	{t: 180, x: 1860, y: 530, anchor: 'right', text: 'Mejor sigue como estás'},
] as const;

const NEIGHBORS = [
	{x: 190, s: 1, c: '#7F828D'},
	{x: 470, s: 0.75, c: '#9A9DA7'},
	{x: 1460, s: 0.75, c: '#9A9DA7'},
	{x: 1740, s: 1, c: '#7F828D'},
];

/** Fachada genérica de banco (sin marca). */
const BankFacade: React.FC<{x: number; y: number}> = ({x, y}) => (
	<g transform={`translate(${x} ${y})`}>
		<path d="M -260 -40 L 0 -150 L 260 -40 Z" fill="#8C93A3" />
		<text y={-62} textAnchor="middle" fontFamily={sans} fontWeight={800} fontSize={44} fill="#F4F5F7" letterSpacing={6}>
			BANCO
		</text>
		<rect x={-250} y={-40} width={500} height={24} fill="#7A8192" />
		{[-190, -95, 0, 95, 190].map((cx) => (
			<rect key={cx} x={cx - 20} y={-16} width={40} height={190} fill="#A7AEBC" />
		))}
		<rect x={-270} y={174} width={540} height={30} fill="#7A8192" />
	</g>
);

const Advisor: React.FC<{x: number; y: number; s: number}> = ({x, y, s}) => (
	<g transform={`translate(${x} ${y}) scale(${s})`}>
		<path d="M -60 -242 C -102 -240 -130 -226 -134 -186 L -124 0 L 124 0 L 134 -186 C 130 -226 102 -240 60 -242 Z" fill="#4E5666" />
		<path d="M -40 -242 L 0 -150 L 40 -242 Z" fill="#F2F2F2" />
		<path d="M -10 -232 L 10 -232 L 16 -170 L 0 -150 L -16 -170 Z" fill="#7A2E3A" />
		<rect x={-24} y={-272} width={48} height={36} fill="#9C7356" />
		<ellipse cx={0} cy={-332} rx={68} ry={76} fill="#B88762" />
		<path d="M -70 -340 C -74 -400 -30 -420 4 -416 C 50 -416 76 -392 70 -340 C 60 -372 20 -380 -10 -376 C -40 -372 -60 -360 -70 -340 Z" fill="#4A3B33" />
		<ellipse cx={-24} cy={-334} rx={7} ry={8} fill="#1A1414" />
		<ellipse cx={24} cy={-334} rx={7} ry={8} fill="#1A1414" />
		<line x1={-40} y1={-356} x2={-12} y2={-358} stroke="#4A3B33" strokeWidth={6} strokeLinecap="round" />
		<line x1={40} y1={-356} x2={12} y2={-358} stroke="#4A3B33" strokeWidth={6} strokeLinecap="round" />
		<path d="M -16 -290 L 16 -290" stroke="#5A2A22" strokeWidth={5} strokeLinecap="round" />
	</g>
);

const Neighbor: React.FC<{x: number; s: number; c: string; rise: number}> = ({x, s, c, rise}) => (
	<g transform={`translate(${x} ${1080 + (1 - rise) * 400}) scale(${s})`}>
		<path d="M -170 40 C -170 -120 -110 -170 0 -170 C 110 -170 170 -120 170 40 Z" fill={c} />
		<circle cx={0} cy={-250} r={80} fill={c} />
	</g>
);

export const S5Banco: React.FC = () => {
	const frame = useSceneFrame();
	const {fps} = useVideoConfig();

	const cardIn = pop(frame, 18, fps);
	const stamp = pop(frame, STAMP_AT, fps, 11, 220);
	const shake = frame >= STAMP_AT + 2 && frame < STAMP_AT + 12 ? Math.sin(frame * 3.1) * (STAMP_AT + 12 - frame) * 1.6 : 0;
	const fadeA = 1 - ease(frame, [PHASE_B - 2, PHASE_B + 12], [0, 1]);
	const moveB = ease(frame, [PHASE_B, PHASE_B + 22], [0, 1]);
	const shrink = ease(frame, [PHASE_B + 6, 205], [1.05, 0.82]);
	const mood = frame < 78 ? 'neutral' : frame < 94 ? 'worried' : 'sad';
	const arms: [number, number] = [15 - 7 * moveB, -80 + 84 * moveB];
	const bg = interpolateColors(frame, [0, PHASE_B, PHASE_B + 30], ['#DCDDE1', '#DCDDE1', '#B4B6BD']);

	return (
		<AbsoluteFill style={{backgroundColor: bg, transform: `translate(${shake}px, ${shake * 0.4}px)`}}>
			<Canvas>
				<g opacity={fadeA}>
					<BankFacade x={1500} y={190} />
					<Advisor x={1490} y={880} s={0.85} />
					<rect x={1060} y={820} width={900} height={280} fill="#7C8494" />
					<rect x={1040} y={800} width={940} height={34} rx={8} fill="#9AA2B0" />
				</g>

				{NEIGHBORS.map((n, i) => (
					<Neighbor key={i} {...n} rise={ease(frame, [PHASE_B + 4 + i * 6, PHASE_B + 24 + i * 6], [0, 1])} />
				))}

				<Pedro x={470 + 490 * moveB} y={1120} scale={shrink} mood={mood} armL={arms} armR={arms} seed={5}>
					<g opacity={fadeA} transform="rotate(-6 0 -150)">
						<rect x={-95} y={-270} width={190} height={240} rx={10} fill="#C9A16A" />
						<rect x={-95} y={-270} width={22} height={240} fill="#A57E4C" />
						<rect x={-55} y={-215} width={130} height={56} rx={6} fill="#F6EBD3" />
						<text x={10} y={-176} textAnchor="middle" fontFamily={hand} fontWeight={700} fontSize={36} fill={warm.ink}>
							Cuaderno
						</text>
					</g>
				</Pedro>
			</Canvas>

			{/* Requisitos del banco */}
			<Card x={960} y={360} anchor="center" style={{opacity: Math.min(1, cardIn * 1.5) * fadeA}}>
				<div
					style={{
						width: 600,
						padding: '34px 40px',
						borderRadius: 24,
						background: '#FFFFFF',
						boxShadow: '0 24px 50px rgba(20,25,40,0.22)',
						transform: `scale(${0.85 + 0.15 * cardIn})`,
					}}
				>
					<div style={{fontFamily: serif, fontWeight: 700, fontSize: 48, color: '#1E2233', marginBottom: 18}}>Para tu préstamo:</div>
					{REQS.map((r) => {
						const x = pop(frame, r.t, fps, 10, 200);
						return (
							<div key={r.label} style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 0', borderTop: '2px solid #ECEEF2'}}>
								<span style={{fontFamily: sans, fontWeight: 600, fontSize: 36, color: '#3A3F52'}}>{r.label}</span>
								<span style={{fontFamily: sans, fontWeight: 800, fontSize: 44, color: '#C30A0A', transform: `scale(${x})`, display: 'inline-block'}}>✕</span>
							</div>
						);
					})}
				</div>
				<div
					style={{
						position: 'absolute',
						left: '50%',
						top: '96%',
						padding: '10px 34px',
						border: '10px solid #C30A0A',
						borderRadius: 18,
						color: '#C30A0A',
						fontFamily: sans,
						fontWeight: 800,
						fontSize: 92,
						letterSpacing: 6,
						whiteSpace: 'nowrap',
						background: 'rgba(255,255,255,0.85)',
						opacity: frame >= STAMP_AT ? 1 : 0,
						transform: `translate(-50%, -50%) rotate(-12deg) scale(${2.4 - 1.4 * stamp})`,
					}}
				>
					NO CLIENTE
				</div>
			</Card>

			{/* Rumores del barrio */}
			{RUMORS.map((r) => {
				const p = pop(frame, r.t, fps, 11, 170);
				return (
					<Card key={r.t} x={r.x} y={r.y} anchor={r.anchor}>
						<div
							style={{
								position: 'relative',
								maxWidth: 560,
								padding: '24px 32px',
								borderRadius: 30,
								background: '#FFFFFF',
								boxShadow: '0 16px 36px rgba(20,25,40,0.25)',
								fontFamily: sans,
								fontWeight: 600,
								fontSize: 40,
								lineHeight: 1.2,
								color: '#2A2D3A',
								opacity: Math.min(1, p * 2),
								transform: `scale(${p})`,
								transformOrigin: r.anchor === 'left' ? 'bottom left' : 'bottom right',
							}}
						>
							“{r.text}”
							<div
								style={{
									position: 'absolute',
									bottom: -22,
									[r.anchor === 'left' ? 'left' : 'right']: 70,
									width: 0,
									height: 0,
									borderLeft: '18px solid transparent',
									borderRight: '18px solid transparent',
									borderTop: '24px solid #FFFFFF',
								}}
							/>
						</div>
					</Card>
				);
			})}

			{REQS.map((r) => (
				<Sfx key={r.t} at={r.t} name="nope" volume={0.4} />
			))}
			<Sfx at={18} name="pop" volume={0.4} />
			<Sfx at={STAMP_AT + 2} name="thud" volume={0.9} />
			{RUMORS.map((r, i) => (
				<Sfx key={r.t} at={r.t} name="pop" volume={0.45} rate={0.8 + i * 0.12} />
			))}
		</AbsoluteFill>
	);
};

