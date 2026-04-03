import { fetchApi, API_BASE_URL } from './client';

export const subjectsApi = {
  getByChildId: (childId) => fetchApi(`/subjects/by-child/${childId}`),
  getById: (id) => fetchApi(`/subjects/${id}`),
  create: (data) => fetchApi('/subjects/', { method: 'POST', body: JSON.stringify(data) }),
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
    const formData = new FormData();
    formData.append('file', file);
    
    // Use custom fetch since we can't send Content-Type: application/json for FormData
    const response = await fetch(`${API_BASE_URL}/subjects/${subjectId}/upload-pdf`, {
      method: 'POST',
      body: formData,
      // Let browser set Content-Type with boundary automatically
    });

    if (!response.ok) {
        let errorMessage = 'Failed to upload PDF';
        try {
            const errorData = await response.json();
            errorMessage = errorData.detail || errorMessage;
        } catch(e) {}
        throw new Error(errorMessage);
    }
    
    return response.json();
  }
};
