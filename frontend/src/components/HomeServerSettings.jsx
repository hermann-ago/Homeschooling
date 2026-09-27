import { useCallback, useEffect, useState } from 'react';
import { systemApi } from '../api/system';
import { useDevice } from './deviceContext';

function clean(error) {
  return (error?.message || String(error)).replace(/^\/[^:]+: /, '');
}

function backupTime(name) {
  const match = /homeschooling-(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z/.exec(name || '');
  if (!match) return name;
  const [, y, mo, d, h, mi, s] = match;
  return new Date(Date.UTC(+y, +mo - 1, +d, +h, +mi, +s)).toLocaleString();
}

/** Controls for the Drive folder, backups and narration usage. */
export default function HomeServerSettings() {
  const device = useDevice();
  const [storage, setStorage] = useState(null);
  const [folderPath, setFolderPath] = useState('');
  const [usage, setUsage] = useState(null);
  const [message, setMessage] = useState('');
  const isHost = Boolean(device?.host);

  const load = useCallback(() => {
    systemApi.storageStatus().then((next) => {
      setStorage(next);
      setFolderPath((current) => current || next.drive_folder || '');
    }).catch(() => {});
    systemApi.narrationUsage().then(setUsage).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

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

  return (
    <section className="bg-surface rounded-2xl border border-border p-6 space-y-6">
      <div>
        <h2 className="text-lg font-bold">Home server</h2>
        <p className="text-sm text-text-secondary">The family's records are kept in a database on the host computer. Books, handwriting, audio and backups are files in the Homeschooling folder that Google Drive for desktop keeps in sync.</p>
      </div>

      <div className="space-y-2">
        <h3 className="font-semibold">Homeschooling Drive folder</h3>
        {storage && (
          <ul className="text-sm text-text-secondary">
            <li>Folder: <span className="font-mono text-xs break-all">{storage.drive_folder || 'not set'}</span></li>
            <li>Status: {storage.drive_folder_available ? 'Available' : 'Not available — is Google Drive for desktop running and signed in?'}</li>
            <li>Database: <span className="font-mono text-xs break-all">{storage.database}</span></li>
          </ul>
        )}
        {isHost ? (
          <form className="flex flex-wrap gap-2 text-sm" onSubmit={(e) => {
            e.preventDefault();
            run(() => systemApi.setDriveFolder(folderPath.trim()), 'Drive folder saved.');
          }}>
            <input value={folderPath} onChange={(e) => setFolderPath(e.target.value)} aria-label="Drive folder path"
              placeholder="G:\My Drive\…\Homeschooling" className="flex-1 min-w-[16rem] rounded-sm border p-2 font-mono text-xs" />
            <button type="submit" className="rounded-sm border px-3 py-2">Use this folder</button>
          </form>
        ) : (
          <p className="text-sm text-text-secondary">The folder can be changed only on the host computer.</p>
        )}
        <p className="text-xs text-text-secondary">For lessons without internet, right-click the Homeschooling folder in File Explorer and choose Offline access → Available offline.</p>
      </div>

      <div className="space-y-2">
        <h3 className="font-semibold">Backups</h3>
        <p className="text-sm text-text-secondary">
          A verified copy of the database goes to the folder's _App Backups every day and when the server stops (the newest 30 are kept).
          {storage?.last_backup ? ` Latest: ${backupTime(storage.last_backup)}.` : ' No backup yet.'}
        </p>
        <div className="flex flex-wrap gap-2 text-sm">
          <button type="button" onClick={() => run(() => systemApi.backupNow(), (r) => `Backup saved: ${r.name}`)} className="rounded-sm border px-3 py-2">Back up now</button>
          <button type="button" onClick={() => run(() => systemApi.exportNow(), (r) => (r.path ? `Excel copy written: ${r.path}` : 'The Drive folder is not available.'))} className="rounded-sm border px-3 py-2">Write the Excel copy</button>
        </div>
        <p className="text-xs text-text-secondary">The Excel copy is for reading only and leaves out answer keys; make changes in the app.</p>
      </div>

      {usage && (
        <div className="space-y-1">
          <h3 className="font-semibold">Narration this month</h3>
          <p className="text-sm text-text-secondary">{usage.characters.toLocaleString()} of {usage.monthly_limit.toLocaleString()} characters (shared by every subject).</p>
        </div>
      )}

      {message && <p className="text-sm" role="status">{message}</p>}
    </section>
  );
}
