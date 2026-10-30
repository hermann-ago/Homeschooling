import { expect, it, vi } from 'vitest';
import { beginNarration, isNarrating, pauseNarration, registerNarrator } from './narration';

it('stops other narration before claiming playback and pauses the active narrator', () => {
  const reading = Symbol('reading'); const feedback = Symbol('feedback');
  const stopReading = vi.fn(); const stopFeedback = vi.fn();
  const unregisterReading = registerNarrator(reading, stopReading);
  const unregisterFeedback = registerNarrator(feedback, stopFeedback);
  beginNarration(reading);
  expect(isNarrating(reading)).toBe(true);
  stopReading.mockClear(); stopFeedback.mockClear();
  beginNarration(feedback);
  expect(stopReading).toHaveBeenCalledTimes(1);
  expect(stopFeedback).not.toHaveBeenCalled();
  expect(isNarrating(feedback)).toBe(true);
  pauseNarration();
  expect(stopFeedback).toHaveBeenCalledTimes(1);
  expect(isNarrating(feedback)).toBe(false);
  unregisterReading(); unregisterFeedback();
});
