import { fetchApi } from './client';

export const systemApi = {
  session: () => fetchApi('/session'),
  requestPairing: (deviceName, role) => fetchApi('/pairing/request', {
    method: 'POST', body: JSON.stringify({ device_name: deviceName, role }),
  }),
  pollPairing: (requestId, pollSecret) => fetchApi('/pairing/poll', {
    method: 'POST', body: JSON.stringify({ request_id: requestId, poll_secret: pollSecret }),
  }),
  waitingPairings: () => fetchApi('/pairing/waiting'),
  approvePairing: (requestId, code, role) => fetchApi('/pairing/approve', {
    method: 'POST', body: JSON.stringify({ request_id: requestId, code, role }),
  }),
  denyPairing: (requestId) => fetchApi(`/pairing/deny/${requestId}`, { method: 'POST' }),
  devices: () => fetchApi('/devices'),
  revokeDevice: (id) => fetchApi(`/devices/${id}`, { method: 'DELETE' }),
  storageStatus: () => fetchApi('/storage/status'),
  setDriveFolder: (path) => fetchApi('/storage/drive-folder', { method: 'POST', body: JSON.stringify({ path }) }),
  backupNow: () => fetchApi('/storage/backup', { method: 'POST' }),
  exportNow: () => fetchApi('/storage/export', { method: 'POST' }),
  narrationUsage: () => fetchApi('/tutor/usage'),
};
