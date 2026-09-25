import { useCallback, useEffect, useState } from 'react';
import { systemApi } from '../api/system';

/** Pairing requests waiting for approval. Only the host computer can see or approve them. */
export default function HostApprovals({ compact = false }) {
  const [waiting, setWaiting] = useState(null);
  const [codes, setCodes] = useState({});
  const [message, setMessage] = useState('');

  const load = useCallback(() => {
    systemApi.waitingPairings().then(setWaiting).catch(() => setWaiting(null));
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 3000);
    return () => window.clearInterval(timer);
  }, [load]);

  if (waiting === null) return null;

  const approve = async (item, role) => {
    try {
      const result = await systemApi.approvePairing(item.id, codes[item.id] || '', role);
      setMessage(`${result.name} is paired as ${result.role}.`);
      load();
    } catch (error) {
      setMessage(error.message.replace(/^\/[^:]+: /, ''));
    }
  };

  return (
    <section className={compact ? 'mt-6 border-t pt-4' : 'rounded-xl border border-border bg-surface p-4'}>
      <h2 className="font-semibold">Devices waiting to pair</h2>
      <p className="text-sm text-text-secondary">Type the code shown on the device, then approve it. This list appears only on the host computer.</p>
      {waiting.length === 0 && <p className="mt-2 text-sm text-text-secondary">No devices are waiting.</p>}
      <ul className="mt-3 space-y-3">
        {waiting.map((item) => (
          <li key={item.id} className="rounded-lg border p-3 text-sm">
            <p><span className="font-medium">{item.name}</span> asks to be a <span className="font-medium">{item.role}</span> device.</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <input aria-label={`Code for ${item.name}`} inputMode="numeric" maxLength={6} placeholder="6-digit code"
                value={codes[item.id] || ''} onChange={(e) => setCodes({ ...codes, [item.id]: e.target.value.replace(/\D/g, '') })}
                className="w-32 rounded border p-2" />
              <button type="button" onClick={() => approve(item, item.role)} className="rounded bg-accent px-3 py-2 text-white">Approve as {item.role}</button>
              {item.role === 'parent' && (
                <button type="button" onClick={() => approve(item, 'learner')} className="rounded border px-3 py-2">Approve as learner</button>
              )}
              <button type="button" onClick={() => systemApi.denyPairing(item.id).then(load)} className="rounded px-3 py-2 text-red-700">Deny</button>
            </div>
          </li>
        ))}
      </ul>
      {message && <p className="mt-2 text-sm">{message}</p>}
    </section>
  );
}
