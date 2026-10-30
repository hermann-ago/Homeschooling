/* @vitest-environment jsdom */
import { useState } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ start: vi.fn(), repeat: vi.fn(), event: vi.fn(), buildNarration: vi.fn(), activityProps: null, readingProps: null, readingFixture: null, complete: vi.fn() }));
vi.mock('../../api/tutor', () => ({ tutorApi: { startInteractive: mocks.start, buildNarration: mocks.buildNarration } }));
vi.mock('../../api/activities', () => ({ activitiesApi: { event: mocks.event, repeat: mocks.repeat } }));
vi.mock('./ActivityLesson', () => ({ default: (props) => {
  mocks.activityProps = props;
  return <section aria-label="Activity engine">{props.renderSessionControls?.(mocks.readingFixture || { activity: null, state: {} })}{props.sessionNotice}{props.options}{props.completionActions}{mocks.readingFixture && <>{props.renderReading({ ...mocks.readingFixture, complete: mocks.complete })}{props.renderNarration?.(mocks.readingFixture)}</>}</section>;
} }));
vi.mock('../ReadAlong', () => ({ default: (props) => { mocks.readingProps = props; return <p>Range reading</p>; } }));
vi.mock('../LessonAudioReplay', () => ({ default: ({ onClose }) => <section aria-label="Listening replay"><button onClick={onClose}>Return to lesson</button></section> }));
import RegistryGuidedLesson from './RegistryGuidedLesson';
import { storageKey } from './durable';

