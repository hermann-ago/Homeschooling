/* @vitest-environment jsdom */
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const api = vi.hoisted(() => ({ estimateGuide: vi.fn(), prepareGuide: vi.fn() }));
vi.mock('../api/tutor', () => ({ tutorApi: api }));
import LessonPreparation from './LessonPreparation';
const topics = [{ id: 1, document_id: 1, title: 'Already read', completed: true, chapter_order: 1 },
  { id: 2, document_id: 1, title: 'Next lesson', chapter_order: 2 }, { id: 3, document_id: 1, title: 'Following lesson', chapter_order: 3 },
  { id: 4, document_id: 1, title: 'Later lesson', chapter_order: 4 }];
beforeEach(() => { api.estimateGuide.mockResolvedValue({ estimated_cost_usd: .01, remaining_usd: 1, allowed: true }); api.prepareGuide.mockResolvedValue({}); });
afterEach(() => { cleanup(); vi.resetAllMocks(); });
function show() { render(<QueryClientProvider client={new QueryClient()}><LessonPreparation subject={{ id: 5, child_id: 1 }} topics={topics} /></QueryClientProvider>); }
it('previews at most two unfinished lessons before paid preparation and retains completed work after failure', async () => {
  show(); fireEvent.click(screen.getByRole('button', { name: 'Preview next two lessons' }));
  await screen.findByText('Following lesson · Up to US$0.010');
  expect(api.prepareGuide).not.toHaveBeenCalled(); expect(api.estimateGuide.mock.calls).toEqual([[1, 2, false, 2], [1, 3, false, 2]]);
  api.prepareGuide.mockResolvedValueOnce({}).mockRejectedValueOnce(new Error('Paused at the allowance.'));
  fireEvent.click(screen.getByRole('button', { name: 'Prepare these lessons' }));
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('1 completed lesson remain saved.'));
  expect(api.prepareGuide.mock.calls).toEqual([[1, 2, 2], [1, 3, 2]]);
});
it('allows both guides regardless of legacy remaining allowance', async () => {
  api.estimateGuide.mockResolvedValue({ estimated_cost_usd: .01, remaining_usd: .015, allowed: true });
  show(); fireEvent.click(screen.getByRole('button', { name: 'Preview next two lessons' }));
  await screen.findByText('Following lesson · Up to US$0.010');
  expect(screen.getByRole('button', { name: 'Prepare these lessons' }).disabled).toBe(false);
  expect(screen.queryByRole('alert')).toBeNull();
  expect(api.prepareGuide).not.toHaveBeenCalled();
});
