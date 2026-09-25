import { fetchApi, request } from './client';

/** PDF bytes proxied from Google Drive by the home server (cached there). */
export async function getDocumentData(documentId, expectedSize) {
  const response = await request(`/documents/${documentId}/content`);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || 'Could not load document');
  }
  const data = await response.arrayBuffer();
  const signature = new TextDecoder().decode(data.slice(0, 4));
  if (signature !== '%PDF') throw new Error('The home server returned something that is not a PDF.');
  if (expectedSize && data.byteLength !== expectedSize) {
    throw new Error(`The PDF was incomplete (${data.byteLength} of ${expectedSize} bytes).`);
  }
  return new Uint8Array(data);
}

export async function getDocument(documentId) {
  return fetchApi(`/documents/${documentId}`);
}

export const driveBooks = () => fetchApi('/documents/drive/books');
