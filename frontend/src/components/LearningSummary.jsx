import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchApi } from '../api/client';
import { subjectsApi } from '../api/subjects';
import { modeHref } from '../api/mode';
import { Button, Dialog, Field, inputClasses } from '../ui';

const payload = (data) => ({ method: 'POST', body: JSON.stringify(data) });

function EvidenceDetails({ child, data, item, onClose, onSaved }) {
  const [concept, setConcept] = useState(item.concept_ids?.[0] || '');
  const [note, setNote] = useState('');
  const [text, setText] = useState(item.first_answer || '');
  const [result, setResult] = useState('Unanswered');
  const [clarifying, setClarifying] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');
  const kind = item.first_result ? 'attempt' : 'review';
  const save = async () => {
    setBusy(true); setProblem('');
    try {
      const endpoint = `/records/learning/${child.id}/${data.subject_id}`;
      const updated = clarifying ? await fetchApi(`${endpoint}/attempts/${encodeURIComponent(item.id)}/clarify`, payload({
        expected_revision: item.revision, transcription: text, note, result,
      })) : await fetchApi(`${endpoint}/link`, payload({ expected_revision: data.link_revision, evidence_kind: kind, evidence_id: item.id,
        map_id: concept ? data.map_id : null, concept_id: concept || null, status: concept ? 'linked' : 'unmapped', note }));
      onSaved(updated); onClose();
    } catch (e) { setProblem(e.message); }
    finally { setBusy(false); }
  };
  const earlier = (item.lineage || []).slice(1).map((id) => data.amendment_history.find((a) => a.id === id)).filter(Boolean);
  return <Dialog open title="Observed learning evidence" description={`${child.name} · ${data.subject} · ${item.topic}`} width={780} onClose={busy ? undefined : onClose}
    footer={<><Button onClick={onClose} disabled={busy}>Cancel</Button><Button variant="primary" onClick={save} disabled={busy || !note.trim() || (clarifying && !text.trim())}>{busy ? 'Saving…' : clarifying ? 'Save answer amendment' : 'Save evidence link'}</Button></>}>
    <div className="flex flex-col gap-4 text-sm">
      {kind === 'attempt' ? <><p className="font-semibold">{item.question_text || item.question_ref}</p><p className="whitespace-pre-wrap">Saved answer: {item.first_answer || 'No readable answer recorded'}</p>
        <p>{item.first_result} · {item.independence?.replaceAll('_', ' ')} · {item.date}</p>
        {item.help_given && <p className="whitespace-pre-wrap">Help supplied: {item.help_given}</p>}
        {item.revised_answer && <p className="whitespace-pre-wrap">Later answer: {item.revised_answer} · {item.after_help_result}</p>}
        {item.source_note && <p className="whitespace-pre-wrap">Evidence note: {item.source_note}</p>}
        {(data.photos || []).filter((p) => p.session_id === item.session_id && (item.evidence_paths || []).includes(p.file_path)).map((p) =>
          <a key={p.id} className="underline text-action" href={modeHref(`/api/student-work/${encodeURIComponent(p.id)}`)} target="_blank" rel="noreferrer">Open saved photo: {p.filename}</a>)}
        {earlier.length > 0 && <details><summary>Original evidence and amendments</summary>{earlier.map((a) => <p key={a.id} className="mt-2">{a.first_answer} · {a.first_result} · {a.source_note}</p>)}</details>}
        <Button size="sm" onClick={() => setClarifying((v) => !v)}>{clarifying ? 'Return to concept link' : 'Correct saved transcription / assessment'}</Button>
      </> : <><p className="font-semibold">{item.concept}</p><p>{item.evidence}</p><p>{item.status} · {item.last_outcome} · next review: {item.next_due || 'None scheduled'}</p></>}
      {clarifying ? <>
        <p className="text-muted">The original remains in the records. This amendment describes the same submitted work; it is not a new independent check. Existing help stays recorded.</p>
        <Field label="Clarified answer"><textarea className={`${inputClasses} h-28 py-2`} value={text} maxLength={4000} onChange={(e) => setText(e.target.value)} /></Field>
        <Field label="Parent assessment"><select className={inputClasses} value={result} onChange={(e) => setResult(e.target.value)}>
          <option value="Unanswered">Awaiting assessment</option><option value="Correct">Correct after checking the actual source</option>
          <option value="Partly correct">Partly correct</option><option value="Not yet">Not yet</option><option value="Source disputed">Source disputed</option>
        </select></Field>
      </> : <>
        <Field label="Concept this evidence actually checks"><select className={inputClasses} value={concept} onChange={(e) => setConcept(e.target.value)}>
          <option value="">Keep at its recorded topic · no clear concept link</option>{data.concepts.map((c) => <option key={c.concept_id} value={c.concept_id}>{c.title}</option>)}
        </select></Field>
        <p className="text-muted">Link only the concept demonstrated by this response. Reading a chapter does not establish every concept in it. Unknown links remain visible.</p>
      </>}
      <Field label="Reason for this parent change"><textarea className={`${inputClasses} h-24 py-2`} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      {problem && <p role="alert" className="text-problem">{problem}</p>}
      <p className="text-muted">This parent action saves an audit record. It uses no AI allowance.</p>
    </div>
  </Dialog>;
}

