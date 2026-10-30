import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { tutorApi } from '../api/tutor';
import { Button } from '../ui';
import { DEFAULT_SCRIPT_CAP_USD } from '../utils/preparationLimits';

export default function LessonPreparation({ subject, topics }) {
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');
  const [progress, setProgress] = useState('');
  const client = useQueryClient();
  const candidates = [...topics].filter((t) => !t.completed && t.document_id).sort((a, b) => a.chapter_order - b.chapter_order).slice(0, 2);
  const total = preview?.reduce((sum, r) => sum + r.estimate.estimated_cost_usd, 0) || 0;
  const allowed = preview?.every((r) => r.estimate.allowed);
  const check = async (count) => {
    setBusy(true); setProblem(''); setProgress(''); setPreview(null);
    try {
      const rows = [];
      for (const topic of candidates.slice(0, count)) rows.push({ topic, estimate: await tutorApi.estimateGuide(subject.child_id, topic.id, false, DEFAULT_SCRIPT_CAP_USD) });
      setPreview(rows);
    } catch (e) { setProblem(e.message); }
    finally { setBusy(false); }
  };
  const prepare = async () => {
    setBusy(true); setProblem('');
    let done = 0;
    try {
      for (const { topic } of preview) {
        setProgress(`Preparing ${topic.title}…`);
        await tutorApi.prepareGuide(subject.child_id, topic.id, DEFAULT_SCRIPT_CAP_USD);
        done += 1;
        setProgress(`${done} guided lesson${done === 1 ? '' : 's'} saved. Voice preparation runs in the background; check each lesson row below.`);
      }
      setPreview(null); client.invalidateQueries({ queryKey: ['reader'] }); client.invalidateQueries({queryKey:['curriculum-preparation']});
    } catch (e) { setProblem(`${done ? `${done} completed lesson${done === 1 ? '' : 's'} remain saved. ` : ''}${e.message}`); }
    finally { setBusy(false); }
  };
  return <section className="rounded-2xl border border-line p-5 bg-surface flex flex-col gap-3 text-sm">
    <h3 className="font-semibold">Prepare upcoming guided lessons</h3>
    <p className="text-muted">Use checked book context and the latest observed learning. This prepares materials without starting lessons or changing student progress. Existing guides are reused; the table below shows tutor and advanced audio preparation.</p>
    {!preview && <div className="flex flex-wrap gap-2"><Button size="sm" disabled={busy || !candidates.length} onClick={() => check(1)}>Preview next lesson</Button>
      <Button size="sm" disabled={busy || candidates.length < 2} onClick={() => check(2)}>Preview next two lessons</Button></div>}
    {preview && <><ul className="list-disc pl-5">{preview.map(({ topic, estimate }) => <li key={topic.id}>{topic.title} · {estimate.reused ? 'Already saved; no text generation charge' : `Up to US$${estimate.estimated_cost_usd.toFixed(3)}`}</li>)}</ul>
      <p>Total estimated text cost: US${total.toFixed(3)}. Provider costs are tracked for both guides.</p>
      {!allowed && <p role="alert" className="text-attention">Check the source review or provider connection for these lessons.</p>}
      <div className="flex gap-2"><Button size="sm" variant="primary" disabled={busy || !allowed} onClick={prepare}>{busy ? 'Preparing…' : 'Prepare these lessons'}</Button>
        <Button size="sm" disabled={busy} onClick={() => setPreview(null)}>Cancel</Button></div></>}
    {progress && <p role="status" className="text-action">{progress}</p>}{problem && <p role="alert" className="text-problem">{problem}</p>}
    {!candidates.length && <p>No upcoming reading lessons with a linked book.</p>}
  </section>;
}
