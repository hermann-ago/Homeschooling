/* @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { Celebration, ProgressDots } from './Progress';

afterEach(cleanup);
const progress = { items: [{ id: 'a', outcome: 'first_try' }, { id: 'b', outcome: 'again' }, { id: 'c', outcome: 'pending' }],
  first_try: 1, graded: 2, practise: ['2. Diego took his horse out.\nHow long was the ride?'] };

it('shows one dot per exercise with what happened to it', () => {
  render(<ProgressDots progress={progress} currentId="c" />);
  expect(screen.getByText('Exercise 1: right on the first try')).toBeTruthy();
  expect(screen.getByText('Exercise 2: right after another go')).toBeTruthy();
  expect(screen.getByText('Exercise 3: still to do').parentElement.className).toContain('is-current');
});

it('celebrates first-try answers and lists what to practise next time', () => {
  render(<Celebration progress={progress} />);
  expect(screen.getByText('1 of 2 right on the first try')).toBeTruthy();
  expect(screen.getByText('2. Diego took his horse out.')).toBeTruthy();
});

it('cheers a perfect lesson and a lesson of grown-up checks', () => {
  const view = render(<Celebration progress={{ items: [], first_try: 3, graded: 3, practise: [] }} />);
  expect(screen.getByText('Every answer right on the first try! 3 of 3')).toBeTruthy();
  view.unmount();
  render(<Celebration progress={{ items: [], first_try: 0, graded: 0, practise: [] }} />);
  expect(screen.getByText('You finished today’s lesson!')).toBeTruthy();
});
