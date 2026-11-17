import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
/* @vitest-environment jsdom */
import { render, screen, cleanup } from '@testing-library/react';
import { afterEach, it, expect, vi } from 'vitest';
import BookNavigation from './BookNavigation';

const api = vi.hoisted(() => ({ navigation: vi.fn() }));
vi.mock('../api/books', () => ({ booksApi: api, bookRoles: [['textbook', 'Textbook']] }));
afterEach(cleanup);

it('says when the contents go on past the last page of the PDF', async () => {
  const chapters = [{ title: 'Lesson 1', page_start: 20, page_end: 25 }];
  api.navigation.mockResolvedValue({ books: [{ key: 'b', document_id: 37, name: 'Course.pdf', role: 'textbook', page_count: 70,
    navigation: { revision: 1, data: { chapters, beyond_end: [{ title: 'Lesson 10: Artifacts', printed_page: 53 },
      { title: 'Lesson 11: Around the World', printed_page: 65 }] } } }] });
  render(<QueryClientProvider client={new QueryClient()}><BookNavigation subject={{ id: 4 }} /></QueryClientProvider>);
  const note = await screen.findByRole('note');
  expect(note.textContent).toContain('2 more chapters after this PDF’s last page (Lesson 10: Artifacts, Lesson 11: Around the World)');
  expect(note.textContent).toContain('missing pages');
});
