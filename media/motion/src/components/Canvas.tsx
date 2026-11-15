import React from 'react';

/** Lienzo SVG de 1920×1080 que ocupa toda la composición. */
export const Canvas: React.FC<{style?: React.CSSProperties; children: React.ReactNode}> = ({style, children}) => (
	<svg viewBox="0 0 1920 1080" width={1920} height={1080} style={{position: 'absolute', left: 0, top: 0, overflow: 'visible', ...style}}>
		{children}
	</svg>
);

/** Burbuja/tarjeta de texto HTML posicionada en el lienzo. */
export const Card: React.FC<{
	x: number;
	y: number;
	anchor?: 'left' | 'center' | 'right';
	style?: React.CSSProperties;
	children: React.ReactNode;
}> = ({x, y, anchor = 'left', style, children}) => {
	const tx = anchor === 'left' ? '0%' : anchor === 'center' ? '-50%' : '-100%';
	return (
		<div style={{position: 'absolute', left: x, top: y, width: 'max-content', transform: `translate(${tx}, -50%)`, ...style}}>
			{children}
		</div>
	);
};
