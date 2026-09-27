import { addDays, format, parseISO } from 'date-fns';

/** "08:00" → "8:00" */
export const shortTime = (time) => (time ? time.replace(/^0(\d)/, '$1') : '');

/** Minutes since midnight for "HH:MM". */
export const minutesOf = (time) => {
  const [h, m] = (time || '0:0').split(':').map(Number);
  return h * 60 + m;
};

/** "8:00–9:00 · pp. 208–210" for a scheduled lesson. */
export function lessonMeta(lesson) {
  const parts = [];
  if (lesson.time_start && lesson.time_end) parts.push(`${shortTime(lesson.time_start)}–${shortTime(lesson.time_end)}`);
  if (lesson.page_from != null && lesson.page_to != null) {
    parts.push(lesson.page_from === lesson.page_to ? `p. ${lesson.page_from}` : `pp. ${lesson.page_from}–${lesson.page_to}`);
  }
  return parts.join(' · ');
}

export const byTime = (a, b) => (a.date || '').localeCompare(b.date || '') || minutesOf(a.time_start) - minutesOf(b.time_start);

/**
 * Which of today's lessons is happening now, and which comes next. `focus` is
 * the one to put first: the current lesson, else the next one not done, else
 * the earliest one left undone.
 */
export function todayFocus(lessons, now = new Date()) {
  const minute = now.getHours() * 60 + now.getMinutes();
  const sorted = [...lessons].sort(byTime);
  const current = sorted.find((l) => !l.is_completed && minutesOf(l.time_start) <= minute && minute < minutesOf(l.time_end));
  const next = sorted.find((l) => !l.is_completed && minutesOf(l.time_start) > minute);
  const focus = current || next || sorted.find((l) => !l.is_completed) || null;
  return { current: current || null, next: next || null, focus };
}

/** The lesson link: the full-screen Lesson view. */
export const lessonPath = (lesson, childId) => {
  const params = new URLSearchParams({ learner: childId ?? lesson.child_id, topic: lesson.topic_id });
  if (lesson.id) params.set('slot', lesson.id);
  return `/lesson?${params}`;
};

export const isoDay = (date) => format(date, 'yyyy-MM-dd');

/** Tomorrow up to two weeks out, for "next lessons" when today is empty. */
export const comingDays = (today = new Date()) => ({ start: isoDay(addDays(today, 1)), end: isoDay(addDays(today, 14)) });

/** The first day in `lessons` and how many lessons it has. */
export function firstDay(lessons = []) {
  if (!lessons.length) return null;
  const date = [...lessons].sort(byTime)[0].date;
  return { date, label: format(parseISO(date), 'EEEE d MMM'), count: lessons.filter((l) => l.date === date).length };
}

export const greeting = (now) => (now.getHours() < 12 ? 'Good morning' : now.getHours() < 18 ? 'Good afternoon' : 'Good evening');
