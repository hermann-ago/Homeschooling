/*
 * The sound that says "these are the book's words": a soft two-note chime,
 * made on the device (no recording), played just before a book reading starts.
 */

const NOTES = [[659.25, 0], [987.77, 0.16]]; // E5, then B5
const LENGTH = 0.75; // seconds until the reading begins
let context = null;

/** Plays the chime and returns a promise for its end, or null when the device cannot play it. */
export function playBookCue() {
  try {
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!Context) return null;
    context ||= new Context();
    if (context.state === 'suspended') context.resume?.();
    const now = context.currentTime;
    NOTES.forEach(([frequency, at]) => {
      const tone = context.createOscillator();
      const volume = context.createGain();
      tone.type = 'sine';
      tone.frequency.value = frequency;
      volume.gain.setValueAtTime(0.0001, now + at);
      volume.gain.exponentialRampToValueAtTime(0.16, now + at + 0.02);
      volume.gain.exponentialRampToValueAtTime(0.0001, now + at + 0.55);
      tone.connect(volume).connect(context.destination);
      tone.start(now + at);
      tone.stop(now + at + 0.6);
    });
    return new Promise((done) => { setTimeout(done, LENGTH * 1000); });
  } catch {
    return null;
  }
}
