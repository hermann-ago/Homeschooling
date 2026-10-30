/* @vitest-environment jsdom */
import { afterEach, expect, it, vi } from 'vitest';
import { focusLessonControl } from './lessonFocus';
afterEach(() => { document.body.replaceChildren(); vi.unstubAllGlobals(); });

it('keeps automatic touch focus off text entry but preserves the Enter action button', () => {
  vi.stubGlobal('matchMedia', () => ({ matches: true }));
  const heading = document.createElement('h2'); heading.tabIndex = -1;
  const answer = document.createElement('textarea');
  const done = document.createElement('button');
  document.body.append(heading, answer, done);
  focusLessonControl(answer, heading);
  expect(document.activeElement).toBe(heading);
  focusLessonControl(done, heading);
  expect(document.activeElement).toBe(done);
});

it('keeps desktop answer focus for keyboard entry', () => {
  vi.stubGlobal('matchMedia', () => ({ matches: false }));
  const answer = document.createElement('textarea');document.body.append(answer);
  focusLessonControl(answer);
  expect(document.activeElement).toBe(answer);
});
