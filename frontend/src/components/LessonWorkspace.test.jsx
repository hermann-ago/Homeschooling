/* @vitest-environment jsdom */
import { useEffect, useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import LessonWorkspace from './LessonWorkspace';
afterEach(cleanup);

it('switches book and tutor without losing an answer, book position or playback', () => {
  const unmounted = vi.fn();
  function Tutor() {
    const [answer, setAnswer] = useState('');
    const [playing, setPlaying] = useState(false);
    useEffect(() => () => unmounted(), []);
    return <aside className="lesson-tutor-panel"><label>Answer<textarea value={answer} onChange={event => setAnswer(event.target.value)} /></label><button onClick={() => setPlaying(!playing)}>{playing ? 'Pause test audio' : 'Play test audio'}</button></aside>;
  }
  function Book() {
    const [page, setPage] = useState(17);
    return <><p>Book page {page}</p><button onClick={() => setPage(page + 1)}>Next page</button></>;
  }
  render(<LessonWorkspace book={<Book />}><Tutor /></LessonWorkspace>);
  fireEvent.change(screen.getByLabelText('Answer'), { target: { value: 'My unfinished answer' } });
  fireEvent.click(screen.getByRole('button', { name: 'Play test audio' }));
  fireEvent.click(screen.getByRole('button', { name: 'Book pages' }));
  fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
  fireEvent.click(screen.getByRole('button', { name: 'Tutor & activities' }));
  expect(screen.getByLabelText('Answer').value).toBe('My unfinished answer');
  expect(screen.getByRole('button', { name: 'Pause test audio' })).toBeTruthy();
  expect(screen.getByText('Book page 18')).toBeTruthy();
  expect(unmounted).not.toHaveBeenCalled();
});

it('does not offer an empty tutor or book panel', () => {
  const { rerender } = render(<LessonWorkspace book={<p>Printed lesson</p>} hasTutor={false} />);
  expect(screen.queryByRole('group', { name: 'Lesson workspace' })).toBeNull();
  rerender(<LessonWorkspace book={null} hasBook={false}><aside>Text lesson</aside></LessonWorkspace>);
  expect(screen.queryByRole('group', { name: 'Lesson workspace' })).toBeNull();
  expect(screen.getByText('Text lesson')).toBeTruthy();
});
