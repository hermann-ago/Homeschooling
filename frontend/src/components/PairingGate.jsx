import { useCallback, useEffect, useState } from 'react';
import { getDeviceToken, setDeviceToken } from '../api/client';
import { systemApi } from '../api/system';
import HostApprovals from './HostApprovals';
import { DeviceContext } from './deviceContext';


const PENDING_KEY = 'homeschool:pairing:v1';

function readPending() {
  try {
    return JSON.parse(sessionStorage.getItem(PENDING_KEY));
  } catch {
    return null;
  }
}

function writePending(value) {
  try {
    if (value) sessionStorage.setItem(PENDING_KEY, JSON.stringify(value));
    else sessionStorage.removeItem(PENDING_KEY);
  } catch {
    // The request still works while this page stays open.
  }
}

/**
 * Household devices pair with the home server using a short code that a parent
 * approves on the host computer. The device then holds a Homeschooling
 * credential (never a Google credential).
 */
export default function PairingGate({ children }) {
  const [session, setSession] = useState(undefined);
  const [pending, setPending] = useState(readPending);
  const [name, setName] = useState('');
  const [role, setRole] = useState('learner');
  const [error, setError] = useState('');

  const refresh = useCallback(() => {
    if (!getDeviceToken()) {
      setSession(null);
      return;
    }
    systemApi.session().then(setSession).catch((failure) => {
      if (failure.status === 401) {
        setDeviceToken(null);
        setSession(null);
      } else {
        setSession({ offline: true, error: failure.message });
      }
    });
  }, []);

  useEffect(() => {
    refresh();
    const expire = () => refresh();
    window.addEventListener('auth:expired', expire);
    window.addEventListener('device:changed', expire);
    return () => {
      window.removeEventListener('auth:expired', expire);
      window.removeEventListener('device:changed', expire);
    };
  }, [refresh]);

  useEffect(() => {
    if (!pending) return undefined;
    const timer = window.setInterval(async () => {
      try {
        const result = await systemApi.pollPairing(pending.request_id, pending.poll_secret);
        if (result.status === 'approved') {
          writePending(null);
          setPending(null);
          setDeviceToken(result.token);
        } else if (result.status !== 'waiting') {
          writePending(null);
          setPending(null);
          setError(result.status === 'denied' ? 'The pairing request was denied.' : 'The code expired. Ask again.');
        }
      } catch {
        // Keep polling; the home server may be restarting.
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [pending]);

  if (session === undefined) return <main className="min-h-screen grid place-items-center">Connecting to the home server…</main>;
  if (session?.offline) {
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
  if (session) {
    return <DeviceContext.Provider value={{ ...session, forget: () => setDeviceToken(null) }}>{children}</DeviceContext.Provider>;
  }

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    try {
      const request = await systemApi.requestPairing(name || navigator.userAgent.slice(0, 40), role);
      writePending(request);
      setPending(request);
    } catch (failure) {
      setError(failure.message.replace(/^\/[^:]+: /, ''));
    }
  };

  return (
    <main className="min-h-screen bg-background grid place-items-center p-6">
      <div className="w-full max-w-md space-y-4">
        {pending ? (
          <section className="rounded-xl bg-surface border border-border p-6 shadow-soft text-center">
            <h1 className="text-xl font-bold">Pairing code</h1>
            <p className="mt-4 font-mono text-4xl tracking-widest" data-testid="pairing-code">{pending.code}</p>
            <p className="mt-4 text-sm text-text-secondary">On the family computer, open Homeschooling and approve this code. This page continues on its own.</p>
            <button type="button" onClick={() => { writePending(null); setPending(null); }} className="mt-4 text-sm underline">Cancel</button>
          </section>
        ) : (
          <form onSubmit={submit} className="rounded-xl bg-surface border border-border p-6 shadow-soft space-y-4">
            <div>
              <h1 className="text-2xl font-bold">Homeschooler</h1>
              <p className="text-sm text-text-secondary mt-1">Pair this device with the family's home server.</p>
            </div>
            <label className="block text-sm">Device name<input value={name} onChange={(e) => setName(e.target.value)} placeholder="Kitchen tablet" maxLength={60} className="mt-1 w-full rounded border p-2" /></label>
            <fieldset className="text-sm">
              <legend>Who uses this device?</legend>
              <label className="mr-4"><input type="radio" name="role" value="learner" checked={role === 'learner'} onChange={() => setRole('learner')} /> A learner</label>
              <label><input type="radio" name="role" value="parent" checked={role === 'parent'} onChange={() => setRole('parent')} /> A parent</label>
            </fieldset>
            {error && <p className="text-sm text-red-700">{error}</p>}
            <button className="w-full rounded bg-accent text-white py-2">Get a pairing code</button>
          </form>
        )}
        <HostApprovals />
      </div>
    </main>
  );
}
