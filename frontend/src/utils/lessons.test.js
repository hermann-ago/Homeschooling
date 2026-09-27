import { describe, expect, it } from 'vitest';
import { firstDay, lessonMeta, lessonPath, shortTime, todayFocus } from './lessons';

const lesson = (id, start, end, extra = {}) => ({ id, time_start: start, time_end: end, date: '2026-09-28', ...extra });
const at = (h, m) => new Date(2026, 8, 28, h, m);

describe('todayFocus', () => {
  const day = [lesson(1, '08:00', '09:00'), lesson(2, '09:00', '10:00'), lesson(3, '10:00', '11:00')];

  it('picks the lesson happening now', () => {
    expect(todayFocus(day, at(9, 15)).focus.id).toBe(2);
    expect(todayFocus(day, at(9, 15)).current.id).toBe(2);
  });

  it('picks the next lesson before school starts', () => {
    const result = todayFocus(day, at(7, 30));
    expect(result.current).toBeNull();
    expect(result.focus.id).toBe(1);
  });

  it('falls back to the earliest undone lesson after the day ends', () => {
    const done = [lesson(1, '08:00', '09:00', { is_completed: true }), lesson(2, '09:00', '10:00'), lesson(3, '10:00', '11:00')];
    expect(todayFocus(done, at(15, 0)).focus.id).toBe(2);
  });

  it('has no focus once everything is done', () => {
    expect(todayFocus([lesson(1, '08:00', '09:00', { is_completed: true })], at(8, 30)).focus).toBeNull();
  });
});

describe('formatting', () => {
  it('drops the leading zero and writes one page as p.', () => {
    expect(shortTime('08:00')).toBe('8:00');
    expect(lessonMeta({ time_start: '10:00', time_end: '11:00', page_from: 277, page_to: 277 })).toBe('10:00–11:00 · p. 277');
  });

  it('links a lesson to the full-screen Lesson view with its slot', () => {
    expect(lessonPath({ id: 9, topic_id: 373, child_id: 1 })).toBe('/lesson?learner=1&topic=373&slot=9');
  });

  it('finds the next school day', () => {
    const next = firstDay([lesson(1, '08:00', '09:00', { date: '2026-09-30' }), lesson(2, '08:00', '09:00'), lesson(3, '09:00', '10:00')]);
    expect(next).toMatchObject({ date: '2026-09-28', count: 2 });
  });
});
