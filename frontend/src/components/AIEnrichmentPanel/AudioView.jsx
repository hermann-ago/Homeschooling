import React, { useState, useEffect, useRef, useCallback } from 'react';
import clsx from 'clsx';
import { Play, Pause, Square } from 'lucide-react';

export default function AudioView({ text }) {
  const [playing, setPlaying] = useState(false);
  const utteranceRef = useRef(null);

  const stop = useCallback(() => {
    window.speechSynthesis.cancel();
    setPlaying(false);
  }, []);

  // Clean up on unmount
  useEffect(() => () => stop(), [stop]);

  const handlePlay = () => {
    if (playing) {
      window.speechSynthesis.pause();
      setPlaying(false);
      return;
    }
    if (window.speechSynthesis.paused) {
      window.speechSynthesis.resume();
      setPlaying(true);
      return;
    }
    // Start fresh
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.9;
    utterance.onend = () => setPlaying(false);
    utterance.onerror = () => setPlaying(false);
    utteranceRef.current = utterance;
    window.speechSynthesis.speak(utterance);
    setPlaying(true);
  };

  return (
    <div className="space-y-4">
      {/* Summary text block */}
      <div className="bg-white rounded-xl border border-sky-200 p-4 text-sm text-text-primary leading-relaxed">
        {text}
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3">
        <button
          onClick={handlePlay}
          className={clsx(
            'flex items-center space-x-2 px-5 py-2.5 rounded-xl text-sm font-bold transition active:scale-95',
            playing
              ? 'bg-sky-600 text-white hover:bg-sky-700'
              : 'bg-sky-100 text-sky-700 hover:bg-sky-200'
          )}
        >
          {playing ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
          <span>{playing ? 'Pause' : 'Play'}</span>
        </button>
        {(playing || window.speechSynthesis.paused) && (
          <button
            onClick={stop}
            className="flex items-center space-x-1.5 px-4 py-2.5 rounded-xl text-sm font-semibold bg-gray-100 hover:bg-gray-200 text-text-secondary transition"
          >
            <Square className="w-3.5 h-3.5" />
            <span>Stop</span>
          </button>
        )}
        <p className="text-xs text-text-secondary ml-auto">
          Powered by your browser's TTS
        </p>
      </div>
    </div>
  );
}
