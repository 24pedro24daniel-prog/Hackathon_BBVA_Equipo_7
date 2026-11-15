// Duraciones de cada bloque en frames (30 fps). Ajusta aquí para calzar con tu ritmo al hablar.
export const FPS = 30;

// `base` es la duración con la que está animada cada escena (versión de 45 s).
// Cada variante le da a la escena otra duración y la escena se acelera en proporción.
export const SCENES = [
	{id: 'bodega', base: 120},
	{id: 'cuaderno', base: 180},
	{id: 'cajon', base: 180},
	{id: 'finDeMes', base: 210},
	{id: 'banco', base: 210},
	{id: 'gotaAGota', base: 180},
	{id: 'circulo', base: 165},
	{id: 'puente', base: 105},
] as const;

export type SceneId = (typeof SCENES)[number]['id'];
export type Variant = 'full' | 'short';

export const DURATIONS: Record<Variant, Record<SceneId, number>> = {
	// 45 s
	full: {
		bodega: 120, // 0.0 – 4.0 s
		cuaderno: 180, // 4.0 – 10.0 s
		cajon: 180, // 10.0 – 16.0 s
		finDeMes: 210, // 16.0 – 23.0 s
		banco: 210, // 23.0 – 30.0 s
		gotaAGota: 180, // 30.0 – 36.0 s
		circulo: 165, // 36.0 – 41.5 s
		puente: 105, // 41.5 – 45.0 s
	},
	// 30 s
	short: {
		bodega: 72, // 0.0 – 2.4 s
		cuaderno: 114, // 2.4 – 6.2 s
		cajon: 114, // 6.2 – 10.0 s
		finDeMes: 132, // 10.0 – 14.4 s
		banco: 144, // 14.4 – 19.2 s
		gotaAGota: 120, // 19.2 – 23.2 s
		circulo: 108, // 23.2 – 26.8 s
		puente: 96, // 26.8 – 30.0 s
	},
};

export const totalFrames = (variant: Variant) => Object.values(DURATIONS[variant]).reduce((acc, f) => acc + f, 0);
