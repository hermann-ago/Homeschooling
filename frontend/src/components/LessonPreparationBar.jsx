import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { LoaderCircle, WandSparkles } from 'lucide-react';
import { curriculumPrepApi } from '../api/preparation';
import { currentMode, modeHref } from '../api/mode';
import { Button, Dialog } from '../ui';
import { CurriculumPreparationDialog } from './CurriculumLessonPrep';
import NarratorPicker from './NarratorPicker';
import PreparationProgress from './PreparationProgress';
import { reviewRecovered } from '../utils/preparationStatus';

// Who wrote the script: the app's writer, the app's script changed afterwards, or written outside the app.
const ORIGIN = { app: 'Written by the app', revised: 'Revised', hand: 'Written by hand' };

const working = (status) => ['queued', 'running'].includes(status?.job?.status)
  || ['queued', 'running', 'aligning'].includes(status?.audio?.status);

/** One visible home for guide and voice preparation, before or during a lesson. */
export default function LessonPreparationBar({ learner, topic, guide, pinned, onChanged }) {
  const [open, setOpen] = useState(false);
  const [narratorsOpen, setNarratorsOpen] = useState(false);
  const previous = useRef(null);
  const { data, error, refetch } = useQuery({
    queryKey: ['curriculum-preparation', currentMode, learner, topic],
    queryFn: () => curriculumPrepApi.lesson(learner, topic),
    refetchInterval: (query) => working(query.state.data) ? 3000 : 30000,
  });
  const stamp = data ? [data.guide_id, data.script_status, data.review?.status, data.job?.status, data.job?.phase, data.audio?.status].join(':') : null;
  useEffect(() => {
    if (stamp && previous.current && previous.current !== stamp) onChanged?.();
    if (stamp) previous.current = stamp;
  }, [stamp, onChanged]);
  const fallback = { guide_id: guide?.guide_id, script_status: guide?.current ? 'ready' : guide ? 'outdated' : 'missing',
    review: guide?.script_review, audio: { status: guide?.audio?.some((track) => track.synchronized && (track.preferred ?? true)) ? 'ready' : 'missing' } };
  const status = data || fallback;
  const busy = working(status);
  const ready = status.script_status === 'ready';
  const voiced = status.audio?.status === 'ready';
  const audioBusy = ['queued', 'running', 'aligning'].includes(status.audio?.status) || busy && status.job?.phase === 'audio';
  const olderVersion = pinned && data?.guide_id && data.guide_id !== guide?.guide_id;
  // The saved script still works, but its instructions or pages changed: offer the update here.
  const update = status.script_status === 'outdated' && !pinned && !busy;
  const label = busy ? status.job?.phase === 'review' ? 'Reviewing lesson…' : status.job?.phase === 'audio' || status.audio?.status === 'running' ? 'Preparing voice…' : 'Preparing lesson…'
    : update ? 'Update lesson & voice' : !ready ? 'Prepare lesson & voice' : !voiced ? 'Prepare voice' : 'Lesson & voice';
  return <section aria-label="Lesson preparation" className="lesson-preparation-bar" data-update={update || undefined}>
    <div className="min-w-0 text-xs text-muted" role="status">
      <p className="font-semibold text-ink">Lesson preparation</p>
      <p>Guide {ready ? 'ready' : status.script_status === 'outdated' ? 'update available' : 'not prepared'}{ORIGIN[status.origin || guide?.origin] ? ` · ${ORIGIN[status.origin || guide?.origin]}` : ''} · Voice {voiced ? 'ready' : audioBusy ? 'preparing' : busy ? 'waiting for the script' : 'not prepared'}</p>
      {update && <p className="text-attention">The teaching instructions or book pages changed since this lesson was prepared.</p>}
      {status.job?.error && !busy && !reviewRecovered(status) && <p className="text-attention">Preparation needs attention</p>}
    </div>
    <div className="flex flex-wrap items-center gap-2">
      <Button size="sm" disabled={busy} onClick={() => setNarratorsOpen(true)}>Narrator &amp; samples</Button>
      {olderVersion ? <Button as="a" size="sm" href={modeHref(`/lesson?learner=${learner}&topic=${topic}`)}>Prepare current version</Button>
        : <Button size="sm" variant={ready && !update ? 'secondary' : 'primary'} icon={busy ? LoaderCircle : WandSparkles} onClick={() => setOpen(true)}>{label}</Button>}
    </div>
    {(busy || data?.job?.status === 'paused') && <div className="basis-full"><PreparationProgress status={status}/></div>}
    {error && <div className="basis-full text-xs"><p role="alert">Could not refresh preparation status. The home computer may still be working.</p><button className="text-action underline" onClick={() => refetch()}>Refresh preparation status</button></div>}
    {open && <CurriculumPreparationDialog learner={learner} topic={{ id: topic, title: data?.title || guide?.title || 'This lesson' }}
      status={status} target={ready ? 'audio' : 'both'} onClose={() => { setOpen(false); refetch(); onChanged?.(); }} />}
    {narratorsOpen && <Dialog open title="Narrator & samples" width={680} onClose={() => setNarratorsOpen(false)}
      footer={<><Button as="a" href={modeHref('/settings#narrator-voices')}>Family &amp; child narrators</Button><Button onClick={() => setNarratorsOpen(false)}>Done</Button></>}>
      <div className="max-h-[60vh] overflow-auto"><NarratorPicker key={topic} topic={topic} onChanged={() => { refetch(); onChanged?.(); }}/></div>
    </Dialog>}
  </section>;
}
