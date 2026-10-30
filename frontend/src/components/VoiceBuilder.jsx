import React, { useEffect, useState } from 'react';
import { AudioLines } from 'lucide-react';
import { tutorApi } from '../api/tutor';
import { Button } from '../ui';

const cleanError = (e) => e.message.replace(/^\/[^:]+: /, '');

/**
 * Builds the lesson's read-along voice (or, with `guide`, the guided lesson's
 * voice) with the home server's text-to-speech. It first shows how much of the
 * monthly allowance it needs; the voice is saved with the lesson, so the tutor
 * and every device reuse it.
 */
export default function VoiceBuilder({ learner, topic, guide = false, disabled, onBuilt, session = null, retry = false, retryMissing=false, onBuildingChange, provider = 'google-gemini' }) {
  const [estimate, setEstimate] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [building, setBuilding] = useState(false);
  useEffect(() => {
    if (!building) return undefined;
    const timer = window.setInterval(() => onBuilt?.(), 4000);
    return () => window.clearInterval(timer);
  }, [building, onBuilt]);

  const run = async (work) => {
    setBusy(true);
    setError('');
    try {
      await work();
    } catch (e) {
      setError(cleanError(e));
    } finally {
      setBusy(false);
    }
  };

  const request=dry=>retryMissing?tutorApi.buildNarration(learner,topic,dry,guide,session,{retryMissing:true})
    :tutorApi.buildNarration(learner,topic,dry,guide,...(session?[session]:[]));
  const ask = () => run(async () => setEstimate(await request(true)));
  const build = () => run(async () => {
    setBuilding(true);
    onBuildingChange?.(true);
    try {
      await request(false);
      setEstimate(null);
    } finally {
      setBuilding(false);
      onBuildingChange?.(false);
      onBuilt?.();
    }
  });

  const paid = estimate?.estimated_cost_usd !== undefined;
  const local = estimate?.provider === 'kokoro-local';
  const narrator = (estimate?.provider || provider) === 'inworld' ? 'Inworld Flash' : (estimate?.provider || provider) === 'elevenlabs' ? 'ElevenLabs' : 'Google';
  const units = estimate?.alignment === 'local' ? 'recording blocks' : 'passages';
  const allowed = estimate && estimate.allowed !== false;
  return (
    <div className="p-4 border-b border-line bg-action-soft/60 text-sm flex flex-col gap-2.5">
      {!estimate ? (
        <Button variant="primary" icon={AudioLines} onClick={ask} disabled={disabled || busy} className="w-full">
          {busy ? 'Checking…' : retryMissing?'Retry missing Google audio':retry ? `Retry ${narrator} voice` : guide ? 'Create the guided lesson voice' : 'Create read-along voice'}
        </Button>
      ) : (
        <>
          <p>
            {retry ? <>Saved audio will be reused. {paid && !estimate.reused ? `Generating the missing audio will cost at most US$${estimate.estimated_cost_usd.toFixed(3)}.` : 'The saved recording will be checked again.'}</> : paid ? estimate.reused ? 'This recording is already saved; replay adds no generation cost.' : local ?
              'Create this voice on the home computer? There is no API charge. Allow a few minutes; completed passages are saved and reused if interrupted.' :
              `Create an expressive voice? The maximum for the remaining ${units} is US$${estimate.estimated_cost_usd.toFixed(3)}. Costs are tracked; provider billing controls spending. Saved audio is reused.` :
              `Create a natural voice? It generates ${estimate.characters.toLocaleString()} characters, tracked with your provider costs.`}
          </p>
          {retryMissing&&<p className="text-[13px] text-muted">Ask Google to reconsider the missing blocks once, using the same text. Working recordings are kept. Another decline stays text-only.</p>}
          {retry && estimate.job_status==='alignment_review' && <p className="text-[13px] text-muted">Retry first checks the saved audio’s timing. If that fails again, preparation pauses and keeps your recording.</p>}
          {!retry && paid && !estimate.reused && <p className="text-[13px] text-muted">{estimate.completed_parts} of {estimate.parts} {units} ready · {local ? 'Home computer' : estimate.model} · {estimate.job_status}. {estimate.alignment === 'local' ? 'One Google request per block. This computer synchronizes the text and cuts the activity pauses.' : 'Unchanged passages are reused across guide versions.'}</p>}
          <div className="flex gap-2">
            <Button variant="primary" className="flex-1" onClick={build} disabled={disabled || busy || !allowed}>
              {busy ? retry ? `Resuming ${narrator} voice…` : 'Creating the voice…' : retry ? `Resume ${narrator} voice` : 'Create voice'}
            </Button>
            <Button onClick={() => setEstimate(null)} disabled={busy}>Cancel</Button>
          </div>
          {!allowed && (
            <p className="text-[13px] text-attention">{estimate.reason || "Check the provider connection and recording status. The device voice still works."}</p>
          )}
        </>
      )}
      {!estimate && !busy && !retry && <p className="text-[13px] text-muted">Until then, the device's own voice reads it (choose “Device voice” below).</p>}
      {building && <p role="status" className="text-[13px] text-muted">Working in the background; you can continue the lesson. Progress is saved even if you refresh.</p>}
      {error && <p role="alert" className="text-[13px] text-problem">{error}</p>}
    </div>
  );
}
