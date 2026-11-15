import React from 'react';
import {random} from 'remotion';
import {warm} from '../theme';

const PRODUCT_COLORS = ['#D9483B', '#F2B544', '#3E8E5E', '#2F6DB5', '#E77F3C', '#8E4FA8', '#E2D3B0', '#C93A63', '#4FA3A5'];

/** Pared con anaqueles llenos de productos genéricos (sin marcas). */
export const Shelves: React.FC<{x?: number; width?: number; top?: number; rows?: number; gap?: number; seed?: string}> = ({
	x = 140,
	width = 1640,
	top = 170,
	rows = 3,
	gap = 175,
	seed = 'shop',
}) => (
	<g>
		{Array.from({length: rows}).map((_, r) => {
			const baseY = top + (r + 1) * gap;
			const items: React.ReactNode[] = [];
			let cx = x + 18;
			let i = 0;
			while (cx < x + width - 60) {
				const kind = random(`${seed}-k-${r}-${i}`);
				const color = PRODUCT_COLORS[Math.floor(random(`${seed}-c-${r}-${i}`) * PRODUCT_COLORS.length)];
				if (kind < 0.45) {
					const w = 46 + random(`${seed}-w-${r}-${i}`) * 40;
					const h = 70 + random(`${seed}-h-${r}-${i}`) * 70;
					items.push(
						<g key={i}>
							<rect x={cx} y={baseY - h} width={w} height={h} rx={4} fill={color} />
							<rect x={cx + 7} y={baseY - h + 16} width={w - 14} height={h * 0.32} rx={3} fill="#FFF7E6" opacity={0.75} />
						</g>,
					);
					cx += w + 8;
				} else if (kind < 0.75) {
					const h = 95 + random(`${seed}-b-${r}-${i}`) * 40;
					items.push(
						<g key={i}>
							<rect x={cx + 9} y={baseY - h} width={14} height={20} rx={3} fill={color} />
							<path d={`M ${cx} ${baseY} L ${cx} ${baseY - h + 45} Q ${cx} ${baseY - h + 22} ${cx + 11} ${baseY - h + 18} L ${cx + 21} ${baseY - h + 18} Q ${cx + 32} ${baseY - h + 22} ${cx + 32} ${baseY - h + 45} L ${cx + 32} ${baseY} Z`} fill={color} opacity={0.9} />
							<rect x={cx + 3} y={baseY - h * 0.55} width={26} height={22} fill="#FFF7E6" opacity={0.8} />
						</g>,
					);
					cx += 40;
				} else {
					const w = 40;
					items.push(
						<g key={i}>
							{[0, 1, 2].map((k) => (
								<g key={k}>
									<rect x={cx} y={baseY - 38 * (k + 1)} width={w} height={36} rx={4} fill={color} />
									<rect x={cx} y={baseY - 38 * (k + 1) + 12} width={w} height={10} fill="#FFF7E6" opacity={0.7} />
								</g>
							))}
						</g>,
					);
					cx += w + 10;
				}
				i++;
			}
			return (
				<g key={r}>
					{items}
					<rect x={x} y={baseY} width={width} height={16} fill={warm.woodLight} />
					<rect x={x} y={baseY + 16} width={width} height={8} fill={warm.woodDark} opacity={0.5} />
				</g>
			);
		})}
	</g>
);

/** Mostrador de madera visto de frente. */
export const Counter: React.FC<{y: number; x?: number; width?: number; height?: number}> = ({y, x = 0, width = 1920, height = 400}) => (
	<g>
		<rect x={x} y={y} width={width} height={height} fill={warm.wood} />
		{Array.from({length: Math.ceil(width / 160)}).map((_, i) => (
			<line key={i} x1={x + i * 160} y1={y + 30} x2={x + i * 160} y2={y + height} stroke={warm.woodDark} strokeWidth={4} opacity={0.45} />
		))}
		<rect x={x - 10} y={y - 6} width={width + 20} height={36} rx={6} fill={warm.woodLight} />
	</g>
);

export const Coin: React.FC<{x: number; y: number; r?: number; spin?: number; opacity?: number}> = ({x, y, r = 22, spin = 0, opacity = 1}) => {
	const sx = Math.max(0.15, Math.abs(Math.cos(spin)));
	return (
		<g transform={`translate(${x} ${y}) scale(${sx} 1)`} opacity={opacity}>
			<circle r={r} fill={warm.coinDark} />
			<circle r={r * 0.82} fill={warm.coin} />
			<text y={r * 0.32} textAnchor="middle" fontSize={r * 0.9} fontWeight={700} fill={warm.coinDark} fontFamily="sans-serif">
				S/
			</text>
		</g>
	);
};

export const Bill: React.FC<{x: number; y: number; w?: number; rot?: number; opacity?: number}> = ({x, y, w = 110, rot = 0, opacity = 1}) => (
	<g transform={`translate(${x} ${y}) rotate(${rot})`} opacity={opacity}>
		<rect x={-w / 2} y={-w * 0.25} width={w} height={w * 0.5} rx={6} fill={warm.bill} stroke={warm.billDark} strokeWidth={3} />
		<circle r={w * 0.15} fill="none" stroke={warm.billDark} strokeWidth={3} />
		<text x={-w / 2 + 10} y={-w * 0.25 + 22} fontSize={w * 0.16} fontWeight={700} fill={warm.billDark} fontFamily="sans-serif">
			S/
		</text>
	</g>
);

