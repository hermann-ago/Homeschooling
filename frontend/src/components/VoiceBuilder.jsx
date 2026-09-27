import React, { useState } from 'react';
import { AudioLines } from 'lucide-react';
import { tutorApi } from '../api/tutor';

const cleanError = (e) => e.message.replace(/^\/[^:]+: /, '');

/**
 * Builds the lesson's read-along voice with the home server's text-to-speech.
 * It first shows how much of the monthly allowance the lesson needs; the voice
 * is saved with the lesson, so the tutor and every device reuse it.
 */
export default function VoiceBuilder({ learner, topic, disabled, onBuilt }) {
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

  const ask = () => run(async () => setEstimate(await tutorApi.buildNarration(learner, topic, true)));
  const build = () => run(async () => {
    await tutorApi.buildNarration(learner, topic, false);
    setEstimate(null);
    onBuilt();
  });

  const left = estimate ? Math.max(0, estimate.monthly_limit - estimate.used_this_month) : 0;
  return (
    <div className="p-3 border-b bg-sky-50 text-sm space-y-2">
      {!estimate ? (
        <button type="button" onClick={ask} disabled={disabled || busy}
          className="w-full h-11 rounded-xl bg-sky-600 text-white font-semibold flex items-center justify-center gap-2 disabled:opacity-50">
          <AudioLines className="w-5 h-5" />
          {busy ? 'Checking…' : 'Create read-along voice'}
        </button>
      ) : (
        <>
          <p>
            Create a natural voice for this lesson? It uses {estimate.characters.toLocaleString()} of the{' '}
            {left.toLocaleString()} characters left this month.
          </p>
          <div className="flex gap-2">
            <button type="button" onClick={build} disabled={disabled || busy || estimate.characters > left}
              className="flex-1 h-11 rounded-xl bg-sky-600 text-white font-semibold disabled:opacity-50">
              {busy ? 'Creating the voice…' : 'Create voice'}
            </button>
            <button type="button" onClick={() => setEstimate(null)} disabled={busy}
              className="h-11 px-4 rounded-xl border bg-white">
              Cancel
            </button>
          </div>
          {estimate.characters > left && (
            <p className="text-xs text-amber-800">Not enough of this month's voice allowance is left; it renews next month. The device voice still works.</p>
          )}
        </>
      )}
      {!estimate && !busy && <p className="text-xs text-text-secondary">Until then, choose “Device voice” below.</p>}
      {error && <p className="text-xs text-red-700">{error}</p>}
    </div>
  );
}
