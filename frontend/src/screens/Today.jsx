import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { format, parseISO } from 'date-fns';
import { BookOpen, Check, Headphones, RotateCcw } from 'lucide-react';
import clsx from 'clsx';
import ScreenHeader from '../app/ScreenHeader';
import { useLearner, useNow } from '../app/learnerContext';
import useReplanAction from '../app/useReplanAction';
import {
  useChildProgress, useFamilyProgress, useSetLessonDone, useSlots, useSlotsFor,
} from '../api/queries';
import { Badge, Button, CheckButton, LessonRow, ProgressBar, useToast } from '../ui';
import { learnerTones } from '../utils/colors';
import { byTime, comingDays, firstDay, greeting, lessonMeta, lessonPath, shortTime, todayFocus } from '../utils/lessons';

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function Avatar({ child, size = 40 }) {
  const tones = learnerTones(child.color);
  return (
    <span className="rounded-xl grid place-items-center font-display font-semibold shrink-0"
      style={{ width: size, height: size, background: tones.soft, color: tones.strong, fontSize: size / 2 }}>
      {child.name.charAt(0)}
    </span>
  );
}

function Card({ className, children }) {
  return <section className={clsx('bg-surface border border-line rounded-2xl', className)}>{children}</section>;
}

/** Marking done and opening lessons, shared by both views. */
function useLessonActions() {
  const navigate = useNavigate();
  const setDone = useSetLessonDone();
  const toast = useToast();
  return {
    toggle: (lesson, done) => setDone.mutate({ slotId: lesson.id, done }, {
      onError: (error) => toast({ tone: 'problem', message: `Not saved: ${error.message.replace(/^\/[^:]+: /, '')}` }),
    }),
    open: (lesson) => navigate(lessonPath(lesson, lesson.child_id)),
    canOpen: (lesson) => Boolean(lesson.topic_id),
  };
}

function UnfinishedCard({ entries, onReplan, busy, onReview }) {
  const total = entries.reduce((sum, e) => sum + e.count, 0);
  if (!total) return null;
  return (
    <Card className="p-5 flex flex-col gap-3.5">
      <div className="flex items-center gap-2.5">
        <span className="w-8 h-8 rounded-[10px] bg-attention-soft text-attention grid place-items-center">
          <RotateCcw aria-hidden="true" className="w-[18px] h-[18px]" />
        </span>
        <h2 className="text-base font-bold">Unfinished from earlier</h2>
      </div>
      <p className="text-sm text-muted leading-relaxed">
        {total} {total === 1 ? 'lesson was' : 'lessons were'} planned before today and not marked done.
      </p>
      <ul className="rounded-xl border border-line-soft divide-y divide-line-soft">
        {entries.filter((e) => e.count).map(({ child, count }) => (
          <li key={child.id}>
            <button type="button" onClick={() => onReview(child)}
              className="w-full flex items-center gap-2.5 px-3.5 py-3 text-left hover:bg-paper rounded-xl">
              <span aria-hidden="true" className="w-2.5 h-2.5 rounded-full" style={{ background: child.color }} />
              <span className="flex-1 text-sm font-semibold">{child.name}</span>
              <span className="text-sm text-muted">{count} {count === 1 ? 'lesson' : 'lessons'}</span>
            </button>
          </li>
        ))}
      </ul>
      <Button variant="strong" onClick={onReplan} disabled={busy}>{busy ? 'Re-planning…' : 'Re-plan from today'}</Button>
      <p className="text-[13px] text-subtle leading-snug">Re-planning moves them, in order, into the coming school days.</p>
    </Card>
  );
}

