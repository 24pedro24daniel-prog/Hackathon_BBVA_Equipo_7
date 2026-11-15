import React from 'react';
import {AbsoluteFill, useVideoConfig} from 'remotion';
import {Canvas} from '../components/Canvas';
import {Pedro} from '../components/Pedro';
import {BoxIcon, Counter, Shelves} from '../components/Props';
import {useSceneFrame} from '../lib/time';
import {Sfx} from '../components/Sfx';
import {ease, pop} from '../lib/anim';
import {sans, serif, warm} from '../theme';

// Puerta de la bodega en coordenadas del lienzo
const DOOR = {x: 520, y: 330, w: 880, h: 670};

export const ShopInterior: React.FC<{mood?: React.ComponentProps<typeof Pedro>['mood']; wave?: number}> = ({mood = 'happy', wave = 0}) => {
	const frame = useSceneFrame();
	const armR: [number, number] = [8 + 78 * wave, 6 + 150 * wave + 18 * Math.sin(frame * 0.45) * wave];
	return (
		<g>
			<rect x={0} y={0} width={1920} height={1080} fill="#F3DDB5" />
			<Shelves seed="s1" top={60} gap={190} />
			<Pedro x={960} y={900} scale={1.15} mood={mood} armR={armR} seed={1} />
			<Counter y={790} />
		</g>
	);
};

export const S1Bodega: React.FC = () => {
	const frame = useSceneFrame();
	const {fps} = useVideoConfig();

	const sunY = ease(frame, [0, 100], [470, 210]);
	const shutter = ease(frame, [12, 50], [0, -DOOR.h - 20]);
	const wave = ease(frame, [48, 60], [0, 1]) - ease(frame, [96, 108], [0, 1]);
	const zoom = ease(frame, [0, 96], [1, 1.08]) * ease(frame, [96, 120], [1, 1.5]);
	const label = pop(frame, 58, fps);

	// El interior se dibuja a escala para llenar la puerta
	const k = DOOR.h / 1080;
	const ix = DOOR.x + (DOOR.w - 1920 * k) / 2;

	return (
		<AbsoluteFill style={{backgroundColor: warm.sky}}>
			<Canvas style={{transform: `scale(${zoom})`, transformOrigin: '960px 640px'}}>
				<defs>
					<linearGradient id="s1-sky" x1="0" y1="0" x2="0" y2="1">
						<stop offset="0" stopColor={warm.skyTop} />
						<stop offset="1" stopColor={warm.sky} />
					</linearGradient>
					<clipPath id="s1-door">
						<rect x={DOOR.x} y={DOOR.y} width={DOOR.w} height={DOOR.h} />
					</clipPath>
				</defs>
				<rect width={1920} height={1080} fill="url(#s1-sky)" />
				<circle cx={1700} cy={sunY} r={90} fill={warm.sun} />
				<circle cx={1700} cy={sunY} r={130} fill={warm.sun} opacity={0.3} />

				{/* Fachada */}
				<rect x={280} y={130} width={1360} height={900} fill={warm.wall} />
				<rect x={260} y={110} width={1400} height={40} rx={6} fill={warm.wallDark} />
				<rect x={560} y={180} width={800} height={118} rx={12} fill="#FFF4DE" stroke={warm.wallDark} strokeWidth={8} />
				<text x={960} y={262} textAnchor="middle" fontFamily={serif} fontWeight={700} fontSize={70} fill={warm.inkRed} letterSpacing={3}>
					BODEGA DON PEDRO
				</text>

				{/* Interior visible por la puerta */}
				<g clipPath="url(#s1-door)">
					<g transform={`translate(${ix} ${DOOR.y}) scale(${k})`}>
						<ShopInterior mood="happy" wave={wave} />
					</g>
					{/* Reja metálica */}
					<g transform={`translate(0 ${shutter})`}>
						<rect x={DOOR.x} y={DOOR.y} width={DOOR.w} height={DOOR.h} fill="#A3A8B0" />
						{Array.from({length: 30}).map((_, i) => (
							<rect key={i} x={DOOR.x} y={DOOR.y + i * 23} width={DOOR.w} height={6} fill="#868B94" />
						))}
						<rect x={DOOR.x} y={DOOR.y + DOOR.h - 24} width={DOOR.w} height={24} fill="#6F747C" />
					</g>
				</g>
				<rect x={DOOR.x - 14} y={DOOR.y - 14} width={DOOR.w + 28} height={DOOR.h + 14} fill="none" stroke={warm.wallDark} strokeWidth={14} />

				{/* Detalles de la vereda */}
				<rect x={0} y={1000} width={1920} height={80} fill="#B9A58C" />
				<BoxIcon x={370} y={955} s={1.1} />
				<BoxIcon x={380} y={872} s={0.95} rot={-4} />
				<BoxIcon x={1530} y={955} s={1.1} rot={3} />
			</Canvas>

			{/* Presentación de Pedro */}
			<div
				style={{
					position: 'absolute',
					left: 90,
					bottom: 90,
					padding: '26px 36px',
					borderRadius: 22,
					background: 'rgba(255, 248, 235, 0.96)',
					boxShadow: '0 18px 40px rgba(80, 45, 10, 0.25)',
					transform: `translateY(${(1 - label) * 60}px) scale(${0.9 + 0.1 * label})`,
					opacity: Math.min(1, label * 1.5) * ease(frame, [100, 114], [1, 0]),
				}}
			>
				<div style={{fontFamily: serif, fontWeight: 700, fontSize: 66, color: warm.text, lineHeight: 1}}>Pedro</div>
				<div style={{fontFamily: sans, fontWeight: 500, fontSize: 30, color: warm.muted, marginTop: 10}}>44 años · bodeguero en Lima</div>
			</div>

			<Sfx at={10} name="shutter" volume={0.7} />
			<Sfx at={58} name="pop" volume={0.6} />
			<Sfx at={98} name="whoosh" volume={0.5} />
		</AbsoluteFill>
	);
};
