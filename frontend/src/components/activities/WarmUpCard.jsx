import { useEffect, useRef, useState } from 'react';
import { tutorApi } from '../../api/tutor';
import { Button } from '../../ui';

/**
 * Before a lesson: where it sits (last time, today, next) and the tutor's
 * closing words from the last finished lesson, with their saved recording.
 * Nothing to answer; Start lesson stays the next step.
 */
export default function WarmUpCard({ warmUp }) {
  const [playing, setPlaying] = useState(false);
  const [problem, setProblem] = useState('');
  const audio = useRef(null);
  useEffect(() => () => { audio.current?.pause(); if (audio.current?.src) URL.revokeObjectURL(audio.current.src); }, []);
  if (!warmUp || (!warmUp.last && !warmUp.next)) return null;
  const { last, today, next } = warmUp;
  const listen = async () => {
    setProblem('');
    if (playing) { audio.current?.pause(); setPlaying(false); return; }
    try {
      if (!audio.current) {
        audio.current = new Audio(await tutorApi.audioPart(last.audio.track_id, last.audio.part));
        audio.current.onended = () => setPlaying(false);
      }
      await audio.current.play();
      setPlaying(true);
    } catch { setProblem('The recording could not play. You can read the reminder instead.'); }
  };
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
      {last.audio && <Button size="sm" variant="quiet" className="self-start" onClick={listen}>{playing ? 'Pause' : '▶ Listen'}</Button>}
      {problem && <p role="status" className="text-xs text-attention">{problem}</p>}
    </>}
  </section>;
}
