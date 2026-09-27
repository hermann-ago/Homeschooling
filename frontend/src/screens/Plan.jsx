import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import {
  addDays, addMonths, addWeeks, differenceInCalendarDays, endOfMonth, endOfWeek, format, isSameDay, isSameMonth, parseISO, startOfMonth, startOfWeek,
} from 'date-fns';
import { ChevronLeft, ChevronRight, Plus, RefreshCw, X } from 'lucide-react';
import clsx from 'clsx';
import ScreenHeader from '../app/ScreenHeader';
import { useLearner } from '../app/learnerContext';
import useReplanAction from '../app/useReplanAction';
import { calendarApi } from '../api/calendar';
import { useBlockedDays, useCompletedTopics, useFamilyProgress, useSchoolYear, useSlotsFor } from '../api/queries';
import { Button, Dialog, Field, IconButton, SegmentedControl, inputClasses, useConfirm, useToast } from '../ui';
import { learnerTones } from '../utils/colors';
import { byTime, isoDay, lessonPath, shortTime } from '../utils/lessons';

const REASONS = { holiday: 'Holiday', sick: 'Sick day', custom: 'Day off' };

function DayOffDialog({ open, onClose, learners, defaultWho, defaultDate, onSaved }) {
  const [form, setForm] = useState({ date: defaultDate, who: defaultWho, type: 'holiday', note: '', replan: true });
  const [saving, setSaving] = useState(false);
  const toast = useToast();
  const set = (changes) => setForm((current) => ({ ...current, ...changes }));

  const save = async () => {
    setSaving(true);
    try {
      await calendarApi.createBlockedDay({
        date: form.date, block_type: form.type, note: form.note.trim() || null,
        child_id: form.who === 'all' ? null : Number(form.who),
      });
      await onSaved(form);
      onClose();
    } catch (error) {
      toast({ tone: 'problem', message: `Could not add the day off: ${error.message.replace(/^\/[^:]+: /, '')}` });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} title="Add a day off"
      description="No lessons are planned on a day off."
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={!form.date || saving} onClick={save}>{saving ? 'Saving…' : 'Add day off'}</Button></>}>
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Date" type="date" value={form.date} onChange={(e) => set({ date: e.target.value })} />
          <Field label="For">
            <select className={inputClasses} value={form.who} onChange={(e) => set({ who: e.target.value })}>
              <option value="all">Everyone</option>
              {learners.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-[13px] font-semibold text-muted">Reason</span>
          <SegmentedControl label="Reason" size="sm" value={form.type} onChange={(type) => set({ type })}
            options={[{ value: 'holiday', label: 'Holiday' }, { value: 'sick', label: 'Sick' }, { value: 'custom', label: 'Other' }]} />
        </div>
        <Field label="Note (optional)" placeholder="e.g. Grandma's visit" value={form.note} onChange={(e) => set({ note: e.target.value })} />
        <label className="flex items-start gap-2.5 text-sm">
          <input type="checkbox" className="mt-0.5 w-4 h-4 accent-[var(--color-action)]" checked={form.replan}
            onChange={(e) => set({ replan: e.target.checked })} />
          <span>Re-plan from today, so lessons on that day move to the next school days</span>
        </label>
      </div>
    </Dialog>
  );
}

function LessonChip({ lesson, child, showName, onOpen }) {
  const tones = learnerTones(child.color);
  const done = lesson.is_completed;
  return (
    <button type="button" onClick={() => onOpen(lesson)} disabled={!lesson.topic_id}
      className="w-full text-left px-3 py-2 rounded-[10px] flex flex-col gap-0.5 hover:brightness-[0.97] disabled:cursor-default"
      style={{ background: tones.soft }}>
      <span className="text-xs font-bold truncate" style={{ color: done ? 'var(--color-subtle)' : tones.strong }}>
        {shortTime(lesson.time_start)}{showName ? ` · ${child.name}` : ''} · {lesson.subject_name}
      </span>
      <span className={clsx('text-[13px] font-semibold truncate', done && 'text-subtle line-through')}>{lesson.topic_title || 'Study time'}</span>
    </button>
  );
}

function BlockedBanner({ block, learner, onRemove }) {
  return (
    <div className="flex items-start gap-2 px-3 py-2 rounded-[10px] bg-attention-soft text-attention">
      <div className="flex-1 min-w-0 flex flex-col">
        <span className="text-xs font-bold uppercase tracking-wide">{REASONS[block.block_type] || 'Day off'}</span>
        <span className="text-[13px] truncate">{block.note || (block.child_id ? learner(block.child_id)?.name : 'Everyone')}</span>
      </div>
      <IconButton icon={X} size="sm" variant="quiet" label="Remove this day off" onClick={() => onRemove(block)}
        className="-mr-1 -my-1 !w-8 !h-8 text-attention" />
    </div>
  );
}

