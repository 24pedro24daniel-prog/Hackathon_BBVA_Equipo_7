import React from 'react';
import {useSceneFrame} from '../lib/time';
import {pedro as c} from '../theme';

export type Mood = 'happy' | 'neutral' | 'worried' | 'sad' | 'shock';

/** Ángulos de un brazo en grados: [hombro→codo, codo→mano]. 0 = colgando, positivo = hacia afuera, 180 = hacia arriba. */
export type Arm = [number, number];

type Props = {
	x: number;
	y: number;
	scale?: number;
	mood?: Mood;
	armL?: Arm;
	armR?: Arm;
	sweat?: boolean;
	/** Desfase para que el parpadeo no coincida entre escenas. */
	seed?: number;
	/** Elementos sostenidos frente al pecho, en coordenadas locales de Pedro. */
	children?: React.ReactNode;
};

const rad = (d: number) => (d * Math.PI) / 180;

const ArmShape: React.FC<{side: -1 | 1; arm: Arm}> = ({side, arm}) => {
	const sh: [number, number] = [side * 116, -205];
	const elbow: [number, number] = [sh[0] + side * 78 * Math.sin(rad(arm[0])), sh[1] + 78 * Math.cos(rad(arm[0]))];
	const hand: [number, number] = [elbow[0] + side * 92 * Math.sin(rad(arm[1])), elbow[1] + 92 * Math.cos(rad(arm[1]))];
	return (
		<g>
			<line x1={elbow[0]} y1={elbow[1]} x2={hand[0]} y2={hand[1]} stroke={c.skin} strokeWidth={40} strokeLinecap="round" />
			<circle cx={hand[0]} cy={hand[1]} r={23} fill={c.skin} />
			<line x1={sh[0]} y1={sh[1]} x2={sh[0] + (elbow[0] - sh[0]) * 0.72} y2={sh[1] + (elbow[1] - sh[1]) * 0.72} stroke={c.polo} strokeWidth={60} strokeLinecap="round" />
		</g>
	);
};

const Face: React.FC<{mood: Mood; blink: number}> = ({mood, blink}) => {
	const eyeRy = 9 * blink * (mood === 'shock' ? 1.35 : 1);
	const brows: Record<Mood, [number, number, number, number]> = {
		// x1, y1 (exterior), x2, y2 (interior) del ceño izquierdo; el derecho es espejo
		happy: [-42, -362, -14, -366],
		neutral: [-42, -360, -14, -361],
		worried: [-42, -356, -14, -368],
		sad: [-42, -354, -14, -369],
		shock: [-42, -374, -14, -376],
	};
	const [bx1, by1, bx2, by2] = brows[mood];
	const mouth: Record<Mood, React.ReactNode> = {
		happy: <path d="M -27 -298 Q 0 -262 27 -298 Q 0 -286 -27 -298 Z" fill="#6B2320" />,
		neutral: <path d="M -17 -289 Q 0 -286 17 -289" stroke="#5A2A22" strokeWidth={5} fill="none" strokeLinecap="round" />,
		worried: <path d="M -20 -284 Q -10 -293 0 -287 Q 10 -281 20 -290" stroke="#5A2A22" strokeWidth={5} fill="none" strokeLinecap="round" />,
		sad: <path d="M -22 -279 Q 0 -298 22 -279" stroke="#5A2A22" strokeWidth={5} fill="none" strokeLinecap="round" />,
		shock: <ellipse cx={0} cy={-286} rx={11} ry={15} fill="#6B2320" />,
	};
	return (
		<g>
			{[-1, 1].map((s) => (
				<g key={s}>
					<ellipse cx={s * 26} cy={-334} rx={7.5} ry={Math.max(1, eyeRy)} fill="#1A1414" />
					<line x1={-s * bx1} y1={by1} x2={-s * bx2} y2={by2} stroke={c.hair} strokeWidth={7} strokeLinecap="round" />
				</g>
			))}
			<path d="M -3 -332 Q -12 -309 3 -305" stroke={c.skinShade} strokeWidth={5} fill="none" strokeLinecap="round" />
			{mood === 'happy' ? (
				<>
					<circle cx={-44} cy={-305} r={11} fill="#E07A6A" opacity={0.35} />
					<circle cx={44} cy={-305} r={11} fill="#E07A6A" opacity={0.35} />
				</>
			) : null}
			{mouth[mood]}
		</g>
	);
};

export const Pedro: React.FC<Props> = ({x, y, scale = 1, mood = 'neutral', armL = [8, 4], armR = [8, 4], sweat, seed = 0, children}) => {
	const frame = useSceneFrame();
	const breathe = 1 + 0.012 * Math.sin((frame + seed * 13) / 11);
	const cycle = (frame + seed * 37) % 96;
	const blink = cycle < 3 ? Math.abs(cycle - 1.5) / 1.5 : 1;
	const sweatT = ((frame + seed * 11) % 45) / 45;

	return (
		<g transform={`translate(${x} ${y}) scale(${scale})`}>
			<g transform={`scale(1 ${breathe})`}>
				{/* Cuello */}
				<rect x={-26} y={-275} width={52} height={50} fill={c.skinShade} />
				{/* Torso con polo */}
				<path d="M -60 -242 C -102 -240 -130 -226 -134 -186 L -124 0 L 124 0 L 134 -186 C 130 -226 102 -240 60 -242 Z" fill={c.polo} />
				{Array.from({length: 7}).map((_, row) =>
					Array.from({length: 9}).map((__, col) => (
						<circle key={`${row}-${col}`} cx={-100 + col * 25 + (row % 2) * 12} cy={-200 + row * 28} r={2.6} fill={c.poloDots} />
					)),
				)}
				{/* Cuello del polo y botones */}
				<path d="M -50 -244 L -6 -200 L -30 -188 L -62 -232 Z" fill={c.poloDark} />
				<path d="M 50 -244 L 6 -200 L 30 -188 L 62 -232 Z" fill={c.poloDark} />
				<rect x={-6} y={-204} width={12} height={58} rx={4} fill={c.poloDark} />
				<circle cx={0} cy={-185} r={3.5} fill="#8D97C9" />
				<circle cx={0} cy={-162} r={3.5} fill="#8D97C9" />
			</g>
			<ArmShape side={-1} arm={armL} />
			<ArmShape side={1} arm={armR} />
			{children}
			{/* Cabeza */}
			<g transform={`translate(0 ${(breathe - 1) * -250})`}>
				<circle cx={-72} cy={-330} r={14} fill={c.skinShade} />
				<circle cx={72} cy={-330} r={14} fill={c.skinShade} />
				<ellipse cx={0} cy={-332} rx={72} ry={80} fill={c.skin} />
				<path d="M -75 -338 C -82 -404 -40 -428 2 -425 C 46 -427 84 -402 75 -338 C 70 -362 52 -384 22 -381 C -8 -392 -52 -378 -75 -338 Z" fill={c.hair} />
				<path d="M -75 -338 L -70 -318 L -64 -346 Z M 75 -338 L 70 -318 L 64 -346 Z" fill={c.hair} />
				<Face mood={mood} blink={blink} />
				{sweat ? (
					<path
						transform={`translate(${62} ${-372 + sweatT * 40})`}
						d="M 0 -14 C 8 -2 10 4 10 8 A 10 10 0 0 1 -10 8 C -10 4 -8 -2 0 -14 Z"
						fill="#9ED3F2"
						opacity={1 - sweatT}
					/>
				) : null}
			</g>
		</g>
	);
};
