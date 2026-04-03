import { fetchApi } from './client';

export const progressApi = {
  getChildProgress: (childId) => fetchApi(`/progress/${childId}`),
  getFamilyOverview: () => fetchApi('/progress/family/overview'),
};
