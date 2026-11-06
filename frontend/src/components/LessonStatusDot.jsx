import { LESSON_STATES } from '../utils/lessonStates';

export default function LessonStatusDot({ state, className = '' }) {
  const info = LESSON_STATES[state];
  if (!info) return null;
  return <span role="img" aria-label={info.label} title={info.label} className={`lesson-dot ${info.className} ${className}`} />;
}

/** The dot pinned to the top-right corner of a lesson card (the card needs `relative`). */
export function CornerDot({ state }) {
  return <LessonStatusDot state={state} className="lesson-dot--corner" />;
}

/** A one-line key to the dots. */
export function LessonStatusLegend({ className = '' }) {
  const shown = ['ready', 'script', 'preparing', 'none', 'done', 'attention'];
  return <ul aria-label="Lesson status colors" className={`flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted ${className}`}>
    {shown.map((state) => <li key={state} className="flex items-center gap-1.5"><LessonStatusDot state={state} />{LESSON_STATES[state].label}</li>)}
  </ul>;
}
