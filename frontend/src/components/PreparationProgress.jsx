/** The server's durable preparation state, including saved partial results. */
import { reviewRecovered } from '../utils/preparationStatus';

export default function PreparationProgress({ status }) {
  const job = status?.job;
  const voice = status?.audio;
  const running = ['queued', 'running'].includes(job?.status);
  const audioRunning = ['queued', 'running', 'aligning'].includes(voice?.status);
  const recovered = reviewRecovered(status);
  const problem = job?.status === 'paused' && !recovered ? status.review?.error || job.error : !running && voice?.status === 'paused' ? voice.error : null;
  if (!job && !audioRunning && !problem) return null;
  const phase = job?.phase;
  const message = problem ? 'Preparation paused'
    : job?.status === 'queued' ? 'Request received · waiting to start'
      : running || audioRunning ? phase === 'review' ? 'Checking the saved lesson script…'
        : phase === 'audio' || audioRunning ? 'Recording and synchronizing the voice…' : 'Writing the lesson script…'
        : recovered ? 'Script reviewed · ready to prepare voice' : job?.status === 'completed' ? 'Preparation finished' : 'Preparation status';
  return <div className="rounded-xl bg-paper p-3 text-sm flex flex-col gap-1" aria-label="Preparation progress">
    <p role={problem ? 'alert' : 'status'} className={problem ? 'font-semibold text-problem' : 'font-semibold'}>{message}{problem ? `: ${problem}` : ''}</p>
    <p className="text-muted">Script: {status.script_status === 'ready' ? 'saved' : status.script_status === 'outdated' ? 'older version saved' : 'not saved yet'} · Voice: {voice?.status === 'ready' ? 'ready' : voice?.completed_parts ? 'partly saved' : 'not ready yet'}</p>
    {voice?.parts > 0 && <p className="text-muted">{voice.completed_parts || 0} of {voice.parts} voice sections synchronized.</p>}
    {running && job.error && <p className="text-muted">{job.error}</p>}
    {(running || audioRunning) && <p className="text-xs text-muted">The home computer continues preparing if you close this window. You can return here to check progress.</p>}
    {running && phase === 'script' && <p className="text-xs text-muted">Writing a full lesson can take several minutes.</p>}
    {problem && <p className="text-xs text-muted">Saved materials are kept. Check the issue before retrying.</p>}
    {problem && job?.error_code === 'provider_quota' && <p className="text-xs text-muted">Script-provider API credits and Inworld voice credits are separate. Adding Inworld credit does not fund lesson-script generation.</p>}
    {problem && status.review?.status === 'failed' && <p className="text-xs text-muted">Open Script review to review the saved script again. A new script is not needed.</p>}
  </div>;
}
