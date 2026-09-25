import { useCallback, useEffect, useState } from 'react';
import { systemApi } from '../api/system';
import HostApprovals from './HostApprovals';
import { useDevice } from './deviceContext';

function clean(error) {
  return (error?.message || String(error)).replace(/^\/[^:]+: /, '');
}

/** Parent controls for Google, synchronisation, spreadsheet maintenance and devices. */
export default function HomeServerSettings() {
  const device = useDevice();
  const [google, setGoogle] = useState(null);
  const [sync, setSync] = useState(null);
  const [unsettled, setUnsettled] = useState([]);
  const [devices, setDevices] = useState([]);
  const [usage, setUsage] = useState(null);
  const [message, setMessage] = useState('');
  const [problems, setProblems] = useState([]);
  const isParent = device?.device?.role === 'parent';
  const isHost = Boolean(device?.host);

  const load = useCallback(() => {
    systemApi.googleStatus().then(setGoogle).catch(() => {});
    systemApi.syncStatus().then(setSync).catch(() => {});
    if (isParent) {
      systemApi.unsettled().then(setUnsettled).catch(() => {});
      systemApi.devices().then(setDevices).catch(() => {});
      systemApi.narrationUsage().then(setUsage).catch(() => {});
    }
  }, [isParent]);

  useEffect(() => { load(); }, [load]);

  if (!isParent) return null;

  const run = async (action, success) => {
    setMessage('');
    try {
      const result = await action();
      if (success) setMessage(typeof success === 'function' ? success(result) : success);
      load();
      return result;
    } catch (error) {
      setMessage(clean(error));
      return null;
    }
  };

  const connect = async () => {
    const result = await run(() => systemApi.connectGoogle());
    if (result?.authorization_url) window.location.assign(result.authorization_url);
  };

  const endMaintenance = async () => {
    const result = await run(() => systemApi.endMaintenance());
    if (result && !result.resumed) setProblems(result.problems || []);
    else if (result) {
      setProblems([]);
      setMessage(`Changes resumed. ${result.edited_rows || 0} edited rows were recorded.`);
    }
  };

  return (
    <section className="bg-surface rounded-2xl border border-border p-6 space-y-6">
      <div>
        <h2 className="text-lg font-bold">Home server</h2>
        <p className="text-sm text-text-secondary">Google Drive holds books and files; the Homeschooling Database workbook is the family's record.</p>
      </div>

      <div className="space-y-2">
        <h3 className="font-semibold">Google connection</h3>
        {google && (
          <ul className="text-sm text-text-secondary">
            <li>Status: {google.connected ? (google.authorization_required ? 'Reconnect needed' : 'Connected') : 'Not connected'}</li>
            <li>Homeschooling folder: <a className="underline" target="_blank" rel="noreferrer" href={`https://drive.google.com/drive/folders/${google.root_folder_id}`}>open in Drive</a></li>
            {google.spreadsheet_id && <li>Database: <a className="underline" target="_blank" rel="noreferrer" href={`https://docs.google.com/spreadsheets/d/${google.spreadsheet_id}`}>Homeschooling Database</a></li>}
          </ul>
        )}
        {isHost ? (
          <div className="flex flex-wrap gap-2 text-sm">
            <label className="rounded border px-3 py-2 cursor-pointer">Add Desktop OAuth client file
              <input type="file" accept="application/json" className="hidden"
                onChange={(e) => e.target.files[0] && run(() => systemApi.uploadGoogleClient(e.target.files[0]), 'OAuth client saved on this computer.')} />
            </label>
            <button type="button" onClick={connect} disabled={!google?.client_configured} className="rounded bg-accent text-white px-3 py-2 disabled:opacity-50">
              {google?.connected ? 'Reconnect Google' : 'Connect Google'}
            </button>
            {google?.connected && (
              <>
                <button type="button" onClick={() => run(() => systemApi.setupGoogle(), 'Folders and workbook are ready.')} className="rounded border px-3 py-2">Check folders and workbook</button>
                <button type="button" onClick={() => window.confirm('Disconnect Google on this computer? Work stays queued until you reconnect.') && run(() => systemApi.disconnectGoogle(), 'Disconnected.')} className="rounded px-3 py-2 text-red-700">Disconnect</button>
              </>
            )}
          </div>
        ) : (
          <p className="text-sm text-text-secondary">Google authorization happens only on the host computer. Other devices never receive Google credentials.</p>
        )}
        {isHost && (
          <p className="text-xs text-text-secondary">
            Google asks for two permissions: read-only Drive access, used only to find existing books inside the Homeschooling folder (Google's permission itself is wider — the app refuses files outside that folder), and access to files this app creates (the workbook, uploaded books, handwriting, audio, backups).
          </p>
        )}
      </div>

      <div className="space-y-2">
        <h3 className="font-semibold">Sync</h3>
        {sync && (
          <p className="text-sm">
            {sync.state === 'saved' && 'Everything is saved to Google.'}
            {sync.state === 'pending' && `${sync.pending} change(s) are safe on this server and waiting for Google.`}
            {sync.state === 'needs_reconciliation' && `${sync.needs_reconciliation} change(s) conflict with the spreadsheet.`}
            {sync.last_error && <span className="block text-xs text-text-secondary">Last problem: {sync.last_error}</span>}
          </p>
        )}
        <button type="button" onClick={() => run(() => systemApi.syncNow(), 'Sync attempted.')} className="rounded border px-3 py-2 text-sm">Sync now</button>
        {unsettled.filter((op) => op.status === 'needs_reconciliation').map((op) => (
          <div key={op.id} className="rounded border border-red-200 bg-red-50 p-3 text-sm">
            <p className="font-medium">{op.summary}</p>
            <p className="text-xs">{op.last_error}</p>
            <p className="text-xs text-text-secondary">Changes: {op.changes.map((c) => `${c.action} ${c.table} ${c.id}`).join(', ')}</p>
            <div className="mt-2 flex gap-2">
              <button type="button" onClick={() => run(() => systemApi.retryOperation(op.id), 'Retried against the current spreadsheet.')} className="rounded border bg-white px-3 py-1">Reload and retry</button>
              <button type="button" onClick={() => window.confirm('Set this change aside? It stays in the local archive for review.') && run(() => systemApi.discardOperation(op.id), 'Change set aside (kept in the archive).')} className="rounded px-3 py-1 text-red-700">Set aside</button>
            </div>
          </div>
        ))}
      </div>

      <div className="space-y-2">
        <h3 className="font-semibold">Edit the spreadsheet by hand</h3>
        <p className="text-sm text-text-secondary">Turn on maintenance mode before editing cells directly. The app pauses changes, then checks the whole workbook and reloads it before resuming.</p>
        {sync?.maintenance ? (
          <button type="button" onClick={endMaintenance} className="rounded bg-accent text-white px-3 py-2 text-sm">I finished editing — check and resume</button>
        ) : (
          <button type="button" onClick={() => run(() => systemApi.beginMaintenance(), 'Changes are paused. Edit the workbook, then return here.')} className="rounded border px-3 py-2 text-sm">Start maintenance mode</button>
        )}
        {problems.length > 0 && (
          <ul className="text-xs text-red-700 list-disc pl-5">{problems.map((p) => <li key={p}>{p}</li>)}</ul>
        )}
      </div>

      {usage && (
        <div className="space-y-1">
          <h3 className="font-semibold">Narration this month</h3>
          <p className="text-sm text-text-secondary">{usage.characters.toLocaleString()} of {usage.monthly_limit.toLocaleString()} characters (shared by every subject).</p>
        </div>
      )}

      <div className="space-y-2">
        <h3 className="font-semibold">Paired devices</h3>
        <ul className="text-sm divide-y">
          {devices.map((d) => (
            <li key={d.id} className="py-2 flex items-center justify-between">
              <span>{d.name} <span className="text-text-secondary">· {d.role}</span></span>
              {d.id !== device?.device?.id && (
                <button type="button" onClick={() => window.confirm(`Remove ${d.name}?`) && run(() => systemApi.revokeDevice(d.id), 'Device removed.')} className="text-red-700 text-xs">Remove</button>
              )}
            </li>
          ))}
        </ul>
        <HostApprovals compact />
      </div>

      {message && <p className="text-sm" role="status">{message}</p>}
    </section>
  );
}
