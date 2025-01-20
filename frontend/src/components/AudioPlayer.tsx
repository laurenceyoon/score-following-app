import React, { forwardRef, useImperativeHandle } from 'react';
import AudioPlayer from 'react-h5-audio-player';
import 'react-h5-audio-player/lib/styles.css';

export interface AudioPlayerRef {
  play: () => void;
  pause: () => void;
}

interface CustomAudioPlayerProps {
  audioFile: File;
  isPlaying: boolean;
  onPlay: () => void;
  onPause: () => void;
  onEnded: () => void;
}

const CustomAudioPlayer = forwardRef<AudioPlayerRef, CustomAudioPlayerProps>(({ 
  audioFile, 
  isPlaying,
  onPlay,
  onPause,
  onEnded 
}, ref) => {
  const playerRef = React.useRef<any>(null);

  useImperativeHandle(ref, () => ({
    play: () => {
      playerRef.current?.audio.current.play();
    },
    pause: () => {
      playerRef.current?.audio.current.pause();
    }
  }));

  const audioUrl = React.useMemo(() => {
    return URL.createObjectURL(audioFile);
  }, [audioFile]);

  // cleanup
  React.useEffect(() => {
    return () => {
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
    };
  }, [audioUrl]);

  return (
    <div>
      <AudioPlayer
        ref={playerRef}
        src={audioUrl}
        showSkipControls={false}
        showJumpControls={false}
        showDownloadProgress={false}
        autoPlay={isPlaying}
        onPlay={onPlay}
        onPause={onPause}
        onEnded={onEnded}
      />
    </div>
  );
});

export default CustomAudioPlayer;
