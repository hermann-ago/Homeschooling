import { focusLessonControl } from '../../utils/lessonFocus';
import { useEffect, useId, useRef, useState } from 'react';
import { Button } from '../../ui';
import { inputClasses } from '../../ui/classes';
import { operationId, readSaved, storageKey, writeSaved } from './durable';
import WorkCamera from './WorkCamera';

/** A draft belongs to one exact session, activity and interaction, including after refresh. */
export default function ResponseCapture({ sessionId, activity, busy, onSubmit, onUpload, onSaveDraft, onPauseNarration, language = 'en-US', draftEvidence = [], compact = false }) {
  const content = activity.content || {};
  const keyboardHelpId = useId();
  const key = storageKey(sessionId, `draft.${activity.id}.${activity.interaction?.id || 'initial'}`);
  const modes = content.response_modes || ['text'];
  const choiceOnly = modes.length === 1 && modes[0] === 'choice';
  const restoredUnsupported = useRef(false);
  // The latest checked answer for these boxes: a retry starts from it, with each box's result.
  const lastBoxes = content.blanks && [...(activity.responses || [])].reverse().find((r) => r.original?.blanks);
  const [draft, setDraft] = useState(() => {
    const fresh={
      method: modes.includes('written_steps') || content.evidence_requirement === 'written_steps' && modes.includes('text') ? 'written_steps' : modes.includes('choice') ? 'choice' : modes.includes('text') ? 'typed' : modes.includes('device_dictation') || modes.includes('audio') ? 'dictation' : modes.includes('photo') ? 'photo' : 'parent_review',
      text: '', reasoning: '', choice_ids: [], matches:{}, blanks: { ...(lastBoxes?.original?.blanks || {}) }, evidence_ids: activity.interaction?.is_replay || activity.interaction?.replay_of ? [] : draftEvidence.map((file) => file.id), response_id: operationId(),
    };
    const saved={...fresh,...readSaved(key,activity.draft || fresh)};
    const supported={typed:modes.includes('text'),choice:modes.includes('choice')&&content.choices?.length>=2,
      dictation:modes.includes('device_dictation')||modes.includes('audio'),photo:modes.includes('photo'),parent_review:modes.includes('parent_review'),
      written_steps:modes.includes('written_steps')||['written_steps','handwriting','diagram'].includes(content.evidence_requirement)};
    if(!supported[saved.method]){restoredUnsupported.current=true;saved.method=fresh.method;}
    return saved;
  });
  const [notice, setNotice] = useState(() => restoredUnsupported.current?'The answer options changed. Your saved words are kept; review them before sending.':'');
  const [savedWhere, setSavedWhere] = useState('');
  const [cameraOpen, setCameraOpen] = useState(false);
  const saveGeneration = useRef(0);
  const fileInput = useRef(null);
  const textInput = useRef(null);
  const draftCallback = useRef(onSaveDraft);
  const draftRevision = useRef(draft.base_draft_revision ?? activity.draft_revision ?? 0);
  const saves = useRef(Promise.resolve());
  const submitting = useRef(false);
  useEffect(() => { draftCallback.current = onSaveDraft; }, [onSaveDraft]);
  useEffect(() => {
    const generation = ++saveGeneration.current;
    const local = writeSaved(key, draft);
    setSavedWhere(local ? 'Draft saved on this device' : 'Draft not saved on this device. Keep this page open.');
    if (!draft.text && !draft.reasoning && !draft.choice_ids?.length && !draft.evidence_ids?.length) return undefined;
    const timer = window.setTimeout(async () => {
      const save = saves.current.catch(() => {}).then(() => draftCallback.current?.({ ...draft, expected_draft_revision: draftRevision.current }));
      saves.current = save;
      const revision = await save;
      if (Number.isInteger(revision)) {
        draftRevision.current = revision;
        const saved = readSaved(key);
        if (saved) writeSaved(key, { ...saved, base_draft_revision: revision });
        if (saveGeneration.current === generation) setSavedWhere('Draft saved to your home server');
      }
    }, 600);
    return () => { window.clearTimeout(timer); saveGeneration.current += 1; };
  }, [key, draft]);
  useEffect(() => { focusLessonControl(textInput.current); }, [activity.interaction?.id]);
  const change = (patch) => setDraft((previous) => ({ ...previous, ...patch }));
  const reasoningRequired = content.require_reasoning || content.evidence_requirement === 'reasoning' || ['explain_thinking', 'predict_then_check', 'find_and_fix_mistake'].includes(activity.kind);
  // Retelling and explanation prompts already ask for the explanation itself.
  // Keep the child's actual words in the answer rather than requiring a duplicate.
  const reasoningInAnswer = ['tell_it_back', 'explain_thinking'].includes(activity.kind) && ['typed', 'dictation'].includes(draft.method);
  const reasoningInputRequired = reasoningRequired && !reasoningInAnswer && !['written_steps', 'parent_review'].includes(draft.method);
  const physicalEvidence = ['written_steps', 'handwriting', 'diagram'].includes(content.evidence_requirement);
  const multiple = content.answer_format === 'multiple_select';
  const matching=draft.method==='typed' && content.matching;
  const selectedMatches=draft.matches || {};
  const validMatches=matching && matching.items.every((item)=>matching.options.some((option)=>option.id===selectedMatches[item.id])) && (matching.allow_reuse || new Set(Object.values(selectedMatches)).size===matching.items.length);
  const validChoices = draft.choice_ids.length > 0 && (multiple || draft.choice_ids.length === 1) && draft.choice_ids.every((id) => content.choices?.some((choice) => choice.id === id));
  const boxes = draft.method === 'typed' && content.blanks;
  const boxValues = draft.blanks || {};
  const validBoxes = boxes && boxes.every((box) => (boxValues[box.id] || '').trim());
  const boxInputs = useRef([]);
  const canSend = draft.method === 'parent_review' || (draft.method === 'photo' ? draft.evidence_ids.length > 0 : boxes ? validBoxes : matching ? validMatches : draft.method === 'choice' ? validChoices : draft.text.trim() || draft.evidence_ids.length > 0);
  const canSubmit = !busy && canSend && (!reasoningInputRequired || Boolean(draft.reasoning.trim()));
  const dictate = () => {
    onPauseNarration?.();
    change({ method: 'dictation' });
    setNotice('Use the microphone on your device keyboard to dictate into the transcript. On Windows, you can use Windows + H. Check the words before confirming your answer.');
    window.setTimeout(() => textInput.current?.focus(), 0);
  };
  const upload = async (file) => {
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024) {
      setNotice('Choose a JPG, PNG or WebP photo smaller than 10 MB.'); return;
    }
    if (draft.evidence_ids.length >= 5) { setNotice('An answer can include up to five photos.'); return; }
    onPauseNarration?.();
    try {
      const id = await onUpload(file);
      if (id) { setDraft((previous) => ({ ...previous, evidence_ids: [...new Set([...previous.evidence_ids, id])] })); setNotice('Photo saved. Add a readable transcript when you can; original work remains available for checking.'); return true; }
    } catch (error) { setNotice(error.message); }
  };
  const send = async () => {
    if (!canSubmit || submitting.current) return;
    submitting.current = true;
    onPauseNarration?.();
    try { await onSubmit({ ...draft, ...(checkOnSend ? { assess_after_save: true } : {}) }); }
    finally { submitting.current = false; }
    // Do not clear until the server's state changes interaction/status. An ambiguous
    // transport failure must retain the original response ID and all original work.
  };
  const submitOnEnter = (event) => {
    if (event.key !== 'Enter' || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey || event.nativeEvent.isComposing || event.keyCode === 229) return;
    event.preventDefault();
    if (canSubmit) void send();
  };
  const checkOnSend = ['typed', 'written_steps', 'choice'].includes(draft.method) && !draft.evidence_ids.length && activity.kind !== 'capture_and_confirm' &&
    (activity.kind !== 'predict_then_check' || activity.interaction?.stage === 'reflection');
  const reasoningBox=<label className="text-sm font-semibold flex flex-col gap-1">{reasoningInputRequired ? 'Explain your thinking' : 'Explain your thinking (optional)'}<textarea rows={compact ? 2 : 3} maxLength={4000} value={draft.reasoning} disabled={busy} onKeyDown={submitOnEnter} aria-describedby={keyboardHelpId} onChange={(event) => change({ reasoning: event.target.value })} className={`${inputClasses} h-auto py-3 font-normal`} /></label>;
  return <div className={compact ? 'response-composer' : 'flex flex-col gap-3'} aria-label="Answer capture">
    {boxes && <fieldset className="flex flex-col gap-2" aria-label="Your answers">
      {boxes.map((box, index) => {
        const result = lastBoxes?.blank_results?.[box.id];
        const unchanged = lastBoxes && (boxValues[box.id] || '') === (lastBoxes.original.blanks[box.id] || '');
        const mark = unchanged && result === true ? 'right' : unchanged && result === false ? 'again' : null;
        return <label key={box.id} className="flex items-center gap-3">
          <span className="min-w-28 text-lg tabular-nums whitespace-pre-wrap">{box.label}</span>
          <input ref={(node) => { boxInputs.current[index] = node; if (index === 0) textInput.current = node; }} lang={language} autoComplete="off" maxLength={100}
            aria-label={`Answer for ${box.label}`} aria-invalid={mark === 'again' || undefined} value={boxValues[box.id] || ''} disabled={busy}
            onKeyDown={(event) => {
              if (event.key !== 'Enter' || event.nativeEvent.isComposing) return;
              event.preventDefault();
              // Enter fills the next empty box; once every box has an answer it checks them.
              if (canSubmit) { void send(); return; }
              const order = [...boxes.keys()].map((i) => (index + 1 + i) % boxes.length);
              const empty = order.find((i) => !(boxValues[boxes[i].id] || '').trim());
              boxInputs.current[empty ?? (index + 1) % boxes.length]?.focus();
            }}
            onChange={(event) => {
              const values = { ...boxValues, [box.id]: event.target.value };
              change({ blanks: values, text: boxes.map((b) => `${b.label} ${values[b.id] || ''}`.trim()).join('\n') });
            }}
            className={`${inputClasses} w-28 text-lg tabular-nums ${mark === 'right' ? 'border-saved bg-action-soft' : mark === 'again' ? 'border-attention bg-attention-soft' : ''}`} />
          {mark === 'right' && <span className="text-saved font-semibold" aria-label="Right">✓</span>}
          {mark === 'again' && <span className="text-attention text-sm whitespace-nowrap">Look again</span>}
        </label>;
      })}
    </fieldset>}
    {content.blanks && modes.includes('photo') && <Button size="sm" variant="quiet" disabled={busy} onClick={() => change({ method: draft.method === 'photo' ? 'typed' : 'photo' })}>
      {draft.method === 'photo' ? 'Type my answers instead' : 'Send a photo of my book instead'}</Button>}
    {!choiceOnly && !content.blanks && <label className="text-sm font-semibold flex flex-col gap-1">How to answer
      <select className={inputClasses} value={draft.method} disabled={busy} onChange={(event) => change({ method: event.target.value })}>
        {modes.includes('text') && <option value="typed">Type an answer</option>}
        {modes.includes('choice') && <option value="choice">{multiple ? 'Select all that apply' : 'Choose an answer'}</option>}
        {(modes.includes('device_dictation') || modes.includes('audio')) && <option value="dictation">Spoken transcript</option>}
        {(modes.includes('written_steps') || physicalEvidence) && <option value="written_steps">Write your steps</option>}
        {modes.includes('photo') && <option value="photo">Photo of my work</option>}
        {modes.includes('parent_review') && <option value="parent_review">Ask a parent to inspect my work</option>}
      </select>
    </label>}
    {draft.method === 'choice' && <fieldset onKeyDown={submitOnEnter}><legend className="text-sm font-semibold mb-2">{multiple ? 'Select all that apply' : 'Choose your answer'}</legend><div className={content.answer_format === 'true_false' ? 'grid grid-cols-2 gap-2' : 'flex flex-col gap-2'}>{(content.choices || []).map((choice) => <label key={choice.id} className={`flex gap-3 items-start rounded-xl border p-3 text-sm cursor-pointer ${draft.choice_ids.includes(choice.id) ? 'border-action bg-action-soft' : 'border-line bg-paper/40'}`}><input className="mt-1 accent-[var(--color-action)]" name={`choice-${activity.id}`} type={multiple ? 'checkbox' : 'radio'} checked={draft.choice_ids.includes(choice.id)} disabled={busy} value={choice.id} onChange={() => change({ choice_ids: multiple ? draft.choice_ids.includes(choice.id) ? draft.choice_ids.filter((id) => id !== choice.id) : [...draft.choice_ids, choice.id] : [choice.id] })} /><span className="whitespace-pre-wrap">{choice.label}</span></label>)}</div></fieldset>}
    {activity.kind === 'find_and_fix_mistake' && modes.includes('text') && <Button size="sm" disabled={busy || Boolean(draft.text)} onClick={() => { change({ method: 'typed', text: content.example || '' }); textInput.current?.focus(); }}>Edit the example</Button>}
    {matching && <fieldset onKeyDown={submitOnEnter} className="flex flex-col gap-3"><legend className="text-sm font-semibold mb-2">Match each item</legend>{matching.items.map((item)=><label key={item.id} className="text-sm font-semibold flex flex-col gap-1">{item.label}<select data-matching className={inputClasses} value={selectedMatches[item.id] || ''} disabled={busy} onChange={(event)=>{
      const matches={...selectedMatches,[item.id]:event.target.value};
      const text=matching.items.filter((row)=>matches[row.id]).map((row)=>`${row.label} → ${matching.options.find((option)=>option.id===matches[row.id])?.label || ''}`).join('\n');
      change({matches,text});
    }}><option value="">Choose a match</option>{matching.options.map((option)=><option key={option.id} value={option.id} disabled={!matching.allow_reuse && Object.entries(selectedMatches).some(([id,value])=>id!==item.id && value===option.id)}>{option.label}</option>)}</select></label>)}</fieldset>}
    {draft.method !== 'choice' && !matching && !boxes && <label className="text-sm font-semibold flex flex-col gap-1">
      {draft.method === 'dictation' ? 'Your spoken transcript' : draft.method === 'written_steps' ? 'Your written steps' : draft.method === 'photo' ? 'What you wrote (optional transcript)' : draft.method === 'parent_review' ? 'What you would like checked (optional)' : activity.kind === 'find_and_fix_mistake' ? 'Your corrected example' : 'Your answer'}
      <textarea ref={textInput} lang={language} rows={draft.method === 'written_steps' ? 4 : compact ? 2 : 3} placeholder={compact ? 'Write your answer…' : undefined} maxLength={4000} value={draft.text} disabled={busy} onKeyDown={submitOnEnter} aria-describedby={keyboardHelpId} onChange={(event) => change({ text: event.target.value })} className={`${inputClasses} h-auto py-3 font-normal`} />
    </label>}
    {(modes.includes('device_dictation') || modes.includes('audio')) && draft.method === 'dictation' && <Button size="sm" disabled={busy} onClick={dictate}>Use device dictation</Button>}
    {reasoningInputRequired ? reasoningBox : draft.method==='choice' && !choiceOnly && <details><summary className="text-sm text-action cursor-pointer">Add an explanation (optional)</summary><div className="mt-2">{reasoningBox}</div></details>}
    {physicalEvidence && <p className="text-sm text-muted">{content.evidence_requirement.replaceAll('_', ' ')} needs the actual work checked. A spoken answer alone does not show everything written on the page.</p>}
    {content.evidence_requirement === 'spelling' && <p className="text-sm text-muted">Type the complete word, including its accents. A photo is optional.</p>}
    {draft.method === 'photo' && !draft.evidence_ids.length && <p role="status" className="text-sm text-muted">Attach a photo before sending. To check the words without a photo, choose Type an answer when available.</p>}
    {(modes.includes('photo') || physicalEvidence) && ['photo', 'written_steps', 'parent_review'].includes(draft.method) && <>
      <Button size="sm" disabled={busy || draft.evidence_ids.length >= 5} onClick={() => { onPauseNarration?.(); setCameraOpen(true); }}>Take photo of my work</Button>
      <Button size="sm" variant="quiet" disabled={busy || draft.evidence_ids.length >= 5} onClick={() => fileInput.current?.click()}>Choose an existing photo</Button>
      <input ref={fileInput} type="file" className="hidden" accept="image/jpeg,image/png,image/webp" aria-label="Photo of your work" onChange={(event) => { upload(event.target.files?.[0]); event.target.value = ''; }} />
      {draft.evidence_ids.length > 0 && <p className="text-sm text-action">{draft.evidence_ids.length} saved photo{draft.evidence_ids.length === 1 ? '' : 's'} attached</p>}
    </>}
    {cameraOpen && <WorkCamera onPhoto={upload} onClose={() => setCameraOpen(false)} />}
    {notice && <p role="status" className="text-sm text-muted">{notice}</p>}
    {reasoningInputRequired && canSend && !draft.reasoning.trim() && <p role="status" className="text-sm text-muted">Add your explanation in “Explain your thinking” before sending.</p>}
    {savedWhere && <p role="status" className={savedWhere.startsWith('Draft not saved') ? 'text-xs text-attention' : 'sr-only'}>{savedWhere}</p>}
    <p id={keyboardHelpId} className="sr-only">{choiceOnly ? 'Enter to send' : boxes ? 'Enter goes to the next box' : 'Enter to send · Shift+Enter for a new line'}</p>
    <Button variant="primary" disabled={!canSubmit} onClick={send}>{busy ? 'Saving…' : draft.method === 'parent_review' ? 'Ask a parent to check' : draft.method === 'dictation' || draft.method === 'photo' || draft.evidence_ids.length ? 'Save answer for confirmation' : checkOnSend ? 'Check my answer' : 'Save answer'}</Button>
  </div>;
}

