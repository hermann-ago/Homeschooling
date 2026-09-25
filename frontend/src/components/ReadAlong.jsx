import React, { useCallback, useEffect, useRef, useState } from 'react';
import clsx from 'clsx';
import { Pause, Play, RotateCcw } from 'lucide-react';
import { tutorApi } from '../api/tutor';
import { partForSentence, sentenceAt } from '../utils/readAlong';

const SPEEDS = [0.75, 0.9, 1, 1.15, 1.3];
const DEVICE = 'device';

/**
 * Read-along narration. Highlighting follows only real timing information:
 * provider timepoints saved with a track, or the device voice's own
 * per-sentence events. Tracks without verified timings play without
 * highlighting and say so.
 */
export default function ReadAlong({ passage, tracks, activeIndex, onActiveIndex, disabled }) {
  const sentences = passage?.sentences || [];
  const usable = (tracks || []).filter((t) => t.status === 'ready' || t.status === 'legacy');
  const [source, setSource] = useState(() => usable.find((t) => t.synchronized)?.track_id || usable[0]?.track_id || DEVICE);
  const [manifest, setManifest] = useState(null);
  const [partIndex, setPartIndex] = useState(0);
  const [partUrl, setPartUrl] = useState(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [error, setError] = useState('');
  const audioRef = useRef(null);
  const pendingSeek = useRef(null);
  const speechIndex = useRef(0);
  const track = usable.find((t) => t.track_id === source);
  const synchronized = source === DEVICE || Boolean(track?.synchronized);

  const stopSpeech = useCallback(() => {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
  }, []);

  useEffect(() => () => stopSpeech(), [stopSpeech]);

  useEffect(() => {
    setManifest(null);
    setPartIndex(0);
    setPlaying(false);
    stopSpeech();
    if (source === DEVICE) return;
    tutorApi.audioManifest(source).then(setManifest).catch((e) => setError(e.message));
  }, [source, stopSpeech]);

  useEffect(() => {
    if (!manifest) return undefined;
    let url = null;
    let active = true;
    tutorApi.audioPart(source, partIndex).then((next) => {
      url = next;
      if (active) setPartUrl(next);
    }).catch((e) => setError(e.message));
    return () => {
      active = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [manifest, partIndex, source]);

  useEffect(() => {
    if (audioRef.current) audioRef.current.playbackRate = speed;
  }, [speed, partUrl]);

  useEffect(() => {
    if (disabled) {
      audioRef.current?.pause();
      stopSpeech();
      setPlaying(false);
    }
  }, [disabled, stopSpeech]);

  const parts = (manifest?.tracks || []).filter((p) => Array.isArray(p.sentenceStarts));

  const speakRef = useRef(null);
  const speakFrom = useCallback((index) => speakRef.current?.(index), []);
  useEffect(() => {
    speakRef.current = (index) => {
      stopSpeech();
      if (!window.speechSynthesis || index >= sentences.length) {
        setPlaying(false);
        return;
      }
      speechIndex.current = index;
      const utterance = new SpeechSynthesisUtterance(sentences[index].text);
      utterance.rate = speed;
      utterance.lang = 'en-US';
      utterance.onstart = () => onActiveIndex(index); // the device reports when this sentence starts
      utterance.onend = () => {
        if (speechIndex.current === index) speakRef.current?.(index + 1);
      };
      utterance.onerror = () => setPlaying(false);
      window.speechSynthesis.speak(utterance);
      setPlaying(true);
    };
  }, [onActiveIndex, sentences, speed, stopSpeech]);

  const seekTo = (index) => {
    onActiveIndex(index);
    if (source === DEVICE) {
      if (playing) speakFrom(index);
      return;
    }
    if (!synchronized || !parts.length) return;
    const target = partForSentence(parts, index);
    if (target < 0) return;
    const time = parts[target].sentenceStarts[index - parts[target].startSentence];
    if (target !== partIndex) {
      pendingSeek.current = time;
      setPartIndex(target);
    } else if (audioRef.current) {
      audioRef.current.currentTime = time;
    }
  };

  const toggle = () => {
    setError('');
    if (source === DEVICE) {
      if (playing) {
        speechIndex.current = -1;
        stopSpeech();
        setPlaying(false);
      } else {
        speakFrom(activeIndex ?? 0);
      }
      return;
    }
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) audio.play().catch((e) => setError(e.message));
    else audio.pause();
  };

  const replay = () => seekTo(activeIndex ?? 0);

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="p-3 border-b space-y-2">
        <div className="flex items-center gap-2">
          <button type="button" onClick={toggle} disabled={disabled} aria-label={playing ? 'Pause' : 'Play'}
            className="w-11 h-11 rounded-xl bg-sky-600 text-white flex items-center justify-center disabled:opacity-40">
            {playing ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5" />}
          </button>
          <button type="button" onClick={replay} disabled={disabled} aria-label="Replay sentence"
            className="w-11 h-11 rounded-xl border flex items-center justify-center disabled:opacity-40">
            <RotateCcw className="w-5 h-5" />
          </button>
          <label className="text-xs text-text-secondary">Speed{' '}
            <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))} className="rounded border p-1">
              {SPEEDS.map((s) => <option key={s} value={s}>{s}×</option>)}
            </select>
          </label>
        </div>
        <label className="block text-xs text-text-secondary">Voice{' '}
          <select value={source} onChange={(e) => setSource(e.target.value)} className="rounded border p-1 max-w-full">
            {usable.map((t) => (
              <option key={t.track_id} value={t.track_id}>{t.voice || t.provider}{t.synchronized ? '' : ' (no highlighting)'}</option>
            ))}
            <option value={DEVICE}>Device voice</option>
          </select>
        </label>
        {!synchronized && (
          <p className="text-xs text-amber-800">This recording has no verified timings for this passage, so sentences are not highlighted.</p>
        )}
        {error && <p className="text-xs text-red-700">{error}</p>}
      </div>
      {partUrl && source !== DEVICE && (
        <audio
          ref={audioRef}
          src={partUrl}
          onLoadedMetadata={(e) => {
            e.currentTarget.playbackRate = speed;
            if (pendingSeek.current !== null) {
              e.currentTarget.currentTime = pendingSeek.current;
              pendingSeek.current = null;
              e.currentTarget.play().catch(() => {});
            } else if (playing) {
              e.currentTarget.play().catch(() => {});
            }
          }}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onTimeUpdate={(e) => {
            if (!synchronized) return;
            const index = sentenceAt(parts[partIndex], e.currentTarget.currentTime);
            if (index !== null && index !== activeIndex) onActiveIndex(index);
          }}
          onEnded={() => {
            const count = manifest?.tracks?.length || 0;
            if (partIndex + 1 < count) {
              setPlaying(true);
              setPartIndex(partIndex + 1);
            } else {
              setPlaying(false);
            }
          }}
        />
      )}
      <ol className="flex-1 overflow-y-auto p-3 space-y-1 text-base leading-relaxed" aria-label="Passage">
        {sentences.map((sentence, index) => (
          <li key={`${index}-${sentence.text.slice(0, 12)}`}>
            <button type="button" onClick={() => seekTo(index)}
              className={clsx('text-left rounded px-1', synchronized && index === activeIndex && 'bg-yellow-200')}
              aria-current={synchronized && index === activeIndex ? 'true' : undefined}>
              {sentence.text}
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
