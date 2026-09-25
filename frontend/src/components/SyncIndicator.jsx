import { useEffect, useState } from 'react';
import { systemApi } from '../api/system';

/** Shows whether the home server is reachable and whether its Drive folder (books, audio) is available. */
export default function SyncIndicator() {
  const [status, setStatus] = useState(undefined);

  useEffect(() => {
    let active = true;
    const load = () => systemApi.storageStatus()
      .then((next) => active && setStatus(next))
      .catch(() => active && setStatus(null));
    load();
    const timer = window.setInterval(load, 30000);
    window.addEventListener('online', load);
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener('online', load);
    };
  }, []);

  if (status === undefined) return null;
  if (!status) {
    return (
      <div className="text-xs" role="status" aria-live="polite">
        <p className="flex items-center gap-2 font-medium"><span className="inline-block h-2 w-2 rounded-full bg-red-600" />Home server unreachable</p>
        <p className="text-text-secondary mt-0.5">Changes cannot be saved until it is back</p>
      </div>
    );
  }
  const folderOk = status.drive_folder_available;
  return (
    <div className="text-xs" role="status" aria-live="polite">
      <p className="flex items-center gap-2 font-medium">
        <span className={`inline-block h-2 w-2 rounded-full ${folderOk ? 'bg-emerald-500' : 'bg-amber-500'}`} />
        Saved on the home server
      </p>
      {!folderOk && <p className="text-text-secondary mt-0.5">Drive folder unavailable: books and audio may not open</p>}
    </div>
  );
}
