/* @vitest-environment jsdom */
import { render, screen, cleanup } from '@testing-library/react';
import { afterEach, it, expect } from 'vitest';
import LessonStatusDot, { LessonStatusLegend } from './LessonStatusDot';
import { LESSON_STATES } from '../utils/lessonStates';
afterEach(cleanup);
it('names every state for screen readers and hover, and shows nothing for an unknown one', () => {
  for (const [state, info] of Object.entries(LESSON_STATES)) {
    cleanup();
    render(<LessonStatusDot state={state} />);
    const dot = screen.getByRole('img', { name: info.label });
    expect(dot.getAttribute('title')).toBe(info.label);
    expect(dot.className).toContain(info.className);
  }
  cleanup();
  const { container } = render(<LessonStatusDot state={undefined} />);
  expect(container.innerHTML).toBe('');
});
it('the legend explains the colors', () => {
  render(<LessonStatusLegend />);
  expect(screen.getByRole('list', { name: 'Lesson status colors' }).textContent).toContain('Ready: script and voice');
});
