/* @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ state: vi.fn(), event: vi.fn(), access: vi.fn(), attachWork: vi.fn() }));
vi.mock('../../api/activities', () => ({ activitiesApi: api }));
vi.mock('../../api/tutor', () => ({ tutorApi: { attachWork: api.attachWork } }));
import ActivityLesson from './ActivityLesson';

const exercise = (patch = {}) => ({ id: 'a1', kind: 'request_book_work', status: 'pending', origin: 'required_book', paced: true,
  content: { prompt: 'Complete the words with s or ss.', response_modes: ['text', 'photo'] },
  interaction: { id: 'i1', status: 'awaiting_work', stage: 'initial' }, responses: [], messages: [], ...patch });
const state = (activity, patch = {}) => ({ session_id: 's1', revision: 1, playback: {}, active_activity: activity, book_work: 'paced',
  activities: [activity], events: [], event_cursor: 0, on_break: false, page_work: {}, ...patch });

beforeEach(() => { vi.resetAllMocks(); window.localStorage.clear(); });
afterEach(cleanup);

it('reads the exercise and moves on with one Done press, without an answer box or skip', async () => {
  api.state.mockResolvedValue(state(exercise({ practice_section: { id: 'p1', kind: 'true_false', title: 'True or false', item: 1, total: 8, completed: 0 } })));
  api.event.mockResolvedValue(state(exercise({ id: 'a9', kind: 'introduce', paced: false, content: { text: 'Next part.' },
    interaction: { id: 'i9', status: 'ready_to_continue' } }), { revision: 2 }));
  render(<ActivityLesson sessionId="s1" />);
  const done = await screen.findByRole('button', { name: 'Done · all 8 in my book' });
  await waitFor(() => expect(document.activeElement).toBe(done));
  expect(screen.getByText(/Do this in your book/)).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Skip for now' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'I have finished writing in my book' })).toBeNull();
  expect(screen.queryByRole('textbox', { name: /answer/i })).toBeNull();
  fireEvent.click(done);
  await waitFor(() => expect(api.event).toHaveBeenCalledTimes(1));
  expect(api.event.mock.calls[0][1]).toMatchObject({ type: 'done_in_book', activity_id: 'a1', interaction_id: 'i1' });
});

it('offers an optional photo check at the end and shows only the answers to look at again', async () => {
  const close = exercise({ id: 'close', kind: 'close_lesson', paced: false, content: { text: 'We finished.' }, interaction: { id: 'ic', status: 'ready_to_continue' } });
  api.state.mockResolvedValue(state(close, { book_check: { count: 3, status: 'completed', summary: 'One answer to look at again.', photos: 2, items: [
    { item_id: 'a1', prompt: 'Complete: A__inatura', answer: 'Asinatura', result: 'check_again', note: 'Count the letters s.' },
    { item_id: 'a2', prompt: 'True or false: the chameleon is big.', answer: 'F', result: 'looks_right', note: '' }] } }));
  render(<ActivityLesson sessionId="s1" />);
  expect(await screen.findByRole('region', { name: 'Check the book pages' })).toBeTruthy();
  expect(screen.getByText('One answer to look at again.')).toBeTruthy();
  expect(screen.getByText('Count the letters s.')).toBeTruthy();
  expect(screen.queryByText('True or false: the chameleon is big.')).toBeNull();
  expect(screen.getByText('1 other answer looked right.')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Finish lesson' })).toBeTruthy();
});
