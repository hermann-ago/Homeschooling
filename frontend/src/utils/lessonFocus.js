/** Keep keyboard navigation on desktop without summoning a touch keyboard. */
export function focusLessonControl(target, fallback) {
  const touch = window.matchMedia?.('(pointer: coarse)').matches;
  const opensKeyboard = target?.matches('textarea, input:not([type="radio"]):not([type="checkbox"]), select, [contenteditable="true"]');
  if (touch && opensKeyboard) fallback?.focus({ preventScroll: true });
  else target?.focus({ preventScroll: true });
}