export function ConfirmResponse({ sessionId, response, busy, onConfirm, checkOnConfirm = false }) {
  const key = storageKey(sessionId, `confirmation.${response.id}`);
  const [saved] = useState(() => readSaved(key));
  const originalText = typeof response.original === 'string' ? response.original : response.original?.text || response.text || '';
  const [text, setText] = useState(saved?.text ?? response.confirmed_text ?? response.proposed_text ?? originalText);
  const [locallySaved, setLocallySaved] = useState(false);
  const edited = useRef(Boolean(saved?.edited));
  useEffect(() => { setLocallySaved(writeSaved(key, { text, edited: edited.current })); }, [key, text]);
  useEffect(() => { if (!edited.current && response.proposed_text) setText(response.proposed_text); }, [response.proposed_text]);
  return <section className="rounded-xl border border-attention bg-attention-soft p-3 flex flex-col gap-3" aria-label="Confirm your answer">
    <p className="font-semibold">Check that this is what you said or wrote.</p>
    <p className="text-sm text-muted">Correct transcription errors here. They are not learner mistakes.</p>
    {response.transcription_status === 'uncertain' && <p className="text-sm text-attention">Some writing was unclear. Check the original photo and correct the proposed words.</p>}
    <label className="text-sm font-semibold flex flex-col gap-1">Confirmed answer<textarea value={text} maxLength={4000} rows={3} disabled={busy} onChange={(event) => { edited.current = true; setText(event.target.value); }} className={`${inputClasses} h-auto py-3 font-normal`} /></label>
    {response.evidence_ids?.length > 0 && <p className="text-sm">{response.evidence_ids.length} original photo{response.evidence_ids.length === 1 ? '' : 's'} saved for checking.</p>}
    <p className="text-xs text-muted">{locallySaved ? 'Transcript edits saved on this device. Confirm to send them to your home server.' : 'Keep this page open until you confirm your transcript.'}</p>
    <Button variant="primary" disabled={busy || !text.trim()} onClick={async () => {
      const next = await onConfirm(text);
      if (next) writeSaved(key, null);
    }}>{checkOnConfirm ? 'Confirm and check my answer' : 'This matches my answer'}</Button>
  </section>;
}
