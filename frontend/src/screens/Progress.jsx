import { Link } from 'react-router';
import { differenceInCalendarDays, format, parseISO } from 'date-fns';
import { Clock } from 'lucide-react';
import clsx from 'clsx';
import ScreenHeader from '../app/ScreenHeader';
import { useLearner } from '../app/learnerContext';
import { useFamilyProgress, useSchoolYear } from '../api/queries';
import { Button, ProgressBar } from '../ui';
import { learnerTones } from '../utils/colors';

/** How far through the school year today is, 0–100. */
function yearPercent(year, today = new Date()) {
  if (!year?.start_date || !year?.end_date) return null;
  const start = parseISO(year.start_date);
  const total = differenceInCalendarDays(parseISO(year.end_date), start);
  if (total <= 0) return null;
  return Math.max(0, Math.min(100, (differenceInCalendarDays(today, start) / total) * 100));
}

function describe(subject, endDate) {
  if (!subject.total_pages) return { kind: 'book' };
  if (subject.progress_percent >= 100) return { kind: 'done' };
  const finish = subject.projected_finish_date ? parseISO(subject.projected_finish_date) : null;
  const late = (finish && endDate && finish > endDate) || subject.status === 'at_risk';
  return { kind: late ? 'late' : 'pace', finish };
}

function LearnerCard({ child, progress, endDate, marker }) {
  const tones = learnerTones(child.color);
  const rows = progress.subjects.map((s) => ({ subject: s, ...describe(s, endDate) }));
  const count = (kind) => rows.filter((r) => r.kind === kind).length;
  const summary = [
    count('pace') + count('done') && `${count('pace') + count('done')} on pace`,
    count('late') && `${count('late')} behind`,
    count('book') && `${count('book')} ${count('book') === 1 ? 'needs' : 'need'} a book`,
  ].filter(Boolean).join(' · ');

  return (
    <article className="bg-surface border border-line rounded-[18px] p-6 flex flex-col gap-5">
      <div className="flex items-center gap-3.5">
        <span className="w-11 h-11 rounded-xl grid place-items-center font-display text-[22px] font-semibold"
          style={{ background: tones.soft, color: tones.strong }}>{child.name.charAt(0)}</span>
        <div className="flex-1 flex flex-col">
          <span className="text-lg font-bold">{child.name}</span>
          <span className="text-[13px] text-muted">{summary || 'No subjects yet'}</span>
        </div>
        <span className="font-display text-[34px] font-medium">{Math.round(progress.overall_progress)}%</span>
      </div>
      <div className="flex flex-col gap-4">
        {rows.map(({ subject, kind, finish }) => (
          kind === 'book' ? (
            <div key={subject.subject_id} className="flex justify-between items-center text-sm">
              <span className="font-semibold">{subject.subject_name}</span>
              <Link to="/curriculum" className="font-semibold text-action hover:text-action-hover">Add a book to track {subject.subject_name}</Link>
            </div>
          ) : (
            <div key={subject.subject_id} className="flex flex-col gap-1.5">
              <div className="flex justify-between gap-3 text-sm">
                <span className="font-semibold">{subject.subject_name}</span>
                <span className={clsx(kind === 'done' ? 'font-semibold text-action' : kind === 'late' ? 'font-semibold text-attention' : 'text-muted')}>
                  {kind === 'done'
                    ? `Complete · ${subject.completed_pages} of ${subject.total_pages} pages`
                    : `${Math.round(subject.progress_percent)}%${finish ? ` · finish ~${format(finish, kind === 'late' ? 'd MMM yyyy' : 'd MMM')}` : ''}`}
                </span>
              </div>
              <ProgressBar value={subject.progress_percent} marker={kind === 'done' ? null : marker}
                color={kind === 'done' ? 'var(--color-action)' : tones.strong}
                label={`${subject.subject_name}: ${Math.round(subject.progress_percent)}% of pages done`} />
            </div>
          )
        ))}
      </div>
    </article>
  );
}

