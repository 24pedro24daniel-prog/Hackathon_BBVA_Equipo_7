import {Easing, interpolate, spring} from 'remotion';

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

/** Interpolación con suavizado in-out, sujeta a los extremos. */
export const ease = (frame: number, input: [number, number], output: [number, number], easing = Easing.inOut(Easing.cubic)) =>
	interpolate(frame, input, output, {...clamp, easing});

/** Interpolación lineal sujeta a los extremos. */
export const lerp = (frame: number, input: number[], output: number[]) => interpolate(frame, input, output, clamp);

/** Resorte 0→1 que arranca en `start`. */
export const pop = (frame: number, start: number, fps: number, damping = 12, stiffness = 140) =>
	spring({frame: frame - start, fps, config: {damping, stiffness, mass: 0.8}});

/** Arco parabólico entre dos puntos, t en [0,1]. */
export const arc = (t: number, from: [number, number], to: [number, number], height: number): [number, number] => {
	const x = from[0] + (to[0] - from[0]) * t;
	const y = from[1] + (to[1] - from[1]) * t - height * 4 * t * (1 - t);
	return [x, y];
};
