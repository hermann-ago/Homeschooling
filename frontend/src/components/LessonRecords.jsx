import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { tutorApi } from '../api/tutor';
import { modeHref } from '../api/mode';
import { learningLabel } from '../utils/learningLabels';
import { Button, Dialog, Field, useToast } from '../ui';

export default function LessonRecords({ child }) {
  const { data: records = [], error } = useQuery({ queryKey: ['lesson-records', child.id], queryFn: () => tutorApi.records(child.id) });
  const [correcting, setCorrecting] = useState(null);
  const [text, setText] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const client = useQueryClient();
  const toast = useToast();
  const save = async () => {
    setBusy(true);
    try {
      await tutorApi.amendAttempt(correcting, text, note);
      await client.invalidateQueries({ queryKey: ['lesson-records', child.id] });
      setCorrecting(null);
      toast('Correction saved. The original answer is preserved.');
    } catch (e) { toast({ tone: 'problem', message: e.message }); }
    finally { setBusy(false); }
  };
  if (error) return <p className="text-sm text-problem">Could not load lesson records: {error.message}</p>;
  if (!records.length) return null;
  return <section className="rounded-2xl border border-line bg-surface p-5 flex flex-col gap-4">
    <div><h2 className="text-lg font-bold">{child.name}’s learning notes</h2><p className="text-sm text-muted mt-1">What they explained, help they received, and questions to revisit.</p></div>
    {records.map(({ session, subject, topic, attempts, pending }) => <details key={session.id} className="rounded-xl border border-line p-4">
      <summary className="cursor-pointer font-semibold text-[15px]">{subject} · {topic}<span className="block text-xs text-muted font-normal mt-1">{session.date} · {session.completion_source === 'manual' ? 'Completed by you' : session.status === 'superseded' ? 'Earlier script · thread saved' : session.status === 'completed' ? 'Saved lesson' : 'In progress'}{pending.length > 0 ? ` · ${pending.length} ${['manual', 'topic_completion'].includes(session.completion_source) ? 'unassessed' : 'to revisit'}` : ''}</span></summary>
      <div className="mt-4 flex flex-col gap-3">
        {session.topic_id && <Button as="a" size="sm" href={modeHref(`/lesson?learner=${child.id}&topic=${session.topic_id}&session=${encodeURIComponent(session.id)}`)}>Open full lesson thread</Button>}
        {session.learner_explained && <p className="text-sm whitespace-pre-line">{session.learner_explained}</p>}
        {session.help_that_worked && <p className="text-sm text-muted whitespace-pre-line">Help: {session.help_that_worked}</p>}
        {pending.length > 0 && <div className="text-sm"><p className="font-semibold mb-1">{['manual', 'topic_completion'].includes(session.completion_source) ? 'Unassessed work' : 'To revisit'}</p><ul className="list-disc pl-5">{pending.map((a) => <li key={a.id}>{a.prompt}</li>)}</ul></div>}
        {attempts.map((a) => <div key={a.id} className="rounded-lg bg-paper/70 p-3 flex flex-col gap-1.5 text-sm">
          <span className="font-semibold">{a.question_text || a.question_ref}</span>
          <p className="whitespace-pre-line">First answer: {a.first_answer || 'No readable answer recorded'}</p>
          <span className="text-xs text-muted">{a.first_result} · {learningLabel(a.independence)}{a.amends_attempt_id ? ' · Amendment' : ''}</span>
          {a.help_given && <p className="whitespace-pre-line text-muted">Help: {a.help_given}</p>}
          {a.revised_answer && <p className="whitespace-pre-line">Later answer: {a.revised_answer} · {a.after_help_result}</p>}
          {a.source_note && <p className="text-xs text-muted">{a.source_note}</p>}
          <Button size="sm" variant="quiet" onClick={() => { setCorrecting(a); setText(a.first_answer || ''); setNote(''); }}>Correct transcription</Button>
        </div>)}
      </div>
    </details>)}
    {correcting && <Dialog open onClose={() => setCorrecting(null)} title="Correct answer transcription"
      footer={<><Button onClick={() => setCorrecting(null)}>Cancel</Button><Button variant="primary" disabled={busy || !note.trim() || text === correcting.first_answer} onClick={save}>{busy ? 'Saving…' : 'Save amendment'}</Button></>}>
      <div className="flex flex-col gap-4"><p className="text-sm text-muted">This preserves the original answer and assessment. A transcription correction is not a learner mistake.</p>
        <label className="text-sm font-semibold">Correct wording<textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} maxLength={4000} className="mt-2 w-full rounded-xl border border-line p-3 font-normal" /></label>
        <Field label="Reason for the correction" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. The handwriting says ‘tribes’, not ‘trees’." />
      </div>
    </Dialog>}
  </section>;
}
