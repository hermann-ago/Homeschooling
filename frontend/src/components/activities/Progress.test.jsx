/* @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { Celebration, ProgressDots, ToFix } from './Progress';

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

it('reads the tutor reply aloud when an exercise to fix is opened', async () => {
  const { fireEvent } = await import('@testing-library/react');
  const voiced = [];
  const fix = { items: [{ id: 'a', outcome: 'fix', check: { read: '12', feedback: 'Look at the tens again.', reply_id: 'r-1:reply' } }, { id: 'b', outcome: 'pending' }] };
  render(<ProgressDots progress={fix} currentId="b" renderVoice={(message) => { voiced.push(message); return <span>voice</span>; }} />);
  fireEvent.click(screen.getByText('Exercise 1: something to fix').closest('button'));
  expect(voiced.at(-1)).toEqual({ id: 'r-1:reply', text: 'Look at the tens again.' });
});

it('lets a grown-up pass a written answer the photo check could not settle, but not a wrong one', () => {
  const passed = [];
  render(<ToFix busy={false} onFix={() => {}} onRetry={() => {}} onGrownUp={(id) => passed.push(id)} progress={{ items: [
    { id: 'count', outcome: 'grown_up', check: { prompt: 'How many houses?', read: '2', feedback: 'Check the count on the map together.' } },
    { id: 'sum', outcome: 'fix', check: { prompt: '3 + 4', read: '8', feedback: 'Count again.' } }] }} />);
  const buttons = screen.getAllByRole('button', { name: '✓ A grown-up says it looks good' });
  expect(buttons).toHaveLength(1);
  fireEvent.click(buttons[0]);
  expect(passed).toEqual(['count']);
});
