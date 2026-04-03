import { fetchApi } from './client';

export const calendarApi = {
  getBlockedDays: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return fetchApi(`/calendar/blocked-days?${query}`);
  },
  createBlockedDay: (data) => fetchApi('/calendar/blocked-days', { method: 'POST', body: JSON.stringify(data) }),
  deleteBlockedDay: (id) => fetchApi(`/calendar/blocked-days/${id}`, { method: 'DELETE' }),
  
  getSchoolYearSettings: () => fetchApi('/calendar/settings/school-year'),
  updateSchoolYearSettings: (data) => fetchApi('/calendar/settings/school-year', { method: 'PUT', body: JSON.stringify(data) }),
};
