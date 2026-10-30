/* @vitest-environment jsdom */
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { FeedbackProvider } from '../ui';

const api = vi.hoisted(() => ({ companions: vi.fn(), createCompanion: vi.fn(), importCompanion: vi.fn(), companionPage: vi.fn() }));
vi.mock('../api/books', () => ({ booksApi: api }));
import BookCompanions from './BookCompanions';

const row = { document_id: 7, name: 'Synthetic Portuguese.pdf', page_count: 2, revision: 1, status: 'needs_review', checked_pages: 1, pending_pages: 1, exercises: 3, visual_elements: 1 };
beforeEach(() => {
  api.companions.mockResolvedValue({ books: [row] });
  api.createCompanion.mockResolvedValue({});
  api.importCompanion.mockResolvedValue({});
  api.companionPage.mockResolvedValue({ status: 'native_draft', printed_page: null, teacher_material: false,
    issues: ['Visual structure not checked'], text: 'Synthetic source text', native_text: 'Original extraction', elements: [] });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });
function show() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <FeedbackProvider><BookCompanions subject={{ id: 5 }} collection={{ books: [row], version_id: 'v1' }} /></FeedbackProvider>
  </QueryClientProvider>);
}
it('distinguishes checked pages from a native draft and inspects source text without starting AI', async () => {
  show();
  expect(await screen.findByText('1 of 2 pages checked · 1 to review')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Inspect JSON for Synthetic Portuguese.pdf' }));
  const dialog = screen.getByRole('dialog');
  expect(await within(dialog).findByText('Synthetic source text')).toBeTruthy();
  expect(within(dialog).getByText('Needs source review')).toBeTruthy();
  fireEvent.change(within(dialog).getByLabelText('Inspect PDF page'), { target: { value: '2' } });
  await waitFor(() => expect(api.companionPage).toHaveBeenCalledWith(5, 7, 2));
  expect(api.createCompanion).not.toHaveBeenCalled();
});
it('creates a local representation explicitly and imports using the observed revision', async () => {
  show();
  fireEvent.click(await screen.findByRole('button', { name: 'Update from checked pages' }));
  await waitFor(() => expect(api.createCompanion).toHaveBeenCalledWith(5, 7));
  await screen.findByText('Book JSON saved. Unchecked pages remain marked for review.');
  const file = new File(['{}'], 'book.json', { type: 'application/json' });
  fireEvent.click(screen.getByRole('button', { name: 'Import JSON for Synthetic Portuguese.pdf' }));
  fireEvent.change(screen.getByLabelText('Upload book JSON'), { target: { files: [file] } });
  await waitFor(() => expect(api.importCompanion).toHaveBeenCalledWith(5, 7, file, 1));
});
it('shows rejected mismatched imports and preserves the existing status', async () => {
  api.importCompanion.mockRejectedValue(new Error('This JSON belongs to a different PDF'));
  show();
  fireEvent.click(await screen.findByRole('button', { name: 'Import JSON for Synthetic Portuguese.pdf' }));
  fireEvent.change(screen.getByLabelText('Upload book JSON'), { target: { files: [new File(['{}'], 'wrong.json')] } });
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'This JSON belongs to a different PDF');
  expect(screen.getByText('1 of 2 pages checked · 1 to review')).toBeTruthy();
});
