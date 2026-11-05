import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Pause, Play } from 'lucide-react';
import { activitiesApi } from '../../api/activities';
import { tutorApi } from '../../api/tutor';
import { modeHref } from '../../api/mode';
import WarmUpCard from './WarmUpCard';
import { Button } from '../../ui';
import { pauseNarration } from '../../utils/narration';
import { focusLessonControl } from '../../utils/lessonFocus';
import { nextStepButton, pressable, useSpaceBar } from '../../utils/spaceBar';
import { NARRATION_SPEEDS } from '../../utils/narrationSettings';
import ReadAlong from '../ReadAlong';
import LessonVoiceStatus from '../LessonVoiceStatus';
import LessonAudioReplay from '../LessonAudioReplay';
import ActivityLesson from './ActivityLesson';
import LessonOptions from './LessonOptions';
import FeedbackVoice from '../FeedbackVoice';
import SessionNarrationControls from './SessionNarrationControls';
import { operationId, readSaved, storageKey, writeSaved } from './durable';
import { narrationPlace, narrationRange } from './narrationRange';

function ActivityReading({ activity, state, guide, activeIndex, onActiveIndex, language,
  onPassageModeChange, complete, onCursor, headless = false, autoPlayRequest = 0, onTransport, selectedSource, selectedSpeed }) {
  const key = storageKey(state.session_id, `narration.${activity.id}.${activity.interaction?.id || 'legacy'}`);
  const start = activity.start_sentence ?? 0;
  const end = activity.end_sentence ?? guide.sentences.length - 1;
  const [savedCursor] = useState(() => {
    const candidates = [readSaved(key), state.playback.narration_cursor,
      !(activity.interaction?.is_replay || activity.interaction?.replay_of) && readSaved(storageKey(state.session_id, `narration.${activity.id}`))];
    return candidates.find((item) => item && Number.isInteger(item.sentence_index) &&
      item.sentence_index >= start && item.sentence_index <= end) || null;
  });
  const latest = useRef({ state, activity });
  const cursor = useRef(savedCursor);
  const timer = useRef(null);
  const saving = useRef(false);
  const place = narrationPlace(activity);
  const transportChanged = useCallback((next) => onTransport?.({ ...next, place }), [onTransport, place]);
  useEffect(() => { latest.current = { state, activity }; }, [state, activity]);
  useEffect(() => {
    onActiveIndex(Math.max(start, Math.min(end, savedCursor?.sentence_index ?? start)));
  }, [activity.id, start, end, savedCursor, onActiveIndex]);
  const save = useCallback(async () => {
    const current = latest.current;
    if (!cursor.current || saving.current || current.state.on_break || current.activity.status !== 'pending') return;
    saving.current = true;
    try {
      await activitiesApi.event(current.state.session_id, { operation_id: operationId(),
        expected_revision: current.state.revision, activity_id: current.activity.id,
        interaction_id: current.activity.interaction?.id, type: 'save_cursor', payload: cursor.current });
    } catch {
      // Local cursor is already durable. The next explicit activity event checks
      // the server revision, and refresh reconciles the authoritative activity.
    } finally { saving.current = false; }
  }, []);
  const changed = useCallback((next) => {
    cursor.current = next; writeSaved(key, next); onCursor(next, activity.id);
    if (!timer.current) timer.current = window.setTimeout(() => { timer.current = null; save(); }, 1000);
  }, [key, onCursor, save, activity.id]);
  useEffect(() => {
    const hide = () => { if (document.visibilityState === 'hidden') save(); };
    document.addEventListener('visibilitychange', hide);
    return () => { window.clearTimeout(timer.current); document.removeEventListener('visibilitychange', hide); };
  }, [save]);
  return <div className="-mx-3">
    <ReadAlong passage={guide} tracks={(guide.audio || []).filter((track) => track.synchronized)}
      activeIndex={activeIndex} onActiveIndex={onActiveIndex} language={language}
      rangeStart={start} rangeEnd={end} visibleThrough={end} savedCursor={savedCursor}
      onCursorChange={changed} onPassageModeChange={onPassageModeChange}
      settingsInHeader selectedSource={selectedSource} selectedSpeed={selectedSpeed}
      externalControls headless={headless} autoPlayRequest={autoPlayRequest} onTransport={transportChanged}
      disabled={state.on_break || activity.status !== 'pending'} onReadingEnd={complete} />
  </div>;
}