const guide = { guide_id: 'guide', sentences: [{ text: 'Intro' }, { text: 'Read A' }, { text: 'Read B' }, { text: 'Future' }], audio: [] };
function show(extra = {}) {
  const onStarted = vi.fn(); const onFinished = vi.fn();
  function Harness() {
    const [index, setIndex] = useState(0);
    return <RegistryGuidedLesson guide={guide} learner="1" topic="2" activeIndex={index} onActiveIndex={setIndex} onStarted={onStarted} onFinished={onFinished} {...extra} />;
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return { ...render(<QueryClientProvider client={client}><Harness /></QueryClientProvider>), onStarted, onFinished };
}
beforeEach(() => { vi.clearAllMocks(); window.localStorage.clear(); mocks.activityProps = null; mocks.readingProps = null; mocks.readingFixture = null; });
afterEach(cleanup);

it('keeps the session-wide voice status visible while an activity is awaiting input',()=>{
  show({session:'s1',guide:{...guide,voice_preparation:{provider:'google-gemini',status:'aligning',parts:3,completed_parts:0,recorded_parts:1,alignment:'local'}}});
  expect(screen.getByRole('status',{name:'Lesson voice preparation'})).toBeTruthy();
  expect(screen.getByText('Synchronizing Google voice…')).toBeTruthy();
  expect(screen.getByText('1 of 3 audio blocks saved · 0 synchronized')).toBeTruthy();
});

it('labels finished reading as saved rather than claiming its recording is missing', async () => {
  const activity = { id: 'read-1', kind: 'read_source', status: 'answered', start_sentence: 1, end_sentence: 2 };
  mocks.readingFixture = { activity, state: { session_id: 's1', revision: 2, playback: {} } };
  show({ session: 's1' });
  expect(await screen.findByText('Reading saved · Continue when you are ready')).toBeTruthy();
  expect(screen.queryByText('Text only · No saved narration for this step')).toBeNull();
});

it('starts an interactive session before handing identity to the shared activity engine', async () => {
  mocks.start.mockResolvedValue({ session_id: 'new-session' });
  const result = show({ slotId: '9' });
  expect(mocks.activityProps).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Start lesson' }));
  await screen.findByRole('region', { name: 'Activity engine' });
  expect(mocks.start).toHaveBeenCalledWith('1', '2', 'guide', '9', 1);
  expect(result.onStarted).toHaveBeenCalledWith('new-session');
  expect(mocks.activityProps.sessionId).toBe('new-session');
});

it('allows starting a different lesson while keeping the unfinished lesson available', async () => {
  mocks.start.mockResolvedValue({ session_id: 'another-session' });
  show({ resumeLesson: { title: 'Earlier reading', path: '/lesson?session=old' } });
  expect(screen.getByRole('button', { name: 'Start lesson' }).disabled).toBe(false);
  expect(screen.getByRole('link', { name: 'Resume unfinished lesson' }).getAttribute('href')).toContain('session=old');
  fireEvent.click(screen.getByRole('button', { name: 'Start lesson' }));
  await screen.findByRole('region', { name: 'Activity engine' });
  expect(mocks.start).toHaveBeenCalledTimes(1);
  expect(mocks.activityProps.sessionId).toBe('another-session');
});

it('repeats a completed lesson and recovers an ambiguous request with the same identity', async () => {
  mocks.repeat.mockRejectedValueOnce(new Error('Lost reply')).mockResolvedValueOnce({ session_id: 'repeat-session' });
  const result = show({ session: 'original', closed: true });
  act(() => mocks.activityProps.onState({ session_id: 'original', playback: {}, active_activity: null, status: 'completed' }));
  fireEvent.click(screen.getByRole('button', { name: 'Repeat this lesson' }));
  await screen.findByText('Lost reply');
  const command = mocks.repeat.mock.calls[0][1];
  fireEvent.click(screen.getByRole('button', { name: 'Repeat this lesson' }));
  await waitFor(() => expect(result.onStarted).toHaveBeenCalledWith('repeat-session'));
  expect(mocks.repeat.mock.calls[1]).toEqual(['original', command]);
  expect(mocks.start).not.toHaveBeenCalled();
});

it('notifies completion exactly once only after the authoritative session is completed', () => {
  const result = show({ session: 's1' });
  const snapshot = { session_id: 's1', playback: {}, active_activity: null, status: 'active' };
  act(() => mocks.activityProps.onState(snapshot));
  expect(result.onFinished).not.toHaveBeenCalled();
  act(() => mocks.activityProps.onState({ ...snapshot, status: 'completed' }));
  act(() => mocks.activityProps.onState({ ...snapshot, status: 'completed' }));
  expect(result.onFinished).toHaveBeenCalledTimes(1);
});

it('ignores a late snapshot from another lesson attempt', () => {
  const result = show({ session: 'current-attempt' });
  act(() => mocks.activityProps.onState({ session_id: 'old-attempt', playback: {}, active_activity: null, status: 'completed' }));
  expect(result.onFinished).not.toHaveBeenCalled();
  expect(screen.queryByRole('button', { name: 'Repeat this lesson' })).toBeNull();
});

it('offers Resume your repeat when the original lesson already has an unfinished repeat', () => {
  show({ session: 'original', closed: true });
  act(() => mocks.activityProps.onState({ session_id: 'original', playback: {}, status: 'completed', active_activity: null,
    attempt_navigation: { resume_repeat: { path: '/lesson?session=existing-repeat' } } }));
  expect(screen.getByRole('link', { name: 'Resume your repeat' }).getAttribute('href')).toContain('session=existing-repeat');
  expect(screen.queryByRole('button', { name: 'Repeat this lesson' })).toBeNull();
  expect(mocks.repeat).not.toHaveBeenCalled();
});

it('keeps listening replay separate from the activity session and returns without completion', () => {
  const result = show({ session: 's1' });
  fireEvent.click(screen.getByRole('button', { name: 'Listen from beginning' }));
  expect(screen.getByRole('region', { name: 'Listening replay' })).toBeTruthy();
  expect(mocks.start).not.toHaveBeenCalled(); expect(mocks.event).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Return to lesson' }));
  expect(screen.getByRole('region', { name: 'Activity engine' })).toBeTruthy();
  expect(result.onFinished).not.toHaveBeenCalled();
});

it('passes the current source range to narration and separates reading completion from Continue', async () => {
  const activity = { id: 'read-1', kind: 'read_source', status: 'pending', start_sentence: 1, end_sentence: 2, interaction: { id: 'i1' } };
  mocks.readingFixture = { activity, state: { session_id: 's1', revision: 1, playback: {}, on_break: false } };
  show({ session: 's1' });
  await waitFor(() => expect(mocks.readingProps).not.toBeNull());
  expect(mocks.readingProps).toMatchObject({ rangeStart: 1, rangeEnd: 2, visibleThrough: 2 });
  expect(mocks.complete).not.toHaveBeenCalled();
  act(() => mocks.readingProps.onReadingEnd());
  expect(mocks.complete).toHaveBeenCalledTimes(1);
  expect(mocks.event).not.toHaveBeenCalled();
});

it('restores a durable cursor belonging to this exact reading activity', async () => {
  const cursor = { track_id: 'voice', part_index: 1, offset_seconds: 8.5, sentence_index: 2 };
  window.localStorage.setItem(storageKey('s1', 'narration.read-1'), JSON.stringify(cursor));
  const activity = { id: 'read-1', kind: 'read_source', status: 'pending', start_sentence: 1, end_sentence: 2, interaction: { id: 'i1' } };
  mocks.readingFixture = { activity, state: { session_id: 's1', revision: 1, playback: {}, on_break: false } };
  show({ session: 's1' });
  await waitFor(() => expect(mocks.readingProps.savedCursor).toEqual(cursor));
});

it('starts a replay at its beginning instead of restoring the previous interaction audio offset', async () => {
  window.localStorage.setItem(storageKey('s1', 'narration.read-1'), JSON.stringify({ track_id: 'voice', part_index: 1, offset_seconds: 8.5, sentence_index: 2 }));
  const activity = { id: 'read-1', kind: 'read_source', status: 'pending', start_sentence: 1, end_sentence: 2,
    interaction: { id: 'i2', replay_of: 'i1' } };
  mocks.readingFixture = { activity, state: { session_id: 's1', revision: 4, playback: {}, on_break: false } };
  show({ session: 's1' });
  await waitFor(() => expect(mocks.readingProps).not.toBeNull());
  expect(mocks.readingProps.savedCursor).toBeNull();
});

it('keeps playback information separate from the shared lesson preparation bar', async () => {
  mocks.readingFixture = { activity: { id: 'read-1', status: 'pending', start_sentence: 1, end_sentence: 2 }, state: { session_id: 'pinned-session', revision: 1, playback: {} } };
  const built = vi.fn();
  mocks.buildNarration.mockResolvedValue({ estimated_cost_usd: 0, reused: true, allowed: true });
  show({ session: 'pinned-session', guide: { ...guide, current: true }, onVoiceBuilt: built });
  fireEvent.click(screen.getByLabelText('Voice information'));
  expect(screen.queryByRole('button', { name: 'Create the guided lesson voice' })).toBeNull();
  expect(mocks.buildNarration).not.toHaveBeenCalled();
  expect(mocks.readingProps.voiceSetup).toBeUndefined();
  expect(built).not.toHaveBeenCalled();
  expect(mocks.event).not.toHaveBeenCalled();
});

it('keeps voice and speed for later steps and restores the session settings after refresh', async () => {
  const activity = { id: 'read-1', kind: 'read_source', status: 'pending', start_sentence: 1, end_sentence: 2, interaction: { id: 'reading' } };
  const state = { session_id: 's1', revision: 1, playback: {}, active_activity: activity };
  mocks.readingFixture = { activity, state };
  const props = { session: 's1', guide: { ...guide, audio: [{ track_id: 'google', provider: 'google-gemini', voice: 'Achird', synchronized: true, status: 'ready', preferred: true }] } };
  const first = show(props);
  expect(screen.getByLabelText('Session voice').value).toBe('google');
  fireEvent.change(screen.getByLabelText('Session reading speed'), { target: { value: '1.3' } });
  fireEvent.change(screen.getByLabelText('Session voice'), { target: { value: 'device' } });
  expect(mocks.readingProps).toMatchObject({ settingsInHeader: true, selectedSource: 'device', selectedSpeed: 1.3 });
  mocks.readingFixture = { activity: { ...activity, id: 'read-2' }, state };
  act(() => mocks.activityProps.onContinue({ ...state, active_activity: mocks.readingFixture.activity }));
  expect(mocks.readingProps).toMatchObject({ selectedSource: 'device', selectedSpeed: 1.3 });
  first.unmount(); show(props);
  expect(screen.getByLabelText('Session reading speed').value).toBe('1.3');
  expect(screen.getByLabelText('Session voice').value).toBe('device');
  expect(mocks.event).not.toHaveBeenCalled();
});

it('puts the active transport in the footer and requests autoplay only on explicit advance', async () => {
  const activity = { id: 'read-1', kind: 'read_source', status: 'pending', start_sentence: 1, end_sentence: 2, interaction: { id: 'reading', sequence: 1 } };
  const state = { session_id: 's1', revision: 1, playback: {}, active_activity: activity };
  mocks.readingFixture = { activity, state };
  show({ session: 's1', guide: { ...guide, activities: [activity] } });
  expect(mocks.readingProps.externalControls).toBe(true);
  expect(mocks.readingProps.autoPlayRequest).toBe(0);
  const toggle = vi.fn();
  act(() => mocks.readingProps.onTransport({ playing: false, available: true, recorded: true, toggle }));
  fireEvent.click(screen.getByRole('button', { name: 'Play narration' }));
  expect(toggle).toHaveBeenCalledTimes(1);
  act(() => mocks.activityProps.onContinue(state));
  expect(mocks.readingProps.autoPlayRequest).toBeGreaterThan(0);
  act(() => mocks.readingProps.onTransport({ playing: true, available: true, recorded: true, toggle }));
  expect(screen.getByRole('button', { name: 'Pause narration' })).toBeTruthy();
});

it('does not restore a cursor from the previous reading step into a later source range', async () => {
  const activity = { id: 'read-2', kind: 'read_source', status: 'pending', start_sentence: 2, end_sentence: 3, interaction: { id: 'i2' } };
  mocks.readingFixture = { activity, state: { session_id: 's1', revision: 2, playback: { narration_cursor: { track_id: 'voice', part_index: 0, offset_seconds: 3, sentence_index: 0 } }, on_break: false } };
  show({ session: 's1' });
  await waitFor(() => expect(mocks.readingProps).not.toBeNull());
  expect(mocks.readingProps.savedCursor?.sentence_index ?? 2).toBeGreaterThanOrEqual(2);
});

it('explains a missing recorded passage and offers device speech without changing the session narrator or advancing', () => {
  const activity = { id: 'read-1', kind: 'read_source', status: 'pending', start_sentence: 1, end_sentence: 2, interaction: { id: 'reading' } };
  mocks.readingFixture = { activity, state: { session_id: 's1', revision: 1, playback: {}, active_activity: activity } };
  show({ session: 's1', guide: { ...guide, activities: [activity], audio: [{ track_id: 'google', provider: 'google-gemini', voice: 'Achird', synchronized: true, status: 'ready' }] } });
  const toggle = vi.fn();
  act(() => mocks.readingProps.onTransport({ playing: false, available: true, recorded: false, unrecorded: true, toggle }));
  expect(screen.getByText(/This passage has no saved recording/)).toBeTruthy();
  expect(toggle).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Use device voice for this passage' }));
  expect(toggle).toHaveBeenCalledTimes(1);
  expect(screen.getByLabelText('Session voice').value).toBe('google');
  expect(mocks.complete).not.toHaveBeenCalled(); expect(mocks.event).not.toHaveBeenCalled();
});
