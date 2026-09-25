import { request } from './client';


export class AnnotationConflictError extends Error {
  constructor(message, current) {
    super(message);
    this.name = 'AnnotationConflictError';
    this.current = current;
  }
}


async function annotationRequest(path, options = {}) {
  const response = await request(`/annotations${path}`, options);

  const body = await response.json().catch(() => ({}));
  if (response.status === 409 && body.detail?.current) {
    throw new AnnotationConflictError(
      body.detail.message || 'Annotations changed on another device',
      body.detail.current,
    );
  }
  if (!response.ok) {
    const detail = typeof body.detail === 'string' ? body.detail : 'Could not save annotations';
    throw new Error(detail);
  }
  return body;
}


function pagePath(childId, documentId, pageNumber) {
  return `/children/${childId}/documents/${documentId}/pages/${pageNumber}`;
}


export function getPageAnnotations(childId, documentId, pageNumber) {
  return annotationRequest(pagePath(childId, documentId, pageNumber));
}


export function savePageAnnotations(childId, documentId, pageNumber, baseRevision, strokes) {
  return annotationRequest(pagePath(childId, documentId, pageNumber), {
    method: 'PUT',
    body: JSON.stringify({ base_revision: baseRevision, strokes }),
  });
}
