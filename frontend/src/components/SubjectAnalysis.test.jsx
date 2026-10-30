/* @vitest-environment jsdom */
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { FeedbackProvider } from '../ui';

const api = vi.hoisted(() => Object.fromEntries(['analysisStatus', 'analysisPreview', 'analyze', 'continueAnalysis', 'pauseAnalysis', 'subjectMap', 'companions', 'refreshSources','importSourceMap'].map((k) => [k, vi.fn()])));
vi.mock('../api/books', async (original) => ({ ...await original(), booksApi: api }));
import SubjectAnalysis from './SubjectAnalysis';

const collection = { id: 'c1', version_id: 'v1', analysis_available: true, books: [{ id: 1 }] };
const job = { id: 'j1', version_id: 'v1', status: 'paused_allowance', stage: 'Connecting exercises', done: 3, total: 3,
  spending: { used_usd: .018, maximum_usd: .02, uncertain_usd: .003 } };
beforeEach(() => {
  api.analysisStatus.mockResolvedValue({ jobs: [] });
  api.analysisPreview.mockResolvedValue({ fingerprint: 'fresh', books: 2, pages: 610, reusable_pages: 610, estimate_low_usd: .1,
    estimate_high_usd: .4, estimate_note: 'Planning estimate', family_allowance: { remaining_usd: 1.5 }, provider: 'openai', model: 'gpt-6-luna' });
});
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it('imports a Codex overview without starting provider analysis', async () => {
  api.importSourceMap.mockResolvedValue({map_id:'codex-map',ai_generation:false});
  show();await screen.findByRole('button',{name:'Import Codex overview'});
  const file=new File(['{}'],'source-map.json',{type:'application/json'});
  fireEvent.change(screen.getByLabelText('Upload Codex source overview'),{target:{files:[file]}});
  await screen.findByText('Codex overview saved. No AI allowance was used.');
  expect(api.importSourceMap).toHaveBeenCalledWith(5,file);
  expect(api.analyze).not.toHaveBeenCalled();expect(api.continueAnalysis).not.toHaveBeenCalled();
});
function show(value = collection) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}>
    <FeedbackProvider><SubjectAnalysis subject={{ id: 5, name: 'History' }} collection={value} /></FeedbackProvider>
  </QueryClientProvider>);
  return client;
}

it('opens a free preview and starts only with the parent-selected cap', async () => {
  show();
  fireEvent.click(screen.getByRole('button', { name: 'Understand these books together' }));
  await screen.findByText('2 books · 610 pages · 610 pages already scanned.');
  expect(api.analyze).not.toHaveBeenCalled();
  expect(screen.queryByLabelText('Maximum for this review (US dollars)')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Start review' }));
  await waitFor(() => expect(api.analyze).toHaveBeenCalledWith(5, { fingerprint: 'fresh', maximum_usd: .25 }));
});

it('keeps the total cap and uncertain reservations visible when continuing', async () => {
  api.analysisStatus.mockResolvedValue({ jobs: [job] });
  show();
  await screen.findByText('Paused at a spending limit');
  expect(screen.getByText('US$0.0030 is reserved for charges awaiting confirmation.')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Continue preparation' }));
  await screen.findByText('2 books · 610 pages · 610 pages already scanned.');
  expect(screen.queryByLabelText('Maximum for this review (US dollars)')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Continue review' }));
  await waitFor(() => expect(api.continueAnalysis).toHaveBeenCalledWith('j1', .25));
  expect(api.analyze).not.toHaveBeenCalled();
});

it.each([true, false])('reopens a saved overview with completion=%s without generating or raising a limit', async (complete) => {
  api.analysisStatus.mockResolvedValue({ jobs: [{ ...job, status: complete ? 'needs_review' : 'paused_allowance', map_id: 'm1' }] });
  api.subjectMap.mockResolvedValue({ overview: 'Travel and trade connect the books.', coverage: { books: 2, pages: 610, exercises: 40, complete, pending_exercises: complete ? 0 : 12 },
    concepts: [{}], connections: [{}], events: [{}], flagged_items: 2, issues: ['Check dates'] });
  show();
  fireEvent.click(await screen.findByRole('button', { name: 'View saved overview' }));
  await screen.findByText('Travel and trade connect the books.');
  expect(screen.getByText('Check dates')).toBeTruthy();
  if (!complete) expect(screen.getByText(/this snapshot still has 12 pending links/)).toBeTruthy();
  expect(api.analysisPreview).not.toHaveBeenCalled();
  expect(api.analyze).not.toHaveBeenCalled();
  expect(api.continueAnalysis).not.toHaveBeenCalled();
});

it('requires the collection to be saved before paid preparation', () => {
  show({ ...collection, analysis_available: false });
  expect(screen.getByRole('button', { name: 'Understand these books together' }).disabled).toBe(true);
});

it('refreshes reusable-file availability when analysis finishes without a page reload', async () => {
  api.analysisStatus.mockResolvedValue({ jobs: [{ ...job, status: 'needs_review', map_id: 'm1' }] });
  const client = show();
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  await screen.findByText('Overview saved · items need review');
  await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['subject-collection', 5] }));
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['subject-knowledge-library'] });
  expect(api.analyze).not.toHaveBeenCalled();
});

it('refreshes corrected source JSONs without starting AI analysis', async () => {
  api.analysisStatus.mockResolvedValue({jobs:[{...job,status:'needs_review',map_id:'m1'}]});
  api.companions.mockResolvedValue({books:[{document_id:21,content_sha256:'checked-hash'}]});
  api.refreshSources.mockResolvedValue({map_id:'m2',ai_generation:false});
  show();
  fireEvent.click(await screen.findByRole('button',{name:'Atualizar com JSONs revisados'}));
  await waitFor(()=>expect(api.refreshSources).toHaveBeenCalledWith(5,expect.objectContaining({
    expected_map_id:'m1',expected_version_id:'v1',expected_source_hashes:{'21':'checked-hash'},decisions:[],
  })));
  expect(api.analyze).not.toHaveBeenCalled();
  expect(api.continueAnalysis).not.toHaveBeenCalled();
});