function SubjectMemory({ child, subject }) {
  const client = useQueryClient();
  const queryKey = ['learning-summary', child.id, subject.id];
  const { data, error, isPending } = useQuery({ queryKey, queryFn: () => fetchApi(`/records/learning/${child.id}/${subject.id}`), refetchOnWindowFocus: true });
  const [view, setView] = useState('topics');
  const [q, setQ] = useState('');
  const [details, setDetails] = useState(null);
  const [supporting, setSupporting] = useState(null);
  const [saved, setSaved] = useState(false);
  if (isPending) return <p role="status">Reading saved learning evidence…</p>;
  if (error) return <p role="alert" className="text-problem">{error.message}</p>;
  let rows = view === 'topics' ? data.topics : view === 'concepts' ? data.concepts : view === 'reviews' ? data.reviews
    : data.evidence.filter((a) => view !== 'unmapped' || !a.concept_ids.length);
  rows = rows.filter((r) => `${r.title || r.topic} ${r.question_text || ''} ${r.concept || ''} ${r.label || ''}`.toLowerCase().includes(q.toLowerCase()));
  if (supporting && view === 'evidence') rows = rows.filter((r) => supporting.includes(r.id));
  return <div className="flex flex-col gap-4 text-sm">
    <p>{data.evidence.length} effective observations · {data.unmapped_evidence.length} without a clear concept link · saved summary {data.summary_version}.</p>
    <p className="text-muted">{data.interpretation} Older difficulties remain available even after many later lessons. Unclear work requires clarification, not a wrong mark.</p>
    {saved && <p role="status" className="text-action">Parent change saved; the learning summary was updated.</p>}
    <div className="flex flex-wrap gap-1">{[['topics', 'Topic evidence'], ['concepts', 'Concept evidence'], ['unmapped', 'Unmapped work'], ['evidence', 'All evidence'], ['reviews', 'Saved reviews']].map(([id, title]) =>
      <Button key={id} size="sm" aria-pressed={view === id} variant={view === id ? 'primary' : 'quiet'} onClick={() => { setView(id); setQ(''); setSupporting(null); }}>{title}</Button>)}</div>
    {supporting && <p>Showing the recorded work supporting this summary. <Button size="sm" onClick={() => setSupporting(null)}>Show all evidence</Button></p>}
    <Field label="Search learning evidence" value={q} onChange={(e) => setQ(e.target.value)} />
    {!rows.length && <p>No observed evidence in this view yet.</p>}
    <div className="flex flex-col gap-3 max-h-[65vh] overflow-y-auto pr-1">{rows.map((r) => <article key={r.id || r.concept_id || r.topic_id} className="rounded-xl border border-line p-4">
      <h4 className="font-semibold">{r.title || r.concept || r.question_text || r.topic}</h4>
      {r.label ? <><p className="mt-1">{r.label} · {r.observations} observations · {r.independent_checks} independent checks</p>
        <p className="text-muted">{r.help_sessions} lessons with help{r.repeated_difficulty ? ' · difficulty observed in more than one lesson' : ''}. Last independent check: {r.last_independent_check || 'Not recorded'}. Next review: {r.next_review || 'None scheduled'}.</p>
        <p className="mt-2">{r.next_action}</p>
        {r.evidence_ids.length > 0 && <Button size="sm" onClick={() => { setView('evidence'); setQ(''); setSupporting(r.evidence_ids); }}>Inspect supporting work</Button>}
      </> : <><p>{r.date || r.last_practice} · {r.first_result || r.status} · {r.independence?.replaceAll('_', ' ') || r.last_outcome}</p>
        <p className="text-muted">{r.topic} · {r.concept_ids.length ? 'Concept link recorded' : 'Retained at its topic without a guessed concept link'}</p>
        <Button size="sm" onClick={() => setDetails(r)}>Inspect / link evidence</Button></>}
    </article>)}</div>
    {(data.link_history.length > 0 || data.amendment_history.length > 0) && <details><summary className="cursor-pointer font-semibold">Parent links and amendment history</summary>
      {data.link_history.map((r) => <p key={r.id} className="mt-2">{r.status} · {r.created_at} · {r.note}</p>)}
      <p className="mt-2">{data.amendment_history.length} original records retained beneath later amendments. Inspect the effective answer to compare them.</p>
    </details>}
    {details && <EvidenceDetails child={child} data={data} item={details} onClose={() => setDetails(null)} onSaved={(next) => { client.setQueryData(queryKey, next); setSaved(true); client.invalidateQueries({ queryKey: ['records'] }); }} />}
  </div>;
}

export default function LearningSummary({ child }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState('');
  const { data: subjects, error } = useQuery({ queryKey: ['learning-subjects', child.id], queryFn: () => subjectsApi.getByChildId(child.id), enabled: open });
  const subject = subjects?.find((s) => String(s.id) === selected) || subjects?.[0];
  return <section className="rounded-2xl border border-line bg-surface p-5 flex flex-col gap-4">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-semibold text-lg">{child.name} · lasting learning memory</h2>
      <Button size="sm" onClick={() => setOpen((v) => !v)}>{open ? 'Hide learning summary' : 'View learning summary'}</Button></div>
    <p className="text-sm text-muted">A source-linked view of observed understanding, help, earlier difficulties and next reviews. Reading completion stays separate.</p>
    {open && <>{error && <p role="alert" className="text-problem">{error.message}</p>}{subject && <><Field label={`Subject for ${child.name}'s learning summary`}><select className={inputClasses} value={subject.id} onChange={(e) => setSelected(e.target.value)}>
      {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></Field><SubjectMemory key={subject.id} child={child} subject={subject} /></>}
      {subjects?.length === 0 && <p>No subjects configured yet.</p>}</>}
  </section>;
}
