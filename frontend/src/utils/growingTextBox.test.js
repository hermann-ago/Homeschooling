/* @vitest-environment jsdom */
import { describe, expect, it } from 'vitest';
import { fitToText } from './growingTextBox';

const box = (scrollHeight) => {
  const el = document.createElement('textarea');
  Object.defineProperty(el, 'scrollHeight', { value: scrollHeight });
  return el;
};

describe('growing text box', () => {
  it('grows to fit its words without a scroll bar', () => {
    window.innerHeight = 1000;
    const el = box(300);
    fitToText(el);
    expect(el.style.height).toBe('300px');
    expect(el.style.overflowY).toBe('hidden');
  });
  it('scrolls only once it would fill most of the screen', () => {
    window.innerHeight = 1000;
    const el = box(900);
    fitToText(el);
    expect(el.style.height).toBe('400px');
    expect(el.style.overflowY).toBe('auto');
  });
});
