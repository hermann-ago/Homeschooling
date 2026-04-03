import { fetchApi } from './client';

export const checklistApi = {
  getToday: (childId) => fetchApi(`/checklist/${childId}/today`),
  getWeek: (childId) => fetchApi(`/checklist/${childId}/week`),
  getMissed: (childId) => fetchApi(`/checklist/${childId}/missed`),
  
  completeSlot: (slotId) => fetchApi(`/checklist/complete/${slotId}`, { method: 'POST' }),
  uncompleteSlot: (slotId) => fetchApi(`/checklist/complete/${slotId}`, { method: 'DELETE' }),
};
