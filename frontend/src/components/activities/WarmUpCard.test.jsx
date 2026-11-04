/* @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import WarmUpCard from './WarmUpCard';

afterEach(cleanup);

it('shows where the lesson sits and the last lesson\'s closing words, with nothing to answer', () => {
  render(<WarmUpCard warmUp={{ last: { title: 'Lesson 17: Mental Math', summary: 'You learned three ways to subtract.', audio: { track_id: 't', part: 23 } },
    today: 'Lesson 18: Elapsed Time', next: 'Lesson 19: Rounding' }} />);
  expect(screen.getByText('Lesson 17: Mental Math')).toBeTruthy();
  expect(screen.getByText('Lesson 18: Elapsed Time')).toBeTruthy();
  expect(screen.getByText('Lesson 19: Rounding')).toBeTruthy();
  expect(screen.getByText('You learned three ways to subtract.')).toBeTruthy();
  expect(screen.getByRole('button', { name: '▶ Listen' })).toBeTruthy();
  expect(screen.queryByRole('textbox')).toBeNull();
  expect(screen.queryByRole('radio')).toBeNull();
});

it('shows only the strip when the last lesson was done in the book without a saved summary', () => {
  render(<WarmUpCard warmUp={{ last: { title: 'Lesson 16' }, today: 'Lesson 17', next: null }} />);
  expect(screen.getByText('Lesson 16')).toBeTruthy();
  expect(screen.queryByText('Last time', { selector: 'p' })).toBeNull();
  expect(screen.queryByRole('button')).toBeNull();
});
