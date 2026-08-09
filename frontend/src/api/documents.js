import { fetchApi, getAuthHeaders } from './client';

export async function getDocumentUrl(blobPath) {
  const headers = await getAuthHeaders();
  const response = await fetch('/api/blob/read', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify({ blobPath }),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || body.detail || 'Could not open document');
  return body.url;
}

export async function getDocument(documentId) {
  return fetchApi(`/documents/${documentId}`);
}
