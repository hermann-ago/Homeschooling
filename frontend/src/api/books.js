import { fetchApi } from './client';

export const booksApi = {
  navigation: subject => fetchApi(`/subjects/${subject}/navigation`),
  extractNavigation: (subject, document) => fetchApi(`/subjects/${subject}/navigation/${document}`, {method:'POST'}),
  saveNavigation: (subject, document, chapters, expected_revision) => fetchApi(`/subjects/${subject}/navigation/${document}`, {method:'PUT', body:JSON.stringify({chapters,expected_revision})}),
  sourcePages: topic => fetchApi(`/topics/${topic}/source-pages`),
  saveSourcePages: (topic, sources, expected_revision) => fetchApi(`/topics/${topic}/source-pages`, {method:'PUT',body:JSON.stringify({sources,expected_revision})}),
  voices: (provider) => fetchApi(provider === 'elevenlabs' ? '/ai/elevenlabs/voices' : provider === 'inworld' ? '/ai/inworld/voices' : '/ai/voices'),
  narrator: topic => fetchApi(`/topics/${topic}/narrator`),
  saveNarrator: (topic, voice) => fetchApi(`/topics/${topic}/narrator`, {method:'PUT',body:JSON.stringify({voice})}),
  sourceNotes: subject => fetchApi(`/subjects/${subject}/source-notes`),
  saveSourceNote: (subject,data) => fetchApi(`/subjects/${subject}/source-notes`,{method:'PUT',body:JSON.stringify(data)}),
  materialSkills: () => fetchApi('/material-skills'),
  saveMaterialSkill: (key, content, expected_version) => fetchApi(`/material-skills/${key}`, { method:'PUT', body:JSON.stringify({content,expected_version}) }),
  incoming: () => fetchApi('/books/incoming'),
  resources: (subject) => fetchApi(`/subjects/${subject}/resources`),
  collection: (subject) => fetchApi(`/subjects/${subject}/book-collection`),
  saveCollection: (subject, data) => fetchApi(`/subjects/${subject}/book-collection`, { method: 'PUT', body: JSON.stringify(data) }),
  import: (subject, books) => fetchApi(`/subjects/${subject}/book-imports`, { method: 'POST', body: JSON.stringify({ books }) }),
  stage: (file) => {
    if (!file.name.toLowerCase().endsWith('.pdf') || file.size > 262144000) throw new Error('Choose a PDF smaller than 250 MB.');
    const form = new FormData();
    form.append('file', file);
    return fetchApi('/books/stage', { method: 'POST', body: form });
  },
  prepare: (book, role, companion_id, answer_for_id) => fetchApi(`/subject-books/${book}/prepare`, { method: 'POST', body: JSON.stringify({ role, companion_id, answer_for_id }) }),
  retry: (job) => fetchApi(`/book-imports/${job}/retry`, { method: 'POST' }),
  practice: (exercise) => fetchApi(`/exercises/${exercise}/practice`, { method: 'POST' }),
  progress: (child) => fetchApi(`/workbook-progress/${child}`),
};

export const collectionPayload = (collection, books = collection.books) => ({
  name: collection.name, expected_revision: collection.revision,
  books: books.map((b, position) => ({ key: b.key, ...(b.document_id ? { document_id: b.document_id } : { path: b.path }),
    role: b.role, edition: b.edition || '', position, is_main: Boolean(b.is_main),
    companion_key: b.companion_key || null, answer_for_key: b.answer_for_key || null,
    answer_for_keys:b.answer_for_keys || (b.answer_for_key ? [b.answer_for_key] : []) })),
});

export const bookRoles = [
  ['textbook', 'Textbook'], ['combined', 'Textbook + workbook'], ['workbook', 'Workbook'], ['test', 'Test booklet'], ['answer_key', 'Answer key'], ['reference', 'Reference'],
];
