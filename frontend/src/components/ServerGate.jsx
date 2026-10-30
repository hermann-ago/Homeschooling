import { useCallback, useEffect, useState } from 'react';
import { systemApi } from '../api/system';
import { DeviceContext } from './deviceContext';
import { MODE_KEY, currentMode, switchBrowserMode } from '../api/mode';

/**
 * Every device on the home network uses the app without pairing; the home
 * server itself refuses anything from outside the network. This only waits for
 * the server and says so plainly when it is not answering.
 */
export default function ServerGate({ children }) {
  const [session, setSession] = useState(undefined);

  const refresh = useCallback(() => {
    systemApi.session().then(setSession).catch((failure) => setSession({ offline: true, error: failure.message }));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    const changed = (event) => { if (event.key === MODE_KEY) window.location.reload(); };
    window.addEventListener('storage', changed);
    return () => window.removeEventListener('storage', changed);
  }, []);
  useEffect(() => {
    if (!session?.test_mode) return;
    const original = document.title;
    document.title = 'TEST MODE · Homeschool';
    return () => { document.title = original; };
  }, [session?.test_mode]);

  if (session === undefined) return <main className="min-h-screen grid place-items-center">Connecting to the home server…</main>;
  if (session.offline) {
    return (
      <main className="min-h-screen grid place-items-center p-6 text-center">
        <div>
          <p className="font-medium">The home server is not answering.</p>
          <p className="text-sm text-text-secondary mt-1">Make sure the family computer is on, awake and running Homeschooling.</p>
          <button onClick={refresh} className="mt-4 rounded-sm bg-accent px-4 py-2 text-white">Try again</button>
          {currentMode !== 'live' && <div className="mt-4"><p className="text-sm">Your test session may have ended. Real records have not been substituted.</p><button className="mt-2 underline text-action" onClick={() => switchBrowserMode(null)}>Return to normal mode</button></div>}
        </div>
      </main>
    );
  }
  return <DeviceContext.Provider value={session}>
    {session.test_mode ? <div className="test-copy">
      <div role="status" className="h-14 md:h-10 flex flex-col md:flex-row items-center justify-center gap-0.5 md:gap-3 bg-attention-soft text-attention border-b border-attention px-3 text-xs md:text-sm">
        <strong>TEST MODE</strong>
        <span>Real student records are protected · AI provider costs are tracked</span>
        <a className="hidden md:inline underline" href="/settings#test-mode">Turn off</a>
      </div>
      <div className="test-copy-content">{children}</div>
    </div> : children}
  </DeviceContext.Provider>;
}
