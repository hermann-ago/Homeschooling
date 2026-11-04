/* @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ videos: vi.fn(), findVideos: vi.fn(), setLessonVideo: vi.fn(), clearLessonVideo: vi.fn() }));
vi.mock('../api/subjects', () => ({ subjectsApi: api }));
import SubjectVideos from './SubjectVideos';
afterEach(cleanup);

it('finds videos from the pages and lets one lesson go without one', async () => {
  const lessons = [{ topic_id: 1, title: 'Lesson 1', video: { open_url: 'https://vimeo.com/1', source: 'found' } }, { topic_id: 2, title: 'Lesson 2', video: null }];
  api.videos.mockResolvedValue({ pages: [], lessons: [] });
  api.findVideos.mockResolvedValue({ pages: ['https://pub.example/unit-1'], videos: 1, matched: 1, unmatched: [], problems: [], lessons });
  render(<SubjectVideos subject={{ id: 7 }} />);
  fireEvent.change(await screen.findByRole('textbox'), { target: { value: ' https://pub.example/unit-1 \n' } });
  fireEvent.click(screen.getByRole('button', { name: 'Find videos' }));
  await waitFor(() => expect(api.findVideos).toHaveBeenCalledWith(7, ['https://pub.example/unit-1']));
  expect(await screen.findByText(/Found 1 videos · 1 matched/)).toBeTruthy();
  expect(screen.getByText('1 of 2 lessons have a video · Change one lesson')).toBeTruthy();
  api.videos.mockResolvedValue({ pages: ['https://pub.example/unit-1'], lessons: [{ ...lessons[0], video: null, hidden: true }, lessons[1]] });
  fireEvent.click(screen.getAllByRole('button', { name: 'Change' })[0]);
  fireEvent.click(screen.getByRole('button', { name: 'No video' }));
  await waitFor(() => expect(api.setLessonVideo).toHaveBeenCalledWith(1, { hidden: true }));
  expect(await screen.findByText('Hidden')).toBeTruthy();
});
