export const API_BASE_URL = `http://${window.location.hostname}:8000`;

export async function fetchApi(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    let errorMessage = 'An error occurred';
    try {
      const errorData = await response.json();
      errorMessage = errorData.detail || errorMessage;
    } catch (e) {
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
