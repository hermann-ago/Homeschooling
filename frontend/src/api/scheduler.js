import { fetchApi } from './client';

export const schedulerApi = {
  getSchedule: (childId, params = {}) => {
    const query = new URLSearchParams(params).toString();
    return fetchApi(`/schedule/${childId}?${query}`);
  },
  recalculate: (childId) => fetchApi(`/schedule/recalculate/${childId}`, { method: 'POST' }),
};
