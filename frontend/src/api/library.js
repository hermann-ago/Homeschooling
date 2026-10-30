import { fetchApi } from './client';

export const libraryApi = {
  teachingSkill: id => fetchApi(`/library/books/${id}/teaching-skill`),
  skillHistory: id => fetchApi(`/library/books/${id}/teaching-skill/history`),
  saveSkill: (id, content, expected_version) => fetchApi(`/library/books/${id}/teaching-skill`, { method: 'PUT', body: JSON.stringify({ content, expected_version }) }),
  exportSkill: id => fetchApi(`/library/books/${id}/teaching-skill`),
  list: child => fetchApi(`/library/books?child_id=${child}`),
  book: (id, child) => fetchApi(`/library/books/${id}?child_id=${child}`),
  add: data => fetchApi('/library/books', { method: 'POST', body: JSON.stringify(data) }),
  enroll: (id, child_id) => fetchApi(`/library/books/${id}/readings`, { method: 'POST', body: JSON.stringify({ child_id }) }),
  pause: (id, child) => fetchApi(`/library/books/${id}/readings/${child}`, { method: 'DELETE' }),
  prepare: (id, child_id) => fetchApi(`/library/books/${id}/prepare`, { method: 'POST', body: JSON.stringify({ child_id }) }),
  upload: async (id, file, revision) => {
    if (!file.name.toLowerCase().endsWith('.pdf') || file.size > 262144000) throw new Error('Choose a PDF book smaller than 250 MB.');
    const form = new FormData();
    form.append('file', file);
    form.append('expected_revision', String(revision));
    // Freeze the multipart boundary once. Network retries with the same
    // operation key must send the exact bytes the server already received.
    const encoded = new Response(form);
    const body = await encoded.blob();
    return fetchApi(`/library/books/${id}/file`, { method: 'POST', body, headers: { 'Content-Type': encoded.headers.get('Content-Type') } });
  },
};
