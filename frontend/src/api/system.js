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
  googleStatus: () => fetchApi('/google/status'),
  uploadGoogleClient: (file) => {
    const form = new FormData();
    form.append('file', file);
    return fetchApi('/google/client', { method: 'POST', body: form });
  },
  connectGoogle: () => fetchApi('/google/connect', { method: 'POST' }),
  setupGoogle: () => fetchApi('/google/setup', { method: 'POST' }),
  disconnectGoogle: () => fetchApi('/google/disconnect', { method: 'POST' }),
  syncStatus: () => fetchApi('/sync/status'),
  syncNow: () => fetchApi('/sync/now', { method: 'POST' }),
  unsettled: () => fetchApi('/sync/unsettled'),
  retryOperation: (id) => fetchApi(`/sync/reconcile/${encodeURIComponent(id)}/retry`, { method: 'POST' }),
  discardOperation: (id) => fetchApi(`/sync/reconcile/${encodeURIComponent(id)}/discard`, { method: 'POST' }),
  beginMaintenance: () => fetchApi('/maintenance/begin', { method: 'POST' }),
  endMaintenance: () => fetchApi('/maintenance/end', { method: 'POST' }),
  narrationUsage: () => fetchApi('/tutor/usage'),
};
