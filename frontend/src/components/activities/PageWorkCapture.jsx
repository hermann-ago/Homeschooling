import { useEffect, useRef, useState } from 'react';
import { Button } from '../../ui';
import { inputClasses } from '../../ui/classes';
import { readSaved, storageKey, writeSaved } from './durable';
import WorkCamera from './WorkCamera';

function ExerciseAnswers({ group, sessionId, draftIdentity, onEvent, onSingleItem, busy }) {
  const key = storageKey(sessionId, `exercise-answers.${draftIdentity || group.items[0].activity_id}`);
  const saved = readSaved(key);
  const [method, setMethod] = useState(() => saved?.method || 'typed');
  const [answers, setAnswers] = useState(() => saved?.answers || {});
  const [stored, setStored] = useState(true);
  const save = (nextAnswers, nextMethod = method) => {
    setAnswers(nextAnswers); setMethod(nextMethod);
    setStored(writeSaved(key, { answers: nextAnswers, method: nextMethod }));
  };
  const included = group.items.filter(item => answers[item.activity_id]?.text?.trim());
  const ready = included.length > 0 && included.every(item => !item.require_reasoning || answers[item.activity_id]?.reasoning?.trim());
  const submit = async (event) => {
    event.preventDefault();
    if (busy || !ready) return;
    const next = await onEvent('submit_exercise_answers', { items: included.map(item => ({
      item_id: item.activity_id, text: answers[item.activity_id].text,
      ...(item.require_reasoning ? { reasoning: answers[item.activity_id].reasoning || '' } : {}),
    })) });
    if (next?.page_work?.id && next.page_work.capture_method === 'typed') writeSaved(key, null);
  };
  const enter = event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent?.isComposing && !event.isComposing && event.keyCode !== 229) {
      event.preventDefault(); event.currentTarget.form?.requestSubmit();
    }
  };
  return <div className="flex flex-col gap-3">
    <label className="text-sm">How to send these answers<select className={`${inputClasses} mt-1`} value={method} disabled={busy} onChange={event => save(answers, event.target.value)}>
      <option value="typed">Type answers together</option><option value="photo">Send a photo</option>
    </select></label>
    {method === 'typed' ? <form aria-label="Exercise answers" className="flex flex-col gap-3" onSubmit={submit}>
      <p className="text-sm text-muted">Type each answer below, including any accents. Check them together; blank parts stay open.</p>
      {group.items.map(item => <fieldset key={item.activity_id} className="flex flex-col gap-2 rounded-xl border border-line p-3">
        <legend className="font-semibold text-sm">Part {item.label}</legend><p className="text-sm whitespace-pre-wrap">{item.prompt}</p>
        <label className="text-sm">Answer {item.label}<textarea rows={2} maxLength={4000} disabled={busy} className={`${inputClasses} h-auto py-2 mt-1`} value={answers[item.activity_id]?.text || ''} onKeyDown={enter} onChange={event => save({ ...answers, [item.activity_id]: { ...answers[item.activity_id], text: event.target.value } })} /></label>
        {item.require_reasoning && <label className="text-sm">Explain answer {item.label}<textarea rows={2} maxLength={4000} disabled={busy} className={`${inputClasses} h-auto py-2 mt-1`} value={answers[item.activity_id]?.reasoning || ''} onKeyDown={enter} onChange={event => save({ ...answers, [item.activity_id]: { ...answers[item.activity_id], reasoning: event.target.value } })} /></label>}
      </fieldset>)}
      <p role="status" className={`text-xs ${stored ? 'text-muted' : 'text-attention'}`}>{stored ? 'Draft saved on this device' : 'Draft could not be saved on this device. Keep this lesson open until you send it.'}</p>
      <p className="text-xs text-muted">Enter to check answers · Shift+Enter for a new line</p>
      <Button type="submit" variant="primary" disabled={busy || !ready}>Check answers</Button>
    </form> : <>
      <ol className="flex flex-col gap-2 text-sm">{group.items.map(item => <li key={item.activity_id}><strong>{item.label}) </strong>{item.prompt}</li>)}</ol>
      <p className="text-sm text-muted">Complete these parts in your book. Then send one photo of your answers together.</p>
      <Button variant="primary" disabled={busy} onClick={() => onEvent('open_page_work', { scope: 'exercise' })}>I have finished these answers</Button>
    </>}
    <Button size="sm" variant="quiet" disabled={busy} onClick={onSingleItem}>Answer one part at a time instead</Button>
  </div>;
}

