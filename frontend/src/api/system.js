import { fetchApi } from './client';

export const systemApi = {
  session: () => fetchApi('/session'),
  storageStatus: () => fetchApi('/storage/status'),
  setDriveFolder: (path) => fetchApi('/storage/drive-folder', { method: 'POST', body: JSON.stringify({ path }) }),
  backupNow: () => fetchApi('/storage/backup', { method: 'POST' }),
  exportNow: () => fetchApi('/storage/export', { method: 'POST' }),
  narrationUsage: () => fetchApi('/tutor/usage'),
};
