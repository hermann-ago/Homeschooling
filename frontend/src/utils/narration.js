// One narrator at a time, including reading, activity prompts and saved feedback.
// Stops are synchronous so a question or a break cannot race the next sentence.
const narrators = new Map();
let active = null;

export function registerNarrator(id, stop) {
  narrators.set(id, stop);
  return () => {
    if (active === id) { stop(); active = null; }
    narrators.delete(id);
  };
}

export function isNarrating(id) { return active === id; }

export function beginNarration(id) {
  for (const [other, stop] of narrators) {
    if (other !== id) stop();
  }
  active = id;
}

export function pauseNarration() {
  for (const stop of narrators.values()) stop();
  active = null;
}
