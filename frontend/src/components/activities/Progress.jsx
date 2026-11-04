import { useEffect, useState } from 'react';

const LABELS = {
  first_try: 'right on the first try', again: 'right after another go', practise: 'to practise again',
  done: 'done', skipped: 'skipped for now', pending: 'still to do',
};

/** One dot per exercise; a dot pops when it turns green. */
export function ProgressDots({ progress, currentId }) {
  const items = progress?.items || [];
  const greens = items.filter((i) => i.outcome === 'first_try').map((i) => i.id).join(',');
  // Dots that were already green when the lesson opened do not pop.
  const [shown, setShown] = useState(() => new Set(greens ? greens.split(',') : []));
  const fresh = new Set(items.filter((i) => i.outcome === 'first_try' && !shown.has(i.id)).map((i) => i.id));
  useEffect(() => {
    if (!fresh.size) return undefined;
    const timer = setTimeout(() => setShown(new Set(greens.split(','))), 600);
    return () => clearTimeout(timer);
  }, [greens, fresh.size]);
  if (items.length < 2) return null;
  return <ol aria-label="Exercises in this lesson" className="progress-dots">
    {items.map((item, n) => <li key={item.id} className={`progress-dot is-${item.outcome}${item.id === currentId ? ' is-current' : ''}${fresh.has(item.id) ? ' is-new' : ''}`}
      title={`Exercise ${n + 1}: ${LABELS[item.outcome]}`}><span className="sr-only">Exercise {n + 1}: {LABELS[item.outcome]}</span></li>)}
  </ol>;
}

/** The end of a lesson: what went well and what to practise, with a few stars. */
export function Celebration({ progress }) {
  if (!progress) return null;
  const { first_try: right = 0, graded = 0, practise = [] } = progress;
  const headline = !graded ? 'You finished today’s lesson!'
    : right === graded ? `Every answer right on the first try! ${graded} of ${graded}`
    : `${right} of ${graded} right on the first try`;
  return <section aria-label="Well done" className="celebration rounded-2xl bg-action-soft p-4 flex flex-col gap-2 text-center">
    <div className="celebration-stars" aria-hidden="true">{[...'★★★★★'].map((star, i) => <span key={i} style={{ '--i': i }}>{star}</span>)}</div>
    <p className="text-lg font-semibold">{headline}</p>
    {practise.length > 0 && <div className="text-sm text-left"><p className="font-semibold">Next time, practise:</p>
      <ul className="list-disc pl-5">{practise.map((prompt, i) => <li key={i}>{(prompt || '').split('\n')[0].slice(0, 120)}</li>)}</ul></div>}
  </section>;
}
