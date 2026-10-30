import { describe, expect, it } from 'vitest';
import { narrationRange } from './narrationRange';

const activity = { id: 'question', kind: 'ask_question', content: { prompt: 'What changed?' }, interaction: { prompt: 'What changed?', sequence: 1 } };
const guide = { sentences: [{ text: 'What changed?' }], activities: [{ id: 'question', kind: 'ask_question', start_sentence: 0, end_sentence: 0 }] };
describe('Exact saved step narration', () => {
  it('matches a planned prompt to its own recording range', () => expect(narrationRange(guide, activity)).toEqual({ start: 0, end: 0 }));
  it('reuses an unchanged planned recording for a fresh replay, keeping later help text-only', () => {
    const repeated = { ...activity, interaction: { id: 'i2', replay_of: 'i1', prompt: 'What changed?', sequence: 2, dialogue_start_sequence: 2 },
      responses: [{ interaction_id: 'i1' }], messages: [{ text: 'Earlier feedback', sequence: 2 }] };
    expect(narrationRange(guide, repeated)).toEqual({ start: 0, end: 0 });
    expect(narrationRange(guide, { ...repeated, messages: [...repeated.messages, { text: 'New hint', sequence: 3 }] })).toBeNull();
    expect(narrationRange(guide, { ...repeated, responses: [...repeated.responses, { interaction_id: 'i2' }] })).toBeNull();
  });
  it('keeps follow-ups, feedback and revised warm-ups text-only', () => {
    expect(narrationRange(guide, { ...activity, interaction: { prompt: 'What changed?', sequence: 2 } })).toBeNull();
    expect(narrationRange(guide, { ...activity, interaction: { prompt: 'A newly generated question' } })).toBeNull();
    expect(narrationRange(guide, { ...activity, responses: [{ status: 'assessed' }] })).toBeNull();
    expect(narrationRange(guide, { ...activity, messages: [{ text: 'A fresh hint' }] })).toBeNull();
    expect(narrationRange(guide, { ...activity, id: 'adaptive-question' })).toBeNull();
  });
});
