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

const pageRanges = new Map();

/**
 * Only book PDF pages `first`–`last` (page 1 of the result is book page `first`).
 * The viewer and the read-along share one download per range; pass a copy
 * (`data.slice()`) to pdf.js, which takes ownership of what it is given.
 */
export function getDocumentPages(documentId, first, last) {
  const key = `${documentId}:${first}:${last}`;
  if (!pageRanges.has(key)) {
    const loading = request(`/documents/${documentId}/pages?first=${first}&last=${last}`).then(async (response) => {
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || 'Could not load the lesson pages');
      }
      const data = await response.arrayBuffer();
      if (new TextDecoder().decode(data.slice(0, 4)) !== '%PDF') throw new Error('The home server returned something that is not a PDF.');
      return new Uint8Array(data);
    });
    loading.catch(() => pageRanges.delete(key));
    pageRanges.set(key, loading);
    // A few lessons' pages stay at hand; older ranges are dropped.
    if (pageRanges.size > 6) pageRanges.delete(pageRanges.keys().next().value);
  }
  return pageRanges.get(key);
}

export async function getDocument(documentId) {
  return fetchApi(`/documents/${documentId}`);
}

export const driveBooks = () => fetchApi('/documents/drive/books');
