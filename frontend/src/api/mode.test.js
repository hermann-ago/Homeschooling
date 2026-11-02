import { afterEach, expect, it, vi } from 'vitest';
import { MODE_KEY, modeHref, switchBrowserMode } from './mode';

afterEach(() => vi.unstubAllGlobals());

it('keeps section anchors after the mode query so Settings shortcuts reach their section', () => {
  expect(modeHref('/settings#narrator-voices')).toBe('/settings?app_mode=live#narrator-voices');
  expect(modeHref('/lesson?learner=1&topic=2#book')).toBe('/lesson?learner=1&topic=2&app_mode=live#book');
  expect(modeHref('/api/voices/Brian/preview')).toBe('/api/voices/Brian/preview?app_mode=live');
});

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
