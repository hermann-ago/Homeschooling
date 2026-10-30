import { fetchApi } from './client';

export const systemApi = {
  checkElevenLabs: () => fetchApi('/ai/elevenlabs/check'),
  checkInworld: () => fetchApi('/ai/inworld/check'),
  session: () => fetchApi('/session'),
  testMode: (enabled) => fetchApi('/test-mode', { method: 'POST', body: JSON.stringify({ enabled }) }),
  resumeTest: (token) => fetchApi('/test-mode', { method: 'POST', body: JSON.stringify({ enabled: true, token }) }),
  aiStatus: () => fetchApi('/ai/status'),
  aiSettings: (data) => fetchApi('/ai/settings', { method: 'PUT', body: JSON.stringify(data) }),
  aiKey: (provider, key) => fetchApi('/ai/key', { method: 'PUT', body: JSON.stringify({ provider, key }) }),
  aiReconcile: (id, charged_usd) => fetchApi(`/ai/requests/${id}/reconcile`, { method: 'PUT', body: JSON.stringify({ charged_usd, verified_provider_bill: true }) }),
  storageStatus: () => fetchApi('/storage/status'),
  setDriveFolder: (path) => fetchApi('/storage/drive-folder', { method: 'POST', body: JSON.stringify({ path }) }),
  backupNow: () => fetchApi('/storage/backup', { method: 'POST' }),
  exportNow: () => fetchApi('/storage/export', { method: 'POST' }),
  narrationUsage: () => fetchApi('/tutor/usage'),
};