export default function Progress() {
  const { learners, selected } = useLearner();
  const { data: family, isLoading } = useFamilyProgress();
  const { data: year } = useSchoolYear();
  const marker = yearPercent(year);
  const endDate = year?.end_date ? parseISO(year.end_date) : null;

  const entries = learners
    .filter((c) => selected === 'all' || c.id === selected)
    .map((child) => ({ child, progress: family?.children.find((p) => p.child_id === child.id) }))
    .filter((e) => e.progress);
  const withSubjects = entries.filter((e) => e.progress.subjects.length);
  const without = entries.filter((e) => !e.progress.subjects.length);
  const late = withSubjects.flatMap(({ child, progress }) => progress.subjects
    .filter((s) => describe(s, endDate).kind === 'late').map((s) => ({ child, subject: s })));
  const lateByChild = [...new Set(late.map((l) => l.child))].map((child) => (
    `${child.name}: ${late.filter((l) => l.child === child).map((l) => l.subject.subject_name).join(', ')}`
  ));

  return (
    <>
      <ScreenHeader actions={year && (
        <span className="text-sm text-muted">
          School year {format(parseISO(year.start_date), 'd MMM')} – {format(parseISO(year.end_date), 'd MMM yyyy')}
        </span>
      )} />
      <div className="px-4 md:px-10 py-7 flex flex-col gap-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-col gap-1.5">
            <h1 className="font-display text-3xl md:text-4xl font-medium">Progress</h1>
            <p className="text-[15px] text-muted">Pages done in each subject's main book, against how far the school year has gone.</p>
          </div>
          {marker != null && (
            <span className="flex items-center gap-2.5 text-[13px] text-muted">
              <span aria-hidden="true" className="w-0.5 h-[18px] bg-ink" />Today in the school year · {Math.round(marker)}%
            </span>
          )}
        </div>

        {isLoading && <p className="text-muted">Loading…</p>}
        <div className={clsx('grid gap-5', withSubjects.length > 1 && 'lg:grid-cols-2')}>
          {withSubjects.map(({ child, progress }) => (
            <LearnerCard key={child.id} child={child} progress={progress} endDate={endDate} marker={marker} />
          ))}
        </div>

        {late.length > 0 && (
          <section className="flex flex-wrap items-center gap-4 md:gap-5 px-6 py-5 rounded-2xl bg-attention-soft">
            <span className="w-10 h-10 shrink-0 rounded-xl bg-surface text-attention grid place-items-center">
              <Clock aria-hidden="true" className="w-5 h-5" />
            </span>
            <div className="flex-1 min-w-[16rem] flex flex-col gap-0.5">
              <span className="text-[15px] font-bold">
                {late.length} {late.length === 1 ? 'subject' : 'subjects'} would finish after {endDate ? format(endDate, 'd MMMM') : 'the school year'}
              </span>
              <span className="text-sm text-[#5C4A2A]">{lateByChild.join(' · ')}. Choose how to catch up.</span>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button as={Link} to="/settings#study-times" size="sm">Add study time</Button>
              <Button as={Link} to="/curriculum" size="sm">Speed up these subjects</Button>
              <Button as={Link} to="/settings#school-year" size="sm">Move the end date</Button>
            </div>
          </section>
        )}

        {without.length > 0 && (
          <div className="flex flex-wrap gap-3.5">
            {without.map(({ child }) => (
              <div key={child.id} className="flex-1 min-w-[16rem] flex items-center gap-3 px-4.5 py-3.5 rounded-2xl border border-dashed border-line text-sm text-muted">
                <span aria-hidden="true" className="w-2.5 h-2.5 rounded-full" style={{ background: child.color }} />
                <strong className="text-ink">{child.name}</strong>
                {child.grade_year && child.grade_year !== 'N/A' ? ` · ${child.grade_year}` : ''} · no subjects yet
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
