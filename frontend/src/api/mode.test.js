import { afterEach, expect, it, vi } from 'vitest';
import { MODE_KEY, switchBrowserMode } from './mode';

afterEach(() => vi.unstubAllGlobals());

it('reloads even when already on the test-mode settings URL', () => {
  const values = new Map();
  const browser = {
    localStorage: { setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) },
    history: { replaceState: vi.fn() },
    location: { href: 'http://localhost:8000/settings#test-mode', reload: vi.fn() },
  };
  vi.stubGlobal('window', browser);
  switchBrowserMode('practice-session');
  expect(values.get(MODE_KEY)).toBe('practice-session');
  expect(browser.location.reload).toHaveBeenCalledTimes(1);
  switchBrowserMode(null);
  expect(values.has(MODE_KEY)).toBe(false);
  expect(browser.location.reload).toHaveBeenCalledTimes(2);
});
