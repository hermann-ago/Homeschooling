import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Camera, MessageCircle } from 'lucide-react';
import { tutorApi } from '../api/tutor';
import { modeHref } from '../api/mode';
import ReadAlong from './ReadAlong';
import FeedbackVoice from './FeedbackVoice';
import LessonAudioReplay from './LessonAudioReplay';
import { Button } from '../ui';
import RegistryGuidedLesson from './activities/RegistryGuidedLesson';

const newId = () => (crypto.randomUUID?.() || `answer-${Date.now()}-${Math.random().toString(16).slice(2)}`);

function LegacyInteractiveGuidedLesson({ guide, learner, topic, session, slotId, closed, resumeLesson,
  activeIndex, onActiveIndex, language, onStarted, onFinished, onPassageModeChange }) {
  const [state, setState] = useState(null);
  const stateRef = useRef(null);
  const indexRef = useRef(null);
  useEffect(() => { indexRef.current = activeIndex; }, [activeIndex]);
  const queue = useRef(Promise.resolve());
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');
  const [answer, setAnswer] = useState('');
  const [evidenceIds, setEvidenceIds] = useState([]);
  const [resumeToken, setResumeToken] = useState(0);
  const [preview, setPreview] = useState(true);
  const [previewAction, setPreviewAction] = useState(null);
  const [previewedActions, setPreviewedActions] = useState([]);
  const [previewRestart, setPreviewRestart] = useState(0);
  const [audioReplay, setAudioReplay] = useState(false);
  const photoRef = useRef(null);
  const actionRef = useRef(null);
  const client = useQueryClient();
  useEffect(() => { actionRef.current?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' }); },
    [state?.playback?.action_id, state?.messages?.length]);
  const update = useCallback((next) => {
    stateRef.current = next;
    setState(next);
    if (next.draft_evidence) setEvidenceIds(next.draft_evidence.map((e) => e.id));
    if (next.error) setProblem(next.error);
  }, []);
  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    tutorApi.conversation(session).then((next) => {
      if (cancelled) return;
      update(next);
      if (next.playback) onActiveIndex(next.playback.sentence_index);
    }).catch((e) => { if (!cancelled) setProblem(e.message); });
    return () => { cancelled = true; };
  }, [session, update]);

  // Queue position saves and student actions so they always use the newest committed revision.
  const perform = useCallback((kind, data = {}, showBusy = true) => {
    const work = async () => {
      const current = stateRef.current;
      if (!current) return null;
      if (showBusy) setBusy(true);
      setProblem('');
      try {
        const next = await tutorApi.interactiveAction(current.session_id, kind, { ...data, expected_revision: current.revision });
        update(next);
        return next;
      } catch (e) {
        setProblem(e.message);
        if (e.status === 409) update(await tutorApi.conversation(current.session_id));
        return null;
      } finally { if (showBusy) setBusy(false); }
    };
    const result = queue.current.catch(() => {}).then(work);
    queue.current = result;
    return result;
  }, [update]);

  const start = async (answerNow = false) => {
    setBusy(true);
    setProblem('');
    try {
      const next = await tutorApi.startInteractive(learner, topic, guide.guide_id, slotId);
      update(next);
      onActiveIndex(next.playback.sentence_index);
      onStarted(next.session_id);
      if (answerNow && !next.playback.action_id) {
        const first = guide.actions.find((a) => next.actions.some((saved) => saved.action_id === a.id && saved.status === 'pending'));
        if (first) {
          const stopped = await perform('playback', { sentence_index: first.end_sentence + 1, action_id: first.id });
          if (stopped) onActiveIndex(first.end_sentence);
        }
      }
    } catch (e) { setProblem(e.message.replace(/^\/[^:]+: /, '')); }
    finally { setBusy(false); }
  };
  const reachedAction = useCallback((id, index) => {
    onActiveIndex(index - 1);
    return perform('playback', { sentence_index: index, action_id: id });
  }, [perform, onActiveIndex]);
  const readingEnded = useCallback(() => perform('playback', {
    sentence_index: guide.sentences.length, reading_finished: true,
  }), [perform, guide.sentences.length]);

  useEffect(() => {
    if (!session || closed || audioReplay) return undefined;
    const savePosition = () => {
      const current = stateRef.current;
      const index = indexRef.current;
      if (index !== null && current?.playback && !current.playback.action_id && current.status !== 'completed' &&
          index !== current.playback.sentence_index) perform('playback', { sentence_index: index }, false);
    };
    const timer = setInterval(savePosition, 5000);
    const hide = () => { if (document.visibilityState === 'hidden') savePosition(); };
    document.addEventListener('visibilitychange', hide);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', hide); };
  }, [session, closed, audioReplay, perform]);

  const submit = async () => {
    const next = await perform('answer', { action_id: state.playback.action_id, message_id: newId(), text: answer, evidence_ids: evidenceIds });
    if (next) { setAnswer(''); setEvidenceIds([]); }
  };
  const retry = () => {
    const failed = [...state.messages].reverse().find((m) => m.role === 'student' && m.action_id === state.playback.action_id && m.status !== 'assessed');
    if (failed) perform('answer', { action_id: failed.action_id, message_id: failed.id, retry: true });
  };
  const upload = async (file) => {
    if (!file) return;
    const savedSize = (stateRef.current?.draft_evidence || []).reduce((sum, e) => sum + (e.size_bytes || 0), 0);
    if (savedSize + file.size > 10 * 1024 * 1024) {
      setProblem('Please choose smaller photos. Each answer can include up to 10 MB of photos.');
      return;
    }
    const work = async () => {
      setBusy(true);
      setProblem('');
      try {
        await tutorApi.attachWork(stateRef.current.session_id, stateRef.current.revision, file, stateRef.current.playback.action_id);
        update(await tutorApi.conversation(stateRef.current.session_id));
      } catch (e) { setProblem(e.message); }
      finally { setBusy(false); }
    };
    queue.current = queue.current.catch(() => {}).then(work);
  };
  const continueLesson = async () => {
    const next = await perform('continue');
    if (next && !next.playback.action_id) {
      onActiveIndex(next.playback.resume_index);
      if (!next.playback.reading_finished) setResumeToken((t) => t + 1);
    }
  };
  const finish = async () => {
    const next = await perform('interactive-finish');
    if (next) {
      await client.invalidateQueries();
      onFinished();
    }
  };
  if (!session || !state?.playback) return <div className="flex flex-col">
    <div className="flex flex-col gap-4 p-5">
    {guide.audio?.some((track) => ['ready', 'legacy'].includes(track.status)) && <p role="status" className="text-sm font-semibold text-action">Guided lesson audio saved · replay adds no generation cost.</p>}
    <p className="text-sm text-muted">Reading stops at student activities. Start the lesson to type an answer, add a photo or ask for help. Previewing alone saves no learner progress.</p>
    {guide.adaptive_context?.warmup && <p className="text-sm text-muted">This lesson starts with a saved recall question: {guide.adaptive_context.warmup.next_prompt}</p>}
    {guide.adaptive_context && !guide.adaptive_context.fresh && <p className="text-xs text-muted">The learner record has changed. Starting refreshes relevant recall work; the saved reading and its recordings stay reusable.</p>}
    {resumeLesson && <p className="text-sm text-muted">Your place in {resumeLesson.title} stays saved while you start this lesson.</p>}
    <Button variant="primary" disabled={busy || closed || !guide.actions?.length} onClick={() => start()}>{busy ? 'Opening…' : session ? 'Resume lesson' : 'Start lesson'}</Button>
    <Button size="sm" variant="quiet" aria-expanded={preview} onClick={() => { setPreview((v) => !v); setProblem(''); }}>{preview ? 'Hide reading preview' : 'Show reading preview'}</Button>
    <Button size="sm" disabled={busy} onClick={() => {
      setPreviewAction(null); setPreviewedActions([]); setResumeToken(0);
      onActiveIndex(0); setPreviewRestart((value) => value + 1); setPreview(true);
    }}>Restart audio</Button>
    {!guide.actions?.length && <p className="text-sm text-muted">Update this guided lesson to add student activities.</p>}
    {problem && <p role="alert" className="text-sm text-problem">{problem}</p>}
    </div>
    {preview && <div><ReadAlong key={previewRestart} passage={guide} tracks={guide.audio} activeIndex={activeIndex}
      onActiveIndex={onActiveIndex} disabled={closed || busy || Boolean(previewAction)} language={language} onPassageModeChange={onPassageModeChange}
      pendingActions={(guide.actions || []).filter((a) => !previewedActions.includes(a.id)).map((a) => a.id)}
      maxSeekIndex={guide.actions?.find((a) => !previewedActions.includes(a.id))?.end_sentence}
      onAction={(id) => { setPreviewAction(guide.actions.find((a) => a.id === id)); }} resumeToken={resumeToken}
      renderAction={(id) => previewAction?.id === id ? <section aria-label="Preview student activity" className="mt-3 flex flex-col gap-3 border-t border-action/30 pt-3">
        <p className="text-sm font-semibold">Reading paused · your turn</p>
        <p className="text-sm text-muted">Start answering to receive tutor feedback. The lesson begins at its first unfinished activity.</p>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="primary" disabled={busy || closed} onClick={() => start(true)}>Start answering</Button>
          {resumeLesson && <a href={modeHref(resumeLesson.path)} className="text-sm font-semibold text-action underline">Resume unfinished lesson</a>}
          <Button size="sm" disabled={busy || closed} onClick={() => {
            setPreviewedActions((ids) => [...ids, previewAction.id]);
            onActiveIndex(previewAction.resume_index ?? previewAction.end_sentence + 1);
            setPreviewAction(null); setResumeToken((t) => t + 1);
          }}>Continue preview without answering</Button>
        </div>
      </section> : null} /></div>}
  </div>;
  const action = state.actions.find((a) => a.action_id === state.playback.action_id);
  const messages = state.messages.filter((m) => m.action_id === action?.action_id);
  const failed = messages.some((m) => m.role === 'student' && m.status !== 'assessed');
  const planned = guide.actions?.some((a) => a.id === action?.action_id);
  const pendingActions = state.actions.filter((a) => a.status === 'pending').map((a) => a.action_id);
  const firstPending = guide.actions?.find((a) => pendingActions.includes(a.id));
  if (audioReplay) return <LessonAudioReplay guide={guide} language={language}
    onClose={() => setAudioReplay(false)} onPassageModeChange={onPassageModeChange} />;
  const actionPanel = action && <section ref={actionRef} aria-label="Student activity" className="mt-3 flex flex-col gap-3 rounded-xl border border-action/30 bg-surface p-3.5">
    {(!planned || action.next_prompt && action.next_prompt !== action.prompt) && <p className="font-semibold text-[15px]">{action.next_prompt || action.prompt}</p>}
    {!planned && <FeedbackVoice key={action.action_id} session={state.session_id} message={{ id: action.action_id, text: action.prompt }} language={language} action />}
    <p className="text-xs text-muted">Reading paused · continue when you are ready.</p>
    {action.exercise && <div className="rounded-lg bg-paper p-3 flex flex-col gap-2">
      <p className="text-xs font-semibold text-muted">{action.exercise.book_name} · page {action.exercise.printed_page || action.exercise.pages.join(', ')} · exercise {action.exercise.reference}</p>
      <p className="text-sm whitespace-pre-wrap">{action.exercise.prompt}</p>
      {action.exercise.student_safe && <a href={modeHref(`/api/exercises/${action.exercise.id}/preview?version_id=${action.exercise.version_id}`)} target="_blank" rel="noreferrer" className="text-sm font-semibold text-action">Open exercise page</a>}
    </div>}
    <div aria-live="polite" className="flex flex-col gap-2.5">
      {messages.map((m) => <div key={m.id} className={m.role === 'student' ? 'rounded-lg bg-paper p-3 text-sm whitespace-pre-line' : 'text-sm leading-relaxed whitespace-pre-line'}>
        <span className="block text-[11px] font-bold text-muted mb-1">{m.role === 'student' ? 'You' : 'Teacher'}</span>
        {m.text || 'Photo answer'}{m.evidence_ids?.length > 0 && <span className="block text-xs text-muted mt-1">{m.evidence_ids.length} photo{m.evidence_ids.length > 1 ? 's' : ''} attached</span>}
        {m.role === 'teacher' && m.text && <FeedbackVoice session={session} message={m} language={language} />}
      </div>)}
    </div>
    {action.status === 'pending' && <>
      <label className="sr-only" htmlFor="student-answer">Your answer or question</label>
      <textarea id="student-answer" value={answer} onChange={(e) => setAnswer(e.target.value)} maxLength={4000} rows={3}
        placeholder={action.kind === 'question' ? 'What would you like to ask?' : 'Your answer…'} disabled={busy}
        className="w-full rounded-xl border border-line bg-paper/40 p-3 text-sm focus-visible:outline-action" />
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="primary" disabled={busy || failed || (!answer.trim() && !evidenceIds.length)} onClick={submit}>{busy ? 'Saving and thinking…' : 'Send answer'}</Button>
        <Button size="sm" icon={Camera} disabled={busy || failed || evidenceIds.length >= 5} onClick={() => photoRef.current?.click()}>Add photo</Button>
        <input ref={photoRef} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" className="hidden" aria-label="Photo of your work"
          onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ''; }} />
      </div>
      {evidenceIds.length > 0 && <p className="text-xs text-action">{evidenceIds.length} photo{evidenceIds.length > 1 ? 's' : ''} ready to send.</p>}
    </>}
    {failed && action.status === 'pending' && <Button size="sm" disabled={busy} onClick={retry}>Retry feedback</Button>}
    {problem && <p role="alert" className="text-sm text-problem">{problem}</p>}
    <div className="flex flex-wrap gap-2">
      {action.status === 'pending' && <Button size="sm" variant="quiet" disabled={busy} onClick={() => perform('skip')}>Skip for now</Button>}
      {action.status !== 'pending' && <Button variant="primary" disabled={busy} onClick={continueLesson}>Continue lesson</Button>}
    </div>
    {action.status === 'skipped' && <p className="text-xs text-muted">Saved to revisit later.</p>}
  </section>;
  return <div className="flex flex-col">
    <div className="px-4 py-3 border-b border-line flex flex-col gap-2">
      <Button size="sm" disabled={busy} onClick={() => setAudioReplay(true)}>Listen from beginning</Button>
      {action && <p className="text-xs text-muted">Playback is paused for this activity. You can listen again without changing your saved place.</p>}
      {state.status === 'completed' ? <><p className="font-semibold text-action">Lesson saved</p><p className="text-sm whitespace-pre-line">{state.summary}</p></> : <>
        <span className="text-xs text-muted">Your answers and progress are saved automatically.</span>
        {!action && !closed && <Button size="sm" icon={MessageCircle} disabled={busy} onClick={() => perform('playback', { sentence_index: activeIndex ?? 0, ask_question: true })}>Ask a question</Button>}
        {state.can_finish && !closed && <Button variant="primary" disabled={busy} onClick={finish}>Finish lesson</Button>}
      </>}
      {!action && problem && <p role="alert" className="text-sm text-problem">{problem}</p>}
      {!planned && actionPanel}
    </div>
    <ReadAlong passage={guide} tracks={guide.audio.filter((t) => t.synchronized)} activeIndex={activeIndex} onActiveIndex={onActiveIndex} language={language}
      onPassageModeChange={onPassageModeChange}
      disabled={closed || busy || Boolean(action) || state.status === 'completed'} onAction={reachedAction} onReadingEnd={readingEnded}
      pendingActions={pendingActions} maxSeekIndex={firstPending?.end_sentence} resumeToken={resumeToken}
      renderAction={(id) => id === action?.action_id ? actionPanel : null} />
  </div>;
}
export default function InteractiveGuidedLesson(props) {
  return props.guide?.activity_contract_version && props.guide?.activities?.length
    ? <RegistryGuidedLesson {...props} />
    : <LegacyInteractiveGuidedLesson {...props} />;
}
