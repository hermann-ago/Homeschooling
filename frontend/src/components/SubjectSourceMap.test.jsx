/* @vitest-environment jsdom */
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { FeedbackProvider } from '../ui';

const api = vi.hoisted(() => ({ subjectMap: vi.fn(), reviewMap: vi.fn(), mapReading: vi.fn(), selectMap: vi.fn() }));
vi.mock('../api/books', async (original) => ({ ...await original(), booksApi: api }));
import SubjectSourceMap from './SubjectSourceMap';

const map = {
  id: 'm1', overview: 'History connects travel and trade.', coverage: { books: 2, pages: 6, exercises: 1, complete: false, pending_exercises: 1 },
  books: [{ id: 'main', document_id: 1, name: 'History textbook', position: 0, role: 'textbook', pages: 4, is_main: true },
    { id: 'work', document_id: 2, name: 'Practice book', position: 1, role: 'workbook', pages: 2, companion_id: 'main' }],
  sections: [{ id: 'u1', document_id: 1, pages: [1, 4], overview: 'The reading introduces Marco Polo.' }],
  concepts: [{ id: 'c1', unit_id: 'u1', review_id: 'concept-1', title: 'Travel and trade', objective: 'Explain the connection.',
    document_id: 1, evidence: [{ page: 2, quote: 'Marco Polo travelled to China.' }], status: 'proposed' }],
  events: [{ unit_id: 'u1', review_id: 'event-1', document_id: 1, title: 'Unknown arrival', start_year: null, end_year: null, date_text: 'During the Middle Ages',
    evidence: { page: 2, quote: 'Marco Polo travelled to China.' } }],
  connections: [{ review_id: 'connection-1', from_concept: 'c1', to_concept: 'c1', relationship: 'Context', explanation: 'Travel connects places.' }],
  exercises: [{ id: 'e1', document_id: 2, chapter: 1, section: 'Mongols', reference: '1', prompt: 'Who travelled?', pages: [1], student_safe: true,
    answer_link_status: 'linked', answer_source: { pages: [2] } }],
  exercise_links: [{ exercise_id: 'e1', review_id: 'link-1', status: 'pending', evidence: [], reason: 'Unfinished link' }],
  flagged_items: 1, issues: ['Inspect the date.'], review_issues: [{ text: 'Inspect the date.', review_id: 'issue-1' }],
  review_revision: 0, review_history: [], unapplied_reviews: [], review_counts: { approved: 0, corrected: 0, rejected: 0 },
};

beforeEach(() => { api.subjectMap.mockResolvedValue(structuredClone(map)); });
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it('shows source-bound cross-book assignments and pending page coverage', async()=>{
  const value=structuredClone(map);value.coverage.pending_pages=4;value.coverage.checked_pages=2;
  value.book_relationships=[{from_document_id:1,to_document_id:2,relationship:'required_reading',source_page:2,
    source_quote:'Read Chapter 1 of the practice book.',target_pages:[1,2],explanation:'An explicit source assignment.'}];
  api.subjectMap.mockResolvedValue(value);show();await screen.findByText(map.overview);
  expect(screen.getByText(/2 pages checked · 4 pages awaiting source review/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Books',exact:true}));
  expect(screen.getByText('An explicit source assignment.')).toBeTruthy();
  expect(screen.getByText(/Read Chapter 1 of the practice book/)).toBeTruthy();
  expect(api.reviewMap).not.toHaveBeenCalled();
});
function show() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <FeedbackProvider><SubjectSourceMap id="m1" onClose={vi.fn()} /></FeedbackProvider></QueryClientProvider>);
}

it('opens source quotations and original page controls without generating or saving a review', async () => {
  api.mapReading.mockResolvedValue({ name: 'History textbook', document_id: 1, pages: [{ page: 2, text: 'Marco Polo travelled to China.', pdf_available: true }] });
  show(); await screen.findByText(map.overview);
  fireEvent.click(screen.getByRole('button', { name: 'Concepts', exact: true }));
  fireEvent.click(screen.getByRole('button', { name: 'Review Travel and trade' }));
  fireEvent.click(screen.getByRole('button', { name: 'Inspect original reading', exact: true }));
  await screen.findByRole('button', { name: 'Open original PDF page 2' });
  expect(api.mapReading).toHaveBeenCalledWith('m1', 'u1');
  expect(api.reviewMap).not.toHaveBeenCalled();
});

it('selects only explicitly checked portions with both current revisions', async () => {
  const checked = structuredClone(map);
  checked.review_counts.approved = 1; checked.review_revision = 3;
  checked.teaching_selection = { selection_number: 2, active: false };
  api.subjectMap.mockResolvedValue(checked);
  api.selectMap.mockResolvedValue({ ...checked, teaching_selection: { selection_number: 3, active: true, map_id: 'm1', review_number: 3, note: 'Checked portions are selected.' } });
  show(); await screen.findByText(map.overview);
  fireEvent.click(screen.getByRole('button', { name: 'Use checked portions for new lessons' }));
  await waitFor(() => expect(api.selectMap).toHaveBeenCalledWith('m1', { expected_revision: 2, expected_review_revision: 3 }));
  await screen.findByText('Checked portions are selected.');
  expect(screen.getByRole('button', { name: 'Use checked portions for new lessons' }).disabled).toBe(true);
});

