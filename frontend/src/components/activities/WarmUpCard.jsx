import { useCallback, useEffect, useRef, useState } from 'react';
import { tutorApi } from '../../api/tutor';
import { Button } from '../../ui';
import { beginNarration, registerNarrator } from '../../utils/narration';
import { useSpaceBar } from '../../utils/spaceBar';

/**
 * Before a lesson: where it sits (last time, today, next) and the tutor's
 * closing words from the last finished lesson, with their saved recording.
 * Nothing to answer. The recording starts by itself when the browser allows
 * it; Space pauses and resumes it, and when it ends Start lesson takes over.
 */
export default function WarmUpCard({ warmUp, onFinished }) {
  const [playing, setPlaying] = useState(false);
  const [problem, setProblem] = useState('');
  const audio = useRef(null);
  const ended = useRef(false);
  const loading = useRef(false);
  const narrator = useRef(Symbol('warm-up'));
  const finished = useRef(onFinished);
  useEffect(() => { finished.current = onFinished; }, [onFinished]);
  const recording = warmUp?.last?.summary && warmUp.last.audio;
  useEffect(() => registerNarrator(narrator.current, () => { audio.current?.pause(); setPlaying(false); }), []);
  useEffect(() => () => { audio.current?.pause(); if (audio.current?.src) URL.revokeObjectURL(audio.current.src); }, []);
  const listen = useCallback(async ({ quiet = false } = {}) => {
    setProblem('');
    if (loading.current) return;
    if (audio.current && !audio.current.paused) { audio.current.pause(); setPlaying(false); return; }
    try {
      if (!audio.current) {
        loading.current = true;
        try { audio.current = new Audio(await tutorApi.audioPart(recording.track_id, recording.part)); }
        finally { loading.current = false; }
        audio.current.onended = () => { setPlaying(false); ended.current = true; finished.current?.(); };
      }
      ended.current = false;
      beginNarration(narrator.current);
      await audio.current.play();
      setPlaying(true);
    } catch (failure) {
      // A browser that blocks sound before a tap still lets Space or Listen start it.
      if (!quiet || failure?.name !== 'NotAllowedError') setProblem('The recording could not play. You can read the reminder instead.');
    }
  }, [recording]);
  useEffect(() => { if (recording) void listen({ quiet: true }); }, [recording, listen]);
  useSpaceBar(() => {
    if (!recording || ended.current) return false;
    void listen();
    return true;
  });
  if (!warmUp || (!warmUp.last && !warmUp.next)) return null;
  const { last, today, next } = warmUp;
  return <section aria-label="Before you start" className="rounded-xl border border-line bg-paper/40 p-3 flex flex-col gap-2">
    <ol aria-label="Where you are" className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
      {last && <li><span className="font-semibold">Last time:</span> {last.title}</li>}
      {last && <li aria-hidden="true">→</li>}
      <li className="text-ink"><span className="font-semibold">Today:</span> {today}</li>
      {next && <li aria-hidden="true">→</li>}
      {next && <li><span className="font-semibold">Next:</span> {next}</li>}
    </ol>
    {last?.summary && <>
      <p className="text-sm font-semibold">Last time</p>
      <p className="text-sm whitespace-pre-line">{last.summary}</p>
      {last.audio && <Button size="sm" variant="quiet" className="self-start" onClick={() => listen()}>{playing ? 'Pause' : '▶ Listen'}</Button>}
      {problem && <p role="status" className="text-xs text-attention">{problem}</p>}
    </>}
  </section>;
}
