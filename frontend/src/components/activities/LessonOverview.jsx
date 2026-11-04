import { modeHref } from '../../api/mode';
import { Button } from '../../ui';
import { activityDefinition,practiceHistory } from './registry';
import { learningLabel } from '../../utils/learningLabels';
import { ProgressDots } from './Progress';

export function LessonPosition({ state, compact = false, header = false }) {
  const roots = (state.activities || []).filter((item) => item.status !== 'not_assigned' && !item.parent_activity_id && !activityDefinition(item).internal);
  const steps=practiceHistory(roots).map((group)=>({...group.items[0],id:group.key,memberIds:group.items.map((item)=>item.id)}));
  const label=(step)=>step.practice_section?.title || activityDefinition(step).label;
  if (!steps.length) return null;
  const byId = new Map((state.activities || []).map((item) => [item.id, item]));
  let current = state.active_activity;
  const visited = new Set();
  while (current?.parent_activity_id && !visited.has(current.id)) {
    visited.add(current.id); current = byId.get(current.parent_activity_id);
  }
  const index = state.status === 'completed' ? steps.length - 1 : Math.max(0, steps.findIndex((step) => step.memberIds.includes(current?.id)));
  const visible = steps.map((step, position) => ({ ...step, position })).filter((step) => steps.length <= 5 || Math.abs(step.position - index) <= 1 || step.position === 0 || step.position === steps.length - 1);
  if (compact) return <nav aria-label="Lesson position" className="text-xs text-muted">{state.status === 'completed' ? 'Lesson finished' : `Step ${index + 1} of ${steps.length} · ${label(steps[index])}`}{state.on_break ? ' · On a break' : ''}</nav>;
  return <nav aria-label="Lesson position" className={header ? 'tutor-lesson-position' : 'rounded-xl bg-paper/60 p-3 text-sm'}>
    <p className="font-semibold mb-2">{state.status === 'completed' ? 'Lesson finished' : `Step ${index + 1} of ${steps.length}`}{state.on_break ? ' · On a break' : ''}</p>
    <div role="progressbar" aria-label="Position in this lesson" aria-valuemin={1} aria-valuemax={steps.length} aria-valuenow={index + 1} aria-valuetext={`${label(steps[index])}, step ${index + 1} of ${steps.length}`} className="h-1 rounded-full bg-line overflow-hidden"><div className="h-full bg-action" style={{ width: `${100 * (index + 1) / steps.length}%` }} /></div>
    <ProgressDots progress={state.progress} currentId={current?.id} />
    <ol className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs">{visible.map((step) => <li key={step.id} aria-current={step.position === index ? 'step' : undefined} className={step.position === index ? 'text-action font-bold' : 'text-muted'}>{step.position + 1}. {label(step)}{step.status === 'skipped' ? ' · to revisit' : ''}</li>)}</ol>
  </nav>;
}

export function AttemptNavigation({ navigation }) {
  if (!navigation?.attempts?.length || navigation.attempts.length < 2) return null;
  return <nav aria-label="Lesson attempts" className="rounded-xl border border-line p-3 text-sm"><p className="font-semibold mb-2">This lesson and its repeats</p><ul className="flex flex-wrap gap-2">{navigation.attempts.map((attempt) => <li key={attempt.id}>{attempt.current
    ? <span aria-current="page" className="block rounded-lg bg-action-soft px-3 py-2 font-semibold">{attempt.label} · You are here</span>
    : <a className="block rounded-lg bg-paper px-3 py-2 text-action underline" href={modeHref(attempt.path)}>{attempt.label} · {attempt.status === 'completed' ? 'Saved' : 'Resume'}</a>}</li>)}</ul></nav>;
}

export function CatchUpNotice({ state, busy, onFocus }) {
  const info = state.catch_up;
  if (!info || state.status === 'completed') return null;
  return <section aria-label="Remaining work from the original lesson" className="rounded-xl bg-action-soft p-3 text-sm flex flex-col gap-2">
    <p className="font-semibold">Your original lesson is complete</p>
    <p>{info.remaining ? `This follow-up is for ${info.remaining} saved ${info.remaining === 1 ? 'activity' : 'activities'}, not another full reading.` : 'The saved work has been addressed. You can finish this follow-up without repeating the reading.'}</p>
    <ul className="flex flex-col gap-1">{info.items.map(item => <li key={item.activity_id}>{item.prompt}<span className="block text-xs text-muted">{['pending', 'skipped'].includes(item.status) ? 'Still to address' : 'Addressed'}</span></li>)}</ul>
    {!info.focused && <Button size="sm" disabled={busy} onClick={onFocus}>{info.remaining ? 'Go to remaining work' : 'Review and finish saved work'}</Button>}
    <a className="text-xs text-action underline" href={modeHref(info.original_path)}>View the completed original lesson</a>
  </section>;
}

