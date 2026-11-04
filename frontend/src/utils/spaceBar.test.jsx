/* @vitest-environment jsdom */
import { cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { pressable, useSpaceBar } from './spaceBar';

function Lesson({ handler }) {
  useSpaceBar(handler);
  return <div><button type="button">Continue lesson</button><textarea aria-label="Answer" /><p>Text</p></div>;
}
afterEach(cleanup);

it('gives Space to the lesson, except while writing', () => {
  const handler = vi.fn(() => true);
  const view = render(<Lesson handler={handler} />);
  fireEvent.keyDown(view.getByText('Text'), { key: ' ' });
  expect(handler).toHaveBeenCalledTimes(1);
  fireEvent.keyDown(view.getByLabelText('Answer'), { key: ' ' });
  expect(handler).toHaveBeenCalledTimes(1);
});

it('stops a handled Space from also pressing the focused button', () => {
  const view = render(<Lesson handler={() => true} />);
  const button = view.getByRole('button');
  const down = fireEvent.keyDown(button, { key: ' ' });
  const up = fireEvent.keyUp(button, { key: ' ' });
  expect(down).toBe(false);
  expect(up).toBe(false);
});

it('leaves Space to a focused button when the lesson does not need it', () => {
  const view = render(<Lesson handler={(target) => !pressable(target)} />);
  expect(fireEvent.keyDown(view.getByRole('button'), { key: ' ' })).toBe(true);
});
