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

export async function getDocumentData(blobPath, expectedSize) {
  const headers = await getAuthHeaders();
  const response = await fetch(`/api/blob/content?blobPath=${encodeURIComponent(blobPath)}`, { headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || body.detail || 'Could not load document');
  }
  const data = await response.arrayBuffer();
  const signature = new TextDecoder().decode(data.slice(0, 4));
  if (signature !== '%PDF') {
    throw new Error(`Hosted PDF response is invalid (${response.headers.get('content-type') || 'unknown type'}, ${data.byteLength} bytes).`);
  }
  if (expectedSize && data.byteLength !== expectedSize) {
    throw new Error(`Hosted PDF response was incomplete (${data.byteLength} of ${expectedSize} bytes).`);
  }
  return new Uint8Array(data);
}

export async function getDocument(documentId) {
  return fetchApi(`/documents/${documentId}`);
}
