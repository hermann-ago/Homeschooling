/** A text box that grows with its words, as a chat box does: no scroll bar
 *  until it would fill most of the screen. */
export function fitToText(box, maxShare = 0.4) {
  if (!box) return;
  const limit = Math.max(136, Math.round((window.innerHeight || 800) * maxShare));
  box.style.height = 'auto';
  const needed = box.scrollHeight + (box.offsetHeight - box.clientHeight);
  box.style.height = `${Math.min(needed, limit)}px`;
  box.style.overflowY = needed > limit ? 'auto' : 'hidden';
}
