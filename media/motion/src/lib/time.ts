import {createContext, useContext} from 'react';
import {useCurrentFrame} from 'remotion';

/** Velocidad de la escena actual: 1 = duración base; >1 = versión corta acelerada. */
export const SpeedContext = createContext(1);

export const useSpeed = () => useContext(SpeedContext);

/** Frame de la escena en su línea de tiempo base (las animaciones están escritas en esos frames). */
export const useSceneFrame = () => useCurrentFrame() * useContext(SpeedContext);
