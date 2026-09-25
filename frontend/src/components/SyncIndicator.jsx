import { useEffect, useState } from 'react';
import { systemApi } from '../api/system';

const LABELS = {
  saved: { text: 'Saved to Google', tone: 'bg-emerald-500' },
  pending: { text: 'Pending sync', tone: 'bg-amber-500' },
  needs_reconciliation: { text: 'Needs reconciliation', tone: 'bg-red-600' },
};

/** Shows whether recent work is confirmed in Google Sheets. */
export default function SyncIndicator() {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    let active = true;
    const load = () => systemApi.syncStatus().then((next) => active && setStatus(next)).catch(() => active && setStatus(null));
    load();
    const timer = window.setInterval(load, 20000);
    const onChange = () => window.setTimeout(load, 300);
    window.addEventListener('sync:state', onChange);
    window.addEventListener('online', load);
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener('sync:state', onChange);
      window.removeEventListener('online', load);
    };
  }, []);

  if (!status) return <p className="text-xs text-text-secondary">Home server unreachable</p>;
  const label = LABELS[status.state] || LABELS.pending;
  let detail = '';
  if (status.maintenance) detail = 'Paused for spreadsheet maintenance';
  else if (status.auth_required) detail = 'A parent must reconnect Google on the host computer';
  else if (!status.connected) detail = 'Google is not connected yet';
  else if (status.state === 'pending') detail = `${status.pending} change${status.pending === 1 ? '' : 's'} waiting${status.online === false ? ' (offline)' : ''}`;
  return (
    <div className="text-xs" role="status" aria-live="polite">
      <p className="flex items-center gap-2 font-medium"><span className={`inline-block h-2 w-2 rounded-full ${label.tone}`} />{label.text}</p>
      {detail && <p className="text-text-secondary mt-0.5">{detail}</p>}
    </div>
  );
}
