import { useState } from 'react';
import { useDevice } from './deviceContext';
import { systemApi } from '../api/system';
import { currentMode, switchBrowserMode } from '../api/mode';
import { Button } from '../ui';

export default function TestModeSettings() {
  const device = useDevice();
  const enabled = device?.test_mode === true;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const requested = new URLSearchParams(window.location.search).get('resume_test');
  const savedSession = /^[a-f0-9]{32}$/.test(requested || '') ? requested : null;
  const resume = async () => {
    setBusy(true); setError('');
    try { const result = await systemApi.resumeTest(savedSession); switchBrowserMode(result.token); }
    catch (failure) { setError(failure.message); setBusy(false); }
  };
  const change = async () => {
    setBusy(true); setError('');
    try {
      const result = await systemApi.testMode(!enabled);
      switchBrowserMode(result.token);
    } catch (failure) {
      setError(failure.message); setBusy(false);
    }
  };
  return <section id="test-mode" className="scroll-mt-6 rounded-2xl border border-line bg-surface p-5 md:p-6 flex flex-col gap-3">
    <div className="flex items-center justify-between gap-4">
      <h2 className="font-display text-2xl font-medium">Test mode</h2>
      <Button role="switch" aria-checked={enabled} aria-label="Test mode" disabled={busy} onClick={change}>
        {busy ? 'Switching…' : enabled ? 'On · turn off' : 'Off · turn on'}
      </Button>
    </div>
    <p className="text-sm">Try lessons, the AI tutor, answers and completion without changing the children’s real records. This setting applies to this browser; other devices continue normally.</p>
    <p className="text-sm text-muted">Prepared lessons and saved recordings can be reused in normal lessons. New AI requests use tracked provider usage and may cost credits.</p>
    <p className="text-sm text-muted">Turning it off returns to real records. Each new test starts from current student records; pretend answers, reviews and progress never carry over.</p>
    {savedSession && <Button disabled={busy} onClick={resume}>Continue saved test session</Button>}
    {enabled && currentMode !== 'live' && <a className="text-sm underline" href={`/settings?resume_test=${currentMode}#test-mode`}>Bookmark this test session</a>}
    {error && <p role="alert" className="text-sm text-problem">{error}</p>}
  </section>;
}
