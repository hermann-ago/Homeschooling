import clsx from 'clsx';
import Badge from './Badge';
import CheckButton from './CheckButton';
import Button from './Button';
import { learnerTones } from '../utils/colors';
import { lessonMeta } from '../utils/lessons';

/**
 * One scheduled lesson: done button, subject, title, time and pages, and an
 * Open action. `now` highlights the lesson happening at the moment.
 */
export default function LessonRow({ lesson, learnerColor, now = false, meta, onToggle, onOpen, busy }) {
  const tones = learnerTones(learnerColor || '#2d5f54');
  const done = Boolean(lesson.is_completed);
  const title = lesson.topic_title || 'Study time';
  return (
    <div className="flex items-center gap-3.5 p-3 rounded-xl" style={now && !done ? { background: tones.soft } : undefined}>
      <CheckButton done={done} current={now} color={tones.strong} label={`${lesson.subject_name}: ${title}`}
        onToggle={(value) => onToggle?.(lesson, value)} disabled={busy} />
      <div className="flex-1 min-w-0 flex flex-col gap-0.5">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold tracking-[0.6px] uppercase" style={{ color: done ? 'var(--color-subtle)' : tones.strong }}>
            {lesson.subject_name}
          </span>
          {now && !done && <Badge color={tones.strong} solid className="text-xs px-2 py-px">Now</Badge>}
        </div>
        <span className={clsx('text-[15px] font-semibold truncate', done && 'text-subtle line-through')}>{title}</span>
        <span className={clsx('text-[13px]', done ? 'text-subtle' : 'text-muted')}>{meta ?? lessonMeta(lesson)}</span>
      </div>
      {onOpen && !done && (
        <Button size="sm" variant={now ? 'primary' : 'secondary'} onClick={() => onOpen(lesson)}>Open</Button>
      )}
    </div>
  );
}
