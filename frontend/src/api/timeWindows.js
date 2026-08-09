import { fetchApi } from './client';

export const timeWindowsApi = {
  getByChildId: (childId) => fetchApi(`/time-windows/by-child/${childId}`),
  create: (data) => fetchApi('/time-windows', { method: 'POST', body: JSON.stringify(data) }),
  delete: (id) => fetchApi(`/time-windows/${id}`, { method: 'DELETE' }),
};
