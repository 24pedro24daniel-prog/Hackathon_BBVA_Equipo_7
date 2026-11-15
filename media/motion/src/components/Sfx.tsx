import React from 'react';
import {Audio, Sequence, staticFile} from 'remotion';
import {useSpeed} from '../lib/time';

// Volumen general de efectos: bajo, porque encima va tu voz en vivo.
const MASTER = 0.55;

export type SfxName =
	| 'coin'
	| 'pop'
	| 'whoosh'
	| 'page'
	| 'write'
	| 'shutter'
	| 'thud'
	| 'drip'
	| 'nope'
	| 'tick'
	| 'drone'
	| 'break'
	| 'chime';

export const Sfx: React.FC<{at: number; name: SfxName; volume?: number; rate?: number}> = ({at, name, volume = 0.6, rate = 1}) => {
	const speed = useSpeed();
	return (
		<Sequence from={Math.round(at / speed)} layout="none" name={`sfx:${name}`}>
			<Audio src={staticFile(`sfx/${name}.wav`)} volume={volume * MASTER} playbackRate={rate} />
		</Sequence>
	);
};
