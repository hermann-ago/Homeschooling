import { fetchApi } from './client';

const sessionPath = (session) => `/tutor/sessions/${encodeURIComponent(session)}`;
const post = (data) => ({
  method: 'POST',
  headers: { 'Idempotency-Key': data.operation_id },
  body: JSON.stringify(data),
});

/** Provider-independent lesson activities; the server validates every command. */
export const activitiesApi = {
  definitions: () => fetchApi('/tutor/activity-definitions'),
  state: (session) => fetchApi(`${sessionPath(session)}/activity-state`),
  repeat: (session, data) => fetchApi(`${sessionPath(session)}/repeat`, post(data)),
  invoke: (session, data) => fetchApi(`${sessionPath(session)}/activities`, post(data)),
  access: (session, enabled) => fetchApi(`${sessionPath(session)}/activity-access`, { method: 'POST', body: JSON.stringify({ enabled }) }),
  event: (session, data) => fetchApi(`${sessionPath(session)}/activity-events`, post(data)),
  events: (session, after = 0) => fetchApi(`${sessionPath(session)}/activity-events?after=${encodeURIComponent(after)}`),
};
