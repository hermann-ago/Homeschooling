import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { booksApi } from '../api/books';
import { Button } from '../ui';

export default function WorkbookProgress({ child }) {
  const { data: subjects = [], error } = useQuery({ queryKey: ['workbook-progress', child.id], queryFn: () => booksApi.progress(child.id) });
  const [opened, setOpened] = useState(null);
  const [problem, setProblem] = useState('');
  const navigate = useNavigate();
  const practice = async (exercise) => { try { navigate((await booksApi.practice(exercise.id)).path); } catch (e) { setProblem(e.message); } };
  const books = subjects.flatMap((s) => s.books.filter((b) => b.role === 'workbook' || b.role === 'test' || b.role === 'combined').map((b) => ({ ...b, subject: s.subject.name })));
  if (!books.length && !error) return null;
  return <section aria-label={`${child.name}'s workbook progress`} className="rounded-2xl border border-line bg-surface p-5 flex flex-col gap-4">
    <h2 className="text-lg font-bold">{child.name} · Workbook progress</h2>
    <p className="text-sm text-muted">Reading, finished exercises, and independent understanding are tracked separately.</p>
    {books.map((book) => {
      const core = book.exercises.filter((e) => !e.optional);
      const assigned = core.filter((e) => e.work_status !== 'available');
      const reviewed = assigned.filter((e) => e.work_status === 'reviewed');
      const chapters = Object.values(book.exercises.reduce((groups, exercise) => {
        const key = exercise.chapter ? `Chapter ${exercise.chapter}` : exercise.section || 'Other exercises';
        (groups[key] ||= { title: key, exercises: [] }).exercises.push(exercise);
        return groups;
      }, {}));
      return <div key={book.id} className="border-t border-line pt-3 flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-3"><div className="flex-1"><h3 className="text-sm font-semibold">{book.subject} · {book.name}</h3>{book.exercises.length > 0 || book.status === 'ready' ? <p className="text-xs text-muted">{reviewed.length} reviewed of {assigned.length} assigned · {core.length - assigned.length} available · {assigned.length - reviewed.length} pending</p> : <p className="text-xs text-muted">{book.status === 'failed' ? 'Preparation paused' : book.status === 'waiting' ? 'Waiting for textbook' : book.status === 'not_prepared' ? 'Awaiting preparation' : 'Preparing exercises'} · exercise progress will appear after preparation.</p>}</div>{book.exercises.length > 0 ? <Button size="sm" onClick={() => setOpened(opened === book.id ? null : book.id)}>View work</Button> : <Button size="sm" onClick={() => navigate('/curriculum')}>Books & lessons</Button>}</div>
        {opened === book.id && <div className="max-h-[34rem] overflow-y-auto divide-y divide-line-soft">{chapters.map((chapter) => <details key={chapter.title} className="py-3">
          <summary className="cursor-pointer text-sm font-semibold">{chapter.title} · {chapter.exercises.filter((e) => e.work_status === 'reviewed').length} of {chapter.exercises.length} reviewed</summary>
          {chapter.exercises.map((e) => <div key={e.id} className="py-3 flex flex-col gap-2">
          <div className="flex flex-wrap justify-between items-center gap-2"><p className="text-sm font-semibold">{e.section} · exercise {e.reference} · page {e.printed_page || e.pages.join(', ')} · {e.work_status}{e.optional ? ' · optional' : ''}</p>
            {e.status === 'matched' && (e.ready_for_practice || e.work_status !== 'available') && <Button size="sm" onClick={() => practice(e)}>{e.work_status === 'reviewed' ? 'Practice again' : e.work_status === 'available' ? 'Start exercise' : 'Resume work'}</Button>}
          </div>
          <p className="text-sm whitespace-pre-wrap">{e.prompt}</p>
          {e.submissions?.filter((submission) => submission.status !== 'assessed').map((submission, i) => <p key={i} className="text-sm whitespace-pre-wrap">Saved submission: {submission.text || 'Photo submitted'} · feedback pending</p>)}
          {e.feedback?.map((text, i) => <p key={i} className="text-sm whitespace-pre-wrap text-muted">{text}</p>)}
          {e.evidence?.map((photo) => <a key={photo.id} href={modeHref(`/api/student-work/${photo.id}`)} target="_blank" rel="noreferrer" className="text-sm font-semibold text-action">Submitted work · {photo.filename}</a>)}
          {e.attempts.map((a) => <div key={a.id} className="rounded-lg bg-paper p-3 text-sm whitespace-pre-wrap"><p>{a.first_answer || 'Awaiting readable answer'} · {a.first_result}</p>{a.help_given && <p>Help: {a.help_given}</p>}{a.revised_answer && <p>Revision: {a.revised_answer} · {a.after_help_result}</p>}<p className="text-xs text-muted mt-1">{a.independence?.replaceAll('_', ' ')}{a.amends_attempt_id ? ' · amendment' : ''}</p></div>)}
        </div>)}</details>)}</div>}
      </div>;
    })}
    {(problem || error) && <p role="alert" className="text-sm text-problem">{problem || error.message}</p>}
  </section>;
}
import { modeHref } from '../api/mode';
