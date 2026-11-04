import { useEffect, useRef } from 'react';

/**
 * Space is a lesson's main control: it pauses and resumes the voice, and once
 * the voice has finished it presses the step's main button. Writing keeps its
 * spaces, and dialogs keep their own keys.
 *
 * Handlers are asked newest first; the first one that returns true handles
 * the key. A handler that returns false leaves Space to the browser, so a
 * focused button still works as usual.
 */
const TYPING = 'textarea, select, [contenteditable="true"], input:not([type="radio"]):not([type="checkbox"])';
let handlers = [];
let swallowKeyUp = false;

function keyDown(event) {
  if (event.key !== ' ' || event.altKey || event.ctrlKey || event.metaKey || event.isComposing) return;
  const target = event.target;
  if (target?.closest?.(TYPING) || target?.closest?.('dialog, [role="dialog"]')) return;
  if (event.repeat) { if (swallowKeyUp) event.preventDefault(); return; }
  for (const handler of [...handlers].reverse()) {
    if (handler.current?.(target)) {
      // Stop the focused button from also clicking on key up.
      event.preventDefault(); swallowKeyUp = true; return;
    }
  }
}

function keyUp(event) {
  if (event.key === ' ' && swallowKeyUp) { event.preventDefault(); swallowKeyUp = false; }
}

/** Is the key on something Space already presses? */
export const pressable = (target) => Boolean(target?.closest?.('button, a[href], [role="button"], input, summary'));

export function useSpaceBar(handler) {
  const ref = useRef(handler);
  useEffect(() => { ref.current = handler; });
  useEffect(() => {
    if (!handlers.length) {
      window.addEventListener('keydown', keyDown, true);
      window.addEventListener('keyup', keyUp, true);
    }
    handlers.push(ref);
    return () => {
      handlers = handlers.filter((item) => item !== ref);
      if (!handlers.length) {
        window.removeEventListener('keydown', keyDown, true);
        window.removeEventListener('keyup', keyUp, true);
        swallowKeyUp = false;
      }
    };
  }, []);
}

/** The button that moves the lesson on: Start lesson, Continue, Finish… */
export function nextStepButton(root = document) {
  return root.querySelector('[data-lesson-start]:not(:disabled), [aria-label="Tutor activities"] [data-lesson-primary]:not(:disabled), '
    + '[aria-label="Tutor activities"] [aria-label="Lesson step controls"]:not([hidden]) button:not(:disabled)');
}
