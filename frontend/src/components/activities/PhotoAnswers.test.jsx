/* @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ state: vi.fn(), event: vi.fn(), access: vi.fn(), attachWork: vi.fn() }));
vi.mock('../../api/activities', () => ({ activitiesApi: api }));
vi.mock('../../api/tutor', () => ({ tutorApi: { attachWork: api.attachWork } }));
import ActivityLesson from './ActivityLesson';
import { ProgressDots } from './Progress';

const exercise = (patch = {}) => ({ id: 'a1', kind: 'request_book_work', status: 'pending', origin: 'required_book', snap: true,
  content: { prompt: 'Complete the words with s or ss.', response_modes: ['text', 'photo'] },
  interaction: { id: 'i1', status: 'awaiting_work', stage: 'initial' }, responses: [], messages: [], ...patch });
const state = (activity, patch = {}) => ({ session_id: 's1', revision: 1, playback: {}, active_activity: activity, book_work: 'tutor',
  activities: [activity], events: [], event_cursor: 0, on_break: false, page_work: {}, ...patch });
const next = () => exercise({ id: 'a9', kind: 'introduce', snap: false, content: { text: 'Next part.' }, interaction: { id: 'i9', status: 'ready_to_continue' } });

beforeEach(() => { vi.resetAllMocks(); window.localStorage.clear(); });
afterEach(cleanup);

it('answers book work with one photo and moves on without an answer box', async () => {
  api.state.mockResolvedValue(state(exercise()));
  api.attachWork.mockResolvedValue({ evidence_id: 'E1' });
  api.event.mockResolvedValue(state(next(), { revision: 3, checking: true,
    progress: { items: [{ id: 'a1', outcome: 'checking', check: { prompt: 'Complete the words with s or ss.' } }] } }));
  render(<ActivityLesson sessionId="s1" />);
  const button = await screen.findByRole('button', { name: /Photo of my work/ });
  await waitFor(() => expect(document.activeElement).toBe(button));
  expect(screen.queryByRole('button', { name: 'I have finished writing in my book' })).toBeNull();
  expect(screen.queryByLabelText(/Answer capture/)).toBeNull();
  // Without a live camera (jsdom), the device's own camera or picker supplies the photo.
  const file = new File(['x'], 'work.jpg', { type: 'image/jpeg' });
  fireEvent.change(screen.getByLabelText('Photo of my work', { selector: 'input' }), { target: { files: [file] } });
  await waitFor(() => expect(api.event).toHaveBeenCalledTimes(1));
  expect(api.attachWork).toHaveBeenCalledWith('s1', 1, file, 'a1');
  expect(api.event.mock.calls[0][1]).toMatchObject({ type: 'snap_work', activity_id: 'a1', payload: { evidence_ids: ['E1'] } });
  expect(await screen.findByText('Checking 1 answer…')).toBeTruthy();
  expect(screen.getByText('Next part.')).toBeTruthy();
});

it('lets the child answer on screen instead, and switch back to the photo', async () => {
  api.state.mockResolvedValue(state(exercise({ interaction: { id: 'i1', status: 'awaiting_input', stage: 'capture' } })));
  render(<ActivityLesson sessionId="s1" />);
  fireEvent.click(await screen.findByRole('button', { name: 'Answer here instead' }));
  expect(await screen.findByLabelText(/Answer capture/)).toBeTruthy();
  expect(screen.queryByRole('button', { name: /Photo of my work/ })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Take a photo instead' }));
  expect(await screen.findByRole('button', { name: /Photo of my work/ })).toBeTruthy();
});

it('opens what a check found from its chip and starts the fix', async () => {
  const fix = vi.fn();
  const progress = { items: [{ id: 'a1', outcome: 'first_try' }, { id: 'a2', outcome: 'fix',
    check: { prompt: 'A__inatura', read: 'Asinatura', feedback: 'Count the letters s.', result: 'Not yet' } }] };
  render(<ProgressDots progress={progress} currentId="a3" onFix={fix} onRetry={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: '1 to look at' }));
  expect(screen.getByText('Asinatura')).toBeTruthy();
  expect(screen.getByText('Count the letters s.')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Fix it now' }));
  expect(fix).toHaveBeenCalledWith('a2');
  expect(screen.queryByText('Count the letters s.')).toBeNull();
});

it('shows the earlier reading while fixing and offers the way back', async () => {
  api.state.mockResolvedValue(state(exercise({ fix: { read: 'Asinatura', feedback: 'Count the letters s.', result: 'Not yet' } })));
  api.event.mockResolvedValue(state(next(), { revision: 2 }));
  render(<ActivityLesson sessionId="s1" />);
  expect(await screen.findByText('I read in your photo: Asinatura')).toBeTruthy();
  expect(screen.getByRole('button', { name: /New photo/ })).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Skip for now' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Back to the lesson' }));
  await waitFor(() => expect(api.event.mock.calls[0][1]).toMatchObject({ type: 'fix_later' }));
});

it('holds Finish while photos are checked and lists what is left to look at', async () => {
  const close = exercise({ id: 'close', kind: 'close_lesson', snap: false, content: { text: 'We finished.' }, interaction: { id: 'ic', status: 'ready_to_continue' } });
  const progress = { items: [{ id: 'a1', outcome: 'fix', check: { prompt: 'A__inatura', read: 'Asinatura', feedback: 'Count the letters s.' } }], first_try: 0, graded: 1, practise: [] };
  api.state.mockResolvedValue(state(close, { checking: true, progress }));
  api.event.mockResolvedValue(state(exercise({ fix: { read: 'Asinatura' } }), { revision: 2 }));
  render(<ActivityLesson sessionId="s1" />);
  expect((await screen.findByRole('button', { name: 'Checking your photos…' })).disabled).toBe(true);
  const list = screen.getByRole('region', { name: 'Answers to look at' });
  expect(list.textContent).toContain('I read: Asinatura');
  fireEvent.click(screen.getAllByRole('button', { name: 'Fix it now' })[0]);
  await waitFor(() => expect(api.event.mock.calls[0][1]).toMatchObject({ type: 'fix_work', activity_id: 'close', payload: { activity_id: 'a1' } }));
});

it('sends a plain step again when only a finished check changed the revision', async () => {
  const intro = next();
  api.state.mockResolvedValueOnce(state(intro)).mockResolvedValue(state(intro, { revision: 2 }));
  const conflict = Object.assign(new Error('changed'), { status: 409 });
  api.event.mockRejectedValueOnce(conflict).mockResolvedValue(state(exercise(), { revision: 3 }));
  render(<ActivityLesson sessionId="s1" />);
  fireEvent.click(await screen.findByRole('button', { name: 'Continue lesson' }));
  await waitFor(() => expect(api.event).toHaveBeenCalledTimes(2));
  expect(api.event.mock.calls[1][1]).toMatchObject({ type: 'continue', expected_revision: 2 });
  expect(screen.queryByText(/Your saved place changed/)).toBeNull();
});
