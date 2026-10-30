/* @vitest-environment jsdom */
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import useViewportHeight from './useViewportHeight';
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
function Viewport() { useViewportHeight(); return null; }

it('adapts to the keyboard and browser chrome without resizing the app during pinch zoom', () => {
  const viewport = Object.assign(new EventTarget(), { height: 780, width: 390, scale: 1 });
  vi.stubGlobal('visualViewport', viewport);
  const { unmount } = render(<Viewport />);
  const height = () => document.documentElement.style.getPropertyValue('--app-height');
  expect(height()).toBe('780px');
  const input = document.createElement('textarea');document.body.append(input);input.focus();
  act(() => { viewport.height = 390; viewport.dispatchEvent(new Event('resize')); });
  expect(height()).toBe('390px');
  expect(document.documentElement.dataset.keyboardOpen).toBe('true');
  act(() => { viewport.scale = 2; viewport.height = 195; viewport.dispatchEvent(new Event('resize')); });
  expect(height()).toBe('390px');
  act(() => { viewport.scale = 1; viewport.height = 780; viewport.dispatchEvent(new Event('resize')); });
  expect(height()).toBe('780px');
  expect(document.documentElement.dataset.keyboardOpen).toBe('false');
  // Turning to landscape is a new baseline, rather than a keyboard opening.
  act(() => { viewport.width = 780; viewport.height = 390; viewport.dispatchEvent(new Event('resize')); });
  expect(document.documentElement.dataset.keyboardOpen).toBe('false');
  input.remove();
  unmount();
  expect(height()).toBe('');
  expect(document.documentElement.dataset.keyboardOpen).toBeUndefined();
});