function PagePhoto({ group, sessionId, onUpload, onEvent, busy, draftEvidence }) {
  const key = storageKey(sessionId, `page-photos.${group.id}`);
  const [photos, setPhotos] = useState(() => readSaved(key)?.ids ?? (group.evidence_ids?.length ? group.evidence_ids : draftEvidence.map(f => f.id)));
  const [camera, setCamera] = useState(false);
  const [error, setError] = useState('');
  const picker = useRef(null);
  useEffect(() => { writeSaved(key, { ids: photos }); }, [key, photos]);
  const upload = async (file) => {
    if (!file || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024) {
      setError('Use a JPG, PNG or WebP photo smaller than 10 MB.'); return false;
    }
    try {
      const id = await onUpload(file);
      if (!id) return false;
      setPhotos(previous => [...new Set([...previous, id])]); setError(''); return true;
    } catch { setError('The photo was not saved. Please try again.'); return false; }
  };
  return <div className="flex flex-col gap-3">
    <p className="text-sm text-muted">One clear photo of these answers is enough. Keep the part labels visible; you do not need the whole book page.</p>
    <ol className="list-none flex flex-col gap-2 text-sm">{group.items.map(item => <li key={item.activity_id}>{item.label && <strong>{item.label}) </strong>}{item.prompt}</li>)}</ol>
    <Button disabled={busy || photos.length >= 5} onClick={() => setCamera(true)}>Take a photo of these answers</Button>
    <Button variant="quiet" disabled={busy || photos.length >= 5} onClick={() => picker.current?.click()}>Choose an existing photo</Button>
    <input ref={picker} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" aria-label="Photo of these answers" onChange={event => { void upload(event.target.files?.[0]); event.target.value = ''; }} />
    {camera && <WorkCamera onPhoto={upload} onClose={() => setCamera(false)} />}
    {photos.length > 0 && <p role="status" className="text-sm text-action">{photos.length} photo{photos.length === 1 ? '' : 's'} attached</p>}
    {error && <p role="alert" className="text-sm text-problem">{error}</p>}
    <Button variant="primary" disabled={busy || !photos.length} onClick={() => onEvent('submit_page_work', { page_work_id: group.id, evidence_ids: photos })}>Read all answers in these photos</Button>
  </div>;
}

function ConfirmPage({ group, sessionId, onEvent, busy }) {
  const key = storageKey(sessionId, `page-answers.${group.id}`);
  const [rows, setRows] = useState(() => readSaved(key)?.rows || group.items.map(item => ({
    item_id: item.activity_id, text: item.text || '', selected: Boolean(item.text?.trim()) && !item.uncertain,
  })));
  useEffect(() => { writeSaved(key, { rows }); }, [key, rows]);
  const change = (id, patch) => setRows(previous => previous.map(row => row.item_id === id ? { ...row, ...patch } : row));
  const selected = rows.filter(row => row.selected && row.text.trim());
  return <div className="flex flex-col gap-3">
    <p className="text-sm">Check the captured words and marks below. Correct any reading mistakes. Leave missing answers unchecked.</p>
    {rows.map((row, index) => <fieldset key={row.item_id} className="rounded-xl border border-line p-3 flex flex-col gap-2">
      <legend className="text-sm font-semibold">{group.items[index].label ? `Part ${group.items[index].label}` : `Item ${index + 1}`}</legend>
      <p className="text-sm whitespace-pre-wrap">{group.items[index].prompt}</p>
      {group.items[index].uncertain && <p className="text-xs text-attention">Some writing was unclear. Check it before including this answer.</p>}
      <label className="text-sm flex gap-2 items-center"><input type="checkbox" checked={row.selected} disabled={busy} onChange={event => change(row.item_id, { selected: event.target.checked })} />Include answer {index + 1}</label>
      <label className="text-sm">Captured answer {index + 1}<textarea rows={2} maxLength={4000} disabled={busy} className={`${inputClasses} h-auto py-2 mt-1`} value={row.text} onChange={event => change(row.item_id, { text: event.target.value })} /></label>
    </fieldset>)}
    <Button variant="primary" disabled={busy || !selected.length} onClick={() => onEvent('confirm_page_work', {
      page_work_id: group.id, items: selected.map(({ item_id, text }) => ({ item_id, text })),
    })}>These match my work · Check {selected.length} answer{selected.length === 1 ? '' : 's'}</Button>
  </div>;
}

