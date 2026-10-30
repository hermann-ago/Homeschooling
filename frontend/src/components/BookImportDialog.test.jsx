/* @vitest-environment jsdom */
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { FeedbackProvider } from '../ui';

const api = vi.hoisted(() => ({ incoming: vi.fn(), collection: vi.fn(), saveCollection: vi.fn(), stage: vi.fn(), import: vi.fn() }));
vi.mock('../api/books', async (original) => ({ ...await original(), booksApi: api }));
vi.mock('../api/documents', () => ({ driveBooks: vi.fn().mockResolvedValue([]) }));
import BookImportDialog from './BookImportDialog';

beforeEach(() => {
  api.collection.mockResolvedValue({ name: 'History books', revision: 0, books: [] });
  api.saveCollection.mockResolvedValue({});
  api.incoming.mockResolvedValue({ books: [
    { name: 'History.pdf', path: 'Incoming Books/History.pdf' },
    { name: 'Activity Book.pdf', path: 'Incoming Books/Future/Activity Book.pdf' },
  ] });
  api.import.mockResolvedValue({ jobs: [] });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

function show() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <FeedbackProvider><BookImportDialog subject={{ id: 5, name: 'History' }} onClose={vi.fn()} /></FeedbackProvider>
  </QueryClientProvider>);
}

it('selects paired resources from nested Incoming Books and preserves their roles', async () => {
  show();
  fireEvent.click(await screen.findByRole('checkbox', { name: /History.pdf/ }));
  fireEvent.click(screen.getByRole('checkbox', { name: /Activity Book.pdf/ }));
  expect(screen.getByLabelText('Role for Activity Book.pdf').value).toBe('workbook');
  fireEvent.change(screen.getByLabelText('Find a book'), { target: { value: 'Future' } });
  expect(screen.queryByRole('checkbox', { name: /History.pdf/ })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Save books to collection' }));
  await waitFor(() => expect(api.saveCollection).toHaveBeenCalledWith(5, expect.objectContaining({ expected_revision: 0,
    books: [expect.objectContaining({ path: 'Incoming Books/History.pdf', role: 'textbook', is_main: true }),
      expect.objectContaining({ path: 'Incoming Books/Future/Activity Book.pdf', role: 'workbook', is_main: false })] })));
  expect(api.import).not.toHaveBeenCalled();
});

it('stages browser uploads before saving the collection without paid preparation', async () => {
  api.stage.mockResolvedValue({ name: 'Workbook.pdf', path: 'Incoming Books/Workbook.pdf' });
  show();
  const file = new File(['%PDF'], 'Workbook.pdf', { type: 'application/pdf' });
  fireEvent.change(screen.getByLabelText('Upload books'), { target: { files: [file] } });
  await screen.findByLabelText('Role for Workbook.pdf');
  expect(api.stage).toHaveBeenCalledWith(file);
  fireEvent.click(screen.getByRole('button', { name: 'Save books to collection' }));
  await waitFor(() => expect(api.saveCollection).toHaveBeenCalledWith(5, expect.objectContaining({
    books: [expect.objectContaining({ path: 'Incoming Books/Workbook.pdf', role: 'workbook' })] })));
  expect(api.import).not.toHaveBeenCalled();
});

it('explicitly pairs a selected key with the selected combined workbook', async () => {
  api.incoming.mockResolvedValue({ books: [{ name: 'Combined.pdf', path: 'Incoming Books/Combined.pdf' }, { name: 'Answer Key.pdf', path: 'Incoming Books/Answer Key.pdf' }] });
  show();
  fireEvent.click(await screen.findByRole('checkbox', { name: /Combined.pdf/ }));
  fireEvent.change(screen.getByLabelText('Role for Combined.pdf'), { target: { value: 'combined' } });
  fireEvent.click(screen.getByRole('checkbox', { name: /Answer Key.pdf/ }));
  fireEvent.change(screen.getByLabelText('Answer key belongs to Answer Key.pdf'), { target: { value: 'selected:Incoming Books/Combined.pdf' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save books to collection' }));
  await waitFor(() => expect(api.saveCollection).toHaveBeenCalledWith(5, expect.objectContaining({ books: [
    expect.objectContaining({ path: 'Incoming Books/Combined.pdf', role: 'combined' }),
    expect.objectContaining({ path: 'Incoming Books/Answer Key.pdf', role: 'answer_key', answer_for_key: 'selected:Incoming Books/Combined.pdf' }),
  ] })));
});

it('retains the existing collection and links additions to its selected textbook', async () => {
  api.collection.mockResolvedValue({ name: 'History collection', revision: 7, books: [
    { key: 'existing-main', document_id: 12, path: 'Lucas/History/Books/History.pdf', name: 'History', role: 'textbook', is_main: true },
  ] });
  show();
  fireEvent.click(await screen.findByRole('checkbox', { name: /Activity Book.pdf/ }));
  await screen.findByLabelText('Companion textbook for Activity Book.pdf');
  fireEvent.change(screen.getByLabelText('Companion textbook for Activity Book.pdf'), { target: { value: 'existing-main' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save books to collection' }));
  await waitFor(() => expect(api.saveCollection).toHaveBeenCalledWith(5, expect.objectContaining({ expected_revision: 7, books: [
    expect.objectContaining({ key: 'existing-main', document_id: 12, is_main: true }),
    expect.objectContaining({ role: 'workbook', companion_key: 'existing-main' }),
  ] })));
});

it('recognizes Portuguese gabarito filenames while requiring an explicit target book', async () => {
  api.incoming.mockResolvedValue({ books: [{ name: 'gabarito-novo-3a.pdf', path: 'Incoming Books/gabarito-novo-3a.pdf' }] });
  show();
  fireEvent.click(await screen.findByRole('checkbox', { name: /gabarito-novo-3a.pdf/ }));
  expect(screen.getByLabelText('Role for gabarito-novo-3a.pdf').value).toBe('answer_key');
  expect(screen.getByLabelText('Answer key belongs to gabarito-novo-3a.pdf').value).toBe('');
});