function WeekCard({ weekSlots, now }) {
  const counts = WEEKDAYS.map((_, index) => weekSlots.filter((s) => (parseISO(s.date).getDay() + 6) % 7 === index).length);
  const days = counts.some((c, i) => i >= 5 && c) ? WEEKDAYS : WEEKDAYS.slice(0, 5);
  const most = Math.max(1, ...counts);
  const todayIndex = (now.getDay() + 6) % 7;
  return (
    <Card className="p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-bold">This week</h2>
        <Link to="/plan" className="text-sm font-semibold text-action hover:text-action-hover">Open plan</Link>
      </div>
      <div className="grid gap-2.5 items-end h-24" style={{ gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))` }}>
        {days.map((day, index) => (
          <div key={day} className="flex flex-col items-center gap-1.5 h-full justify-end">
            <div className={clsx('w-full rounded-lg', index === todayIndex ? 'bg-ink' : 'bg-line')}
              style={{ height: Math.max(6, (counts[index] / most) * 56) }} title={`${counts[index]} lessons`} />
            <span className={clsx('text-xs', index === todayIndex ? 'font-bold' : 'text-muted')}>{day}</span>
          </div>
        ))}
      </div>
      <p className="text-[13px] text-muted">{days.map((_, i) => counts[i]).join(' · ')} lessons</p>
    </Card>
  );
}

/* ── Everyone ─────────────────────────────────────────────────────────── */

function LearnerLane({ child, lessons, coming, now, actions }) {
  const done = lessons.filter((l) => l.is_completed).length;
  const { current, focus } = todayFocus(lessons, now);
  const tones = learnerTones(child.color);
  const next = firstDay(coming);
  return (
    <Card className="overflow-hidden flex flex-col">
      <div className="flex items-center gap-3 px-5 py-4 border-b border-line-soft">
        <Avatar child={child} />
        <div className="flex-1 flex flex-col">
          <span className="text-[17px] font-bold">{child.name}</span>
          {child.grade_year && child.grade_year !== 'N/A' && <span className="text-[13px] text-muted">{child.grade_year} grade</span>}
        </div>
        {lessons.length > 0 && (
          <div className="flex flex-col items-end gap-1.5">
            <span className="text-[13px] text-muted">{done} of {lessons.length} done</span>
            <ProgressBar value={(done / lessons.length) * 100} color={tones.strong} height={6} className="w-24"
              label={`${child.name}: ${done} of ${lessons.length} lessons done`} />
          </div>
        )}
      </div>
      <div className="p-2 flex flex-col">
        {lessons.length === 0 ? (
          <p className="p-3 text-sm text-muted">
            No lessons today.{next && ` Next: ${next.label} (${next.count} ${next.count === 1 ? 'lesson' : 'lessons'}).`}
          </p>
        ) : [...lessons].sort(byTime).map((lesson) => (
          <LessonRow key={lesson.id} lesson={{ ...lesson, child_id: child.id }} learnerColor={child.color}
            now={lesson.id === focus?.id} tag={current?.id === lesson.id ? 'Now' : 'Next'}
            onToggle={actions.toggle} onOpen={actions.canOpen(lesson) ? actions.open : undefined} />
        ))}
      </div>
    </Card>
  );
}

function EveryoneToday({ learners, select }) {
  const now = useNow();
  const actions = useLessonActions();
  const replan = useReplanAction();
  const { data: family } = useFamilyProgress();
  const hasSubjects = (child) => (family?.children.find((c) => c.child_id === child.id)?.subjects.length ?? 1) > 0;
  const active = learners.filter(hasSubjects);
  const notSetUp = learners.filter((c) => !hasSubjects(c));

  const today = useSlotsFor(active, 'today');
  const missed = useSlotsFor(active, 'missed');
  const week = useSlotsFor(active, 'week');
  const coming = useSlotsFor(active, comingDays(now));

  const all = today.flatMap((t) => t.data || []);
  const done = all.filter((l) => l.is_completed).length;
  const withLessons = today.filter((t) => t.data?.length).length;
  const unfinished = missed.map(({ child, data }) => ({ child, count: (data || []).filter((l) => !l.is_completed).length }));

  return (
    <>
      <ScreenHeader />
      <div className="flex flex-col xl:flex-row gap-8 px-4 md:px-10 py-8">
        <section className="flex-1 min-w-0 flex flex-col gap-6">
          <div className="flex flex-col gap-1.5">
            <h1 className="font-display text-4xl md:text-[40px] font-medium tracking-tight">{greeting(now)}</h1>
            <p className="text-base text-muted">
              {format(now, 'EEEE, d MMMM')} · {all.length
                ? `${all.length} ${all.length === 1 ? 'lesson' : 'lessons'} for ${withLessons} ${withLessons === 1 ? 'learner' : 'learners'} · ${done} done`
                : 'no lessons today'}
            </p>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {today.map(({ child, data }, index) => (
              <LearnerLane key={child.id} child={child} lessons={data || []} coming={coming[index].data} now={now} actions={actions} />
            ))}
          </div>
          {notSetUp.length > 0 && (
            <div className="flex flex-wrap items-center gap-4 px-5 py-4 rounded-2xl border border-dashed border-line">
              <div className="flex gap-1.5">{notSetUp.map((child) => <Avatar key={child.id} child={child} size={32} />)}</div>
              <p className="flex-1 min-w-[12rem] text-sm text-muted">
                <strong className="text-ink">{notSetUp.map((c) => c.name).join(' and ')}</strong>{' '}
                {notSetUp.length === 1 ? 'has' : 'have'} no subjects yet, so nothing can be planned.
              </p>
              <Button as={Link} to="/curriculum" size="sm" onClick={() => select(notSetUp[0].id)}>Add subjects</Button>
            </div>
          )}
        </section>
        <aside className="xl:w-[336px] shrink-0 flex flex-col gap-5">
          <UnfinishedCard entries={unfinished} busy={replan.busy} onReview={(child) => select(child.id)}
            onReplan={() => replan.run(unfinished.filter((e) => e.count).map((e) => e.child))} />
          <WeekCard weekSlots={week.flatMap((w) => w.data || [])} now={now} />
        </aside>
      </div>
    </>
  );
}

/* ── One learner ──────────────────────────────────────────────────────── */

function NowCard({ lesson, child, isCurrent, actions }) {
  const tones = learnerTones(child.color);
  return (
    <article className="bg-surface border border-line rounded-[20px] overflow-hidden">
      <div className="px-6 md:px-8 py-7 flex flex-col gap-2.5" style={{ background: tones.soft }}>
        <div className="flex flex-wrap items-center gap-2.5">
          <Badge color={tones.strong} solid className="text-xs tracking-wide">
            {isCurrent ? 'NOW' : 'NEXT'} · {shortTime(lesson.time_start)}–{shortTime(lesson.time_end)}
          </Badge>
          <span className="text-[13px] font-bold tracking-[0.6px] uppercase" style={{ color: tones.strong }}>{lesson.subject_name}</span>
        </div>
        <h2 className="font-display text-3xl md:text-[34px] font-medium leading-tight">{lesson.topic_title || 'Study time'}</h2>
        {lesson.page_from != null && (
          <p className="text-[15px] text-ink/80">
            {lesson.page_from === lesson.page_to ? `Book page ${lesson.page_from}` : `Book pages ${lesson.page_from}–${lesson.page_to}`}
          </p>
        )}
      </div>
      <div className="px-6 md:px-8 py-5 flex flex-wrap items-center gap-3">
        {actions.canOpen(lesson) && (
          <>
            <Button variant="primary" size="lg" icon={BookOpen} onClick={() => actions.open(lesson)}>Open the lesson</Button>
            <Button size="lg" icon={Headphones} onClick={() => actions.open(lesson)}>Read along</Button>
          </>
        )}
        <div className="flex-1" />
        <Button size="lg" icon={Check} onClick={() => actions.toggle(lesson, true)}>Mark done</Button>
      </div>
    </article>
  );
}

function SubjectsCard({ childId, color }) {
  const { data } = useChildProgress(childId);
  if (!data) return null;
  const tones = learnerTones(color);
  return (
    <Card className="p-5 flex flex-col gap-3.5">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-bold">Subjects</h2>
        <Link to="/progress" className="text-sm font-semibold text-action hover:text-action-hover">Progress</Link>
      </div>
      {data.subjects.length === 0 && <p className="text-sm text-muted">No subjects yet.</p>}
      {data.subjects.map((s) => {
        const complete = s.progress_percent >= 100;
        if (!s.total_pages) {
          return (
            <div key={s.subject_id} className="flex justify-between items-center text-sm">
              <span className="font-semibold">{s.subject_name}</span>
              <Link to="/curriculum" className="font-semibold text-action">Add a book</Link>
            </div>
          );
        }
        return (
          <div key={s.subject_id} className="flex flex-col gap-1.5">
            <div className="flex justify-between gap-3 text-sm">
              <span className="font-semibold">{s.subject_name}</span>
              <span className={complete ? 'font-semibold text-action' : 'text-muted'}>
                {complete ? 'Complete' : `${Math.round(s.progress_percent)}%${s.projected_finish_date ? ` · finish ~${format(parseISO(s.projected_finish_date), 'd MMM')}` : ''}`}
              </span>
            </div>
            <ProgressBar value={s.progress_percent} height={6} color={complete ? 'var(--color-action)' : tones.strong} label={s.subject_name} />
          </div>
        );
      })}
    </Card>
  );
}

function LearnerToday({ child }) {
  const now = useNow();
  const actions = useLessonActions();
  const replan = useReplanAction();
  const [showAll, setShowAll] = useState(false);
  const { data: lessons = [], isLoading } = useSlots(child.id, 'today');
  const { data: missedAll = [] } = useSlots(child.id, 'missed');
  const { data: coming = [] } = useSlots(child.id, comingDays(now));
  const missed = missedAll.filter((l) => !l.is_completed);
  const sorted = [...lessons].sort(byTime).map((l) => ({ ...l, child_id: child.id }));
  const { current, focus } = todayFocus(sorted, now);
  const rest = sorted.filter((l) => l.id !== focus?.id);
  const done = sorted.filter((l) => l.is_completed).length;
  const next = firstDay(coming);
  const tones = learnerTones(child.color);

  return (
    <>
      <ScreenHeader />
      <div className="flex flex-col xl:flex-row gap-8 px-4 md:px-10 py-8">
        <section className="flex-1 min-w-0 flex flex-col gap-6">
          <div className="flex flex-col gap-1.5">
            <h1 className="font-display text-4xl md:text-[40px] font-medium tracking-tight">{child.name}'s {format(now, 'EEEE')}</h1>
            <p className="text-base text-muted">
              {sorted.length
                ? `${sorted.length} ${sorted.length === 1 ? 'lesson' : 'lessons'} between ${shortTime(sorted[0].time_start)} and ${shortTime(sorted[sorted.length - 1].time_end)} · ${done} done`
                : isLoading ? 'Loading…' : 'No lessons today'}
            </p>
          </div>

          {focus ? (
            <NowCard lesson={focus} child={child} isCurrent={Boolean(current && current.id === focus.id)} actions={actions} />
          ) : (
            <Card className="px-8 py-7 flex flex-col gap-2">
              <h2 className="font-display text-[28px] font-medium">{sorted.length ? 'All done for today' : 'A day off from lessons'}</h2>
              <p className="text-[15px] text-muted">
                {next ? `Next lessons: ${next.label} (${next.count} ${next.count === 1 ? 'lesson' : 'lessons'}).` : 'Nothing is planned in the next two weeks.'}
              </p>
            </Card>
          )}

          {!sorted.length && next && (
            <div className="flex flex-col gap-2.5">
              <h2 className="text-[13px] font-bold tracking-[0.8px] uppercase text-muted">Coming up {next.label}</h2>
              <Card className="p-2">
                {coming.filter((l) => l.date === next.date).sort(byTime).map((lesson) => (
                  <LessonRow key={lesson.id} lesson={{ ...lesson, child_id: child.id }} learnerColor={child.color}
                    openLabel="Preview" onOpen={actions.canOpen(lesson) ? actions.open : undefined} />
                ))}
              </Card>
            </div>
          )}

          {rest.length > 0 && (
            <div className="flex flex-col gap-2.5">
              <h2 className="text-[13px] font-bold tracking-[0.8px] uppercase text-muted">{focus ? 'Also today' : 'Today'}</h2>
              <Card className="p-2">
                {rest.map((lesson) => (
                  <LessonRow key={lesson.id} lesson={lesson} learnerColor={child.color}
                    onToggle={actions.toggle} onOpen={actions.canOpen(lesson) ? actions.open : undefined} />
                ))}
              </Card>
            </div>
          )}
        </section>

        <aside className="xl:w-[360px] shrink-0 flex flex-col gap-5">
          {missed.length > 0 && (
            <Card className="p-5 flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <h2 className="text-base font-bold">Unfinished from earlier</h2>
                <Badge tone="attention">{missed.length}</Badge>
              </div>
              <ul className="flex flex-col divide-y divide-line-soft">
                {missed.slice(0, showAll ? undefined : 4).map((lesson) => (
                  <li key={lesson.id} className="flex items-center gap-3 py-2.5">
                    <CheckButton size={28} label={`${lesson.subject_name}: ${lesson.topic_title}`} color={tones.strong}
                      onToggle={(value) => actions.toggle(lesson, value)} />
                    <div className="flex-1 min-w-0 flex flex-col">
                      <span className="text-sm font-semibold truncate">{lesson.topic_title || 'Study time'}</span>
                      <span className="text-[13px] text-muted">
                        {lesson.subject_name} · {format(parseISO(lesson.date), 'EEE d MMM')}
                        {lesson.page_from != null && ` · ${lessonMeta({ page_from: lesson.page_from, page_to: lesson.page_to })}`}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
              <div className="flex gap-2">
                {missed.length > 4 && (
                  <Button className="flex-1" onClick={() => setShowAll(!showAll)}>{showAll ? 'Show fewer' : `Show all ${missed.length}`}</Button>
                )}
                <Button className="flex-1" variant="strong" disabled={replan.busy} onClick={() => replan.run([child])}>
                  {replan.busy ? 'Re-planning…' : 'Re-plan from today'}
                </Button>
              </div>
            </Card>
          )}
          <SubjectsCard childId={child.id} color={child.color} />
        </aside>
      </div>
    </>
  );
}

export default function Today() {
  const { learners, selected, select, learner } = useLearner();
  const child = selected === 'all' ? null : learner(selected);
  if (!learners.length) {
    return <p className="p-10 text-muted">Add the family's learners in <Link className="text-action font-semibold" to="/settings">Settings</Link>.</p>;
  }
  return child ? <LearnerToday key={child.id} child={child} /> : <EveryoneToday learners={learners} select={select} />;
}

