/* @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
const api = vi.hoisted(() => ({ lesson: vi.fn() }));
vi.mock('../api/preparation', () => ({ curriculumPrepApi: api }));
vi.mock('./CurriculumLessonPrep', () => ({ CurriculumPreparationDialog: ({ target }) => <p>Preparing {target}</p> }));
import LessonPreparationBar from './LessonPreparationBar';
import { currentMode } from '../api/mode';
afterEach(() => { cleanup(); vi.resetAllMocks(); });

function show(status, extra = {}) {
  api.lesson.mockResolvedValue(status);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const changed = vi.fn();
  render(<QueryClientProvider client={client}><LessonPreparationBar learner={1} topic={2} onChanged={changed} {...extra} /></QueryClientProvider>);
  return { client, changed };
}

it('puts voice creation beside its saved guide status during a current pinned session', async () => {
  show({ guide_id: 'g1', script_status: 'ready', audio: { status: 'missing' } },
    { guide: { guide_id: 'g1', current: true, audio: [] }, pinned: true });
  fireEvent.click(await screen.findByRole('button', { name: 'Prepare voice' }));
  expect(screen.getByText('Preparing audio')).toBeTruthy();
  expect(screen.queryByRole('link')).toBeNull();
});

it('refreshes the lesson after background preparation finishes and prevents another start while busy', async () => {
  const { client, changed } = show({ script_status: 'missing', job: { status: 'running', phase: 'script' }, audio: { status: 'missing' } });
  expect((await screen.findByRole('button', { name: 'Preparing lesson…' })).disabled).toBe(true);
  await act(async () => client.setQueryData(['curriculum-preparation', currentMode, 1, 2],
    { guide_id: 'g1', script_status: 'ready', job: { status: 'completed' }, audio: { status: 'ready' } }));
  await waitFor(() => expect(changed).toHaveBeenCalledOnce());
  expect(screen.getByRole('button', { name: 'Lesson & voice' }).disabled).toBe(false);
});

it('keeps an older pinned guide separate from preparation of its newer version', async () => {
  show({ guide_id: 'g2', script_status: 'ready', audio: { status: 'ready' } },
    { guide: { guide_id: 'g1', current: true, audio: [] }, pinned: true });
  expect(await screen.findByRole('link', { name: 'Prepare current version' })).toBeTruthy();
});
