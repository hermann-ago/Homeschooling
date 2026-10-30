/* @vitest-environment jsdom */
import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { LearnerContext } from '../app/learnerContext';

const api = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('../api/client', () => ({ fetchApi: api.fetch }));
import Records from './Records';

beforeEach(() => {
  api.fetch.mockImplementation(async (path) => {
    if (path === '/records/options') return { subjects: [{ id: 5, child_id: 1, name: 'History' }, { id: 6, child_id: 2, name: 'Math' }] };
    const query = new URLSearchParams(path.split('?')[1]);
    const empty = query.get('q') === 'unfindable' || query.get('child_id') === '2';
    return { total: empty ? 0 : 26, columns: [{ key: 'date', label: 'Date' }, { key: 'first_answer', label: 'Original answer' }],
      statuses: ['Partly correct'], rows: empty ? [] : [{ id: `answer-${query.get('page')}`, child: 'Lucas', subject: 'History', date: '2026-09-24', first_answer: 'His original words', lesson_path: '/lesson?learner=1&topic=2&session=original', details: { 'Help given': 'Look at the map', evidence: [{ id: 'photo-1', filename: 'Saved photo.png' }] } }] };
  });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

function show() {
  function Family() {
    const [selected, select] = useState(1);
    return <LearnerContext.Provider value={{ selected, select, single: selected, learners: [{ id: 1, name: 'Lucas', color: '#336699' }, { id: 2, name: 'Mila', color: '#996633' }] }}><Records /></LearnerContext.Provider>;
  }
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Family /></QueryClientProvider>);
}

it('filters and sorts the table, downloads the same filters and shows original evidence', async () => {
  show();
  await screen.findByText('His original words');
  fireEvent.click(screen.getByRole('button', { name: /Details for Lucas/ }));
  const dialog = screen.getByRole('dialog');
  expect(within(dialog).getByText('Look at the map')).toBeTruthy();
  expect(within(dialog).getByRole('link', { name: 'Open full lesson thread' }).getAttribute('href')).toContain('session=original');
  expect(within(dialog).getByRole('link', { name: 'Saved photo.png' }).getAttribute('href')).toBe('/api/student-work/photo-1?app_mode=live');
  fireEvent.click(within(dialog).getByRole('button', { name: 'Close' }));
  fireEvent.click(screen.getByRole('button', { name: 'Next' }));
  await waitFor(() => expect(api.fetch.mock.calls.at(-1)[0]).toContain('page=2'));
  fireEvent.change(screen.getByLabelText('Subject'), { target: { value: '5' } });
  await waitFor(() => expect(api.fetch.mock.calls.at(-1)[0]).toContain('subject_id=5'));
  expect(api.fetch.mock.calls.at(-1)[0]).toContain('page=1');
  fireEvent.change(screen.getByLabelText('Search answers, topics or notes'), { target: { value: 'original' } });
  fireEvent.click(screen.getByRole('button', { name: 'Search' }));
  await waitFor(() => expect(api.fetch.mock.calls.at(-1)[0]).toContain('q=original'));
  const download = screen.getByRole('link', { name: 'Download filtered CSV' }).getAttribute('href');
  expect(download).toContain('q=original'); expect(download).toContain('child_id=1'); expect(download).not.toContain('page=');
  fireEvent.click(screen.getByRole('button', { name: /Original answer/ }));
  await waitFor(() => expect(api.fetch.mock.calls.at(-1)[0]).toContain('sort=first_answer'));
  fireEvent.change(screen.getByLabelText('Records'), { target: { value: 'reviews' } });
  await waitFor(() => expect(api.fetch.mock.calls.at(-1)[0]).toContain('view=reviews'));
  expect(api.fetch.mock.calls.at(-1)[0]).toContain('sort=date');
});

it('resets subject and pagination on child change and handles empty results', async () => {
  show(); await screen.findByText('His original words');
  fireEvent.change(screen.getByLabelText('Subject'), { target: { value: '5' } });
  fireEvent.click(await screen.findByRole('button', { name: 'Next' }));
  fireEvent.click(screen.getByRole('button', { name: /Mila/ }));
  await screen.findByText('No records match these filters.');
  const last = api.fetch.mock.calls.at(-1)[0];
  expect(last).toContain('child_id=2'); expect(last).toContain('page=1'); expect(last).not.toContain('subject_id=5');
});

it('shows an actionable loading failure', async () => {
  api.fetch.mockRejectedValue(new Error('The home server could not be reached'));
  show();
  expect(await screen.findByRole('alert')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy();
});

it('makes nested capture amendments and completion states readable to a parent', async () => {
  api.fetch.mockResolvedValue({ total: 1, columns: [{ key: 'date', label: 'Date' }], statuses: [], rows: [{
    id: 'synthetic-session', child: 'Practice learner', subject: 'History', details: {
      'Capture history': [{ original: { text: 'The trees united.' }, confirmed_answer: 'The tribes united.',
        parent_observation: { independently_observed: false, note: 'Checked the source page.' } }],
      'Completion summary': { reading: { status: 'reached' }, understanding: 'Not assessed', pending_work: [{ prompt: 'Explain the cause.' }] },
    },
  }] });
  show();
  fireEvent.click(await screen.findByRole('button', { name: /Details for Practice learner/ }));
  const dialog = screen.getByRole('dialog');
  expect(within(dialog).getByText(/original: text: The trees united.*confirmed answer: The tribes united\./s)).toBeTruthy();
  expect(within(dialog).getByText(/reading: status: reached.*understanding: Not assessed.*Explain the cause\./s)).toBeTruthy();
  expect(dialog.textContent).not.toContain('[object Object]');
});
