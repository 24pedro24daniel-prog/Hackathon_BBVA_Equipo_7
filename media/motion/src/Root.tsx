import React from 'react';
import {Composition} from 'remotion';
import {FPS, totalFrames} from './timeline';
import {Storytelling} from './Video';

export const RemotionRoot: React.FC = () => (
	<>
		<Composition id="Storytelling" component={Storytelling} defaultProps={{variant: 'full' as const}} durationInFrames={totalFrames('full')} fps={FPS} width={1920} height={1080} />
		<Composition id="Storytelling30" component={Storytelling} defaultProps={{variant: 'short' as const}} durationInFrames={totalFrames('short')} fps={FPS} width={1920} height={1080} />
	</>
);
