import React from 'react';
import {AbsoluteFill, Sequence, useCurrentFrame} from 'remotion';
import {lerp} from './lib/anim';
import {SpeedContext} from './lib/time';
import {S1Bodega} from './scenes/S1Bodega';
import {S2Cuaderno} from './scenes/S2Cuaderno';
import {S3Cajon} from './scenes/S3Cajon';
import {S4FinDeMes} from './scenes/S4FinDeMes';
import {S5Banco} from './scenes/S5Banco';
import {S6GotaAGota} from './scenes/S6GotaAGota';
import {S7Circulo} from './scenes/S7Circulo';
import {S8Puente} from './scenes/S8Puente';
import {DURATIONS, SCENES, SceneId, Variant} from './timeline';

const COMPONENTS: Record<SceneId, React.FC> = {
	bodega: S1Bodega,
	cuaderno: S2Cuaderno,
	cajon: S3Cajon,
	finDeMes: S4FinDeMes,
	banco: S5Banco,
	gotaAGota: S6GotaAGota,
	circulo: S7Circulo,
	puente: S8Puente,
};

// Fundido entre escenas; el puente entra por corte porque continúa el mismo anillo
const DISSOLVE = 8;

const FadeIn: React.FC<{frames: number; children: React.ReactNode}> = ({frames, children}) => {
	const frame = useCurrentFrame();
	return <AbsoluteFill style={{opacity: frames > 0 ? lerp(frame, [0, frames], [0, 1]) : 1}}>{children}</AbsoluteFill>;
};

export type StorytellingProps = {variant: Variant};

export const Storytelling: React.FC<StorytellingProps> = ({variant}) => {
	let start = 0;
	return (
		<AbsoluteFill style={{backgroundColor: '#000'}}>
			{SCENES.map((scene, i) => {
				const frames = DURATIONS[variant][scene.id];
				const overlap = i === 0 || scene.id === 'puente' ? 0 : DISSOLVE;
				const from = start - overlap;
				start += frames;
				const Scene = COMPONENTS[scene.id];
				return (
					<Sequence key={scene.id} from={from} durationInFrames={frames + overlap} name={scene.id}>
						<SpeedContext.Provider value={scene.base / frames}>
							<FadeIn frames={overlap}>
								<Scene />
							</FadeIn>
						</SpeedContext.Provider>
					</Sequence>
				);
			})}
		</AbsoluteFill>
	);
};
