import React, { useCallback, useEffect, useRef, useState } from 'react';
import clsx from 'clsx';
import { Pause, Play, RotateCcw, VolumeX } from 'lucide-react';
import { tutorApi } from '../api/tutor';
import { partForSentence, sentenceAt } from '../utils/readAlong';
import { beginNarration, isNarrating, registerNarrator } from '../utils/narration';
import { NARRATION_SPEEDS, narrationVoiceLabel } from '../utils/narrationSettings';

const DEVICE = 'device';

/**
 * Read-along narration. Highlighting follows only real timing information:
 * provider timepoints saved with a track, or the device voice's own
 * per-sentence events. Tracks without verified timings play without
 * highlighting and say so.
 */
export default function ReadAlong({ passage, tracks, activeIndex, onActiveIndex, disabled, language = 'en-US',
  onAction, onReadingEnd, pendingActions = [], renderAction, resumeToken = 0, maxSeekIndex, onPassageModeChange,
  rangeStart = 0, rangeEnd, visibleThrough, savedCursor, onCursorChange, voiceSetup,
  externalControls = false, headless = false, autoPlayRequest = 0, onTransport,
  settingsInHeader = false, selectedSource, selectedSpeed, bookOnPage = false }) {
  const sentences = passage?.sentences || [];
  const lastSentence = Math.min(rangeEnd ?? sentences.length - 1, sentences.length - 1);
  const resumableCursor = savedCursor && Number.isInteger(savedCursor.sentence_index) &&
    savedCursor.sentence_index >= rangeStart && savedCursor.sentence_index <= lastSentence ? savedCursor : null;
  const usable = (tracks || []).filter((t) => t.status === 'ready' || t.status === 'legacy');
  const [source, setSource] = useState(() => selectedSource || (resumableCursor?.track_id === DEVICE || usable.some((t) => t.track_id === resumableCursor?.track_id) ? resumableCursor.track_id : null) || usable.find((t) => t.preferred && t.synchronized)?.track_id || usable.find((t) => t.synchronized)?.track_id || usable[0]?.track_id || DEVICE);
  const narratorChosen = useRef(Boolean(resumableCursor && (resumableCursor.track_id !== DEVICE || usable.length > 0)));
  const playbackStarted = useRef(false);
  const [manifest, setManifest] = useState(null);
  const [partIndex, setPartIndex] = useState(0);
  const [partUrl, setPartUrl] = useState(null);
  const [playing, setPlaying] = useState(false);
  // The range was read to its end; the next step can take over.
  const [ended, setEnded] = useState(false);
  // The book's own words are followed on the highlighted page; the panel keeps the teacher's.
  const [showBookText, setShowBookText] = useState(false);
  const followBook = bookOnPage && !showBookText;
  const preferredSource = usable.find((t) => t.preferred && t.synchronized)?.track_id;
  useEffect(() => {
    if (playing) playbackStarted.current = true;
    if (!selectedSource && preferredSource && !narratorChosen.current && !playbackStarted.current) setSource(preferredSource);
  }, [preferredSource, playing, selectedSource]);
  const [speed, setSpeed] = useState(selectedSpeed ?? 1);
  useEffect(() => {
    if (selectedSource && selectedSource !== source) { narratorChosen.current = true; setSource(selectedSource); }
  }, [selectedSource, source]);
  useEffect(() => { if (NARRATION_SPEEDS.includes(selectedSpeed)) setSpeed(selectedSpeed); }, [selectedSpeed]);
  const [error, setError] = useState('');
  const reportPlaybackError = useCallback((e) => {
    // Quickly pausing or seeking can cancel a pending play promise normally.
    if (e.name !== 'AbortError') setError(e.message);
  }, []);
  const audioRef = useRef(null);
  const toggleRef = useRef(null);
  const replayRef = useRef(null);
  const autoplayed = useRef(0);
  const latestAutoplay = useRef(autoPlayRequest);
  latestAutoplay.current = autoPlayRequest;
  const listRef = useRef(null);
  const pendingSeek = useRef(null);
  const speechIndex = useRef(0);
  const narratorId = useRef(Symbol('read-along'));
  const cursorCallback = useRef(onCursorChange);
  const cursorRef = useRef(resumableCursor);
  const restoredCursor = useRef(false);
  const rangeEnded = useRef(false);
  useEffect(() => { cursorCallback.current = onCursorChange; }, [onCursorChange]);
  const reportCursor = useCallback((cursor) => {
    cursorRef.current = cursor;
    cursorCallback.current?.(cursor);
  }, []);
  const track = usable.find((t) => t.track_id === source);
  const fallbackParts=track?.fallback_parts||0;
  const [stoppedAction, setStoppedAction] = useState(null);
  useEffect(() => {
    if (stoppedAction && !pendingActions.includes(stoppedAction)) setStoppedAction(null);
  }, [pendingActions, stoppedAction]);
  const synchronized = source === DEVICE || Boolean(track?.synchronized);
  const passageMode = source !== DEVICE && manifest?.timing === 'passage' && !manifest?.tracks?.[partIndex]?.fallback;
  useEffect(() => {
    onPassageModeChange?.(passageMode);
    return () => onPassageModeChange?.(false);
  }, [passageMode, onPassageModeChange]);

  const stopSpeech = useCallback(() => {
    speechIndex.current = -1;
    if (isNarrating(narratorId.current)) window.speechSynthesis?.cancel();
  }, []);
  useEffect(() => registerNarrator(narratorId.current, () => {
    autoplayed.current = latestAutoplay.current;
    if (pendingSeek.current) pendingSeek.current.play = false;
    audioRef.current?.pause();
    stopSpeech();
    setPlaying(false);
    if (cursorRef.current) cursorCallback.current?.(cursorRef.current);
  }), [stopSpeech]);
  const stopAtAction = useCallback((actionId, index) => {
    audioRef.current?.pause();
    speechIndex.current = -1;
    stopSpeech();
    setPlaying(false);
    setStoppedAction(actionId);
    onActiveIndex(index - 1);
    onAction?.(actionId, index);
  }, [onAction, onActiveIndex, stopSpeech]);

  useEffect(() => () => stopSpeech(), [stopSpeech]);

  // Keep the sentence being read in view, so a child can follow without scrolling.
  useEffect(() => {
    listRef.current?.querySelector('[aria-current="true"]')?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' });
  }, [activeIndex]);

  useEffect(() => {
    let active = true;
    audioRef.current?.pause();
    setManifest(null);
    setPartUrl(null);
    setPartIndex(0);
    restoredCursor.current = false;
    setPlaying(false);
    stopSpeech();
    if (source !== DEVICE) tutorApi.audioManifest(source).then((next) => { if (active) setManifest(next); }).catch((e) => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [source, stopSpeech, fallbackParts]);

  useEffect(() => {
    if (!manifest || restoredCursor.current) return;
    restoredCursor.current = true;
    const saved = resumableCursor?.track_id === source ? resumableCursor : null;
    const target = saved ? saved.part_index : partForSentence(manifest.tracks || [], rangeStart);
    if (target >= 0 && target < (manifest.tracks?.length || 0)) {
      pendingSeek.current = { time: saved?.offset_seconds || 0, play: false };
      setPartIndex(target);
    }
  }, [manifest, source, resumableCursor, rangeStart]);

  useEffect(() => {
    if (!manifest) return undefined;
    if (manifest.tracks?.[partIndex]?.fallback) { setPartUrl(null); return undefined; }
    let url = null;
    let active = true;
    tutorApi.audioPart(source, partIndex).then((next) => {
      url = next;
      if (active) setPartUrl(next);
      else { URL.revokeObjectURL(next); url = null; }
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

  const parts = manifest?.tracks || [];
  // A legacy passage with no sentence timings cannot stop truthfully inside
  // its audio. Refuse to play across a pending activity; offer device voice.
  const unsafePassages = synchronized && manifest?.timing === 'passage' && parts.some((part) => {
    if (part.fallback) return false;
    const end = part.startSentence + part.sentenceCount - 1;
    if (end >= rangeStart && part.startSentence <= lastSentence &&
        (part.startSentence < rangeStart || end > lastSentence)) return true;
    return sentences.slice(part.startSentence, part.startSentence + part.sentenceCount - 1)
      .some((s) => pendingActions.includes(s.pause_after));
  });
  const held = disabled || Boolean(stoppedAction && pendingActions.includes(stoppedAction));
  const activePart = passageMode ? parts.find((p) => activeIndex !== null && activeIndex >= p.startSentence && activeIndex < p.startSentence + p.sentenceCount) : null;

  const speakRef = useRef(null);
  const resumeRef = useRef(null);
  const endRef = useRef(onReadingEnd);
  useEffect(() => { endRef.current = onReadingEnd; }, [onReadingEnd]);
  const speakFrom = useCallback((index) => speakRef.current?.(index), []);
  const finishRange = useCallback(() => {
    audioRef.current?.pause();
    stopSpeech();
    setPlaying(false);
    setEnded(true);
    if (!rangeEnded.current) { rangeEnded.current = true; endRef.current?.(); }
  }, [stopSpeech]);
  useEffect(() => {
    speakRef.current = (index) => {
      stopSpeech();
      if (!window.speechSynthesis || index > lastSentence) {
        setPlaying(false);
        if (index > lastSentence) finishRange();
        return;
      }
      index = Math.max(rangeStart, index);
      speechIndex.current = index;
      const utterance = new SpeechSynthesisUtterance(sentences[index].text);
      utterance.rate = speed;
      utterance.lang = language;
      const voices = window.speechSynthesis.getVoices?.() || [];
      utterance.voice = voices.find((v) => v.lang.toLowerCase() === language.toLowerCase()) || voices.find((v) => v.lang.slice(0, 2) === language.slice(0, 2)) || null;
      utterance.onstart = () => {
        setEnded(false);
        onActiveIndex(index);
        reportCursor({ track_id: source, part_index: source === DEVICE ? 0 : partIndex, offset_seconds: 0, sentence_index: index });
      }; // the device reports when this sentence starts
      utterance.onend = () => {
        if (speechIndex.current !== index) return;
        const actionId = sentences[index].pause_after;
        if (onAction && actionId && pendingActions.includes(actionId)) {
          stopAtAction(actionId, index + 1);
        } else if (index >= lastSentence) finishRange();
        else if (source !== DEVICE && parts[partIndex]?.fallback && index + 1 >= parts[partIndex].startSentence + parts[partIndex].sentenceCount) {
          if (partIndex + 1 < parts.length) {
            pendingSeek.current = { time: 0, play: true };
            setPlaying(true); setPartIndex(partIndex + 1);
          }
          else { setPlaying(false); setEnded(true); endRef.current?.(); }
        } else speakRef.current?.(index + 1);
      };
      utterance.onerror = () => setPlaying(false);
      window.speechSynthesis.speak(utterance);
      setPlaying(true);
    };
  }, [language, onActiveIndex, sentences, speed, stopSpeech, onAction, pendingActions, source, manifest, partIndex, stopAtAction, rangeStart, lastSentence, finishRange, reportCursor]);

  useEffect(() => {
    const part = manifest?.tracks?.[partIndex];
    if (!part?.fallback || source === DEVICE) return;
    if (externalControls) {
      pendingSeek.current = null;
      setPlaying(false);
      const saved = cursorRef.current;
      const index = saved?.track_id === source && saved.part_index === partIndex && saved.sentence_index >= part.startSentence && saved.sentence_index < part.startSentence + part.sentenceCount
        ? saved.sentence_index : part.startSentence;
      onActiveIndex(index);
      reportCursor({ track_id: source, part_index: partIndex, offset_seconds: 0, sentence_index: index });
      return;
    }
    const start = pendingSeek.current;
    pendingSeek.current = null;
    if ((start?.play || playing) && !disabled) speakFrom(part.startSentence);
  }, [manifest, partIndex, source]);

  const seekTo = (index, shouldPlay = playing, continued = false) => {
    if (disabled || held && !continued || unsafePassages) return;
    if (continued) setStoppedAction(null);
    index = Math.max(rangeStart, index);
    if (maxSeekIndex !== undefined) index = Math.min(index, maxSeekIndex);
    if (index > lastSentence) {
      finishRange();
      return;
    }
    rangeEnded.current = false;
    if (shouldPlay) beginNarration(narratorId.current);
    onActiveIndex(index);
    if (source === DEVICE) {
      if (shouldPlay) speakFrom(index);
      return;
    }
    if (!synchronized || !parts.length) return;
    const target = partForSentence(parts, index);
    if (target < 0) return;
    if (parts[target].fallback) {
      audioRef.current?.pause();
      if (target !== partIndex) { pendingSeek.current = { time: 0, play: shouldPlay }; setPartIndex(target); }
      else if (shouldPlay) speakFrom(index);
      return;
    }
    stopSpeech();
    const targetPassageMode = parts[target].timing === 'passage' || manifest.timing === 'passage';
    const time = targetPassageMode ? 0 : parts[target].sentenceStarts[index - parts[target].startSentence];
    if (targetPassageMode) onActiveIndex(parts[target].startSentence);
    if (target !== partIndex) {
      pendingSeek.current = { time, play: shouldPlay };
      setPartIndex(target);
    } else if (audioRef.current) {
      audioRef.current.currentTime = time;
      if (shouldPlay) audioRef.current.play().catch(reportPlaybackError);
    }
  };

  const toggle = () => {
    setError('');
    if (disabled || held || unsafePassages) return;
    if (!playing) beginNarration(narratorId.current);
    if (source === DEVICE || parts[partIndex]?.fallback) {
      if (playing) {
        speechIndex.current = -1;
        stopSpeech();
        setPlaying(false);
      } else {
        rangeEnded.current = false;
        speakFrom(Math.max(rangeStart, activeIndex ?? rangeStart));
      }
      return;
    }
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused && !synchronized) audio.play().catch(reportPlaybackError);
    else if (audio.paused && cursorRef.current?.track_id === source && cursorRef.current?.part_index === partIndex && audio.currentTime > 0) audio.play().catch(reportPlaybackError);
    else if (audio.paused) seekTo(activeIndex ?? rangeStart, true);
    else audio.pause();
  };
  toggleRef.current = toggle;
  const recordedPart = source !== DEVICE && Boolean(partUrl) && !parts[partIndex]?.fallback;
  const unrecordedPart = source !== DEVICE && Boolean(parts[partIndex]?.fallback);
  const deviceAvailable = (source === DEVICE || unrecordedPart) && Boolean(window.speechSynthesis && typeof SpeechSynthesisUtterance !== 'undefined');
  useEffect(() => {
    onTransport?.({ playing, ended, recorded: recordedPart, unrecorded: unrecordedPart, error, available: (recordedPart || deviceAvailable) && !held && !unsafePassages, toggle: () => toggleRef.current?.(), replay: () => replayRef.current?.() });
  }, [onTransport, playing, ended, recordedPart, unrecordedPart, deviceAvailable, held, unsafePassages, error]);
  useEffect(() => {
    if (!autoPlayRequest || autoplayed.current === autoPlayRequest || !recordedPart || held || unsafePassages) return;
    autoplayed.current = autoPlayRequest;
    beginNarration(narratorId.current);
    if (audioRef.current?.readyState >= 1) toggleRef.current?.();
    else pendingSeek.current = { time: pendingSeek.current?.time ?? cursorRef.current?.offset_seconds ?? 0, play: true };
  }, [autoPlayRequest, recordedPart, held, unsafePassages]);

  const replay = () => seekTo(activeIndex ?? 0);
  replayRef.current = replay;
  useEffect(() => { resumeRef.current = () => seekTo(activeIndex ?? 0, true, true); });
  useEffect(() => {
    if (resumeToken > 0 && !disabled) resumeRef.current?.();
  }, [resumeToken]);

  // Sentences grouped into runs of the same kind, so a guided lesson's teacher parts stand apart.
  const runs = [];
  sentences.forEach((sentence, index) => {
    if (index < rangeStart || index > lastSentence || (visibleThrough !== undefined && index > visibleThrough)) return;
    const kind = sentence.kind === 'teacher' ? 'teacher' : 'book';
      const paragraph = sentence.paragraphIndex ?? null;
      if (runs.length && runs[runs.length - 1].kind === kind && runs[runs.length - 1].paragraph === paragraph && !sentences[index - 1]?.pause_after) runs[runs.length - 1].items.push(index);
      else runs.push({ kind, paragraph, items: [index] });
  });
  const sentenceButton = (index) => (
      <span key={`${index}-${sentences[index].text.slice(0, 12)}`} role="button" tabIndex={disabled ? -1 : 0} aria-disabled={disabled || undefined}
        onClick={() => { if (!disabled) seekTo(index); }}
        onKeyDown={(event) => { if (!disabled && ['Enter', ' '].includes(event.key)) { event.preventDefault(); seekTo(index); } }}
        className={clsx('inline text-left rounded-[4px] px-0.5 -mx-0.5 hover:bg-paper-deep focus-visible:outline-2 focus-visible:outline-action',
        synchronized && (passageMode ? activePart && index >= activePart.startSentence && index < activePart.startSentence + activePart.sentenceCount : index === activeIndex) && 'bg-[#F7DE8A] hover:bg-[#F7DE8A]')}
      aria-current={synchronized && (passageMode ? activePart && index >= activePart.startSentence && index < activePart.startSentence + activePart.sentenceCount : index === activeIndex) ? 'true' : undefined}>
      {sentences[index].text}
      </span>
  );

  const flow = (index) => <React.Fragment key={index}>{sentenceButton(index)}{' '}</React.Fragment>;

  return (
    <div className="flex flex-col" style={headless ? { display: 'none' } : undefined}>
      {!settingsInHeader && <div className="p-4 border-b border-line flex flex-col gap-3">
        <div className="flex items-center gap-3">
          {!externalControls && <button type="button" onClick={toggle} disabled={held || unsafePassages} aria-label={playing ? 'Pause' : 'Play'}
            className="w-14 h-14 shrink-0 rounded-full bg-action text-white grid place-items-center hover:bg-action-hover disabled:opacity-40">
            {playing ? <Pause className="w-6 h-6" fill="currentColor" /> : <Play className="w-6 h-6 translate-x-px" fill="currentColor" />}
          </button>}
          <button type="button" onClick={replay} disabled={held || unsafePassages} aria-label={passageMode ? 'Replay passage' : 'Replay sentence'} title={passageMode ? 'Replay passage' : 'Replay sentence'}
            className="w-11 h-11 shrink-0 rounded-xl border border-line bg-surface grid place-items-center hover:bg-paper disabled:opacity-40">
            <RotateCcw className="w-5 h-5" />
          </button>
          <label className="flex-1 min-w-0 flex flex-col gap-0.5 text-xs font-semibold text-muted">Voice
            <select value={source} onChange={(e) => { narratorChosen.current = true; setSource(e.target.value); }}
              className="h-9 px-2 rounded-lg border border-line bg-surface text-sm font-normal text-ink w-full">
              {usable.map((t) => (
                <option key={t.track_id} value={t.track_id}>{narrationVoiceLabel(t, externalControls)}</option>
              ))}
              <option value={DEVICE}>Device voice</option>
            </select>
          </label>
        </div>
        <div role="group" aria-label="Speed" className="flex gap-1">
          {NARRATION_SPEEDS.map((s) => (
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
        {passageMode && <p className="text-[13px] text-muted">The passage being read is highlighted. Saved playback resumes at its last position; replay begins at the passage boundary.</p>}
        {unsafePassages && <p role="alert" className="text-[13px] text-attention">{externalControls ? 'This recording crosses a step boundary. This step stays text-only.' : 'This older recording crosses a student activity without timing information. Choose Device voice to stop at each question, or prepare a new recording.'}</p>}
        {stoppedAction && pendingActions.includes(stoppedAction) && !disabled && <button type="button" className="text-sm font-semibold text-action underline" onClick={() => stopAtAction(stoppedAction, sentences.findIndex((s) => s.pause_after === stoppedAction) + 1)}>Open paused activity</button>}
        {source !== DEVICE && <p className="text-xs text-muted">AI-generated voice · saved recording</p>}
        {manifest?.fallback_parts > 0 && <p className="text-xs text-attention">{externalControls ? 'Some passages have no saved recording and stay text-only. You can choose Device voice to listen to them.' : 'Some passages use device voice because Google declined them. Their original wording is preserved.'}</p>}
        {error && <p className="text-[13px] text-problem">{error}</p>}
        {usable.length === 0 && voiceSetup && <div className="text-xs text-muted">
          <p>This guided lesson has no saved voice recording yet.</p>
          <details className="mt-2"><summary className="cursor-pointer font-semibold text-action">Prepare a recorded voice</summary><div className="mt-2">{voiceSetup}</div></details>
        </div>}
      </div>}
      {partUrl && source !== DEVICE && (
        <audio
          ref={audioRef}
          src={partUrl}
          onLoadedMetadata={(e) => {
            e.currentTarget.playbackRate = speed;
            if (pendingSeek.current !== null) {
              const pending = pendingSeek.current;
              e.currentTarget.currentTime = pending.time;
              pendingSeek.current = null;
              if (pending.play && !held && !unsafePassages) e.currentTarget.play().catch(reportPlaybackError);
            } else if (playing && !held && !unsafePassages) {
              e.currentTarget.play().catch(() => {});
            }
          }}
          onPlay={() => { beginNarration(narratorId.current); setPlaying(true); setEnded(false); if (passageMode && parts[partIndex]) onActiveIndex(parts[partIndex].startSentence); }}
          onPause={() => { setPlaying(false); if (cursorRef.current) cursorCallback.current?.(cursorRef.current); }}
          onTimeUpdate={(e) => {
            reportCursor({ track_id: source, part_index: partIndex, offset_seconds: e.currentTarget.currentTime,
              sentence_index: Math.max(rangeStart, activeIndex ?? rangeStart) });
            if (!synchronized) return;
            const part = parts[partIndex];
            if (part?.sentenceStarts && lastSentence + 1 >= part.startSentence && lastSentence + 1 < part.startSentence + part.sentenceStarts.length &&
                e.currentTarget.currentTime >= part.sentenceStarts[lastSentence + 1 - part.startSentence]) { finishRange(); return; }
            if (manifest.timing !== 'passage' && part?.sentenceStarts) {
              const boundary = sentences.findIndex((s, i) => i >= part.startSentence && i < part.startSentence + part.sentenceStarts.length &&
                pendingActions.includes(s.pause_after) && i + 1 < part.startSentence + part.sentenceStarts.length &&
                e.currentTarget.currentTime >= part.sentenceStarts[i + 1 - part.startSentence]);
              if (boundary >= 0 && !stoppedAction) { stopAtAction(sentences[boundary].pause_after, boundary + 1); return; }
            }
            const index = sentenceAt(parts[partIndex], e.currentTarget.currentTime);
            if (index !== null && index > lastSentence) { finishRange(); return; }
            if (index !== null && index !== activeIndex) onActiveIndex(index);
          }}
          onEnded={() => {
            if (stoppedAction && pendingActions.includes(stoppedAction)) return;
            const part = parts[partIndex];
            const last = part ? part.startSentence + (passageMode ? part.sentenceCount : part.sentenceStarts?.length || 0) - 1 : null;
            const actionId = last !== null ? sentences[last]?.pause_after : null;
            if (onAction && actionId && pendingActions.includes(actionId)) {
              stopAtAction(actionId, last + 1);
              return;
            }
            if (last !== null && last >= lastSentence) { finishRange(); return; }
            const count = manifest?.tracks?.length || 0;
            if (partIndex + 1 < count) {
              // Loading another media source can emit pause before metadata.
              // Preserve continuation independently of that temporary event.
              pendingSeek.current = { time: 0, play: true };
              setPlaying(true);
              setPartIndex(partIndex + 1);
            } else {
              setPlaying(false);
              setEnded(true);
              endRef.current?.();
            }
          }}
        />
      )}
      <div ref={listRef} className="p-4 flex flex-col gap-3 text-[17px] leading-relaxed" aria-label="Passage">
        {unrecordedPart && <div role="status" className="sticky top-0 z-10 flex items-start gap-2 rounded-xl border border-attention/30 bg-[#fff7e8] px-3 py-2.5 text-sm">
          <VolumeX aria-hidden="true" size={18} className="mt-0.5 shrink-0 text-attention" />
          <div><p className="font-semibold">No recorded audio for this passage</p>
            <p className="mt-0.5 text-muted">Read this part yourself, or use device voice.</p></div>
        </div>}
        {bookOnPage && runs.some((run) => run.kind === 'book') && <p className="book-follow-note">
          <span>{followBook ? 'Follow the highlighted lines in the book.' : 'The book text is also highlighted on the page.'}</span>
          <button type="button" onClick={() => setShowBookText((shown) => !shown)}>{followBook ? 'Show the text here' : 'Hide the text here'}</button>
        </p>}
        {runs.filter((run) => !(followBook && run.kind === 'book')).map((run) => (run.kind === 'teacher' ? (
          <div key={run.items[0]} className="teacher-note text-[16px]">
            <span className="teacher-note-label">Teacher</span>
            <p className="m-0">{run.items.map(flow)}</p>
            {sentences[run.items.at(-1)]?.pause_after && renderAction?.(sentences[run.items.at(-1)].pause_after)}
          </div>
        ) : (
          <p key={run.items[0]} className="m-0">{run.items.map(flow)}</p>
        )))}
      </div>
    </div>
  );
}
