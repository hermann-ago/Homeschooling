export const MODE_KEY = 'homeschooling.test-mode';
// Fixed for this loaded page: a stale test tab must never start sending live writes.
export const currentMode = typeof window === 'undefined' ? 'live' : window.localStorage.getItem(MODE_KEY) || 'live';

export function modeHref(path) {
  return `${path}${path.includes('?') ? '&' : '?'}app_mode=${encodeURIComponent(currentMode)}`;
}

export function switchBrowserMode(token) {
  if (token) window.localStorage.setItem(MODE_KEY, token);
  else window.localStorage.removeItem(MODE_KEY);
  // A same-URL navigation only changes the hash; it would leave this page's
  // fixed request mode active. Always load a fresh page after the switch.
  window.history.replaceState(null, '', '/settings#test-mode');
  window.location.reload();
}