it('saves a parent correction with the current revision and retains the history', async () => {
  const updated = structuredClone(map);
  updated.review_revision = 1; updated.concepts[0].title = 'Marco Polo and trade';
  updated.concepts[0].parent_review = { status: 'corrected', note: 'Checked the book.', review_number: 1 };
  updated.review_counts.corrected = 1;
  updated.review_history = [{ id: 'r1', target_id: 'concept-1', kind: 'concept', status: 'corrected', review_number: 1,
    original: map.concepts[0], note: 'Checked the book.', changes: { title: 'Marco Polo and trade' } }];
  api.reviewMap.mockResolvedValue(updated);
  show(); await screen.findByText(map.overview);
  fireEvent.click(screen.getByRole('button', { name: 'Concepts', exact: true }));
  fireEvent.click(screen.getByRole('button', { name: 'Review Travel and trade' }));
  fireEvent.change(screen.getByLabelText('Review decision'), { target: { value: 'corrected' } });
  fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Marco Polo and trade' } });
  fireEvent.change(screen.getByLabelText('Parent note'), { target: { value: 'Checked the book.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save parent review' }));
  await waitFor(() => expect(api.reviewMap).toHaveBeenCalledWith('m1', { expected_revision: 0, kind: 'concept', target_id: 'concept-1',
    status: 'corrected', note: 'Checked the book.', changes: { title: 'Marco Polo and trade' } }));
  await screen.findByText('Parent review saved on the home server. No AI generation charge.');
  expect(screen.getByText('Marco Polo and trade')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'History', exact: true }));
  expect(screen.getByText('Parent corrected · concept · revision 1')).toBeTruthy();
  expect(screen.getByText('Travel and trade')).toBeTruthy();
});

it('preserves original exercise numbers and exposes exact quotation checks', async () => {
  api.reviewMap.mockRejectedValue(new Error('The quotation must match the selected original PDF page'));
  show(); await screen.findByText(map.overview);
  fireEvent.click(screen.getByRole('button', { name: 'Exercises', exact: true }));
  fireEvent.click(screen.getByRole('button', { name: 'Review Chapter 1 · Mongols · 1' }));
  fireEvent.change(screen.getByLabelText('Review decision'), { target: { value: 'corrected' } });
  fireEvent.click(screen.getByRole('button', { name: 'Add reading evidence' }));
  fireEvent.change(screen.getByLabelText('PDF page 1'), { target: { value: '2' } });
  fireEvent.change(screen.getByLabelText('Exact quotation 1'), { target: { value: 'Wrong source quotation.' } });
  fireEvent.change(screen.getByLabelText('Parent note'), { target: { value: 'Testing source validation.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save parent review' }));
  await screen.findByRole('alert');
  expect(api.reviewMap.mock.calls[0][1].changes.evidence).toEqual([{ unit_id: 'u1', page: 2, quote: 'Wrong source quotation.' }]);
  expect(screen.getByText(/Chapter 1 · Mongols · 1/, { selector: 'h3' })).toBeTruthy();
});

it('shows unknown historical dates and review filters without assuming the child has learned them', async () => {
  show(); await screen.findByText(map.overview);
  fireEvent.click(screen.getByRole('button', { name: 'Timeline', exact: true }));
  expect(screen.getByText('Unknown date')).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Parent review filter'), { target: { value: 'reviewed' } });
  expect(screen.getByText('No items match this view.')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Books', exact: true }));
  expect(screen.getByText('Reading companion: History textbook')).toBeTruthy();
});

it('reloads a concurrent parent review without silently resubmitting the correction', async () => {
  const conflict = new Error('Another parent changed this map. Reopen it before saving your correction.'); conflict.status = 409;
  api.reviewMap.mockRejectedValue(conflict);
  show(); await screen.findByText(map.overview);
  fireEvent.click(screen.getByRole('button', { name: 'Review items', exact: true }));
  fireEvent.click(screen.getByRole('button', { name: 'Review Inspect the date.' }));
  fireEvent.click(screen.getByRole('button', { name: 'Save parent review' }));
  expect(await screen.findByRole('alert')).toBeTruthy();
  expect(api.subjectMap).toHaveBeenCalledTimes(2);
  expect(api.reviewMap).toHaveBeenCalledTimes(1);
  expect(within(screen.getByRole('dialog', { name: 'Parent review' })).getByLabelText('Review decision').value).toBe('approved');
});

it('includes uncertain exercise links alongside general source warnings', async () => {
  const flagged = structuredClone(map); flagged.exercise_links[0].status = 'needs_review';
  api.subjectMap.mockResolvedValue(flagged);
  show(); await screen.findByText(map.overview);
  fireEvent.click(screen.getByRole('button', { name: 'Review items', exact: true }));
  expect(screen.getByText('Who travelled?')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Review Chapter 1 · Mongols · 1' }));
  fireEvent.change(screen.getByLabelText('Review decision'), { target: { value: 'corrected' } });
  expect(screen.getByRole('button', { name: 'Add reading evidence' })).toBeTruthy();
  expect(api.reviewMap).not.toHaveBeenCalled();
});
