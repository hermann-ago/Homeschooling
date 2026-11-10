import { useEffect, useState } from 'react';
import { Button, Dialog } from '../../ui';

const LABELS = {
  first_try: 'right on the first try', again: 'right after another go', practise: 'to practise again',
  done: 'done', skipped: 'skipped for now', pending: 'still to do',
  checking: 'being checked', fix: 'something to fix', unchecked: 'not checked yet',
};
const MARK = { fix: '!', unchecked: '?' };
const short = (text) => { const line = (text || '').trim(); return line.length > 400 ? `${line.slice(0, 400)}…` : line; };

/** What a photo check found for one exercise, with the way to fix it. */
function CheckDetail({ item, number, canFix, busy, onFix, onRetry, onClose }) {
  const check = item.check || {};
  const fix = item.outcome === 'fix';
  const failed = item.outcome === 'unchecked';
  return <Dialog open title={`Exercise ${number} · ${LABELS[item.outcome]}`} onClose={onClose} width={520}
    footer={<div className="flex flex-wrap justify-end gap-2 w-full">
      <Button onClick={onClose}>{fix || failed ? 'Later' : 'Close'}</Button>
      {failed && onRetry && <Button disabled={busy} onClick={() => { onClose(); onRetry(item.id); }}>Try the check again</Button>}
      {(fix || failed) && onFix && <Button variant="primary" disabled={busy || !canFix} onClick={() => { onClose(); onFix(item.id); }}>{fix ? 'Fix it now' : 'Take the photo again'}</Button>}
    </div>}>
    <div className="flex flex-col gap-3 text-sm">
      {check.prompt && <p className="whitespace-pre-wrap font-semibold">{short(check.prompt)}</p>}
      {item.outcome === 'checking' && <p role="status" className="text-muted">Your photo is being checked. Keep going with the lesson.</p>}
      {check.read && <p className="rounded-xl bg-paper p-3"><span className="block text-xs text-muted">I read in your photo</span>{check.read}</p>}
      {check.feedback && <p className="whitespace-pre-wrap">{check.feedback}</p>}
      {failed && <p className="text-attention">{check.error || 'This photo could not be checked yet. Nothing was marked wrong.'}</p>}
      {(fix || failed) && !canFix && <p className="text-xs text-muted">Finish the answer you are fixing first.</p>}
    </div>
  </Dialog>;
}

/** One chip per exercise. A chip with a photo check opens what the check found. */
export function ProgressDots({ progress, currentId, canFix = true, busy = false, onFix, onRetry }) {
  const items = progress?.items || [];
  const greens = items.filter((i) => i.outcome === 'first_try').map((i) => i.id).join(',');
  // Dots that were already green when the lesson opened do not pop.
  const [shown, setShown] = useState(() => new Set(greens ? greens.split(',') : []));
  const [open, setOpen] = useState(null);
  const fresh = new Set(items.filter((i) => i.outcome === 'first_try' && !shown.has(i.id)).map((i) => i.id));
  useEffect(() => {
    if (!fresh.size) return undefined;
    const timer = setTimeout(() => setShown(new Set(greens.split(','))), 600);
    return () => clearTimeout(timer);
  }, [greens, fresh.size]);
  if (items.length < 2 && !items.some((i) => i.check)) return null;
  const toFix = items.filter((i) => ['fix', 'unchecked'].includes(i.outcome));
  const checking = items.filter((i) => i.outcome === 'checking').length;
  const opened = items.find((i) => i.id === open && i.check);
  return <div className="progress-tracker">
    <ol aria-label="Exercises in this lesson" className="progress-dots">
      {items.map((item, n) => <li key={item.id} className={`progress-dot is-${item.outcome}${item.id === currentId ? ' is-current' : ''}${fresh.has(item.id) ? ' is-new' : ''}`}
        title={`Exercise ${n + 1}: ${LABELS[item.outcome]}`}>
        {item.check ? <button type="button" onClick={() => setOpen(item.id)}><span aria-hidden="true">{MARK[item.outcome] || ''}</span><span className="sr-only">Exercise {n + 1}: {LABELS[item.outcome]}</span></button>
          : <span className="sr-only">Exercise {n + 1}: {LABELS[item.outcome]}</span>}
      </li>)}
    </ol>
    {(checking > 0 || toFix.length > 0) && <p className="progress-status" role="status">
      {checking > 0 && <span className="text-muted">Checking {checking} answer{checking === 1 ? '' : 's'}…</span>}
      {toFix.length > 0 && <button type="button" className="progress-fix" onClick={() => setOpen(toFix[0].id)}>{toFix.length} to look at</button>}
    </p>}
    {opened && <CheckDetail item={opened} number={items.indexOf(opened) + 1} canFix={canFix} busy={busy} onFix={onFix} onRetry={onRetry} onClose={() => setOpen(null)} />}
  </div>;
}

/** At the end of the lesson: the answers still to look at, each one tap from fixing. */
export function ToFix({ progress, checking, busy, onFix, onRetry }) {
  const items = (progress?.items || []).map((item, n) => ({ ...item, number: n + 1 })).filter((i) => ['fix', 'unchecked'].includes(i.outcome));
  if (!items.length && !checking) return null;
  return <section aria-label="Answers to look at" className="rounded-xl border border-line p-3 flex flex-col gap-2">
    <h2 className="font-semibold">{items.length ? 'Answers to look at' : 'Almost done'}</h2>
    {checking && <p role="status" className="text-sm text-muted">Your last photos are still being checked…</p>}
    {items.map((item) => <article key={item.id} className="rounded-xl bg-paper p-3 text-sm flex flex-col gap-1">
      <p className="font-semibold">Exercise {item.number}</p>
      <p className="whitespace-pre-wrap">{short(item.check?.prompt).split('\n').slice(0, 3).join('\n')}</p>
      {item.check?.read && <p className="text-muted">I read: {item.check.read}</p>}
      {item.outcome === 'fix' ? item.check?.feedback && <p>{item.check.feedback}</p> : <p className="text-attention">This photo could not be checked yet.</p>}
      <div className="flex flex-wrap gap-2 mt-1">
        <Button size="sm" variant="primary" disabled={busy} onClick={() => onFix(item.id)}>{item.outcome === 'fix' ? 'Fix it now' : 'Take the photo again'}</Button>
        {item.outcome === 'unchecked' && <Button size="sm" disabled={busy} onClick={() => onRetry(item.id)}>Try the check again</Button>}
      </div>
    </article>)}
    {items.length > 0 && <p className="text-xs text-muted">You can also finish now. Anything left here is saved for a grown-up as “to practise”.</p>}
  </section>;
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