/** Keeps the original book reader while the shared activity engine owns progress. */
/** An unfinished session runs an earlier script than the one now prepared: the family chooses. */
export function EarlierVersionChoice({ earlier, guide, busy, closed, onOpen }) {
  const [command] = useState(() => ({ operation_id: operationId(), expected_revision: earlier.revision, guide_id: earlier.updated_guide_id || guide.guide_id }));
  return <div className="flex flex-col gap-2 rounded-xl border border-line p-3">
    <p className="text-sm">This lesson was started with an earlier version. A newer version has been prepared since then.</p>
    <Button data-lesson-start variant="primary" disabled={busy || closed} onClick={() => onOpen(command)}>{busy ? 'Opening the updated lesson…' : 'Start the updated lesson'}</Button>
    <Button as="a" href={modeHref(earlier.path)}>Continue the earlier version</Button>
    <p className="text-xs text-muted">Answers from the earlier version stay saved either way.</p>
  </div>;
}

export default function RegistryGuidedLesson({ guide, learner, topic, session, slotId, closed, resumeLesson, earlierVersion, warmUp,
  activeIndex, onActiveIndex, language, onStarted, onFinished, onPassageModeChange, onSource, lessonOptions, onVoiceBuilt }) {
  const [startedSession, setStartedSession] = useState(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');
  const [replay, setReplay] = useState(false);
  const sessionId = session || startedSession;
  const settingsKey = storageKey(sessionId || guide.guide_id, 'narration-settings');
  const [settings, setSettings] = useState(() => readSaved(settingsKey, { source: null, speed: 1 }));
  const settingsRef = useRef(settings);
  useEffect(() => {
    const saved = readSaved(settingsKey);
    if (saved) { settingsRef.current = saved; setSettings(saved); }
    else writeSaved(settingsKey, settingsRef.current);
  }, [settingsKey]);
  const changeSettings = useCallback((patch) => {
    if (patch.source) pauseNarration();
    const next = { ...settingsRef.current, ...patch };
    settingsRef.current = next; setSettings(next); writeSaved(settingsKey, next);
  }, [settingsKey]);
  const tracks = (guide.audio || []).filter((track) => track.synchronized && ['ready', 'legacy'].includes(track.status));
  const selectedSource = settings.source === 'device' || tracks.some((track) => track.track_id === settings.source)
    ? settings.source : tracks.find((track) => track.preferred)?.track_id || tracks[0]?.track_id || 'device';
  const selectedSpeed = NARRATION_SPEEDS.includes(settings.speed) ? settings.speed : 1;
  const completed = useRef(false);
  const [finished, setFinished] = useState(Boolean(closed));
  const [navigation, setNavigation] = useState(null);
  const readingCursor = useRef(null);
  const activeActivity = useRef(null);
  const activeInteraction = useRef(null);
  const currentSession = useRef(sessionId);
  const [transport, setTransport] = useState(null);
  const transportRef = useRef(null);
  const activePlace = useRef('');
  useEffect(() => { transportRef.current = transport; }, [transport]);
  // Space: pause or resume this step's voice; once it has finished, move on.
  useSpaceBar((target) => {
    const voice = transportRef.current;
    if (sessionId && voice && voice.place === activePlace.current && voice.available && !voice.ended) { voice.toggle(); return true; }
    if (pressable(target)) return false;
    const next = nextStepButton();
    if (!next) return false;
    next.click();
    return true;
  });
  useEffect(() => {
    // When the voice finishes, the next-step button waits under the finger.
    if (!transport?.ended || transport.place !== activePlace.current) return;
    if (document.activeElement?.closest?.('textarea, input, select, [contenteditable="true"]')) return;
    const next = nextStepButton();
    if (next) focusLessonControl(next);
  }, [transport?.ended, transport?.place]);
  const [playRequest, setPlayRequest] = useState(null);
  const [feedbackRequest,setFeedbackRequest]=useState(null);
  const seenReplies=useRef(null);
  const feedbackVoice=tracks.find((track)=>track.track_id===selectedSource);
  const playSequence = useRef(0);
  const advance = useCallback((next) => {
    if (next?.active_activity) setPlayRequest({ session: next.session_id, place: narrationPlace(next.active_activity), token: ++playSequence.current });
  }, []);
  useEffect(() => {
    currentSession.current = sessionId; completed.current = false;
    readingCursor.current = null; activeActivity.current = null; activeInteraction.current = null; setFinished(false); setNavigation(null);
    seenReplies.current=null;setFeedbackRequest(null);
  }, [sessionId]);
  const client = useQueryClient();
  const handleState = useCallback((next) => {
    if (next.session_id !== currentSession.current) return;
    setNavigation(next.attempt_navigation || null);
    const activity = next.active_activity;
    activePlace.current = narrationPlace(activity);
    const messages=(activity?.messages || []).filter((message)=>!(activity.interaction?.is_replay || activity.interaction?.replay_of) || message.sequence>activity.interaction.dialogue_start_sequence);
    const reply=[...messages].reverse().find((message)=>message.role==='teacher');
    if (seenReplies.current && reply && !seenReplies.current.has(reply.id)) setFeedbackRequest({sessionId:next.session_id,id:reply.id});
    // Restored, revisited and late historical replies remain available on demand.
    seenReplies.current ||= new Set();
    for (const saved of next.activities || []) for (const message of saved.messages || []) if (message.role==='teacher') seenReplies.current.add(message.id);
    if (activeActivity.current !== activity?.id || activeInteraction.current !== activity?.interaction?.id) {
      activeActivity.current = activity?.id;
      activeInteraction.current = activity?.interaction?.id;
      readingCursor.current = next.playback.narration_cursor;
      if (activity?.start_sentence !== undefined && activity.start_sentence !== null) onActiveIndex(activity.start_sentence);
    }
    if (next.status === 'completed' && !completed.current) {
      setFinished(true);
      completed.current = true; client.invalidateQueries(); onFinished?.();
    }
  }, [client, onActiveIndex, onFinished]);
  const setCursor = useCallback((cursor, activityId) => {
    if (activeActivity.current === activityId) readingCursor.current = cursor;
  }, []);
  const getCursor = useCallback(() => readingCursor.current, []);
  const reading = useCallback(({ activity, state, complete }) => <ActivityReading
    key={`${state.session_id}.${narrationPlace(activity)}`} activity={activity} state={state} guide={guide}
    activeIndex={activeIndex} onActiveIndex={onActiveIndex} language={language}
    onPassageModeChange={onPassageModeChange} complete={complete} onCursor={setCursor}
    onTransport={setTransport} autoPlayRequest={playRequest?.session === state.session_id && playRequest.place === narrationPlace(activity) ? playRequest.token : 0}
    selectedSource={selectedSource} selectedSpeed={selectedSpeed} />,
  [guide, activeIndex, onActiveIndex, language, onPassageModeChange, setCursor, playRequest, selectedSource, selectedSpeed]);
  const sessionControls = ({ activity, state, busy }) => <SessionNarrationControls tracks={tracks} source={selectedSource} speed={selectedSpeed}
    onChange={changeSettings} onReplay={() => transport?.replay?.()}
    canReplay={Boolean(!busy && !state.on_break && transport?.place === narrationPlace(activity) && transport.available && transport.replay)}
    error={transport?.place === narrationPlace(activity) ? transport.error : null} />;
  // The tutor's commentary, sentence by sentence, marking the one being spoken.
  const teacherText = (activity) => {
    const range = narrationRange(guide, activity);
    if (!range) return null;
    const speaking = transport?.place === narrationPlace(activity) && transport.playing;
    return guide.sentences.slice(range.start, range.end + 1).map((sentence, offset) => {
      const index = range.start + offset;
      return <span key={index}>
        {offset > 0 && (sentence.paragraphBoundary ? '\n\n' : ' ')}
        <span aria-current={speaking && index === activeIndex ? 'true' : undefined}>{sentence.text}</span>
      </span>;
    });
  };
  const narration = ({ activity, state, busy }) => {
    if (!activity || state.status === 'completed') return null;
    const range = narrationRange(guide, activity);
    const available = Boolean(!busy && range && transport?.place === narrationPlace(activity) && transport.available);
    const playing = available && transport.playing;
    const unrecorded = Boolean(range && transport?.place === narrationPlace(activity) && transport.unrecorded);
    const preparing = ['queued', 'running', 'aligning'].includes(guide.voice_preparation?.status);
    const voiceError = guide.voice_preparation?.error;
    const preparationProgress = Number.isInteger(guide.voice_preparation?.completed_parts) && guide.voice_preparation.parts
      ? ` · ${guide.voice_preparation.completed_parts} of ${guide.voice_preparation.parts} ${guide.voice_preparation.alignment === 'local' ? 'audio blocks synchronized' : 'passages saved'}` : '';
    const voiceLabel = activity.kind === 'read_source' && ['answered', 'completed'].includes(activity.status) ? 'Reading saved · Continue when you are ready'
      : !range ? 'Text only · No saved narration for this step'
      : unrecorded ? playing ? 'Device voice · This passage only' : 'This passage has no saved recording. You can listen with device voice or keep reading yourself.'
      : playing ? 'Reading aloud'
      : available && transport.recorded ? 'Saved lesson voice · Autoplay on next step'
      : guide.voice_preparation?.status === 'aligning' ? `Synchronizing the saved voice with the lesson…${preparationProgress}`
      : guide.voice_preparation?.status === 'alignment_review' ? 'The voice is saved. Its synchronization needs review before playback.'
      : voiceError?.includes('daily request allowance') ? voiceError
      : preparing ? `Preparing the saved lesson voice…${preparationProgress}`
      : voiceError ? voiceError.includes('429') ? 'Google voice paused: quota or rate limit. Try preparing it later.' : 'Voice preparation paused. Your lesson is saved.'
      : available ? 'Device voice · Play to listen' : 'Text only · No saved narration for this step';
    // A step without narration shows nothing; routine voice states need no words.
    // A step with a recording still mounts its hidden reader: that reader loads
    // the audio and reports when it is available.
    if (!range && voiceLabel === 'Text only · No saved narration for this step') return null;
    const routine = ['Reading aloud', 'Saved lesson voice · Autoplay on next step', 'Reading saved · Continue when you are ready', 'Device voice · Play to listen', 'Text only · No saved narration for this step'].includes(voiceLabel);
    return <div className="tutor-narration-controls">
      {range && activity.kind !== 'read_source' && <ActivityReading key={`${state.session_id}.${narrationPlace(activity)}`} headless
        activity={{ ...activity, start_sentence: range.start, end_sentence: range.end }} state={state} guide={guide}
        activeIndex={activeIndex} onActiveIndex={onActiveIndex} language={language} complete={() => {}} onCursor={setCursor}
        selectedSource={selectedSource} selectedSpeed={selectedSpeed}
        onTransport={setTransport} autoPlayRequest={playRequest?.session === state.session_id && playRequest.place === narrationPlace(activity) ? playRequest.token : 0} />}
      <p className={routine ? 'sr-only' : 'text-xs text-muted'}>{voiceLabel}</p>
      <button type="button" className={unrecorded && !playing ? 'tutor-device-passage-button' : 'tutor-narration-button'} aria-label={playing ? 'Pause narration' : unrecorded ? 'Use device voice for this passage' : 'Play narration'} disabled={!available || state.on_break} onClick={() => transport?.toggle()}>{playing ? <Pause aria-hidden="true" size={20} fill="currentColor" /> : unrecorded ? 'Use device voice' : <Play aria-hidden="true" size={20} fill="currentColor" />}</button>
    </div>;
  };
  const start = async () => {
    if (busy || closed) return;
    setBusy(true); setProblem(''); pauseNarration();
    try {
      const next = await tutorApi.startInteractive(learner, topic, guide.guide_id, slotId, 1);
      advance(next);
      setStartedSession(next.session_id); onStarted?.(next.session_id);
    } catch (error) { setProblem(error.message); }
    finally { setBusy(false); }
  };
  const repeat = async (options = {}) => {
    if (busy || !sessionId) return;
    setBusy(true); setProblem(''); pauseNarration();
    const key = storageKey(sessionId, options.unfinishedOnly ? 'continue-unfinished' : options.fromBeginning ? 'repeat-from-beginning' : 'repeat');
    const command = readSaved(key) || { operation_id: operationId(), ...(options.unfinishedOnly ? { unfinished_only: true } : { from_beginning: true }) };
    writeSaved(key, command);
    try {
      const next = await activitiesApi.repeat(sessionId, command);
      setStartedSession(next.session_id); onStarted?.(next.session_id);
      writeSaved(key, null);
    } catch (error) {
      if (error.status >= 400 && error.status < 500) writeSaved(key, null);
      setProblem(error.message);
    } finally { setBusy(false); }
  };
  if (replay) return <LessonAudioReplay guide={guide} language={language}
    onClose={() => { pauseNarration(); setReplay(false); }} onPassageModeChange={onPassageModeChange} />;
  const options = <>
    <div><label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={settings.feedbackAudio !== false} onChange={(event)=>{pauseNarration();changeSettings({feedbackAudio:event.target.checked});}} />Speak new teacher replies</label><p className="mt-1 text-xs text-muted">Uses the selected lesson narrator; generation costs are tracked. Text appears immediately; you can continue while audio prepares. Imported narrators may have text-only replies.</p></div>
    <div><Button size="sm" variant="quiet" data-close-options onClick={() => { pauseNarration(); setReplay(true); }}>Listen from beginning</Button><p className="mt-1 text-xs text-muted">Listening uses a separate place and does not complete your activities.</p></div>
    {lessonOptions}
  </>;
  const completionActions = <div className="flex flex-col gap-2"><p className="text-xs text-muted">Your original lesson thread stays saved when you repeat.</p>{navigation?.resume_repeat ? <Button as="a" variant="primary" href={modeHref(navigation.resume_repeat.path)}>Resume your repeat</Button> : <Button variant="primary" disabled={busy} onClick={repeat}>{busy ? 'Opening your repeat…' : 'Repeat this lesson'}</Button>}{navigation?.next_lesson?.resume && !navigation.resume_repeat && <Button as="a" href={modeHref(navigation.next_lesson.path)}>Resume unfinished lesson</Button>}{problem && <p role="alert" className="text-sm text-problem">{problem}</p>}</div>;
  return <div className="registry-lesson">
    {!sessionId && <header className="tutor-chat-header"><div className="tutor-header-top"><p className="font-semibold text-sm">Your tutor</p><LessonOptions>{options}</LessonOptions></div>{sessionControls({ activity: null, state: {}, busy })}</header>}
    {!sessionId && <LessonVoiceStatus compact guide={guide} learner={learner} topic={topic} closed={closed} onChanged={onVoiceBuilt}/>}
    {!sessionId ? <div className="p-5 mt-auto flex flex-col gap-3">
      {warmUp && (warmUp.last || warmUp.next) ? <WarmUpCard warmUp={warmUp} onFinished={() => focusLessonControl(nextStepButton())} /> : <p className="text-sm text-muted">Read with your book beside you. Your teacher will show one activity at a time and keep your answers and saved place together.</p>}
      {resumeLesson && <><p className="text-sm text-muted">Your place in {resumeLesson.title} stays saved while you start this lesson.</p><a href={modeHref(resumeLesson.path)} className="text-sm font-semibold text-action underline">Resume unfinished lesson</a></>}
      {earlierVersion ? <EarlierVersionChoice earlier={earlierVersion} guide={guide} busy={busy} closed={closed}
        onOpen={async (command) => { setBusy(true); setProblem(''); pauseNarration();
          try { const next = await activitiesApi.replaceScript(earlierVersion.session_id, command); advance(next); setStartedSession(next.session_id); onStarted?.(next.session_id); }
          catch (error) { setProblem(error.message); } finally { setBusy(false); } }} />
        : <Button data-lesson-start variant="primary" disabled={busy || closed} onClick={start}>{busy ? 'Opening lesson and preparing its voice…' : 'Start lesson'}</Button>}
      {problem && <p role="alert" className="text-sm text-problem">{problem}</p>}
    </div> : <ActivityLesson key={sessionId} sessionId={sessionId} language={language} onState={handleState}
      onRepeat={repeat} onContinue={advance} onPauseNarration={pauseNarration} getNarrationCursor={getCursor} renderReading={reading} renderTeacherText={teacherText} renderNarration={narration} renderSessionControls={sessionControls}
      renderFeedback={({message,history=false})=>feedbackVoice && ['google-gemini','elevenlabs','kokoro-local'].includes(feedbackVoice.provider) ? <FeedbackVoice key={`${message.id}.${selectedSource}`} session={sessionId} message={message} language={language} trackId={selectedSource} speed={selectedSpeed} autoPlay={!history && settings.feedbackAudio !== false && feedbackRequest?.sessionId===sessionId && feedbackRequest.id===message.id} /> : !history && <p className="mt-2 text-xs text-muted">This reply is text-only with the selected narrator.</p>}
      sessionNotice={<LessonVoiceStatus compact guide={guide} learner={learner} topic={topic} session={sessionId} closed={closed} onChanged={onVoiceBuilt}/>} onSource={onSource} options={options} completionActions={finished ? completionActions : null} />}
  </div>;
}
