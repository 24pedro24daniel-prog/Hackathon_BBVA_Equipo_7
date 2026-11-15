import {loadFont as loadFranklin} from '@remotion/google-fonts/LibreFranklin';
import {loadFont as loadSerif} from '@remotion/google-fonts/SourceSerif4';
import {loadFont as loadCaveat} from '@remotion/google-fonts/Caveat';

export const sans = loadFranklin('normal', {weights: ['400', '500', '600', '700', '800'], subsets: ['latin']}).fontFamily;
export const serif = loadSerif('normal', {weights: ['600', '700'], subsets: ['latin']}).fontFamily;
export const hand = loadCaveat('normal', {weights: ['500', '700'], subsets: ['latin']}).fontFamily;

// Marca TuCaserito (BBVA 2025, ver DESIGN.md)
export const brand = {
	electric: '#001391',
	midnight: '#070E46',
	slate: '#46536D',
	light: '#85C8FF',
	bg: '#F7F8F8',
	logoBg: '#F1F4FB',
};

// Mundo del problema: cálido al inicio, se apaga hacia el círculo
export const warm = {
	sky: '#F9D9A6',
	skyTop: '#F4B87A',
	sun: '#FFE7A8',
	wall: '#E8B76A',
	wallDark: '#C98F45',
	paper: '#F6EBD3',
	paperLine: '#C9D7E8',
	kraft: '#E9D8B8',
	wood: '#9A5B2E',
	woodDark: '#6E3E1C',
	woodLight: '#C07A42',
	ink: '#2B2A4A',
	inkRed: '#B8322A',
	coin: '#E8B83A',
	coinDark: '#B98A1C',
	bill: '#7FB77E',
	billDark: '#4E8A4E',
	text: '#3A2A1A',
	muted: '#7A6650',
};

export const danger = '#C30A0A';
export const dark = {
	bg: '#140B10',
	ring: '#7A1A1A',
	ringHot: '#D33A2C',
	text: '#F3E6E0',
};

// Pedro (persona de la PPT: 44 años, pelo negro corto, polo azul marino)
export const pedro = {
	skin: '#C98E62',
	skinShade: '#A9714A',
	hair: '#1C1A1F',
	polo: '#25306B',
	poloDark: '#1A2350',
	poloDots: '#3B4888',
};