export default function Plan() {
  const { learners, selected, learner } = useLearner();
  const [params, setParams] = useSearchParams();
  const view = params.get('view') === 'month' ? 'month' : 'week';
  const [anchor, setAnchor] = useState(() => new Date());
  const [dayOff, setDayOff] = useState(null);
  const navigate = useNavigate();
  const client = useQueryClient();
  const confirm = useConfirm();
  const toast = useToast();
  const replan = useReplanAction();
  const { data: family } = useFamilyProgress();
  const { data: year } = useSchoolYear();

  const hasSubjects = (child) => (family?.children.find((c) => c.child_id === child.id)?.subjects.length ?? 1) > 0;
  const shown = selected === 'all' ? learners.filter(hasSubjects) : [learner(selected)].filter(Boolean);
  const single = selected === 'all' ? null : selected;

  const start = view === 'week' ? startOfWeek(anchor, { weekStartsOn: 1 }) : startOfWeek(startOfMonth(anchor), { weekStartsOn: 1 });
  const end = view === 'week' ? endOfWeek(anchor, { weekStartsOn: 1 }) : endOfWeek(endOfMonth(anchor), { weekStartsOn: 1 });
  const range = { start: isoDay(start), end: isoDay(end) };
  const slots = useSlotsFor(shown, range);
  const { data: blocked = [] } = useBlockedDays(single, range.start, range.end);
  const { data: checked = [] } = useCompletedTopics(single);

  const lessonsOn = (day) => slots.flatMap(({ child, data }) => (data || [])
    .filter((l) => l.date === isoDay(day)).map((l) => ({ ...l, child_id: child.id, child })))
    .sort(byTime);
  const blocksOn = (day) => blocked.filter((b) => b.date === isoDay(day));
  const checkedOn = (day) => checked.filter((c) => isSameDay(new Date(c.completed_at), day));
  const open = (lesson) => navigate(lessonPath(lesson, lesson.child_id));

  const move = (step) => setAnchor((current) => (view === 'week' ? addWeeks(current, step) : addMonths(current, step)));
  const setView = (next) => setParams(next === 'month' ? { view: 'month' } : {}, { replace: true });

  const removeBlock = async (block) => {
    if (!(await confirm({ title: `Remove the day off on ${format(parseISO(block.date), 'EEEE d MMMM')}?`, confirmLabel: 'Remove' }))) return;
    try {
      await calendarApi.deleteBlockedDay(block.id);
      await client.invalidateQueries({ queryKey: ['blocked-days'] });
      toast('Day off removed. Re-plan to use that day for lessons again.');
    } catch (error) {
      toast({ tone: 'problem', message: `Could not remove it: ${error.message}` });
    }
  };

  const afterDayOff = async (form) => {
    await client.invalidateQueries({ queryKey: ['blocked-days'] });
    const affected = form.who === 'all' ? learners.filter(hasSubjects) : [learner(Number(form.who))];
    if (form.replan) await replan.apply(affected);
    else toast('Day off added. Re-plan when you want lessons to move.');
  };

  const weekDays = Array.from({ length: 7 }, (_, i) => addDays(start, i));
  const shownWeekDays = weekDays.filter((d, i) => i < 5 || lessonsOn(d).length || blocksOn(d).length);
  const title = view === 'week'
    ? `${format(start, 'd MMM')} – ${format(addDays(start, 4), 'd MMM')}`
    : format(anchor, 'MMMM yyyy');

  const endDate = year?.end_date ? parseISO(year.end_date) : null;
  const pace = shown.map((child) => ({
    child,
    subjects: (family?.children.find((c) => c.child_id === child.id)?.subjects || [])
      .filter((s) => s.projected_finish_date && s.progress_percent < 100),
  })).filter((entry) => entry.subjects.length);

  return (
    <>
      <ScreenHeader actions={(
        <div className="flex gap-2.5">
          <Button icon={Plus} onClick={() => setDayOff({ date: isoDay(new Date()) })}>Add a day off</Button>
          <Button variant="primary" icon={RefreshCw} disabled={replan.busy || !shown.length} onClick={() => replan.run(shown)}>
            {replan.busy ? 'Re-planning…' : 'Re-plan from today'}
          </Button>
        </div>
      )} />
      <div className="px-4 md:px-10 py-7 flex flex-col gap-5">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-display text-3xl md:text-4xl font-medium min-w-[14rem]">{title}</h1>
          <div className="flex gap-1">
            <IconButton icon={ChevronLeft} size="sm" label={view === 'week' ? 'Previous week' : 'Previous month'} onClick={() => move(-1)} />
            <IconButton icon={ChevronRight} size="sm" label={view === 'week' ? 'Next week' : 'Next month'} onClick={() => move(1)} />
            <Button size="sm" variant="quiet" onClick={() => setAnchor(new Date())}>Today</Button>
          </div>
          <div className="flex-1" />
          <SegmentedControl label="View" size="sm" value={view} onChange={setView}
            options={[{ value: 'week', label: 'Week' }, { value: 'month', label: 'Month' }]} />
        </div>

        {view === 'week' ? (
          <div className="grid gap-3.5 grid-cols-1 sm:grid-cols-2 lg:grid-cols-[repeat(var(--days),minmax(0,1fr))]"
            style={{ '--days': shownWeekDays.length }}>
              {shownWeekDays.map((day) => {
                const lessons = lessonsOn(day);
                const today = isSameDay(day, new Date());
                return (
                  <section key={day.toISOString()} aria-label={format(day, 'EEEE d MMMM')}
                    className={clsx('bg-surface rounded-2xl p-3.5 flex flex-col gap-2 min-h-40', today ? 'border-2 border-ink' : 'border border-line')}>
                    <div className="flex items-baseline justify-between px-1 pb-1">
                      <span className="text-[15px] font-bold">{format(day, 'EEE d')}</span>
                      {today && <span className="text-xs font-bold text-action">TODAY</span>}
                    </div>
                    {blocksOn(day).map((b) => <BlockedBanner key={b.id} block={b} learner={learner} onRemove={removeBlock} />)}
                    {lessons.map((lesson) => (
                      <LessonChip key={`${lesson.child_id}-${lesson.id}`} lesson={lesson} child={lesson.child} showName={shown.length > 1} onOpen={open} />
                    ))}
                    {!lessons.length && !blocksOn(day).length && (
                      <button type="button" onClick={() => setDayOff({ date: isoDay(day) })}
                        className="flex-1 min-h-16 rounded-[10px] border border-dashed border-line text-[13px] text-subtle hover:text-ink hover:border-muted">
                        No lessons
                      </button>
                    )}
                  </section>
                );
              })}
          </div>
        ) : (
          <div className="bg-surface border border-line rounded-2xl overflow-hidden">
            <div className="grid grid-cols-7 border-b border-line bg-paper">
              {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => (
                <div key={d} className="py-2.5 text-center text-xs font-bold tracking-wider uppercase text-muted">{d}</div>
              ))}
            </div>
            <div className="grid grid-cols-7">
              {Array.from({ length: differenceInCalendarDays(end, start) + 1 }, (_, i) => addDays(start, i)).map((day) => {
                const lessons = lessonsOn(day);
                const blocks = blocksOn(day);
                const done = checkedOn(day);
                const today = isSameDay(day, new Date());
                return (
                  <button key={day.toISOString()} type="button"
                    onClick={() => { setAnchor(day); setView('week'); }}
                    aria-label={`${format(day, 'EEEE d MMMM')}: ${lessons.length} lessons${blocks.length ? ', day off' : ''}. Show the week`}
                    className={clsx('min-h-24 md:min-h-28 p-1.5 border-b border-r border-line-soft text-left flex flex-col gap-1 hover:bg-paper',
                      !isSameMonth(day, anchor) && 'bg-paper/60 text-subtle', today && 'outline-2 -outline-offset-2 outline-ink')}>
                    <span className={clsx('text-xs font-semibold px-1', today && 'text-action font-bold')}>{format(day, 'd')}</span>
                    {blocks.length > 0 && (
                      <span className="text-[11px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-md bg-attention-soft text-attention truncate">
                        {blocks[0].note || REASONS[blocks[0].block_type]}
                      </span>
                    )}
                    {lessons.slice(0, 3).map((lesson) => {
                      const tones = learnerTones(lesson.child.color);
                      return (
                        <span key={`${lesson.child_id}-${lesson.id}`} className={clsx('text-[11px] leading-tight px-1.5 py-0.5 rounded-md truncate', lesson.is_completed && 'line-through opacity-70')}
                          style={{ background: tones.soft, color: tones.strong }}>
                          {lesson.subject_name}
                        </span>
                      );
                    })}
                    {lessons.length > 3 && <span className="text-[11px] text-muted px-1">+{lessons.length - 3} more</span>}
                    {done.length > 0 && (
                      <span className="text-[11px] px-1.5 py-0.5 rounded-md bg-action-soft text-action truncate">
                        {done.length} {done.length === 1 ? 'chapter' : 'chapters'} checked
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {pace.length > 0 && (
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-5 py-3.5 rounded-2xl bg-paper-deep text-sm text-muted">
            <span className="font-bold text-ink">At this pace</span>
            {pace.map(({ child, subjects }) => (
              <span key={child.id}>
                <span className="font-bold" style={{ color: learnerTones(child.color).strong }}>{child.name}</span>
                {' · '}
                {subjects.map((s, i) => {
                  const late = endDate && parseISO(s.projected_finish_date) > endDate;
                  return (
                    <span key={s.subject_id} className={clsx(late && 'text-attention font-semibold')}>
                      {i > 0 && ' · '}{s.subject_name} ~{format(parseISO(s.projected_finish_date), late ? 'd MMM yyyy' : 'd MMM')}
                    </span>
                  );
                })}
              </span>
            ))}
          </div>
        )}
      </div>
      {dayOff && (
        <DayOffDialog open onClose={() => setDayOff(null)} learners={learners} defaultDate={dayOff.date}
          defaultWho={selected === 'all' ? 'all' : String(selected)} onSaved={afterDayOff} />
      )}
    </>
  );
}

