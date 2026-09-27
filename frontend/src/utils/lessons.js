/** "8:00–9:00 · pp. 208–210" for a scheduled lesson. */
export function lessonMeta(lesson) {
  const parts = [];
  if (lesson.time_start && lesson.time_end) parts.push(`${lesson.time_start}–${lesson.time_end}`);
  if (lesson.page_from != null && lesson.page_to != null) {
    parts.push(lesson.page_from === lesson.page_to ? `p. ${lesson.page_from}` : `pp. ${lesson.page_from}–${lesson.page_to}`);
  }
  return parts.join(' · ');
}
