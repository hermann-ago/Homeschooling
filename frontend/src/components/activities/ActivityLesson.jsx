import { Fragment, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ArrowUp, Camera, Coffee, MessageCircleQuestion, PencilLine } from 'lucide-react';
import { activitiesApi } from '../../api/activities';
import { tutorApi } from '../../api/tutor';
import { modeHref } from '../../api/mode';
import { Button } from '../../ui';
import { inputClasses } from '../../ui/classes';
import ActivityCard from './ActivityCards';
import ResponseCapture, { ConfirmResponse } from './ResponseCapture';
import { activityDefinition, needsResponse, responseStage, visibleActivities, practiceHistory } from './registry';
import { operationCommitted, operationId, readSaved, storageKey, writeSaved } from './durable';
import { learningLabel } from '../../utils/learningLabels';
import { AttemptNavigation, CatchUpNotice, ClosingSummary, LessonPosition } from './LessonOverview';
import { Celebration, ToFix } from './Progress';
import SnapWork from './SnapWork';
import LessonOptions from './LessonOptions';
import PageWorkCapture from './PageWorkCapture';
import BookCheck from './BookCheck';
import { focusLessonControl } from '../../utils/lessonFocus';
import { fitToText } from '../../utils/growingTextBox';

const responseText = (response) => response.confirmed_text || (typeof response.original === 'string' ? response.original : response.original?.text) || response.text || '';
const clean = (error) => (error?.message || String(error)).replace(/^\/[^:]+: /, '');

function SavedThread({ activity, excludeMessageId, showInitialPrompt = false,renderFeedback }) {
  const linkedMessages = new Set((activity.responses || []).map((response) => response.message_id));
  const entries = [
    ...(activity.responses || []).map((response, index) => ({ type: 'response', value: response,
      order: (response.support_snapshot?.dialogue_sequence ?? activity.messages?.find((message) => message.id === response.message_id)?.sequence ?? index) + 0.25 + index / 1000 })),
    ...(activity.messages || []).filter((message) => message.id !== excludeMessageId && (message.role !== 'student' || !linkedMessages.has(message.id))).map((message, index) => ({ type: 'message', value: message, order: message.sequence ?? 1000 + index })),
  ].sort((a, b) => a.order - b.order);
  // The question an answer replies to is the teacher's: it stands on the tutor side, once per change.
  const prompts = entries.filter((entry) => entry.type === 'response').map(({ value: response }) => {
    const interaction = activity.interactions?.find((item) => item.id === response.interaction_id);
    return [response.id, interaction?.sequence > 1 || showInitialPrompt ? interaction?.prompt || activity.content?.prompt : null];
  });
  const shownPrompts = new Map(prompts.map(([id, prompt], index) => [id, prompt && prompt !== prompts[index - 1]?.[1] ? prompt : null]));
  const promptFor = (response) => shownPrompts.get(response.id);
  return <div aria-live="polite" className="flex flex-col gap-2">
    {entries.map(({ type, value: response }) => type === 'message' ? <article key={response.id} className={`tutor-message is-${response.role === 'student' ? 'child' : 'tutor'} text-sm`}><p className="sr-only">{response.role === 'student' ? 'You' : 'Teacher'}</p><p className="whitespace-pre-wrap">{response.text}</p>{response.role==='teacher' && renderFeedback?.({message:response,history:true})}{response.evidence_ids?.map((id, index) => <a key={id} className="block text-action underline" href={modeHref(`/api/student-work/${encodeURIComponent(id)}`)} target="_blank" rel="noreferrer">Open original work photo {index + 1}</a>)}</article> : <Fragment key={response.id}>
      {(() => {
        const prompt = promptFor(response);
        return prompt ? <article className="tutor-message is-tutor text-sm"><p className="sr-only">Teacher</p><p className="whitespace-pre-wrap">{prompt}</p></article> : null;
      })()}
      <article className="tutor-message is-child is-answer text-sm">
      <p className="text-xs font-bold text-muted">Your {response.method === 'dictation' ? 'spoken answer' : response.method === 'written_steps' ? 'written steps' : 'answer'}</p>
      <p className="whitespace-pre-wrap mt-1">{responseText(response) || (response.evidence_ids?.length ? 'Photo answer' : 'Awaiting a readable answer')}</p>
      {response.confirmed_text && response.original?.text && response.confirmed_text !== response.original.text && <details className="mt-2"><summary className="text-xs cursor-pointer font-semibold">Original capture</summary><p className="mt-1 whitespace-pre-wrap">{response.original.text}</p></details>}
      {response.original?.reasoning && <p className="mt-2 whitespace-pre-wrap">Your thinking: {response.original.reasoning}</p>}
      {response.evidence_ids?.length > 0 && <p className="text-xs text-muted mt-2">{response.evidence_ids.length} original photo{response.evidence_ids.length === 1 ? '' : 's'} saved</p>}
      {response.evidence_ids?.map((id, index) => <a key={id} className="block mt-1 text-action underline text-xs" href={modeHref(`/api/student-work/${encodeURIComponent(id)}`)} target="_blank" rel="noreferrer">Open original work photo {index + 1}</a>)}
      <p className="text-xs text-muted mt-2">{response.source_disputed ? response.source_issue_acknowledged ? 'Source note saved · Not graded' : 'Source note · Not graded' : learningLabel(response.status)}{response.result ? ` · ${learningLabel(response.result)}` : ''}</p>
      {response.feedback && <p className="mt-2 whitespace-pre-wrap">{response.feedback}</p>}
    </article></Fragment>)}
  </div>;
}

// A question the child typed: it already stands in the conversation as their own message.
const isOwnQuestion = (activity) => Boolean(activity?.parent_activity_id && activity.origin === 'adaptive'
  && activity.kind === 'explain_or_observe' && activity.content?.title === 'Your question');

/** A tutor message from an earlier step: a long one shows its start and opens on request. */
function PastBubble({ children }) {
  const box = useRef(null);
  const [long, setLong] = useState(false);
  const [open, setOpen] = useState(false);
  useLayoutEffect(() => { if (box.current) setLong(box.current.scrollHeight > 260); }, []);
  return <div className="tutor-bubble">
    <div ref={box} className={long && !open ? 'tutor-bubble-clamp' : undefined}>{children}</div>
    {long && <button type="button" className="tutor-bubble-more" aria-expanded={open} onClick={() => setOpen((value) => !value)}>{open ? 'Show less' : 'Show more'}</button>}
  </div>;
}

/** A finished step, as in a chat: the tutor's message on the left, the child's replies on the right.
 *  Collapsed (the thread toggle), each step is one quiet line that opens on request. */
