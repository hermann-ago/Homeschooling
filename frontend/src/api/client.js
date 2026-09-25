export const API_BASE_URL = '/api';
const TOKEN_KEY = 'homeschool:device-token:v1';
const MUTATING = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export function getDeviceToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setDeviceToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Pairing lasts for this page only when storage is unavailable.
  }
  window.dispatchEvent(new Event('device:changed'));
}

export async function getAuthHeaders() {
  const token = getDeviceToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function newOperationId() {
  return (crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`).replace(/[^A-Za-z0-9-]/g, '');
}

function publishSync(response) {
  const state = response.headers.get('x-sync-state');
  if (state) {
    window.dispatchEvent(new CustomEvent('sync:state', {
      detail: { state, operationId: response.headers.get('x-operation-id') },
    }));
  }
}

/**
 * Fetch from the home server. Writes carry an Idempotency-Key and are retried
 * with the same key after a network failure, so a lost response never creates
 * a duplicate record.
 */
export async function request(endpoint, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const headers = { ...(await getAuthHeaders()), ...options.headers };
  if (!(options.body instanceof FormData) && options.body !== undefined) {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
  }
  if (MUTATING.has(method) && !headers['Idempotency-Key']) headers['Idempotency-Key'] = newOperationId();
  const attempts = MUTATING.has(method) ? 3 : 2;
  let lastError;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`, { ...options, method, headers });
      publishSync(response);
      if (response.status === 401) window.dispatchEvent(new Event('auth:expired'));
      return response;
    } catch (error) {
      lastError = error;
      await new Promise((resolve) => setTimeout(resolve, 600 * (attempt + 1)));
    }
  }
  throw new Error(`The home server could not be reached (${lastError?.message || 'network error'}).`);
}

export async function fetchApi(endpoint, options = {}) {
  const response = await request(endpoint, options);
  if (!response.ok) {
    let errorMessage = `Request failed (${response.status})`;
    try {
      const errorData = await response.json();
      const detail = errorData.detail;
      errorMessage = typeof detail === 'string' ? detail : detail?.message || errorMessage;
    } catch {
      // Ignored
    }
    const error = new Error(`${endpoint}: ${errorMessage}`);
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}
