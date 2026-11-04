import { useEffect, useState } from 'react';
import { subjectsApi } from '../api/subjects';
import { Button } from '../ui';
import { inputClasses } from '../ui/classes';

/**
 * The publisher's video lesson pages for a subject. Finding reads the pages
 * and gives each lesson the video with its number; a lesson can also get its
 * own link, or none. Lessons prepared from now on show the video as a step.
 */
export default function SubjectVideos({ subject }) {
  const [saved, setSaved] = useState(null);
  const [pages, setPages] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [problem, setProblem] = useState('');
  const [editing, setEditing] = useState(null);
  const [link, setLink] = useState('');
  useEffect(() => {
    let active = true;
    subjectsApi.videos(subject.id).then((next) => { if (active) { setSaved(next); setPages(next.pages.join('\n')); } })
      .catch((error) => { if (active) setProblem(error.message); });
    return () => { active = false; };
  }, [subject.id]);
  const run = async (work) => {
    setBusy(true); setProblem('');
    try { return await work(); } catch (error) { setProblem(error.message); return null; } finally { setBusy(false); }
  };
  const find = () => run(async () => {
    const next = await subjectsApi.findVideos(subject.id, pages.split('\n').map((p) => p.trim()).filter(Boolean));
    setResult(next); setSaved({ pages: next.pages, lessons: next.lessons });
  });
  const reload = async () => setSaved(await subjectsApi.videos(subject.id));
  const lessons = saved?.lessons || [];
  const withVideo = lessons.filter((lesson) => lesson.video).length;
  return <div className="flex flex-col gap-1.5">
    <span className="text-[13px] font-semibold text-muted">Video lessons</span>
    <label className="text-[13px] text-subtle flex flex-col gap-1">The publisher's video pages for this book, one link per line
      <textarea rows={3} value={pages} disabled={busy} onChange={(event) => setPages(event.target.value)} placeholder="https://…/math-4-unit-1"
        className={`${inputClasses} h-auto py-2 text-sm text-ink`} /></label>
    <Button size="sm" className="self-start" disabled={busy || !pages.trim()} onClick={find}>{busy ? 'Finding videos…' : 'Find videos'}</Button>
    {result && <p role="status" className="text-[13px]">Found {result.videos} videos · {result.matched} matched to lessons by number.
      {result.unmatched.length > 0 && ` Not matched: ${result.unmatched.join(', ')}.`}{result.problems.length > 0 && ` ${result.problems.join('. ')}.`}</p>}
    {problem && <p role="alert" className="text-[13px] text-problem">{problem}</p>}
    {lessons.length > 0 && <details className="text-[13px]">
      <summary className="cursor-pointer text-action">{withVideo} of {lessons.length} lessons have a video · Change one lesson</summary>
      <ul className="mt-2 flex flex-col gap-1 max-h-64 overflow-auto">
        {lessons.map((lesson) => <li key={lesson.topic_id} className="flex flex-col gap-1 border-b border-line py-1">
          <div className="flex items-center gap-2">
            <span className="flex-1 min-w-0 truncate">{lesson.title}</span>
            {lesson.video ? <a className="text-action underline shrink-0" href={lesson.video.open_url} target="_blank" rel="noreferrer">Video</a>
              : <span className="text-subtle shrink-0">{lesson.hidden ? 'Hidden' : 'No video'}</span>}
            <button type="button" className="text-action shrink-0" onClick={() => { setEditing(editing === lesson.topic_id ? null : lesson.topic_id); setLink(''); }}>Change</button>
          </div>
          {editing === lesson.topic_id && <div className="flex flex-wrap items-center gap-2">
            <input className={`${inputClasses} h-9 flex-1 min-w-48 text-sm`} aria-label={`Video link for ${lesson.title}`} placeholder="Vimeo or YouTube link"
              value={link} disabled={busy} onChange={(event) => setLink(event.target.value)} />
            <Button size="sm" disabled={busy || !link.trim()} onClick={() => run(async () => { await subjectsApi.setLessonVideo(lesson.topic_id, { url: link.trim() }); await reload(); setEditing(null); })}>Use this link</Button>
            <Button size="sm" variant="quiet" disabled={busy} onClick={() => run(async () => { await subjectsApi.setLessonVideo(lesson.topic_id, { hidden: true }); await reload(); setEditing(null); })}>No video</Button>
            {(lesson.hidden || lesson.video?.source === 'manual') && <Button size="sm" variant="quiet" disabled={busy}
              onClick={() => run(async () => { await subjectsApi.clearLessonVideo(lesson.topic_id); await reload(); setEditing(null); })}>Undo my change</Button>}
          </div>}
        </li>)}
      </ul>
    </details>}
    <span className="text-[13px] text-subtle">Each video plays inside its lesson, from the publisher's own player, as a step after the welcome. After undoing a change, Find videos again restores the found video.</span>
  </div>;
}