export function ClosingSummary({ state, busy, onRevisit, onRepeat }) {
  const summary = state.learning_summary;
  if (!summary) return null;
  const finished = state.status === 'completed';
  const pending = summary.pending_work || [];
  const resume = state.attempt_navigation?.resume_repeat;
  const next = state.attempt_navigation?.next_lesson;
  const manual=state.completion_summary?.completion_source==='manual'||state.completion_summary?.completion_source==='topic_completion';
  return <section aria-label="What you did in this lesson" className="rounded-2xl border border-action/30 bg-action-soft/40 p-4 flex flex-col gap-3">
    <h2 tabIndex={-1} className="font-semibold focus-visible:outline-action">What you did</h2>
    {summary.lesson_title && <p className="text-sm text-muted">{summary.lesson_title}</p>}
    {manual&&<p className="text-sm font-semibold">{state.completion_summary.completion_source==='manual'?'Marked complete by you.':'This chapter was already marked complete.'} Saved work is preserved; completion does not assess unanswered work.</p>}
    <dl className="grid grid-cols-2 gap-3 text-sm">
      <div><dt className="text-muted">Reading reached</dt><dd className="font-semibold">{summary.reading.total ? `${summary.reading.reached} of ${summary.reading.total} reading steps` : 'No reading assigned'}</dd></div>
      <div><dt className="text-muted">Answers checked</dt><dd className="font-semibold">{summary.answers.captured ? `${summary.answers.checked} of ${summary.answers.captured} saved answers` : 'No answers saved yet'}</dd></div>
      <div><dt className="text-muted">Help used</dt><dd className="font-semibold">{summary.help.activity_count ? `${summary.help.activity_count} ${summary.help.activity_count === 1 ? 'activity' : 'activities'}` : 'No help recorded'}</dd></div>
      <div><dt className="text-muted">{manual?'Unassessed work':'Still to return to'}</dt><dd className="font-semibold">{pending.length} {pending.length === 1 ? 'activity' : 'activities'}</dd></div>
    </dl>
    {summary.answered_work?.length > 0 && <details className="text-sm"><summary className="font-semibold cursor-pointer">Questions you answered</summary><ul className="mt-2 flex flex-col gap-2">{summary.answered_work.map((item) => <li key={item.activity_id} className="rounded-lg bg-surface p-2"><p className="whitespace-pre-wrap">{item.prompt}</p><p className="text-xs text-muted mt-1">{item.checked ? 'Answer checked' : 'Answer saved · Not checked yet'}</p></li>)}</ul></details>}
    {summary.help.activity_labels?.length > 0 && <details className="text-sm"><summary className="font-semibold cursor-pointer">Where you used help</summary><ul className="mt-2 list-disc pl-5">{summary.help.activity_labels.map((label, index) => <li key={index} className="whitespace-pre-wrap">{label}</li>)}</ul></details>}
    <p className="text-xs text-muted">Reading and finishing a lesson are saved separately from understanding. Help stays part of your learning record.</p>
    {pending.length > 0 ? <ul className="flex flex-col gap-2">{pending.map((item) => <li key={item.activity_id} className="rounded-xl bg-surface p-3 text-sm"><p className="font-semibold whitespace-pre-wrap">{item.prompt}</p><p className="text-xs text-muted mt-1">{item.reason === 'skipped' ? 'Left to revisit' : learningLabel(item.reason)}{!item.has_response ? ' · No answer recorded' : ''}</p>{!finished && item.can_revisit && <Button size="sm" className="mt-2" disabled={busy} onClick={() => onRevisit(item.activity_id)}>Return to this activity</Button>}</li>)}</ul> : <p className="text-sm">No unfinished activities in this lesson.</p>}
    {finished && !manual && pending.length > 0 && (resume ? <Button as="a" href={modeHref(resume.path)}>Continue unfinished work</Button> : <Button disabled={busy} onClick={() => onRepeat({ unfinishedOnly: true })}>Continue unfinished work</Button>)}
    {finished && next && <div className="border-t border-line pt-3"><p className="text-sm text-muted mb-2">{next.title}</p><Button as="a" variant="primary" href={modeHref(next.path)}>{next.resume ? 'Resume unfinished lesson' : 'Open next lesson'}</Button></div>}
  </section>;
}
