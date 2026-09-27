import { useCallback, useEffect, useState } from 'react';
import { systemApi } from '../api/system';
import { DeviceContext } from './deviceContext';

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

  if (session === undefined) return <main className="min-h-screen grid place-items-center">Connecting to the home server…</main>;
  if (session.offline) {
    return (
      <main className="min-h-screen grid place-items-center p-6 text-center">
        <div>
          <p className="font-medium">The home server is not answering.</p>
          <p className="text-sm text-text-secondary mt-1">Make sure the family computer is on, awake and running Homeschooling.</p>
          <button onClick={refresh} className="mt-4 rounded bg-accent px-4 py-2 text-white">Try again</button>
        </div>
      </main>
    );
  }
  return <DeviceContext.Provider value={session}>{children}</DeviceContext.Provider>;
}