/** Cajón de dinero abierto, visto de frente. `fill` 0→1 controla cuánta plata hay dentro. */
export const Cajon: React.FC<{x: number; y: number; w?: number; fill: number; label?: string}> = ({x, y, w = 520, fill, label}) => {
	const h = w * 0.42;
	const depth = w * 0.26;
	const coins = Math.round(Math.max(0, Math.min(1, fill)) * 34);
	const spots = Array.from({length: 34}).map((_, i) => {
		const row = Math.floor(i / 9);
		const rx = random(`cajon-x-${i}`);
		const ry = random(`cajon-y-${i}`);
		return {
			cx: x - w / 2 + 50 + rx * (w - 100),
			cy: y - 18 - row * (depth / 4.2) - ry * 10,
		};
	});
	return (
		<g>
			{/* Interior */}
			<path d={`M ${x - w / 2} ${y} L ${x - w / 2 + 34} ${y - depth} L ${x + w / 2 - 34} ${y - depth} L ${x + w / 2} ${y} Z`} fill={warm.woodDark} />
			<path d={`M ${x - w / 2 + 34} ${y - depth} L ${x + w / 2 - 34} ${y - depth} L ${x + w / 2 - 50} ${y - depth + 22} L ${x - w / 2 + 50} ${y - depth + 22} Z`} fill="#000" opacity={0.25} />
			{fill > 0.15 ? <Bill x={x - w * 0.18} y={y - depth * 0.45} w={w * 0.3} rot={-8} /> : null}
			{fill > 0.4 ? <Bill x={x + w * 0.16} y={y - depth * 0.55} w={w * 0.3} rot={10} /> : null}
			{spots.slice(0, coins).map((s, i) => (
				<g key={i}>
					<ellipse cx={s.cx} cy={s.cy + 4} rx={24} ry={10} fill={warm.coinDark} />
					<ellipse cx={s.cx} cy={s.cy} rx={24} ry={10} fill={warm.coin} />
				</g>
			))}
			{/* Frente */}
			<rect x={x - w / 2} y={y} width={w} height={h} rx={10} fill={warm.wood} />
			<rect x={x - w / 2} y={y} width={w} height={14} fill={warm.woodLight} />
			<rect x={x - 60} y={y + h * 0.48} width={120} height={20} rx={10} fill={warm.woodDark} />
			{label ? (
				<text x={x} y={y + h * 0.36} textAnchor="middle" fontSize={w * 0.065} fontWeight={700} fill="#FFF1DA" fontFamily="Libre Franklin, sans-serif" letterSpacing={2}>
					{label}
				</text>
			) : null}
		</g>
	);
};

export const HouseIcon: React.FC<{x: number; y: number; s?: number; color?: string; roof?: string}> = ({x, y, s = 1, color = '#F6EBD3', roof = warm.inkRed}) => (
	<g transform={`translate(${x} ${y}) scale(${s})`}>
		<rect x={-110} y={-60} width={220} height={170} rx={8} fill={color} />
		<path d="M -140 -50 L 0 -170 L 140 -50 Z" fill={roof} strokeLinejoin="round" stroke={roof} strokeWidth={14} />
		<rect x={-30} y={20} width={60} height={90} rx={6} fill={warm.wood} />
		<rect x={-90} y={-20} width={46} height={46} rx={4} fill="#9ED3F2" />
		<rect x={44} y={-20} width={46} height={46} rx={4} fill="#9ED3F2" />
		<rect x={70} y={-150} width={26} height={60} fill={roof} />
	</g>
);

export const StoreIcon: React.FC<{x: number; y: number; s?: number}> = ({x, y, s = 1}) => (
	<g transform={`translate(${x} ${y}) scale(${s})`}>
		<rect x={-125} y={-60} width={250} height={170} rx={8} fill="#F6EBD3" />
		{Array.from({length: 6}).map((_, i) => (
			<path key={i} d={`M ${-140 + i * 46.6} -120 L ${-140 + (i + 1) * 46.6} -120 L ${-140 + (i + 1) * 46.6} -60 Q ${-140 + (i + 0.5) * 46.6} -30 ${-140 + i * 46.6} -60 Z`} fill={i % 2 ? '#FFFFFF' : '#2F6DB5'} />
		))}
		<rect x={-140} y={-140} width={280} height={24} rx={6} fill={warm.wood} />
		<rect x={-95} y={0} width={110} height={70} rx={4} fill="#9ED3F2" />
		<rect x={40} y={0} width={55} height={110} rx={4} fill={warm.wood} />
	</g>
);

export const BoxIcon: React.FC<{x: number; y: number; s?: number; rot?: number}> = ({x, y, s = 1, rot = 0}) => (
	<g transform={`translate(${x} ${y}) rotate(${rot}) scale(${s})`}>
		<rect x={-50} y={-40} width={100} height={80} rx={4} fill="#C99A5B" stroke="#8E6634" strokeWidth={4} />
		<rect x={-12} y={-40} width={24} height={30} fill="#E7C893" />
	</g>
);
