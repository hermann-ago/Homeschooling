import { fetchApi } from './client';

export const calendarApi = {
  getCompletedTopics: (childId) => fetchApi(`/calendar/completed-topics/${childId}`),
  getBlockedDays: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return fetchApi(`/calendar/blocked-days?${query}`);
  },
  createBlockedDay: (data) => fetchApi('/calendar/blocked-days', { method: 'POST', body: JSON.stringify(data) }),
  deleteBlockedDay: (id) => fetchApi(`/calendar/blocked-days/${id}`, { method: 'DELETE' }),
  
  getSchoolYearSettings: () => fetchApi('/calendar/settings/school-year'),
  updateSchoolYearSettings: (data) => fetchApi('/calendar/settings/school-year', { method: 'PUT', body: JSON.stringify(data) }),
};
