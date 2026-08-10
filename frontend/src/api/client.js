import { supabase } from '../lib/supabase';

export const API_BASE_URL = '/api';

export async function getAuthHeaders() {
  const { data } = supabase ? await supabase.auth.getSession() : { data: {} };
  return data.session ? { Authorization: `Bearer ${data.session.access_token}` } : {};
}

export async function fetchApi(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  const authHeaders = await getAuthHeaders();
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders,
      ...options.headers,
    },
  });

  if (!response.ok) {
    if (response.status === 401) {
      window.dispatchEvent(new Event('auth:expired'));
    }
    let errorMessage = `Request failed (${response.status})`;
    try {
      const errorData = await response.json();
      errorMessage = errorData.detail || errorMessage;
    } catch {
      // Ignored
    }
    throw new Error(errorMessage);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return null;
  }
  
  return response.json();
}
