/* @vitest-environment jsdom */
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
const api = vi.hoisted(() => ({ knowledgeLibrary: vi.fn(), saveKnowledge: vi.fn(), reuseKnowledge: vi.fn() }));
vi.mock('../api/books', () => ({ booksApi: api }));
import SubjectKnowledge from './SubjectKnowledge';
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it('assigns checked source knowledge without analyzing or copying another child', async () => {
  api.knowledgeLibrary.mockResolvedValue({ collections: [{ source_subject_id: 5, collection_id: 'history', subject: 'History', grade: '3rd', collection_name: 'Volume Two', coverage: { books: 2 } }] });
  api.reuseKnowledge.mockResolvedValue({ collection: {}, knowledge_file: { path: 'Sibling/History/Subject Knowledge/subject-knowledge-v1.json' } });
  render(<QueryClientProvider client={new QueryClient()}><SubjectKnowledge subject={{ id: 8 }} collection={{ id: null, revision: 0, version_id: null }} /></QueryClientProvider>);
  expect(api.knowledgeLibrary).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Use saved subject knowledge' }));
  await screen.findByRole('option', { name: /Volume Two/ });
  fireEvent.change(screen.getByLabelText('Saved knowledge collection'), { target: { value: '5' } });
  fireEvent.click(screen.getByRole('button', { name: 'Use this collection' }));
  await waitFor(() => expect(api.reuseKnowledge).toHaveBeenCalledWith(8, { source_subject_id: 5, expected_revision: 0, expected_version_id: null }));
  expect(await screen.findByText(/Saved · Sibling/)).toBeTruthy();
  expect(api.saveKnowledge).not.toHaveBeenCalled();
});
