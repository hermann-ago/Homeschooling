/* @vitest-environment jsdom */
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { FeedbackProvider } from '../ui';

const api = vi.hoisted(() => ({ fetchApi: vi.fn(), getByChildId: vi.fn() }));
vi.mock('../api/client', () => ({ fetchApi: api.fetchApi }));
vi.mock('../api/subjects', () => ({ subjectsApi: { getByChildId: api.getByChildId } }));
import LearningSummary from './LearningSummary';

const data = { subject_id: 5, subject: 'History', summary_version: 1, interpretation: 'Observed evidence only.', map_id: 'm1', link_revision: 0,
  topics: [], concepts: [{ concept_id: 'c1', title: 'Mongol Empire', label: 'Needs clarification', observations: 1, independent_checks: 0,
    help_sessions: 0, evidence_ids: ['a1'], next_action: 'Clarify the handwriting.' }],
  evidence: [{ id: 'a1', revision: 1, topic: 'Earlier travel lesson', question_text: 'Who travelled?', question_ref: 'Q1', first_answer: 'unclear',
    first_result: 'Unreadable', independence: 'not_assessed', concept_ids: [], date: '2026-09-24', lineage: ['a1'] },
    { id: 'a2', revision: 1, topic: 'Another lesson', first_answer: 'another', first_result: 'Correct', concept_ids: [], lineage: ['a2'] }],
  reviews: [], unmapped_evidence: ['a1', 'a2'], link_history: [], amendment_history: [],
};

beforeEach(() => { api.getByChildId.mockResolvedValue([{ id: 5, name: 'History' }]); api.fetchApi.mockResolvedValue(structuredClone(data)); });
afterEach(() => { cleanup(); vi.resetAllMocks(); });
function show() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <FeedbackProvider><LearningSummary child={{ id: 1, name: 'Lucas' }} /></FeedbackProvider></QueryClientProvider>);
}

it('opens supporting evidence by identity even when concept and topic titles differ', async () => {
  show(); expect(api.fetchApi).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'View learning summary' }));
  await screen.findByText('2 effective observations · 2 without a clear concept link · saved summary 1.');
  fireEvent.click(screen.getByRole('button', { name: 'Concept evidence' }));
  fireEvent.click(screen.getByRole('button', { name: 'Inspect supporting work' }));
  expect(screen.getAllByRole('button', { name: 'Inspect / link evidence' }).length).toBe(1);
  expect(screen.getByText('Who travelled?')).toBeTruthy();
  expect(screen.queryByText('Another lesson')).toBeNull();
  expect(api.fetchApi).toHaveBeenCalledTimes(1);
});

it('amends unclear work with an explicit note and defaults to awaiting assessment', async () => {
  show(); fireEvent.click(screen.getByRole('button', { name: 'View learning summary' }));
  await screen.findByText(/2 effective observations/);
  fireEvent.click(screen.getByRole('button', { name: 'Unmapped work' }));
  fireEvent.click(screen.getAllByRole('button', { name: 'Inspect / link evidence' })[0]);
  fireEvent.click(screen.getByRole('button', { name: 'Correct saved transcription / assessment' }));
  expect(screen.getByLabelText('Parent assessment').value).toBe('Unanswered');
  fireEvent.change(screen.getByLabelText('Clarified answer'), { target: { value: 'Marco Polo' } });
  fireEvent.change(screen.getByLabelText('Reason for this parent change'), { target: { value: 'Checked the photograph.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save answer amendment' }));
  await waitFor(() => expect(api.fetchApi).toHaveBeenCalledWith('/records/learning/1/5/attempts/a1/clarify', {
    method: 'POST', body: JSON.stringify({ expected_revision: 1, transcription: 'Marco Polo', note: 'Checked the photograph.', result: 'Unanswered' }),
  }));
});

it('lets a parent associate only selected observed work and shows save failures', async () => {
  show(); fireEvent.click(screen.getByRole('button', { name: 'View learning summary' }));
  await screen.findByText(/2 effective observations/);
  fireEvent.click(screen.getByRole('button', { name: 'All evidence' }));
  fireEvent.click(screen.getAllByRole('button', { name: 'Inspect / link evidence' })[0]);
  fireEvent.change(screen.getByLabelText('Concept this evidence actually checks'), { target: { value: 'c1' } });
  fireEvent.change(screen.getByLabelText('Reason for this parent change'), { target: { value: 'Question assesses this concept.' } });
  api.fetchApi.mockRejectedValueOnce(new Error('Another parent changed these links.'));
  fireEvent.click(screen.getByRole('button', { name: 'Save evidence link' }));
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Another parent changed these links.');
  const sent = JSON.parse(api.fetchApi.mock.calls.at(-1)[1].body);
  expect(sent).toEqual({ expected_revision: 0, evidence_kind: 'attempt', evidence_id: 'a1', map_id: 'm1', concept_id: 'c1', status: 'linked', note: 'Question assesses this concept.' });
});
