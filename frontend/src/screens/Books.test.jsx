/* @vitest-environment jsdom */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { LearnerContext } from '../app/learnerContext';
import Books, { BookDetail } from './Books';

const api = vi.hoisted(() => ({ list: vi.fn(), book: vi.fn(), enroll: vi.fn(), pause: vi.fn(), upload: vi.fn(), prepare: vi.fn(), add: vi.fn() }));
vi.mock('../api/library', () => ({ libraryApi: api }));
vi.mock('../components/TeachingSkillEditor', () => ({ default: () => <p>Teaching instructions</p> }));
vi.mock('../components/BookNavigation', () => ({ default: () => <p>Source preparation</p> }));

const learner = { id: 1, name: 'Lucas', color: '#476859' };
const stages = [{ id: 1, title: 'The Gateway' }, { id: 2, title: 'Case Against the State' }];
const book = { id: 'library-02', position: 2, title: 'The Law', author: 'Frederic Bastiat', year: 1850, stage: 1, stage_title: 'The Gateway',
  estimated_pages: 60, revision: 1, document: null, readings: [], source_label: 'Provided source', source_url: 'https://mises.org/library/book/law', availability: '100% Free' };
const reading = { id: 'reading-1', child_id: 1, subject_id: 3, subject: { id: 3, name: 'The Law' }, topics: [], total_topics: 0, completed_topics: 0, job: null, resume_session: null };

function show(path = '/books') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } });
  return render(<QueryClientProvider client={client}><LearnerContext.Provider value={{ learners: [learner], single: 1, selected: 1, select: vi.fn() }}>
    <MemoryRouter initialEntries={[path]}><Routes><Route path="/books" element={<Books />} /><Route path="/books/:bookId" element={<BookDetail />} /></Routes></MemoryRouter>
  </LearnerContext.Provider></QueryClientProvider>);
}

beforeEach(() => {
  api.list.mockResolvedValue({ stages, books: [book, { ...book, id: 'library-12', title: 'Political Authority', author: 'Michael Huemer', stage: 2, readings: [reading] }] });
  api.book.mockResolvedValue(book);
});
afterEach(() => { cleanup(); Object.values(api).forEach(fn => fn.mockReset()); });

it('searches by author, filters stages and distinguishes a saved reading list from an uploaded file', async () => {
  show();
  expect(await screen.findByText('The Law')).toBeTruthy();
  expect(screen.getByText('Political Authority')).toBeTruthy();
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search books' }), { target: { value: 'huemer' } });
  expect(screen.queryByText('The Law')).toBeNull();
  expect(screen.getByText('Political Authority')).toBeTruthy();
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: '' } });
  fireEvent.click(screen.getByRole('button', { name: '1. The Gateway' }));
  expect(screen.queryByText('Political Authority')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'All stages' }));
  fireEvent.change(screen.getByRole('combobox', { name: 'Show' }), { target: { value: 'mine' } });
  expect(screen.queryByText('The Law')).toBeNull();
  expect(screen.getByText('Political Authority')).toBeTruthy();
  expect(api.prepare).not.toHaveBeenCalled();
});

it('adds optional reading without starting source indexing or inventing topics', async () => {
  api.enroll.mockImplementation(async () => { api.book.mockResolvedValue({ ...book, readings: [reading] }); return reading; });
  show('/books/library-02');
  fireEvent.click(await screen.findByRole('button', { name: "Add to Lucas's curriculum" }));
  expect(await screen.findByText(/In Lucas's curriculum. Upload the PDF/)).toBeTruthy();
  expect(api.enroll).toHaveBeenCalledWith('library-02', 1);
  expect(api.prepare).not.toHaveBeenCalled();
  expect(screen.queryByRole('link', { name: 'Open reader' })).toBeNull();
});

it('saves an uploaded PDF without starting AI preparation', async () => {
  api.book.mockResolvedValue({ ...book, readings: [reading] });
  const file = new File(['%PDF fixture'], 'book.pdf', { type: 'application/pdf' });
  api.upload.mockImplementation(async () => { api.book.mockResolvedValue({ ...book, readings: [reading], document: { id: 2, page_count: 60, original_filename: 'book.pdf', file_path: 'Family Library/Books/book.pdf' } }); });
  show('/books/library-02');
  fireEvent.change(await screen.findByLabelText('Upload book PDF'), { target: { files: [file] } });
  await waitFor(() => expect(api.upload).toHaveBeenCalledWith('library-02', file, 1));
  expect(await screen.findByRole('button', { name: 'Prepare chapter map' })).toBeTruthy();
  expect(api.prepare).not.toHaveBeenCalled();
});

it('pauses only the selected child and offers to resume retained progress', async () => {
  api.book.mockResolvedValue({ ...book, readings: [{ ...reading, active: true, completed_topics: 1 }] });
  api.pause.mockImplementation(async () => {
    api.book.mockResolvedValue({ ...book, readings: [{ ...reading, active: false, completed_topics: 1 }] });
  });
  show('/books/library-02');
  fireEvent.click(await screen.findByRole('button', { name: "Remove from Lucas's curriculum" }));
  await waitFor(() => expect(api.pause).toHaveBeenCalledWith('library-02', 1));
  expect(await screen.findByRole('button', { name: "Add to Lucas's curriculum" })).toBeTruthy();
  expect(screen.getByText(/Saved progress is retained/)).toBeTruthy();
  expect(api.prepare).not.toHaveBeenCalled();
});

it('opens the existing reader with the exact learner, topic and unfinished session', async () => {
  api.book.mockResolvedValue({ ...book, document: { id: 2, page_count: 60 }, readings: [{ ...reading, total_topics: 2,
    topics: [{ id: 42, title: 'An argument', page_start: 1, page_end: 3 }, { id: 43, title: 'A question', page_start: 3, page_end: 5 }],
    job: { status: 'ready', stage: 'Ready', done: 60, total: 60 }, resume_session: { id: 'session-7', topic_id: 43 } }] });
  show('/books/library-02');
  const link = await screen.findByRole('link', { name: 'Resume reading session' });
  const params = new URL(link.href).searchParams;
  expect(params.get('learner')).toBe('1');
  expect(params.get('topic')).toBe('43');
  expect(params.get('session')).toBe('session-7');
  expect(screen.getByText('0 of 2 topics read')).toBeTruthy();
  expect(screen.getByText('An argument')).toBeTruthy();
});

it('keeps paused indexing retryable and displays its saved progress', async () => {
  api.book.mockResolvedValue({ ...book, document: { id: 2, page_count: 60 }, readings: [{ ...reading, job: { status: 'failed', stage: 'Reading pages', done: 12, total: 60, error: 'Book allowance reached' } }] });
  api.prepare.mockResolvedValue({ ...reading });
  show('/books/library-02');
  expect(await screen.findByText('Book allowance reached')).toBeTruthy();
  expect(screen.getByText(/Reading pages.*12 of 60.*contents pages read/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Prepare chapter map' }));
  await waitFor(() => expect(api.prepare).toHaveBeenCalledWith('library-02', 1));
});