/** inConversation: the heading and instruction already stand in the tutor's message above. */
export default function PageWorkCapture({ group, sessionId, draftIdentity, onUpload, onEvent, onSingleItem, busy, draftEvidence = [], inConversation = false }) {
  const working = ['transcription_queued', 'transcribing', 'assessment_queued', 'assessing'].includes(group.status);
  return <section aria-label="Page answers together" className="flex flex-col gap-4">
    {!inConversation && <div><h2 className="font-semibold">{group.scope === 'exercise' ? 'One exercise · All parts together' : 'Send this book work together'}</h2><p className="text-xs text-muted">{group.scope === 'exercise' ? `${group.items.length} parts · One submission` : `Book page ${group.items[0]?.page} · ${group.items.length} questions · Each answer keeps its own record`}</p></div>}
    {group.instruction && !inConversation && <p className="font-semibold whitespace-pre-wrap">{group.instruction}</p>}
    {group.status === 'ready' && (group.can_type ? <ExerciseAnswers key={draftIdentity || group.items[0].activity_id} group={group} sessionId={sessionId} draftIdentity={draftIdentity} onEvent={onEvent} onSingleItem={onSingleItem} busy={busy} /> : <>
      <ol className="flex flex-col gap-2 text-sm">{group.items.map(item => <li key={item.activity_id}><strong>{item.label}) </strong>{item.prompt}</li>)}</ol>
      <p className="text-sm text-muted">Complete these parts in your book. Then send one photo of your answers together.</p>
      <Button variant="primary" disabled={busy} onClick={() => onEvent('open_page_work', { scope: 'exercise' })}>I have finished these answers</Button>
      <Button size="sm" variant="quiet" disabled={busy} onClick={onSingleItem}>Answer one part at a time instead</Button>
    </>)}
    {group.status === 'capture' && <PagePhoto group={group} sessionId={sessionId} onUpload={onUpload} onEvent={onEvent} busy={busy} draftEvidence={draftEvidence} />}
    {group.status === 'confirmation' && <ConfirmPage group={group} sessionId={sessionId} onEvent={onEvent} busy={busy} />}
    {working && <p role="status" className="text-sm text-muted">{group.status.startsWith('transcri') ? 'Reading the answers in your saved photos…' : 'Checking your confirmed answers together…'}</p>}
    {(group.status.endsWith('_failed') || working && !busy) && <div className="flex flex-col gap-2"><p role="alert" className="text-sm text-attention">{group.error || 'Recover the saved page request to see its result.'}</p><Button disabled={busy} onClick={() => onEvent('retry_page_work', { page_work_id: group.id })}>Recover saved page request</Button></div>}
    {group.status === 'completed' && <>
      <p className="text-sm text-action">Your answers are saved. Anything missing or needing another try stays open.</p>
      {group.items.map((item, index) => <article className="rounded-xl bg-paper p-3 text-sm" key={item.activity_id}>
        <p className="font-semibold">{item.label ? `Part ${item.label}` : `Item ${index + 1}`}</p><p className="mt-1">{item.prompt}</p>
        {item.confirmed_text ? <><p className="mt-2 whitespace-pre-wrap">Your answer: {item.confirmed_text}</p><p className="mt-2 text-action">{item.feedback || 'Saved for checking'}</p></> : <p className="mt-2 text-muted">Not sent · No result recorded</p>}
      </article>)}
    </>}
    {group.id && <Button size="sm" variant="quiet" disabled={busy || working} onClick={() => onEvent('close_page_work', { page_work_id: group.id })}>{group.status === 'completed' ? 'Return to the lesson' : 'Return to one question at a time'}</Button>}
  </section>;
}