function ActivityHistory({ activity, activities, language, onSource, expanded, finished = false, ancestors = [],renderFeedback }) {
  if (ancestors.includes(activity.id)) return null;
  const children = activities.filter((item) => item.parent_activity_id === activity.id);
  const question = isOwnQuestion(activity);
  const label = question ? 'Your question' : activityDefinition(activity).label;
  const result = activity.status === 'skipped' ? 'To revisit' : activity.status === 'in_book' ? 'Done in the book' : activity.status === 'pending' ? finished ? 'Saved · Not completed' : 'In progress' : 'Completed';
  const body = <>{!question && <PastBubble><ActivityCard activity={activity} language={language} onSource={onSource} readOnly /></PastBubble>}<SavedThread activity={activity} renderFeedback={renderFeedback} />
    {children.map((child) => <ActivityHistory key={child.id} activity={child} activities={activities} language={language} onSource={onSource} expanded={expanded} finished={finished} ancestors={[...ancestors, activity.id]} renderFeedback={renderFeedback} />)}</>;
  if (expanded) return <div className="tutor-past">
    {!question && <p className="tutor-step-label">{label}{result !== 'Completed' && <span> · {result}</span>}</p>}
    {body}
  </div>;
  return <details className="tutor-past-step">
    <summary>{label} · {result}</summary>
    <div className="tutor-past-step-body">{body}</div>
  </details>;
}

function ParentReview({ response, busy, onEvent, sourceIssue = false }) {
  const [result, setResult] = useState('Unanswered');
  const [text, setText] = useState(responseText(response));
  const [note, setNote] = useState('');
  const [independent, setIndependent] = useState(false);
  const [assisted, setAssisted] = useState(false);
  return <details className="rounded-xl border border-attention bg-attention-soft p-3">
    <summary className="font-semibold cursor-pointer">{sourceIssue ? 'Review this answer together (optional)' : 'Inspect the original work together'}</summary>
    <div className="mt-3 flex flex-col gap-3 text-sm">
      <p>{sourceIssue ? 'You can optionally record your judgment about this answer. Continuing does not require a review.' : 'Check the actual page, spelling, calculations or diagram before assessing. Unclear or missing evidence stays unassessed.'}</p>
      <label className="font-semibold flex flex-col gap-1">Parent transcript<textarea rows={3} className={`${inputClasses} h-auto py-2 font-normal`} value={text} disabled={busy} onChange={(event) => setText(event.target.value)} /></label>
      <label className="font-semibold flex flex-col gap-1">Parent assessment<select className={inputClasses} value={result} disabled={busy} onChange={(event) => setResult(event.target.value)}>{['Unanswered', 'Correct', 'Partly correct', 'Not yet', 'Unreadable', 'Source disputed'].map((value) => <option key={value} value={value}>{value === 'Unanswered' ? 'Awaiting assessment' : value}</option>)}</select></label>
      <label className="font-semibold flex flex-col gap-1">What you checked<textarea rows={2} className={`${inputClasses} h-auto py-2 font-normal`} value={note} disabled={busy} maxLength={2000} onChange={(event) => setNote(event.target.value)} /></label>
      {!note.trim() && <p className="text-xs text-muted">Add a short note about what you checked to save a review.</p>}
      <label className="flex gap-2 items-start"><input type="checkbox" checked={independent} disabled={busy || assisted} onChange={(event) => setIndependent(event.target.checked)} />I observed an independent answer without substantive help</label>
      <label className="flex gap-2 items-start"><input type="checkbox" checked={assisted} disabled={busy} onChange={(event) => { setAssisted(event.target.checked); if (event.target.checked) setIndependent(false); }} />The learner received help or a supplied answer</label>
      <Button size="sm" disabled={busy || !note.trim()} onClick={() => onEvent('parent_review', { response_id: response.id, text, result, note, independently_observed: independent, assistance_used: assisted })}>Save parent review</Button>
    </div>
  </details>;
}

/** Chronological, server-owned lesson. Upcoming activity content never enters the DOM. */
// Steps that carry no typed answer: safe to send again on the refreshed lesson.
const SAFE_AGAIN = ['continue', 'reading_done', 'done_in_book', 'snap_work', 'fix_work', 'fix_later', 'retry_photo_check'];

