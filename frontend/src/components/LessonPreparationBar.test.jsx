/* @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
const api = vi.hoisted(() => ({ lesson: vi.fn() }));
vi.mock('../api/preparation', () => ({ curriculumPrepApi: api }));
vi.mock('./CurriculumLessonPrep', () => ({ CurriculumPreparationDialog: ({ target }) => <p>Preparing {target}</p> }));
vi.mock('./NarratorPicker', () => ({ default: ({topic}) => <p>Sample picker for lesson {topic}</p> }));
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

it('refreshes the lesson after background preparation finishes and permits viewing progress while busy', async () => {
  const { client, changed } = show({ script_status: 'missing', job: { status: 'running', phase: 'script' }, audio: { status: 'missing' } });
  const progress = await screen.findByRole('button', { name: 'Preparing lesson…' });
  expect(progress.disabled).toBe(false);
  fireEvent.click(progress);
  expect(screen.getByText('Preparing both')).toBeTruthy();
  await act(async () => client.setQueryData(['curriculum-preparation', currentMode, 1, 2],
    { guide_id: 'g1', script_status: 'ready', job: { status: 'completed' }, audio: { status: 'ready' } }));
  await waitFor(() => expect(changed).toHaveBeenCalledOnce());
  expect(screen.getByRole('button', { name: 'Lesson & voice' }).disabled).toBe(false);
});

it('shows the actual background failure and the script already saved',async()=>{
  show({script_status:'ready',job:{status:'paused',phase:'audio',error:'Inworld credits unavailable'},audio:{status:'paused',parts:5,completed_parts:2}});
  expect(await screen.findByRole('alert')).toHaveProperty('textContent',expect.stringContaining('Inworld credits unavailable'));
  expect(screen.getByText(/Script: saved/)).toBeTruthy();
  expect(screen.getByText('2 of 5 voice sections synchronized.')).toBeTruthy();
});

it('explains that exhausted script credits are separate from Inworld voice credits',async()=>{
  show({script_status:'missing',job:{status:'paused',phase:'script',error_code:'provider_quota',error:'No API credits remain.'},audio:{status:'missing'}});
  expect(await screen.findByRole('alert')).toHaveProperty('textContent',expect.stringContaining('No API credits remain.'));
  expect(screen.getByText(/Script-provider API credits and Inworld voice credits are separate/)).toBeTruthy();
});

it('stops showing a stale review failure after the saved script is approved',async()=>{
  show({script_status:'ready',review:{status:'approved'},job:{status:'paused',phase:'review',error:'Old provider failure'},audio:{status:'missing'}});
  expect(await screen.findByText('Script reviewed · ready to prepare voice')).toBeTruthy();
  expect(screen.queryByRole('alert')).toBeNull();
  expect(screen.queryByText('Preparation needs attention')).toBeNull();
  expect(screen.getByRole('button',{name:'Prepare voice'}).disabled).toBe(false);
});

it('refreshes the reader when only the saved review changes',async()=>{
  const {client,changed}=show({guide_id:'g1',script_status:'ready',review:{status:'failed'},audio:{status:'missing'}});
  await screen.findByRole('button',{name:'Prepare voice'});
  await act(async()=>client.setQueryData(['curriculum-preparation',currentMode,1,2],
    {guide_id:'g1',script_status:'ready',review:{status:'approved'},audio:{status:'missing'}}));
  await waitFor(()=>expect(changed).toHaveBeenCalledOnce());
});

it('keeps an older pinned guide separate from preparation of its newer version', async () => {
  show({ guide_id: 'g2', script_status: 'ready', audio: { status: 'ready' } },
    { guide: { guide_id: 'g1', current: true, audio: [] }, pinned: true });
  expect(await screen.findByRole('link', { name: 'Prepare current version' })).toBeTruthy();
});

it('opens narrator samples directly from the lesson preparation bar without starting generation', async () => {
  show({ script_status: 'ready', audio: { status: 'ready' } });
  fireEvent.click(await screen.findByRole('button', { name: 'Narrator & samples' }));
  expect(screen.getByRole('dialog', { name: 'Narrator & samples' })).toBeTruthy();
  expect(screen.getByText('Sample picker for lesson 2')).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Family & child narrators' }).getAttribute('href')).toMatch(/^\/settings\?app_mode=.*#narrator-voices$/);
  expect(screen.queryByText('Preparing audio')).toBeNull();
});

it('offers the update beside the notice when a saved script is outdated', async () => {
  show({ guide_id: 'g1', script_status: 'outdated', audio: { status: 'ready' } }, { guide: { guide_id: 'g1', current: false, audio: [] } });
  expect(await screen.findByText(/changed since this lesson was prepared/)).toBeTruthy();
  expect(screen.getByRole('region', { name: 'Lesson preparation' }).dataset.update).toBe('true');
  fireEvent.click(screen.getByRole('button', { name: 'Update lesson & voice' }));
  expect(screen.getByText('Preparing both')).toBeTruthy();
});
