import React, { useState } from 'react';
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
export default function VoiceBuilder({ learner, topic, guide = false, disabled, onBuilt }) {
  const [estimate, setEstimate] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

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

  const ask = () => run(async () => setEstimate(await tutorApi.buildNarration(learner, topic, true, guide)));
  const build = () => run(async () => {
    await tutorApi.buildNarration(learner, topic, false, guide);
    setEstimate(null);
    onBuilt();
  });

  const left = estimate ? Math.max(0, estimate.monthly_limit - estimate.used_this_month) : 0;
  return (
    <div className="p-4 border-b border-line bg-action-soft/60 text-sm flex flex-col gap-2.5">
      {!estimate ? (
        <Button variant="primary" icon={AudioLines} onClick={ask} disabled={disabled || busy} className="w-full">
          {busy ? 'Checking…' : guide ? 'Create the guided lesson voice' : 'Create read-along voice'}
        </Button>
      ) : (
        <>
          <p>
            Create a natural voice for this {guide ? 'guided lesson' : 'lesson'}? It uses {estimate.characters.toLocaleString()} of the{' '}
            {left.toLocaleString()} characters left this month.
          </p>
          <div className="flex gap-2">
            <Button variant="primary" className="flex-1" onClick={build} disabled={disabled || busy || estimate.characters > left}>
              {busy ? 'Creating the voice…' : 'Create voice'}
            </Button>
            <Button onClick={() => setEstimate(null)} disabled={busy}>Cancel</Button>
          </div>
          {estimate.characters > left && (
            <p className="text-[13px] text-attention">Not enough of this month's voice allowance is left; it renews next month. The device voice still works.</p>
          )}
        </>
      )}
      {!estimate && !busy && <p className="text-[13px] text-muted">Until then, the device's own voice reads it (choose “Device voice” below).</p>}
      {error && <p className="text-[13px] text-problem">{error}</p>}
    </div>
  );
}
