/* @vitest-environment jsdom */
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { FeedbackProvider } from '../ui';

const api = vi.hoisted(() => ({ collection: vi.fn(), saveCollection: vi.fn(), analysisStatus: vi.fn(), companions: vi.fn().mockResolvedValue({ books: [] }), materialSkills: vi.fn().mockResolvedValue({skills:[]}) }));
vi.mock('../api/books', async (original) => ({ ...await original(), booksApi: api }));
import SubjectBookCollection from './SubjectBookCollection';

const saved = () => ({ id: 'collection-1', name: 'History collection', revision: 2, version: 2, version_id: 'version-2', analysis_available: true, books: [
  { key: 'text-1', document_id: 1, name: 'Volume One', role: 'textbook', edition: 'First edition', is_main: true, position: 0 },
  { key: 'text-2', document_id: 2, name: 'Volume Two', role: 'textbook', edition: 'Second edition', is_main: false, position: 1 },
  { key: 'work', document_id: 3, name: 'Practice', role: 'workbook', companion_key: 'text-1', position: 2 },
  { key: 'key', document_id: 4, name: 'Teacher Key', role: 'answer_key', answer_for_key: 'work', position: 3 },
] });

beforeEach(() => { api.collection.mockResolvedValue(saved()); api.saveCollection.mockResolvedValue({}); api.analysisStatus.mockResolvedValue({ jobs: [] }); });
afterEach(() => { cleanup(); vi.clearAllMocks(); });

function show() {
  const onAdd = vi.fn();
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <FeedbackProvider><SubjectBookCollection subject={{ id: 5, name: 'History' }} onAdd={onAdd} /></FeedbackProvider>
  </QueryClientProvider>);
  return onAdd;
}

it('shows the complete collection and offers an explicit review without starting preparation', async () => {
  const onAdd = show();
  expect(await screen.findByText('Volume One · main book')).toBeTruthy();
  expect(screen.getByText('Answers for: Practice')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Understand these books together' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Add books to collection' }));
  expect(onAdd).toHaveBeenCalledOnce();
  expect(api.saveCollection).not.toHaveBeenCalled();
});

it('saves a changed reading order, main book, edition and explicit companion without preparation', async () => {
  show();
  await screen.findByText('Volume One · main book');
  fireEvent.click(screen.getByRole('button', { name: 'Organize books' }));
  const dialog = screen.getByRole('dialog');
  fireEvent.click(within(dialog).getByRole('button', { name: 'Move Volume Two earlier' }));
  fireEvent.click(within(dialog).getAllByRole('radio')[0]);
  fireEvent.change(within(dialog).getByLabelText('Edition for Volume Two'), { target: { value: '2026 edition' } });
  fireEvent.change(within(dialog).getByLabelText('Collection companion for Practice'), { target: { value: 'text-2' } });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Save collection' }));
  await waitFor(() => expect(api.saveCollection).toHaveBeenCalledWith(5, expect.objectContaining({ expected_revision: 2, books: [
    expect.objectContaining({ key: 'text-2', position: 0, is_main: true, edition: '2026 edition' }),
    expect.objectContaining({ key: 'text-1', position: 1, is_main: false }),
    expect.objectContaining({ key: 'work', companion_key: 'text-2' }),
    expect.objectContaining({ key: 'key', answer_for_key: 'work' }),
  ] })));
});

it('keeps edits visible after a stale-device save is rejected', async () => {
  api.saveCollection.mockRejectedValue(new Error('This collection changed on another device. Reopen it before saving.'));
  show();
  await screen.findByText('Volume One · main book');
  fireEvent.click(screen.getByRole('button', { name: 'Organize books' }));
  fireEvent.change(screen.getByLabelText('Collection name'), { target: { value: 'My History library' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save collection' }));
  expect(await screen.findByRole('alert')).toBeTruthy();
  expect(screen.getByLabelText('Collection name').value).toBe('My History library');
});

it('retains two exact targets for a shared answer key when saving the collection', async () => {
  const source=saved();source.books[0].role='combined';source.books[1].role='combined';
  source.books[3].answer_for_key='text-1';source.books[3].answer_for_keys=['text-1','text-2'];
  api.collection.mockResolvedValue(source);
  show();await screen.findByText('Volume One · main book');
  fireEvent.click(screen.getByRole('button',{name:'Organize books'}));
  expect(screen.getByLabelText('Answers in Teacher Key for Volume One').checked).toBe(true);
  expect(screen.getByLabelText('Answers in Teacher Key for Volume Two').checked).toBe(true);
  fireEvent.click(screen.getByRole('button',{name:'Save collection'}));
  await waitFor(()=>expect(api.saveCollection).toHaveBeenCalledWith(5,expect.objectContaining({books:expect.arrayContaining([
    expect.objectContaining({key:'key',answer_for_keys:['text-1','text-2']})
  ])})));
});
