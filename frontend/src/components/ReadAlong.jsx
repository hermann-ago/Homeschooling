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
export default function ReadAlong({ passage, tracks, activeIndex, onActiveIndex, disabled, language = 'en-US' }) {
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
  const listRef = useRef(null);
  const pendingSeek = useRef(null);
  const speechIndex = useRef(0);
  const track = usable.find((t) => t.track_id === source);
  const synchronized = source === DEVICE || Boolean(track?.synchronized);

  const stopSpeech = useCallback(() => {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
  }, []);

  useEffect(() => () => stopSpeech(), [stopSpeech]);

  // Keep the sentence being read in view, so a child can follow without scrolling.
  useEffect(() => {
    listRef.current?.querySelector('[aria-current="true"]')?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' });
  }, [activeIndex]);

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
      utterance.lang = language;
      utterance.onstart = () => onActiveIndex(index); // the device reports when this sentence starts
      utterance.onend = () => {
        if (speechIndex.current === index) speakRef.current?.(index + 1);
      };
      utterance.onerror = () => setPlaying(false);
      window.speechSynthesis.speak(utterance);
      setPlaying(true);
    };
  }, [language, onActiveIndex, sentences, speed, stopSpeech]);

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

  // Sentences grouped into runs of the same kind, so a guided lesson's teacher parts stand apart.
  const runs = [];
  sentences.forEach((sentence, index) => {
    const kind = sentence.kind === 'teacher' ? 'teacher' : 'book';
    if (runs.length && runs[runs.length - 1].kind === kind) runs[runs.length - 1].items.push(index);
    else runs.push({ kind, items: [index] });
  });
  const sentenceButton = (index) => (
    <button key={`${index}-${sentences[index].text.slice(0, 12)}`} type="button" onClick={() => seekTo(index)}
      className={clsx('inline text-left rounded-[4px] px-0.5 -mx-0.5 hover:bg-paper-deep',
        synchronized && index === activeIndex && 'bg-[#F7DE8A] hover:bg-[#F7DE8A]')}
      aria-current={synchronized && index === activeIndex ? 'true' : undefined}>
      {sentences[index].text}
    </button>
  );

  const flow = (index) => <React.Fragment key={index}>{sentenceButton(index)}{' '}</React.Fragment>;

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="p-4 border-b border-line flex flex-col gap-3">
        <div className="flex items-center gap-3">
          <button type="button" onClick={toggle} disabled={disabled} aria-label={playing ? 'Pause' : 'Play'}
            className="w-14 h-14 shrink-0 rounded-full bg-action text-white grid place-items-center hover:bg-action-hover disabled:opacity-40">
            {playing ? <Pause className="w-6 h-6" fill="currentColor" /> : <Play className="w-6 h-6 translate-x-px" fill="currentColor" />}
          </button>
          <button type="button" onClick={replay} disabled={disabled} aria-label="Replay sentence" title="Replay sentence"
            className="w-11 h-11 shrink-0 rounded-xl border border-line bg-surface grid place-items-center hover:bg-paper disabled:opacity-40">
            <RotateCcw className="w-5 h-5" />
          </button>
          <label className="flex-1 min-w-0 flex flex-col gap-0.5 text-xs font-semibold text-muted">Voice
            <select value={source} onChange={(e) => setSource(e.target.value)}
              className="h-9 px-2 rounded-lg border border-line bg-surface text-sm font-normal text-ink w-full">
              {usable.map((t) => (
                <option key={t.track_id} value={t.track_id}>{t.voice || t.provider}{t.synchronized ? '' : ' (no highlighting)'}</option>
              ))}
              <option value={DEVICE}>Device voice</option>
            </select>
          </label>
        </div>
        <div role="group" aria-label="Speed" className="flex gap-1">
          {SPEEDS.map((s) => (
            <button key={s} type="button" aria-pressed={speed === s} onClick={() => setSpeed(s)}
              className={clsx('flex-1 h-8 rounded-full text-[13px] font-semibold',
                speed === s ? 'bg-ink text-white' : 'border border-line bg-surface hover:bg-paper')}>
              {s}×
            </button>
          ))}
        </div>
        {!synchronized && (
          <p className="text-[13px] text-attention">This recording has no verified timings for this passage, so sentences are not highlighted.</p>
        )}
        {error && <p className="text-[13px] text-problem">{error}</p>}
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
      <div ref={listRef} className="flex-1 overflow-y-auto p-4 flex flex-col gap-3 text-[17px] leading-relaxed" aria-label="Passage">
        {runs.map((run) => (run.kind === 'teacher' ? (
          <div key={run.items[0]} className="rounded-xl bg-action-soft/70 px-3.5 py-2.5 text-[16px]">
            <span className="block mb-0.5 text-[11px] font-bold tracking-[0.8px] uppercase text-action">Teacher</span>
            <span className="block">{run.items.map(flow)}</span>
          </div>
        ) : (
          <p key={run.items[0]} className="m-0">{run.items.map(flow)}</p>
        )))}
      </div>
    </div>
  );
}