export default function ActivityLesson({ sessionId, language = 'en-US', onState, onPauseNarration, onContinue, onRepeat, renderReading, renderSpokenText, renderNarration, renderFeedback, renderSessionControls, sessionNotice, onSource, getNarrationCursor, options, completionActions }) {
  const [state, setState] = useState(null);
  const stateRef = useRef(null);
  const [problem, setProblem] = useState('');
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState(() => readSaved(storageKey(sessionId, 'pending')));
  // Help belongs to one step: it closes when the lesson moves on.
  const [helpFor, setHelpFor] = useState(null);
  const [fullThread, setFullThread] = useState(true);
  const [triedAgain, setTriedAgain] = useState(null); // interaction where the grown-up asked for another go
  const [snapSlot, setSnapSlot] = useState(null);
  const [askFor, setAskFor] = useState(null);
  // Where a written answer sits (inside the text box) and where its button sits (the control row).
  const [answerSlot, setAnswerSlot] = useState(null);
  const [toolsSlot, setToolsSlot] = useState(null);
  const [submitSlot, setSubmitSlot] = useState(null);
  const [singleItemExercise, setSingleItemExercise] = useState(null);
  const [typing, setTyping] = useState(null); // the exercise answered here instead of with a photo
  const [following, setFollowing] = useState(true);
  const followingRef = useRef(true);
  const threadScroll = useRef(null);
  const threadContent = useRef(null);
  const activeHeading = useRef(null);
  const lessonPanel = useRef(null);
  const workbox = useRef(null);
  useLayoutEffect(() => {
    // A new step joins the conversation at its end. One taller than the view
    // starts at its own beginning; the rest of the conversation stays above it.
    const view = threadScroll.current, step = workbox.current;
    if (!view || !step) return;
    const tall = step.offsetHeight > view.clientHeight - 24;
    view.scrollTop = tall ? Math.max(0, step.offsetTop - 8) : view.scrollHeight;
    followingRef.current = !tall; setFollowing(!tall);
  }, [state?.active_activity?.id, state?.active_activity?.interaction?.id, state?.on_break, state?.page_work?.id, state?.page_work?.status]);
  useEffect(() => {
    if (busy || pending) return;
    const closing = state?.active_activity?.kind === 'close_lesson' || state?.status === 'completed';
    const panel = lessonPanel.current;
    const reading = state?.active_activity?.kind === 'read_source' && state.active_activity.status === 'pending';
    const next = !reading && panel?.querySelector('[data-lesson-primary]:not(:disabled), [aria-label="Lesson step controls"]:not([hidden]) button:not(:disabled):not([data-answer-submit])');
    // Native button focus gives Enter/Space their usual behavior, without a
    // global shortcut that could submit while the learner is writing.
    if (next && panel?.contains(document.activeElement) && document.activeElement.matches('textarea, input, select, [contenteditable="true"]')) return;
    const target = next || (closing ? panel?.querySelector('[aria-label="What you did in this lesson"] h2') : null) || panel?.querySelector('[aria-label="Exercise answers"] textarea, [aria-label="Answer capture"] textarea, [aria-label="Answer capture"] input[type="radio"], [aria-label="Answer capture"] select[data-matching]') || activeHeading.current;
    focusLessonControl(target, activeHeading.current);
  }, [state?.active_activity?.id, state?.active_activity?.interaction?.id, state?.active_activity?.interaction?.status, state?.active_activity?.kind, state?.active_activity?.status, state?.status, state?.on_break, state?.page_work?.status, busy, Boolean(pending)]);
  useLayoutEffect(() => {
    if (followingRef.current && threadScroll.current) threadScroll.current.scrollTop = threadScroll.current.scrollHeight;
  }, [state, busy, pending, problem]);
  useEffect(() => {
    if (!threadContent.current || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(() => {
      if (followingRef.current && threadScroll.current) threadScroll.current.scrollTop = threadScroll.current.scrollHeight;
    });
    observer.observe(threadContent.current);
    return () => observer.disconnect();
  }, [Boolean(state)]);
  const callbacks = useRef({ onState, onPauseNarration, onContinue, getNarrationCursor });
  useEffect(() => { callbacks.current = { onState, onPauseNarration, onContinue, getNarrationCursor }; }, [onState, onPauseNarration, onContinue, getNarrationCursor]);
  const queue = useRef(Promise.resolve());
  const sending = useRef(false);
  const pendingKey = storageKey(sessionId, 'pending');
  const update = useCallback((next, background = false) => {
    if (!next) return;
    const before = stateRef.current;
    const samePlace = background && before && before.active_activity?.id === next.active_activity?.id
      && before.active_activity?.interaction?.id === next.active_activity?.interaction?.id && Boolean(before.on_break) === Boolean(next.on_break);
    stateRef.current = next; setState(next);
    if (next.error) setProblem(next.error);
    callbacks.current.onState?.(next);
    if (!samePlace && (next.on_break || next.active_activity && next.active_activity.kind !== 'read_source')) callbacks.current.onPauseNarration?.();
    const saved = readSaved(pendingKey);
    if (operationCommitted(next, saved)) { writeSaved(pendingKey, null); setPending(null); }
  }, [pendingKey]);
  const refresh = useCallback(async () => {
    try { const next = await activitiesApi.state(sessionId); update(next); return next; }
    catch (error) { setProblem(clean(error)); return null; }
  }, [sessionId, update]);
  useEffect(() => {
    let cancelled = false; let loading = false; let failedLoad = '';
    const load = async () => {
      if (loading) return; loading = true;
      try {
        const next = await activitiesApi.state(sessionId);
        if (!cancelled && failedLoad) {
          const recovered = failedLoad; failedLoad = '';
          setProblem((previous) => previous === recovered ? '' : previous);
        }
        if (!cancelled && (!stateRef.current || next.revision !== stateRef.current.revision || next.event_cursor !== stateRef.current.event_cursor ||
            next.tutor_activity_access !== stateRef.current.tutor_activity_access ||
            JSON.stringify(next.attempt_navigation) !== JSON.stringify(stateRef.current.attempt_navigation))) update(next, true);
      } catch (error) { if (!cancelled) { failedLoad = clean(error); setProblem(failedLoad); } }
      finally { loading = false; }
    };
    stateRef.current = null; setState(null); setPending(readSaved(pendingKey));
    load(); const timer = window.setInterval(load, 4000);
    // While a photo is being checked, look for its result more often.
    const quick = window.setInterval(() => { if (stateRef.current?.checking) load(); }, 1500);
    return () => { cancelled = true; window.clearInterval(timer); window.clearInterval(quick); };
  }, [sessionId, pendingKey, update]);

  const execute = useCallback((command) => {
    if (sending.current) return Promise.resolve(null);
    sending.current = true;
    const fixing = Boolean(stateRef.current?.active_activity?.fix);
    const work = async (retry = true) => {
      setBusy(true); setProblem(''); callbacks.current.onPauseNarration?.();
      // Persist the exact operation before transport. A retry replays this object.
      writeSaved(pendingKey, command); setPending(command);
      try {
        const next = await activitiesApi.event(sessionId, command);
        writeSaved(pendingKey, null); setPending(null); update(next);
        if (command.type === 'request_hint' && next.error) {
          writeSaved(pendingKey, command); setPending(command);
        }
        if (['continue', 'acknowledge_source_issue', 'advance_stage', 'acknowledge_return', 'reveal', 'go_back', 'restart_lesson', 'done_in_book'].includes(command.type)
            || command.type === 'snap_work' && !fixing
            || command.type === 'parent_check' && command.payload?.result === 'checked') callbacks.current.onContinue?.(next);
        return next;
      } catch (error) {
        setProblem(clean(error));
        const next = await activitiesApi.state(sessionId).catch(() => null);
        if (next) update(next);
        if (error.status === 409 && retry && next && !operationCommitted(next, command) && SAFE_AGAIN.includes(command.type)
            && next.active_activity?.id === command.activity_id && (next.active_activity?.interaction?.id || null) === (command.interaction_id || null)) {
          // Only the revision moved (a photo check finished): the same step, sent once more.
          command = { ...command, expected_revision: next.revision };
          return work(false);
        }
        if (error.status === 409 && !operationCommitted(next, command)) {
          // A rejected revision did not run. Keep the answer draft and ask the
          // child to retry on the refreshed activity, never silently resubmit it.
          writeSaved(pendingKey, null); setPending(null);
          setProblem('Your saved place changed. Review the current activity and send your answer again; your draft is preserved.');
        } else if (error.status >= 400 && error.status < 500 && error.status !== 408) {
          writeSaved(pendingKey, null); setPending(null);
        }
        return null;
      } finally { sending.current = false; setBusy(false); }
    };
    const result = queue.current.catch(() => {}).then(() => work()); queue.current = result; return result;
  }, [pendingKey, sessionId, update]);
  const event = useCallback((type, payload = {}) => {
    if (readSaved(pendingKey)) { setProblem('Recover the saved action below before starting another action.'); return Promise.resolve(null); }
    const current = stateRef.current; const activity = current?.active_activity;
    if (!current || !activity) return Promise.resolve(null);
    if (type === 'request_hint') {
      const saved = current.pending_support_commands?.find((command) => command.activity_id === activity.id && command.interaction_id === activity.interaction?.id && (command.payload.kind || 'hint') === (payload.kind || 'hint'));
      if (saved) return execute({ ...saved, expected_revision: current.revision });
    }
    if (['take_break', 'request_followup', 'request_hint', 'go_back', 'restart_lesson'].includes(type)) {
      callbacks.current.onPauseNarration?.();
      const cursor = callbacks.current.getNarrationCursor?.();
      if (cursor) payload = { ...payload, cursor };
    }
    return execute({ operation_id: operationId(), expected_revision: current.revision, activity_id: activity.id,
      interaction_id: activity.interaction?.id, type, payload });
  }, [execute, pendingKey]);
  const saveDraft = useCallback(async (activityId, interactionId, draft) => {
    const current = stateRef.current;
    if (sending.current || !current || current.on_break || current.active_activity?.id !== activityId ||
        current.active_activity?.interaction?.id !== interactionId) return;
    try {
      const saved = await activitiesApi.event(sessionId, { operation_id: operationId(), expected_revision: current.revision,
        activity_id: activityId, interaction_id: interactionId, type: 'save_draft', payload: draft });
      return saved.active_activity?.draft_revision;
    } catch (error) {
      if (error.status === 409) setProblem('This draft changed on another device. Your local answer is preserved; review it before sending.');
      // The browser copy remains durable while disconnected. A changed prompt
      // cannot receive this draft because identity is checked on the server.
      return null;
    }
  }, [sessionId]);
  const upload = async (file) => {
    setBusy(true); setProblem(''); callbacks.current.onPauseNarration?.();
    try {
      const current = stateRef.current;
      const result = await tutorApi.attachWork(sessionId, current.revision, file, current.active_activity.id);
      await refresh();
      return result.evidence_id || result.id;
    } catch (error) { setProblem(clean(error)); throw error; }
    finally { setBusy(false); }
  };
  const snap = async (file) => {
    callbacks.current.onPauseNarration?.();
    try {
      const attach = () => tutorApi.attachWork(sessionId, stateRef.current.revision, file, stateRef.current.active_activity.id);
      let saved;
      try { saved = await attach(); } catch (error) {
        if (error.status !== 409 || !await refresh()) throw error;
        saved = await attach();
      }
      await refresh();
      return Boolean(await event('snap_work', { evidence_ids: [saved.evidence_id || saved.id] }));
    } catch (error) { setProblem(clean(error)); return false; }
  };
  if (!state) return <section className="p-4" aria-label="Tutor activities">{problem ? <><p role="alert" className="text-problem">{problem}</p><Button size="sm" onClick={refresh}>Try opening the lesson again</Button></> : <p role="status">Opening your saved lesson…</p>}</section>;
  const activity = state.active_activity;
  const helpKey = activity ? `${activity.id}.${activity.interaction?.id || ''}` : null;
  const helpOpen = helpKey !== null && helpFor === helpKey;
  const setHelpOpen = (next) => setHelpFor((typeof next === 'function' ? next(helpOpen) : next) ? helpKey : null);
  const definition = activityDefinition(activity);
  const status = activity?.interaction?.status;
  const stage = responseStage(activity);
  const responses = activity?.responses || [];
  const currentResponses = responses.filter((item) => !activity?.interaction?.id || !item.interaction_id || item.interaction_id === activity.interaction.id);
  const response = [...currentResponses].reverse().find((item) => item.status !== 'assessed') || currentResponses.at(-1);
  const awaitingConfirmation = status === 'awaiting_confirmation' || response?.status === 'awaiting_confirmation';
  const awaitingAssessment = response?.answer_only_recheck_available || ['ready_to_assess', 'assessment_pending', 'assessment_failed'].includes(status) || !status && ['confirmed', 'assessment_pending', 'assessment_failed'].includes(response?.status);
  const parentReview = !response?.answer_only_recheck_available && activity?.status === 'pending' && (status === 'parent_review' || response?.status === 'parent_review');
  const sourceIssue = parentReview && response?.source_disputed;
  const awaitingReveal = status === 'awaiting_reveal' || String(stage) === 'awaiting_reveal';
  const workedReady = activity?.kind !== 'worked_example' || ['practice', 'complete'].includes(stage);
  const directCapture = activity?.direct_capture ?? (activity?.content?.evidence_requirement === 'spelling' && activity.content.response_modes?.includes('text'));
  const physicalReady = directCapture || activity?.kind !== 'request_book_work' || ['capture', 'response', 'awaiting_confirmation', 'ready_to_assess', 'completed'].includes(String(stage)) || activity.physical_complete;
  const paced = Boolean(activity?.paced);
  const snapKey = activity ? `${activity.id}.${activity.interaction?.id || ''}` : null;
  // Book work is answered with a photo unless the child chooses to answer here.
  const snapMode = Boolean(activity?.snap) && typing !== snapKey && !state.page_work?.id && !state.on_break;
  const captures = !paced && !snapMode && activity && needsResponse(activity) && activity.status === 'pending' && (!status || ['awaiting_input', 'awaiting_followup'].includes(status) || directCapture && status === 'awaiting_work') && !awaitingConfirmation && !awaitingAssessment && !parentReview && !awaitingReveal && workedReady && physicalReady;
  const currentMessages = activity?.interaction?.is_replay || activity?.interaction?.replay_of
    ? (activity.messages || []).filter((item) => item.sequence > activity.interaction.dialogue_start_sequence)
    : activity?.messages || [];
  const latestFeedback = [...currentMessages].reverse().find((item) => item.role === 'teacher');
  // As in a chat, answers to the question on screen follow it (checked or not); only answers
  // to an earlier question of this step stand above it.
  const archivedResponses = responses.filter((item) => item.interaction_id && activity?.interaction?.id && item.interaction_id !== activity.interaction.id);
  const archivedResponseIds = new Set(archivedResponses.map((item) => item.id));
  const linkedStudentIds = new Set(responses.map((item) => item.message_id));
  const archivedMessages = (activity?.messages || []).filter((item) => item.id !== latestFeedback?.id && !(item.role === 'student' && linkedStudentIds.has(item.id)));
  const archivedActivity = activity && { ...activity, responses: archivedResponses, messages: archivedMessages };
  const pendingActivity = activity && { ...activity, responses: responses.filter((item) => !archivedResponseIds.has(item.id)), messages: [] };
  const sectionPlace=activity?.practice_section?.id || activity?.id;
  const exercisePreview = !state.page_work?.id && state.page_work?.exercise && singleItemExercise !== activity?.id
    ? { ...state.page_work.exercise, status: 'ready' } : null;
  const workGroup = snapMode ? null : state.page_work?.id ? state.page_work : exercisePreview;
  // Hands-on book work: a grown-up looks at the book and confirms, instead of Continue.
  const parentCheck = !paced && activity?.kind === 'explain_or_observe' && activity.content?.parent_check && activity.status === 'pending';
  const canContinue = activity && (activity.can_continue_discussion || activity.status !== 'pending' || status === 'ready_to_continue' && !needsResponse(activity) && workedReady) && (activity.kind !== 'read_source' || activity.status !== 'pending');
  const unfinished = state.activities?.filter((item) => item.status === 'skipped').length || 0;
  const history = visibleActivities(state);
  const groupedIds = new Set([...history.map((item) => item.id), ...(activity ? [activity.id] : [])]);
  const modes = activity?.content?.response_modes || [];
  // As in a chat, any written answer goes in the text box at the bottom; the card above it
  // holds only what the child picks or fills in (choices, answer boxes, matching).
  const plainAnswer = Boolean(captures && !workGroup && !activity.content?.blanks && !activity.content?.matching
    && (['text', 'written_steps', 'device_dictation', 'audio'].some((mode) => modes.includes(mode))
      || ['written_steps', 'handwriting', 'diagram'].includes(activity.content?.evidence_requirement)));
  const canAsk = Boolean(activity && !definition.internal && !state.on_break && state.status !== 'completed' && state.status !== 'superseded'
    && ['pending', 'answered'].includes(activity.status) && !['close_lesson', 'take_break_and_return'].includes(activity.kind) && !activity.parent_activity_id);
  const working = busy || Boolean(pending);
  // While a written answer is open, the child can switch the box to a question and back.
  const askInstead = plainAnswer && askFor === snapKey;
  // The child's own question already stands in the conversation as their message.
  const ownQuestion = isOwnQuestion(activity);
  const blockRepeat = (keyEvent) => { if (keyEvent.repeat && ['Enter', ' '].includes(keyEvent.key)) keyEvent.preventDefault(); };
  const mainStep = !paced && !snapMode && !parentCheck && (state.on_break || sourceIssue || activity?.kind === 'read_source' && activity.status === 'pending'
    || canContinue && definition.family !== 'unsupported' && definition.family !== 'break');
  // What the child answers with sits in the dock, above the text box (as a question
  // card does in a chat app); the tutor's words stay in the conversation.
  const pageWorkInDock = Boolean(workGroup && ['ready', 'capture', 'confirmation'].includes(workGroup.status));
  const pageWork = workGroup && <PageWorkCapture inConversation={pageWorkInDock} key={workGroup.id || activity.id} group={workGroup} sessionId={sessionId} draftIdentity={`${activity.id}.${activity.interaction?.id}`} onUpload={upload} onEvent={async (type, payload) => { if(type === 'close_page_work') setSingleItemExercise(activity.id); return event(type, payload); }} onSingleItem={() => setSingleItemExercise(activity.id)} busy={working} draftEvidence={(state.draft_evidence || []).filter(file => file.action_id === activity?.id)} />;
  const checkOnConfirm = activity?.kind !== 'predict_then_check' || activity.interaction?.stage === 'reflection';
  const answerPanel = state.on_break ? null : pageWorkInDock ? pageWork
    : !workGroup && captures && !(plainAnswer && askInstead) ? <ResponseCapture compact key={`${activity.id}.${activity.interaction?.id || stage}`} sessionId={sessionId} activity={activity} language={language} draftEvidence={state.draft_evidence || []} busy={working} onPauseNarration={onPauseNarration} onUpload={upload} onSaveDraft={(draft) => saveDraft(activity.id, activity.interaction?.id, draft)} onSubmit={(payload) => event('submit_response', payload)}
      submitSlot={submitSlot} toolsSlot={toolsSlot} {...(plainAnswer ? { textSlot: answerSlot } : {})} />
    : !workGroup && awaitingConfirmation && response ? <>
      <ConfirmResponse key={response.id} sessionId={sessionId} language={language} response={response} busy={working} checkOnConfirm={checkOnConfirm} submitSlot={submitSlot} onConfirm={(text) => event('confirm_response', { response_id: response.id, text, ...(checkOnConfirm ? { assess_after_confirm: true } : {}) })} />
      {response.transcription_status === 'failed' && <Button size="sm" disabled={working} onClick={() => event('retry_transcription', { response_id: response.id })}>Retry saved photo transcription</Button>}
      {response.evidence_ids?.length > 0 && <Button size="sm" variant="quiet" disabled={working} onClick={() => event('request_parent_review', { response_id: response.id })}>Ask a parent to inspect this photo</Button>}
    </> : null;
  const composer = state.status !== 'completed' && state.status !== 'superseded' && <TutorComposer sessionId={sessionId} language={language} canAsk={canAsk} busy={working} onPauseNarration={onPauseNarration}
    answering={plainAnswer && !askInstead && !state.on_break} onAnswerSlot={setAnswerSlot} onToolsSlot={setToolsSlot}
    onAsk={(text) => event('request_followup', { prompt: text })} />;
  return <section ref={lessonPanel} aria-label="Tutor activities" className="tutor-chat">
    <header className="tutor-chat-header">
      <LessonPosition state={state} header busy={working} canFix={Boolean(activity) && !activity.fix && !state.on_break && state.status !== 'completed'}
        onFix={(id) => event('fix_work', { activity_id: id })} onRetry={(id) => event('retry_photo_check', { activity_id: id })} />
      <div className="tutor-header-actions">
        {activity && !state.on_break && <button type="button" className="tutor-icon-button" aria-label="Take a break" title="Take a break" disabled={working} onClick={() => event('take_break')}><Coffee size={18} aria-hidden="true" /></button>}
        <LessonOptions>
          {renderSessionControls && <div className="flex flex-col gap-2"><p className="text-xs font-semibold text-muted">Voice and reading speed</p>{renderSessionControls({ activity, state, busy: working, inMenu: true })}</div>}
          <div className="flex flex-col gap-2">
            <Button size="sm" variant="quiet" data-close-options disabled={working || !state.can_go_back} onClick={() => event('go_back')}>Go back one step</Button>
            <Button size="sm" variant="quiet" data-close-options disabled={working || state.status === 'superseded' || state.status === 'completed' && !onRepeat} onClick={() => state.status === 'completed' ? onRepeat?.({ fromBeginning: true }) : event('restart_lesson')}>Start lesson over</Button>
            <p className="text-xs text-muted">Earlier answers, hints and feedback stay saved in your lesson thread.</p>
          </div>
          {options}
          <AttemptNavigation navigation={state.attempt_navigation} />
          <label className="flex items-start gap-3 text-sm"><input type="checkbox" className="mt-1 accent-[var(--color-action)]" checked={Boolean(state.playback?.tutor_activity_access)} disabled={busy} onChange={async (change) => {
            setBusy(true); setProblem('');
            try { await activitiesApi.access(sessionId, change.target.checked); await refresh(); }
            catch (error) { setProblem(clean(error)); }
            finally { setBusy(false); }
          }} /><span>Allow desktop tutor for this lesson<span className="block text-xs text-muted mt-1">The connected tutor can inspect this session and prepare supported activities. Student answers and parent assessments stay on family devices.</span></span></label>
        </LessonOptions>
      </div>
    </header>
    {sessionNotice}
    <div className="tutor-thread-wrap">
      <div ref={threadScroll} className="tutor-thread custom-scrollbar" aria-label="Lesson conversation" tabIndex={0} onScroll={() => {
        const el = threadScroll.current;
        const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        followingRef.current = nearBottom; setFollowing(nearBottom);
      }}>
        <div ref={threadContent} className="tutor-thread-content">
          {history.length > 0 && <section aria-label="Saved lesson thread" className="tutor-history">
            <button type="button" className="tutor-history-toggle" onClick={() => setFullThread((value) => !value)}>{fullThread ? 'Collapse lesson thread' : 'Show full lesson thread'}</button>
            {practiceHistory(history.filter((item) => !groupedIds.has(item.parent_activity_id))).map((group) => group.section ? <details key={group.key} open={fullThread || undefined}><summary>{group.section.title} · {group.items.length} items</summary><div className="flex flex-col gap-4 mt-3">{group.items.map((completed) => <ActivityHistory key={completed.id} activity={completed} activities={history} language={language} onSource={onSource} expanded={fullThread} renderFeedback={renderFeedback} />)}</div></details>
              : <ActivityHistory key={group.key} activity={group.items[0]} activities={history} language={language} onSource={onSource} expanded={fullThread} renderFeedback={renderFeedback} />)}
          </section>}
          {activity && (archivedResponses.length > 0 || archivedMessages.length > 0 || history.some((item) => item.parent_activity_id === activity.id)) && <section aria-label="Earlier exchanges in this activity" className="flex flex-col gap-3">
            <SavedThread activity={archivedActivity} showInitialPrompt renderFeedback={renderFeedback} />
            {history.filter((item) => item.parent_activity_id === activity.id).map((completed) => <ActivityHistory key={completed.id} activity={completed} activities={history} language={language} onSource={onSource} expanded renderFeedback={renderFeedback} />)}
          </section>}
          <section ref={workbox} aria-label="Current lesson action" className="tutor-current-step">
      {state.on_break ? <section aria-label="Lesson break" className="flex flex-col gap-2"><h2 className="font-semibold">Your place is saved</h2><p className="text-sm">Take your break. Your pending activity and original answers will be here when you return.</p></section> : <>
        <CatchUpNotice state={state} busy={working} onFocus={() => event('focus_unfinished')} />
        {activity?.kind === 'close_lesson' && activity.status === 'pending' && <ToFix progress={state.progress} checking={Boolean(state.checking)} busy={working}
          onFix={(id) => event('fix_work', { activity_id: id })} onRetry={(id) => event('retry_photo_check', { activity_id: id })} />}
        {activity?.kind === 'close_lesson' && activity.status === 'pending' && state.book_check?.count > 0 && <BookCheck check={state.book_check} sessionId={sessionId} onUpload={upload} onEvent={event} busy={working} />}
        <ClosingSummary state={state} busy={working} onRepeat={onRepeat} onRevisit={(activityId) => event('revisit_activity', { activity_id: activityId })} />
            {workGroup ? <><p className="tutor-step-label">{workGroup.scope === 'exercise' ? `Exercise · ${workGroup.items.length} parts together` : state.page_work?.id ? `Book page ${state.page_work.items[0]?.page} · ${state.page_work.items.length} answers together` : 'Book work together'}</p>
              {pageWorkInDock ? <div className="tutor-bubble">{workGroup.instruction && <p className="font-semibold whitespace-pre-wrap">{workGroup.instruction}</p>}<p className={workGroup.instruction ? 'mt-2 text-sm' : undefined}>Answer {workGroup.items.length === 1 ? 'it' : `all ${workGroup.items.length} parts`} in the box below.</p></div> : pageWork}</> : activity && !definition.internal ? <article key={sectionPlace} aria-label="Current tutor activity" className="tutor-current">
              {activity.practice_section && !snapMode && <progress className="tutor-step-progress" max={activity.practice_section.total} value={activity.practice_section.completed} aria-label={`${activity.practice_section.completed} of ${activity.practice_section.total} items saved`} />}
              {!ownQuestion && <p className="tutor-step-label"><span ref={activeHeading} tabIndex={-1} className="focus-visible:outline-action">{activity.content?.video ? 'Video lesson' : definition.label}</span>{activity.practice_section && <span> · {activity.practice_section.title} {activity.practice_section.item} of {activity.practice_section.total}</span>}{needsResponse(activity) && !['required_book', 'required', 'book'].includes(activity.origin) && <span> · {activity.origin === 'review' ? 'Review' : 'Extra practice'}</span>}</p>}
              {!ownQuestion && <div className="tutor-bubble"><ActivityCard activity={activity} state={state} language={language} busy={working} onEvent={event} onSource={onSource} renderReading={renderReading} renderSpokenText={renderSpokenText} docked /></div>}
              {activity.review_after_video && activity.status === 'pending' && <div className="tutor-note flex flex-col gap-2">
                <p className="text-sm">You watched the video. This is the book's mini lesson on the same idea: read it as a quick review, or skip ahead.</p>
                <Button size="sm" className="self-start" disabled={working} onClick={() => event('reading_done')}>Skip the review</Button>
              </div>}
              <SavedThread activity={pendingActivity} />
              {activity.responses?.filter((saved) => saved.key_recheck_available).map((saved) => <Button key={saved.id} size="sm" disabled={working} onClick={() => event('recheck_key', { response_id: saved.id })}>Recheck this answer against the book key</Button>)}
              {latestFeedback && <article aria-label="Latest teacher reply" className="tutor-reply text-sm"><p className="whitespace-pre-wrap">{latestFeedback.text}</p>{renderFeedback?.({message:latestFeedback,state,activity})}</article>}
            </article> : state.status === 'superseded' ? <div className="flex flex-col gap-3"><p role="status" className="text-sm text-muted">This earlier script and its lesson thread are saved.</p>{state.attempt_navigation?.resume_repeat && <Button as="a" variant="primary" href={modeHref(state.attempt_navigation.resume_repeat.path)}>Open the updated lesson</Button>}</div> : <p role="status" className="text-sm text-muted">{state.status === 'completed' || state.legacy?.status === 'completed' ? `Lesson saved.${unfinished ? ` ${unfinished} activities remain to revisit.` : ''}` : 'Your teacher is preparing the next activity.'}</p>}
      </>}
      {state.status === 'completed' && completionActions}
      {!state.on_break && !workGroup && <>{state.orientation && <div className="flex flex-col gap-2" role="status"><p className="text-sm">{typeof state.orientation === 'string' ? state.orientation : state.orientation.text || 'Welcome back. Return to the activity where you paused.'}</p><Button size="sm" disabled={working} onClick={() => event('acknowledge_return')}>Continue with this activity</Button></div>}{activity && !definition.internal && <>
        {activity.fix && activity.status === 'pending' && <div role="status" className="tutor-note is-attention text-sm flex flex-col gap-1">
          <p className="font-semibold">Let’s look at this one again</p>
          {activity.fix.read && <p>I read in your photo: {activity.fix.read}</p>}
          {activity.fix.feedback && <p className="whitespace-pre-wrap">{activity.fix.feedback}</p>}
        </div>}
        {snapMode && <p role="status" className="tutor-hint">{activity.fix ? 'Fix it in your book, then take a new photo.' : 'Do this in your book, then take a photo. It is checked while you keep going.'}</p>}
        {!snapMode && state.page_work?.available_count > 1 && <div className="tutor-note flex flex-col gap-2"><p className="text-sm">You can photograph these {state.page_work.available_count} book questions together.</p><Button disabled={working} onClick={() => event('open_page_work')}>Send this page together</Button></div>}
        {paced && <p role="status" className="tutor-hint">Do this in your book, then press <strong>Done</strong>. A grown-up checks the book later.</p>}
        {!paced && !snapMode && activity.kind === 'request_book_work' && !physicalReady && activity.status === 'pending' && <Button data-lesson-primary variant="primary" disabled={working} onKeyDown={blockRepeat} onClick={() => event('physical_complete')}>I have finished writing in my book</Button>}
        {awaitingAssessment && response && <div className="flex flex-col gap-2">
          <p className="text-sm text-muted">{response.feedback_failure === 'invalid_reply'
            ? response.feedback_replacement_used ? 'The replacement reply could not be checked. Your answer stays saved. Leave this activity to revisit; it is not marked wrong.' : 'The AI reply could not be checked. Request one replacement with its provider cost tracked; your saved answer and any help stay unchanged.'
            : response.feedback_failure === 'provider_quota' ? 'Your answer is saved. The AI account is out of credits, so a grown-up needs to add credits before this answer can be checked.'
            : 'Your answer is saved. Checking it will keep the original attempt and any help separate.'}</p>
          <Button variant="primary" disabled={working || response.feedback_failure === 'invalid_reply' && response.feedback_replacement_used} onClick={() => event('assess', { response_id: response.id, ...(response.feedback_failure === 'invalid_reply' && !response.feedback_replacement_used ? { replace_invalid_reply: true } : {}) })}>{response.feedback_failure === 'invalid_reply' ? response.feedback_replacement_used ? 'Replacement needs review' : 'Generate replacement feedback' : status === 'assessment_failed' || status === 'assessment_pending' ? 'Retry feedback for this answer' : 'Check my answer'}</Button>
        </div>}
        {sourceIssue && <div role="status" className="tutor-note text-sm"><p className="font-semibold">A note about the book</p><p className="mt-1">The sources disagree on this detail. Your answer is saved and is not marked wrong. You can keep going.</p></div>}
        {parentReview && response && <>{!sourceIssue && <p className="text-sm text-attention">This work needs a parent to check the actual source or written evidence. It is not marked wrong.</p>}<ParentReview key={response.id} response={response} sourceIssue={sourceIssue} busy={working} onEvent={event} /></>}
        {awaitingReveal && <Button variant="primary" disabled={working} onClick={() => event('reveal')}>Check my prediction</Button>}
        {definition.family === 'break' && <Button variant="primary" disabled={working} onClick={() => event('take_break')}>Save my place and take a break</Button>}
        {activity.kind === 'close_lesson' && <Celebration progress={state.progress} />}
        {!state.learning_summary && activity.kind === 'close_lesson' && activity.content?.unfinished?.length > 0 && <div><p className="font-semibold">Work to return to</p><ul className="list-disc pl-5 text-sm">{activity.content.unfinished.map((text, i) => <li key={i}>{text}</li>)}</ul></div>}
        {definition.family === 'unsupported' && <p role="alert">This activity needs a supported definition. Ask a parent to review it; no learner result has been inferred.</p>}
        {activity.can_continue_discussion && <p className="text-sm text-muted">You can continue with this explanation, or add more to your answer if you want.</p>}
        {activity.kind === 'close_lesson' && <p role="status" className="text-sm text-muted">Your work is saved. Choose Finish lesson to mark this chapter complete in Curriculum. Any work left to revisit stays in your record.</p>}
        {parentCheck && <p role="status" className="tutor-hint">{triedAgain === activity.interaction?.id ? 'Have another go, then show your book again.' : 'When you are done, show your book to a grown-up.'}</p>}
        {activity.status === 'pending' && !['close_lesson', 'take_break_and_return'].includes(activity.kind) && <div className="lesson-help">
          {/* After a miss, the teaching set aside by "Let me try first" is one tap away. */}
          {activity.teaching_available && (activity.responses?.length > 0 || activity.parent_activity_id) && <button type="button" className="tutor-chip" disabled={working} onClick={() => event('show_teaching')}>Show me how</button>}
          <button type="button" className="tutor-chip" aria-expanded={helpOpen} aria-controls={`help-${activity.id}`} disabled={working} onClick={() => setHelpOpen((open) => !open)}>{helpOpen ? 'Close help' : 'Help'}</button>
          {needsResponse(activity) && !paced && (activity.fix
            ? <button type="button" className="tutor-chip" disabled={working} onClick={() => event('fix_later')}>Back to the lesson</button>
            : <button type="button" className="tutor-chip" disabled={working} onClick={() => event('skip')}>Skip for now</button>)}
          {!needsResponse(activity) && activity.can_try_first && <button type="button" className="tutor-chip" disabled={working} onClick={() => event('try_first')}>Let me try first</button>}
          {helpOpen && <div id={`help-${activity.id}`} role="group" aria-label="Help choices" className="tutor-help-choices">
            {activity.teaching_available && !activity.responses?.length && !activity.parent_activity_id && <button type="button" className="tutor-chip" disabled={working} onClick={() => { setHelpOpen(false); event('show_teaching'); }}>Show me the lesson first</button>}
            {(needsResponse(activity) && !paced || activity.kind === 'read_source') && [['explain', 'Explain it another way'], ['example', 'Show me an example'], ['hint', 'Give me a hint']].map(([kind, label]) =>
              <button type="button" key={kind} className="tutor-chip" disabled={working || !['awaiting_input', 'awaiting_followup', 'ready_to_assess', 'awaiting_work', ...(activity.kind === 'read_source' ? ['ready_to_continue'] : [])].includes(status)}
                onClick={() => { setHelpOpen(false); event('request_hint', { kind }); }}>{label}</button>)}
            {!paced && activity.kind === 'request_book_work' && activity.origin === 'required_book' && !activity.assignment_item_id &&
              <button type="button" className="tutor-chip" disabled={working} onClick={() => { setHelpOpen(false); event('parent_check', { result: 'checked' }); }}>A grown-up checked this in the book</button>}
            <p className="text-xs text-muted basis-full">You can also ask your tutor anything in the box below.</p>
          </div>}
        </div>}
      </>}</>}
          </section>
        </div>
      </div>
      {!following && <button className="tutor-latest" onClick={() => { followingRef.current = true; setFollowing(true); threadScroll.current.scrollTop = threadScroll.current.scrollHeight; }}>↓ Back to latest</button>}
    </div>
    <footer className="tutor-dock">
      <div ref={setSnapSlot} className="tutor-snap-slot" />
      {pending && !busy && <div role="alert" className="tutor-note is-attention flex flex-col gap-2"><p className="text-sm">An action is saved on this browser. Recover its result before sending anything else.</p><Button size="sm" onClick={() => execute(pending)}>Recover saved action</Button>{pending.type === 'request_hint' && <Button size="sm" variant="quiet" onClick={() => { writeSaved(pendingKey, null); setPending(null); setProblem('This help request is kept for later. Your answer is safe; choosing the same help again recovers that request.'); }}>Leave this help request for later</Button>}</div>}
      {busy && <p role="status" className="tutor-dock-status">Saving your work and preparing the next response…</p>}
      {state.notice && <p role="status" className="tutor-dock-status text-attention">{state.notice}</p>}
      {problem && <p role="alert" className="tutor-dock-status text-problem">{problem}</p>}
      {/* As in a chat app: the text box never moves; what a step asks for opens as a card above it. */}
      <div className="tutor-dock-input">
        {answerPanel && <div className="tutor-dock-card custom-scrollbar" role="region" aria-label="Your answer to this step">{answerPanel}</div>}
        {composer}
      </div>
      <div className="tutor-controls">
        {renderNarration && !state.on_break && <div className="tutor-narration">{renderNarration({ activity, state, busy: working })}</div>}
        {plainAnswer && canAsk && <button type="button" className="tutor-icon-button" aria-pressed={askInstead} disabled={working}
          aria-label={askInstead ? 'Write my answer instead' : 'Ask the tutor a question instead'} title={askInstead ? 'Write my answer instead' : 'Ask a question instead'}
          onClick={() => setAskFor(askInstead ? null : snapKey)}>{askInstead ? <PencilLine size={18} aria-hidden="true" /> : <MessageCircleQuestion size={18} aria-hidden="true" />}</button>}
        {Boolean(activity?.snap) && !snapMode && !state.on_break && !state.page_work?.id && <button type="button" className="tutor-icon-button" aria-label="Take a photo instead" title="Take a photo instead" disabled={working} onClick={() => setTyping(null)}><Camera size={18} aria-hidden="true" /></button>}
        <div className="tutor-controls-main" aria-label="Lesson step controls">
          <div ref={setSubmitSlot} className="contents" />
          {snapMode && <SnapWork key={snapKey} busy={working} onSnap={snap} viewSlot={snapSlot} onType={() => setTyping(snapKey)}
            label={activity.fix ? 'New photo' : activity.practice_section?.total > 1 ? `Photo of all ${activity.practice_section.total - activity.practice_section.item + 1}` : 'Photo of my work'} />}
          {paced && !state.on_break && <Button data-lesson-primary variant="primary" disabled={working} onKeyDown={blockRepeat} onClick={() => event('done_in_book')}>
            {activity.practice_section?.total > 1 ? `Done · all ${activity.practice_section.total - activity.practice_section.item + 1} in my book` : 'Done in my book'}
          </Button>}
          {parentCheck && !state.on_break && <>
            <Button variant="primary" disabled={working} onClick={() => event('parent_check', { result: 'checked' })}>✓ Looks good</Button>
            <Button disabled={working} onClick={async () => { if (await event('parent_check', { result: 'try_again' })) setTriedAgain(activity.interaction?.id); }}>Let&apos;s try again</Button>
          </>}
          {mainStep && <Button variant="primary" disabled={working || activity?.kind === 'close_lesson' && Boolean(state.checking) && !state.on_break} onKeyDown={blockRepeat} onClick={() => event(state.on_break ? 'resume' : sourceIssue ? 'acknowledge_source_issue' : activity.kind === 'read_source' && activity.status === 'pending' ? 'reading_done' : activity.kind === 'close_lesson' ? 'finish' : 'continue', sourceIssue ? { response_id: response.id } : {})}>
            {state.on_break ? 'Return to lesson' : state.page_work?.status === 'completed' ? 'Continue lesson' : activity.kind === 'read_source' && activity.status === 'pending' ? 'I have finished this reading' : activity.kind === 'close_lesson' ? state.checking ? 'Checking your photos…' : 'Finish lesson' : activity.fix ? 'Back to the lesson' : activity.practice_section?.item < activity.practice_section?.total ? activity.practice_section.kind==='spelling' ? 'Next word' : 'Next item' : 'Continue lesson'}
          </Button>}
        </div>
      </div>
    </footer>
  </section>;
}

/** The always-ready text box, as in a chat: a question for the tutor at any step.
 *  Enter sends; Shift+Enter starts a new line. */
function TutorComposer({ sessionId, language, canAsk, busy, onAsk, onPauseNarration, answering = false, onAnswerSlot, onToolsSlot }) {
  const key = storageKey(sessionId, 'composer-question');
  const [text, setText] = useState(() => readSaved(key)?.text || '');
  const box = useRef(null);
  useEffect(() => { writeSaved(key, text ? { text } : null); }, [key, text]);
  useLayoutEffect(() => {
    fitToText(box.current);
  }, [text]);
  const send = async () => {
    const value = text.trim();
    if (!value || busy || !canAsk) return;
    onPauseNarration?.();
    if (await onAsk(value)) { setText(''); writeSaved(key, null); }
  };
  // Other ways to answer (photo, voice, a parent's check) sit as icons inside the box.
  const tools = <div ref={onToolsSlot} className="tutor-composer-tools" role="group" aria-label="Other ways to answer" />;
  if (answering) return <div className="tutor-composer-box" data-answering><div ref={onAnswerSlot} className="tutor-composer-slot" />{tools}</div>;
  return <form aria-label="Message your tutor" className="tutor-composer-box" onSubmit={(formEvent) => { formEvent.preventDefault(); void send(); }}>
    <textarea ref={box} rows={1} lang={language} maxLength={2000} value={text} disabled={!canAsk} aria-label="Ask your tutor"
      placeholder={canAsk ? 'Ask your tutor anything…' : 'You can ask a question during a lesson step'}
      onChange={(change) => setText(change.target.value)}
      onKeyDown={(keyEvent) => {
        if (keyEvent.key !== 'Enter' || keyEvent.shiftKey || keyEvent.nativeEvent.isComposing || keyEvent.keyCode === 229) return;
        keyEvent.preventDefault(); void send();
      }} />
    {tools}
    <button type="submit" className="tutor-composer-send" aria-label="Ask" disabled={busy || !canAsk || !text.trim()}><ArrowUp size={18} aria-hidden="true" /></button>
  </form>;
}
