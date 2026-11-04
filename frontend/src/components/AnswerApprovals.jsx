import {useState} from 'react';
import {useQueryClient} from '@tanstack/react-query';
import {tutorApi} from '../api/tutor';
import {Button} from '../ui';
import {inputClasses} from '../ui/classes';

/**
 * Answer boxes the book's key does not cover: the lesson writer proposed an
 * answer for each box; once a grown-up approves (or corrects) them, the
 * child's answers are checked instantly. Teacher only.
 */
export default function AnswerApprovals({guideId, entries}) {
  const client = useQueryClient();
  const [values, setValues] = useState(() => Object.fromEntries(entries.map((e) =>
    [e.index, e.blanks.map((_, i) => (e.approved_answers || e.proposed_answers)[i] || '')])));
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');
  const ready = (e) => values[e.index].every((v) => v.trim());
  const run = async (work) => {
    setBusy(true); setProblem('');
    try { await work(); await client.invalidateQueries({queryKey: ['script-review', guideId]}); }
    catch (e) { setProblem(e.message); } finally { setBusy(false); }
  };
  const approve = (list) => run(() => Promise.all(list.map((e) => tutorApi.approveAnswers(guideId, e.index, values[e.index]))));
  const waiting = entries.filter((e) => !e.approved_answers && ready(e));
  return <details className="mt-3 border-t border-line pt-2" open={entries.some((e) => !e.approved_answers) || undefined}>
    <summary className="cursor-pointer font-semibold">Answers to approve (no answer key)</summary>
    <p className="text-xs text-muted mt-1">The book has no key for these boxes. Check the expected answers and correct any. Once approved, your child's answers are checked instantly; until then the tutor checks them.</p>
    <ol className="mt-2 flex flex-col gap-3">
      {entries.map((e) => <li key={e.index} className="flex flex-col gap-2">
        <p className="whitespace-pre-line text-muted">{e.prompt}</p>
        {e.blanks.map((label, i) => <label key={i} className="flex flex-col gap-1">
          <span>{label}</span>
          <input className={`${inputClasses} w-full`} value={values[e.index][i]} disabled={busy} aria-label={`Expected answer for ${label}`}
            onChange={(event) => setValues((all) => ({...all, [e.index]: all[e.index].map((v, j) => j === i ? event.target.value : v)}))} />
        </label>)}
        <div className="flex items-center gap-2">
          {e.approved_answers
            ? <><span className="text-saved font-semibold">Approved ✓</span>
                <Button size="sm" disabled={busy || !ready(e)} onClick={() => approve([e])}>Save changes</Button>
                <Button size="sm" variant="quiet" disabled={busy} onClick={() => run(() => tutorApi.withdrawAnswers(guideId, e.index))}>Withdraw</Button></>
            : <Button size="sm" disabled={busy || !ready(e)} onClick={() => approve([e])}>Approve</Button>}
        </div>
      </li>)}
    </ol>
    {waiting.length > 1 && <Button className="mt-3" variant="primary" disabled={busy} onClick={() => approve(waiting)}>Approve all {waiting.length}</Button>}
    {problem && <p role="alert" className="text-problem mt-2">{problem}</p>}
  </details>;
}
