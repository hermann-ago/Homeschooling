/* @vitest-environment jsdom */
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { FeedbackProvider } from '../ui';

const api = vi.hoisted(() => ({ teachingSkill: vi.fn(), skillHistory: vi.fn(), saveSkill: vi.fn() }));
const bookApi = vi.hoisted(() => ({ teachingSkill: vi.fn(), skillHistory: vi.fn(), saveSkill: vi.fn() }));
vi.mock('../api/subjects', () => ({ subjectsApi: api }));
vi.mock('../api/library', () => ({ libraryApi: bookApi }));
import TeachingSkillEditor, { MarkdownPreview } from './TeachingSkillEditor';

afterEach(() => { cleanup(); vi.clearAllMocks(); });
describe('Teaching skills', () => {
  it('saves library instructions against the book for every current and future reader', async () => {
    bookApi.teachingSkill.mockResolvedValue({ version: 1, content: '# Shared book\nUse original source examples.', file_path: 'Family Library/library-02/Teaching Skill/SKILL-v1.md' });
    bookApi.skillHistory.mockResolvedValue([]);
    bookApi.saveSkill.mockImplementation((id, content) => Promise.resolve({ version: 2, content }));
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <FeedbackProvider><TeachingSkillEditor subject={{ id: 15, name: 'The Law' }} libraryBook="library-02" /></FeedbackProvider>
    </QueryClientProvider>);
    const editor = await screen.findByLabelText('Teaching instructions for The Law');
    expect(screen.getByText(/Shared instructions for this book, for every child/)).toBeTruthy();
    fireEvent.change(editor, { target: { value: '# Shared book\nUse trading fruit as an example.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(bookApi.saveSkill).toHaveBeenCalledWith('library-02', '# Shared book\nUse trading fruit as an example.', 1));
    expect(api.saveSkill).not.toHaveBeenCalled();
  });
  it('edits and restores instructions as new versions using the current version guard', async () => {
    api.teachingSkill.mockResolvedValue({ version: 2, content: '# History\n\nUse maps.', file_path: 'Lucas/History/Teaching Skill/SKILL-v2.md' });
    api.skillHistory.mockResolvedValue([{ id: 1, version: 1, content: '# History\n\nAsk for a retelling.' }]);
    api.saveSkill.mockImplementation((id, content) => Promise.resolve({ version: 3, content }));
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <FeedbackProvider><TeachingSkillEditor subject={{ id: 5, name: 'History' }} /></FeedbackProvider>
    </QueryClientProvider>);
    const editor = await screen.findByLabelText('Teaching instructions for History');
    fireEvent.change(editor, { target: { value: '# History\n\nUse maps and short questions.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.saveSkill).toHaveBeenCalledWith(5, '# History\n\nUse maps and short questions.', 2));
    await screen.findByText(/Version 3/);
    fireEvent.change(screen.getByLabelText('Previous skill versions'), { target: { value: '1' } });
    fireEvent.click(await screen.findByRole('button', { name: 'Restore this version' }));
    await waitFor(() => expect(api.saveSkill).toHaveBeenLastCalledWith(5, '# History\n\nAsk for a retelling.', 3));
  });
  it('renders a readable preview without executing embedded HTML', () => {
    const { container } = render(<MarkdownPreview content={'# History\n## Teaching style\n<script>doSomething()</script>\n- One question\n- Wait for the learner'} />);
    expect(screen.getByRole('heading', { name: 'History' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Teaching style' })).toBeTruthy();
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(container.querySelector('script')).toBeNull();
  });
  it('keeps an unsaved draft and its original revision when another device changes the saved skill', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    api.teachingSkill.mockResolvedValue({ version: 2, content: '# History\nUse maps.' });
    api.skillHistory.mockResolvedValue([]);
    api.saveSkill.mockRejectedValue(new Error('The teaching skill changed. Reload it before saving.'));
    render(<QueryClientProvider client={client}><FeedbackProvider><TeachingSkillEditor subject={{ id: 5, name: 'History' }} /></FeedbackProvider></QueryClientProvider>);
    fireEvent.change(await screen.findByLabelText('Teaching instructions for History'), { target: { value: '# My draft' } });
    client.setQueryData(['teaching-skill', 5], { version: 3, content: '# Other device' });
    await screen.findByText(/saved instructions changed elsewhere/);
    expect(screen.getByLabelText('Teaching instructions for History').value).toBe('# My draft');
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.saveSkill).toHaveBeenCalledWith(5, '# My draft', 2));
    expect(await screen.findByRole('alert')).toBeTruthy();
  });
});
