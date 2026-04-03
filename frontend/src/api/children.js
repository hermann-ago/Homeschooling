import { fetchApi } from './client';

export const childrenApi = {
  getAll: () => fetchApi('/children/'),
  getById: (id) => fetchApi(`/children/${id}`),
  create: (data) => fetchApi('/children/', { method: 'POST', body: JSON.stringify(data) }),
  update: (id, data) => fetchApi(`/children/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id) => fetchApi(`/children/${id}`, { method: 'DELETE' }),
};
