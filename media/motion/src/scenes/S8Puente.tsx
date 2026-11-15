import React from 'react';
import {AbsoluteFill, Img, interpolateColors, staticFile, useVideoConfig} from 'remotion';
import {Canvas, Card} from '../components/Canvas';
import {Pedro} from '../components/Pedro';
import {Coin} from '../components/Props';
import {CENTER, onRing, Ring} from '../components/Ring';
import {useSceneFrame} from '../lib/time';
import {Sfx} from '../components/Sfx';
import {ease, lerp, pop} from '../lib/anim';
import {brand, dark, sans, serif} from '../theme';
import {PEDRO_IN_RING, RING_END} from './S7Circulo';

const BREAK = 16;
const PHONE = {x: 960, y: 540, w: 380, h: 760};

const ArcPiece: React.FC<{r: number; a1: number; a2: number}> = ({r, a1, a2}) => {
	const [x1, y1] = onRing(r, a1);
	const [x2, y2] = onRing(r, a2);
	return <path d={`M ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2}`} fill="none" stroke={dark.ring} strokeWidth={22} strokeLinecap="round" />;
};

export const S8Puente: React.FC = () => {
	const frame = useSceneFrame();
	const {fps} = useVideoConfig();

	const broken = frame >= BREAK;
	const burst = ease(frame, [BREAK, BREAK + 26], [0, 1], (x) => 1 - (1 - x) ** 3);
	const flash = lerp(frame, [BREAK - 2, BREAK + 2, BREAK + 16], [0, 0.85, 0]);
	const bg = interpolateColors(frame, [BREAK, BREAK + 12], [dark.bg, brand.bg]);

	const phoneIn = pop(frame, 2, fps, 14, 120);
	const phoneY = 1500 - (1500 - PHONE.y) * phoneIn;
	const logo = pop(frame, 26, fps, 10, 140);
	const glow = ease(frame, [24, 40], [0, 1]) * (0.85 + 0.15 * Math.sin(frame / 6));

	const move = ease(frame, [12, 40], [0, 1]);
	const pedroX = PEDRO_IN_RING.x + (450 - PEDRO_IN_RING.x) * move;
	const pedroY = PEDRO_IN_RING.y + (1180 - PEDRO_IN_RING.y) * move;
	const pedroS = PEDRO_IN_RING.scale + (1.05 - PEDRO_IN_RING.scale) * move;
	const wave = ease(frame, [46, 56], [0, 1]);
	const armR: [number, number] = [8 + 60 * wave, 6 + 140 * wave + 12 * Math.sin(frame * 0.45) * wave];

	const kicker = ease(frame, [30, 42], [0, 1]);
	const name = pop(frame, 44, fps, 12, 150);

	const [cx, cy] = onRing(RING_END.r, RING_END.angle);

	return (
		<AbsoluteFill style={{backgroundColor: bg}}>
			{/* Luz de marca detrás del teléfono */}
			<AbsoluteFill style={{background: `radial-gradient(circle at ${PHONE.x}px ${PHONE.y}px, rgba(133,200,255,${0.55 * glow}) 0%, rgba(133,200,255,0) 38%)`}} />

			<Canvas>
				{!broken ? (
					<g>
						<Ring r={RING_END.r} draw={1} flow={RING_END.flowEnd} nodes={[1, 1, 1, 1]} />
						<Coin x={cx} y={cy} r={30} spin={frame * 0.4} />
					</g>
				) : (
					<g opacity={1 - burst}>
						{Array.from({length: 8}).map((_, k) => {
							const a1 = -90 + k * 45 + 4;
							const mid = a1 + 18;
							const [dx, dy] = onRing(700 * burst, mid);
							return (
								<g key={k} transform={`translate(${dx - CENTER[0]} ${dy - CENTER[1]}) rotate(${(k % 2 ? 1 : -1) * 70 * burst} ${CENTER[0]} ${CENTER[1]})`}>
									<ArcPiece r={RING_END.r} a1={a1} a2={a1 + 37} />
								</g>
							);
						})}
					</g>
				)}
				<Pedro x={pedroX} y={pedroY} scale={pedroS} mood={frame >= BREAK + 6 ? 'happy' : 'sad'} armR={armR} seed={8} />
			</Canvas>

			{/* Teléfono con TuCaserito */}
			<Card x={PHONE.x} y={phoneY} anchor="center">
				<div
					style={{
						width: PHONE.w,
						height: PHONE.h,
						borderRadius: 60,
						background: brand.midnight,
						padding: 16,
						boxShadow: `0 40px 80px rgba(0,19,145,${0.25 + 0.2 * glow})`,
						transform: `rotate(${(1 - phoneIn) * 8}deg)`,
					}}
				>
					<div
						style={{
							width: '100%',
							height: '100%',
							borderRadius: 46,
							background: brand.logoBg,
							display: 'flex',
							flexDirection: 'column',
							alignItems: 'center',
							justifyContent: 'center',
							position: 'relative',
							overflow: 'hidden',
						}}
					>
						<div style={{position: 'absolute', top: 18, width: 110, height: 30, borderRadius: 15, background: brand.midnight}} />
						<Img src={staticFile('logo.jpeg')} style={{width: 270, transform: `scale(${logo})`, opacity: Math.min(1, logo * 1.5)}} />
						<div style={{fontFamily: serif, fontWeight: 700, fontSize: 46, color: brand.electric, marginTop: 6, opacity: Math.min(1, logo * 1.5)}}>TuCaserito</div>
					</div>
				</div>
			</Card>

			{/* Remate */}
			<Card x={1230} y={540}>
				<div style={{fontFamily: sans, fontWeight: 500, fontSize: 46, color: brand.slate, opacity: kicker, transform: `translateY(${(1 - kicker) * 24}px)`}}>
					Pero Pedro conoce a…
				</div>
				<div
					style={{
						fontFamily: serif,
						fontWeight: 700,
						fontSize: 118,
						lineHeight: 1.1,
						color: brand.electric,
						opacity: Math.min(1, name * 1.5),
						transform: `scale(${0.7 + 0.3 * name})`,
						transformOrigin: 'left center',
					}}
				>
					TuCaserito
				</div>
			</Card>

			<AbsoluteFill style={{backgroundColor: '#FFFFFF', opacity: flash}} />

			<Sfx at={2} name="whoosh" volume={0.6} />
			<Sfx at={BREAK} name="break" volume={0.8} />
			<Sfx at={44} name="chime" volume={0.9} />
		</AbsoluteFill>
	);
};
