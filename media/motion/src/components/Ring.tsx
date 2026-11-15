import React from 'react';
import {dark, sans} from '../theme';

export const CENTER: [number, number] = [960, 540];

export const NODES = [
	{angle: -90, label: 'No le alcanza'},
	{angle: 0, label: 'Pide prestado'},
	{angle: 90, label: 'Paga cuotas con la venta del día'},
	{angle: 180, label: 'Vuelve a no alcanzarle'},
] as const;

const rad = (d: number) => (d * Math.PI) / 180;
export const onRing = (r: number, angle: number): [number, number] => [CENTER[0] + r * Math.cos(rad(angle)), CENTER[1] + r * Math.sin(rad(angle))];

/** Círculo vicioso: anillo con flechas en sentido horario y cuatro estaciones. */
export const Ring: React.FC<{
	r: number;
	draw: number;
	flow: number;
	nodes: number[];
	labelsOpacity?: number;
}> = ({r, draw, flow, nodes, labelsOpacity = 1}) => (
	<g>
		<circle cx={CENTER[0]} cy={CENTER[1]} r={r} fill="none" stroke={dark.ring} strokeWidth={22} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - draw} transform={`rotate(-90 ${CENTER[0]} ${CENTER[1]})`} strokeLinecap="round" />
		<circle cx={CENTER[0]} cy={CENTER[1]} r={r} fill="none" stroke={dark.ringHot} strokeWidth={6} pathLength={1} strokeDasharray="0.015 0.03" strokeDashoffset={-flow} opacity={0.75 * draw} />
		{[-45, 45, 135, 225].map((a) => {
			const [x, y] = onRing(r, a);
			return (
				<path key={a} d="M -22 -22 L 16 0 L -22 22 Z" fill={dark.ringHot} transform={`translate(${x} ${y}) rotate(${a + 90})`} opacity={draw >= 1 ? 1 : 0} />
			);
		})}
		{NODES.map((n, i) => {
			const p = nodes[i] ?? 0;
			const [x, y] = onRing(r, n.angle);
			const [lx, ly] = onRing(r + (n.angle === 90 ? 95 : n.angle === -90 ? 80 : 70), n.angle);
			const anchor = n.angle === 0 ? 'start' : n.angle === 180 ? 'end' : 'middle';
			return (
				<g key={n.label}>
					<g transform={`translate(${x} ${y}) scale(${p})`}>
						<circle r={36} fill={dark.ringHot} />
						<text y={14} textAnchor="middle" fontFamily={sans} fontWeight={800} fontSize={38} fill="#FFFFFF">
							{i + 1}
						</text>
					</g>
					<text x={lx} y={ly + 16} textAnchor={anchor} fontFamily={sans} fontWeight={700} fontSize={46} fill={dark.text} opacity={Math.min(1, p) * labelsOpacity}>
						{n.label}
					</text>
				</g>
			);
		})}
	</g>
);
