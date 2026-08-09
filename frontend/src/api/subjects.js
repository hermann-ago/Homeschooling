import { upload } from '@vercel/blob/client';
import { fetchApi, getAuthHeaders } from './client';
import { inspectPdf } from '../utils/pdf';

export const subjectsApi = {
  getByChildId: (childId) => fetchApi(`/subjects/by-child/${childId}`),
  getById: (id) => fetchApi(`/subjects/${id}`),
  create: (data) => fetchApi('/subjects', { method: 'POST', body: JSON.stringify(data) }),
  update: (id, data) => fetchApi(`/subjects/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id) => fetchApi(`/subjects/${id}`, { method: 'DELETE' }),

  getTopics: (subjectId) => fetchApi(`/subjects/${subjectId}/topics`),
  updateTopic: (subjectId, topicId, data) => fetchApi(`/subjects/${subjectId}/topics/${topicId}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteTopic: (subjectId, topicId) => fetchApi(`/subjects/${subjectId}/topics/${topicId}`, { method: 'DELETE' }),
  deleteSubject: (subjectId) => fetchApi(`/subjects/${subjectId}`, { method: 'DELETE' }),
  setMainBook: (subjectId, pdfFilename) => fetchApi(`/subjects/${subjectId}/books/set-main-book?pdf_filename=${encodeURIComponent(pdfFilename)}`, { method: 'PUT' }),
  deleteBook: (subjectId, pdfFilename) => fetchApi(`/subjects/${subjectId}/books?pdf_filename=${encodeURIComponent(pdfFilename)}`, { method: 'DELETE' }),
  setBookOffset: (subjectId, pdfFilename, offset) => fetchApi(`/subjects/${subjectId}/books/set-book-offset?pdf_filename=${encodeURIComponent(pdfFilename)}&offset=${offset}`, { method: 'PUT' }),
  toggleTopicComplete: (subjectId, topicId) => fetchApi(`/subjects/${subjectId}/topics/${topicId}/toggle-complete`, { method: 'POST' }),
  generateChapters: (subjectId, count) => fetchApi(`/subjects/${subjectId}/generate-chapters?count=${count}`, { method: 'POST' }),
  completePrevious: (subjectId, topicId) => fetchApi(`/subjects/${subjectId}/topics/${topicId}/complete-previous`, { method: 'POST' }),

  uploadPdf: async (subjectId, file) => {
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      throw new Error('Please select a PDF file.');
    }
    if (file.size > 262144000) throw new Error('PDFs are limited to 250 MiB.');
    const { pageCount, tocText } = await inspectPdf(file);
    if (!tocText) throw new Error('No selectable text was found in the first 15 pages. Scanned PDFs need OCR first.');
    const headers = await getAuthHeaders();
    const blob = await upload(`documents/${crypto.randomUUID()}-${file.name.replace(/[^a-zA-Z0-9._-]/g, '_')}`, file, {
      access: 'private',
      handleUploadUrl: '/api/blob/upload',
      clientPayload: JSON.stringify({ authorization: headers.Authorization }),
      multipart: file.size > 8 * 1024 * 1024,
    });
    return fetchApi(`/subjects/${subjectId}/documents`, {
      method: 'POST',
      body: JSON.stringify({
        blob_path: new URL(blob.url).pathname.slice(1),
        original_filename: file.name,
        size_bytes: file.size,
        page_count: pageCount,
        toc_text: tocText,
      }),
    });
  }
};
