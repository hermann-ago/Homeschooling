import { AudioLines, CheckCircle2, CircleAlert, LoaderCircle } from 'lucide-react';
import { useState } from 'react';
import VoiceBuilder from './VoiceBuilder';

/** Session-wide preparation feedback, independent of the selected activity/player. */
export default function LessonVoiceStatus({ guide, learner, topic, session, onChanged, closed, compact = false }) {
  const [retrying, setRetrying] = useState(false);
  const tracks=(guide?.audio || []).filter(t=>t.synchronized && t.status==='ready');
  const preferred=tracks.find(t=>t.preferred && !t.fallback_parts);
  const pending=guide?.voice_preparation;
  const job=preferred && pending?.provider!==preferred.provider
    ? {provider:preferred.provider,status:'ready'} : pending;
  const provider=job?.provider || tracks[0]?.provider;
  const voice=provider?.startsWith('google') ? 'Google voice' : provider==='elevenlabs' ? 'ElevenLabs voice' : provider==='inworld' ? 'Inworld voice' : provider==='kokoro-local' ? 'Lesson voice' : 'Recorded voice';
  const busy=retrying || ['queued','running','aligning'].includes(job?.status);
  const noAudio=job?.status==='ready_with_fallback' && job.recorded_parts===0;
  const ready=!noAudio && (['ready','ready_with_fallback'].includes(job?.status) || !job && tracks.length>0);
  const paused=noAudio || ['paused','failed','alignment_review','partial'].includes(job?.status);
  const retryMissing=job?.status==='ready_with_fallback'&&!job?.missing_retry_used;
  let title,description;
  if(guide?.script_review&&['not_reviewed','outdated','failed','needs_changes','needs_source_review'].includes(guide.script_review.status)&&!ready&&!busy) {
    title=guide.script_review.summary;description='The script is saved. Check its review in Curriculum → Preparation options before requesting new audio.';
  } else if(retrying && !['running','aligning','queued'].includes(job?.status)) {
    title=`Resuming ${voice}…`;description='Reusing the saved recording and retrying preparation. Progress is saved in the background.';
  } else if(job?.status==='queued') {
    title=`${voice} queued`;description='Waiting to start in the background. You can continue the lesson.';
  } else if(job?.status==='aligning') {
    title=`Synchronizing ${voice}…`;description='Matching the saved audio to the lesson text and activity pauses. You can keep reading.';
  } else if(job?.status==='running') {
    title=`Preparing ${voice}…`;description='Working in the background. You can continue with text or Device voice.';
  } else if(job?.status==='alignment_review') {
    title=`${voice} paused · synchronization needs attention`;description='The saved audio is kept, but its timing is not ready for playback. You can continue with Device voice.';
  } else if(noAudio) {
    title=`${voice} declined · no audio saved`;
    description='Google declined every requested audio block. There is no Google recording for this lesson. Your script remains available to read.';
  } else if(paused) {
    title=`${voice} preparation paused`;
    description=/429|quota|rate limit|daily request allowance/i.test(job?.error || '')
      ? 'The voice provider’s request limit was reached. Saved audio is kept; you can use Device voice.'
      : 'Your lesson and any saved audio are kept. You can continue with text or Device voice.';
  } else if(ready) {
    title=`${voice} ready`;
    if(job?.status==='ready_with_fallback' || !preferred && tracks.some(t=>t.fallback_parts>0)) {
      title=`${voice} · some passages text-only`;
      description=job?.missing_retry_used
        ? 'Google declined one or more sections again. Working recordings are saved; those sections remain text-only.'
        : 'Saved recordings are available. Passages Google declined stay text-only; you can choose Device voice for those passages.';
    }
  } else {
    title='Recorded lesson voice has not started';description='You can continue with text or Device voice.';
  }
  const count=Number.isInteger(job?.parts) && job.parts>0;
  const progress=count && !ready ? noAudio ? `0 of ${job.parts} audio blocks recorded` : job.alignment==='local' && Number.isInteger(job.recorded_parts)
    ? `${job.recorded_parts} of ${job.parts} audio blocks saved · ${job.completed_parts || 0} synchronized`
    : Number.isInteger(job.completed_parts) ? `${job.completed_parts} of ${job.parts} passages saved` : null : null;
  const Icon=busy ? LoaderCircle : paused ? CircleAlert : ready ? CheckCircle2 : AudioLines;
  // The preparation bar owns generation/retry actions in the guided workspace.
  // Keep this notice small enough to leave the current activity visible.
  if (compact && ready) return null;
  return <aside aria-label="Lesson voice preparation" aria-live="polite" aria-atomic="true" role="status"
    className={`shrink-0 mx-3 mb-2 rounded-lg px-3 py-2 text-xs ${paused ? 'bg-attention-soft text-attention' : 'bg-action-soft/60 text-action'}`}>
    <div className="flex items-start gap-2"><Icon size={15} aria-hidden="true" className={`shrink-0 mt-px ${busy ? 'animate-spin motion-reduce:animate-none' : ''}`}/>
      <div className="min-w-0"><p className="font-semibold">{title}</p>
        {description && !compact && <p className="mt-1 leading-relaxed">{description}</p>}
        {progress && <p className="mt-1 tabular-nums">{progress}</p>}
        {paused && job?.error && <details className="mt-1"><summary className="cursor-pointer">Voice preparation details</summary><p className="mt-1 break-words">{job.error}</p></details>}
        {!compact && (paused || retrying || retryMissing) && ['google-gemini','elevenlabs','inworld'].includes(provider) && learner && topic && !closed && <VoiceBuilder
          provider={provider}
          learner={learner} topic={topic} guide session={session} retry retryMissing={retryMissing} onBuilt={onChanged} onBuildingChange={setRetrying}/>}
      </div>
    </div>
  </aside>;
}
