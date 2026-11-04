import { afterEach, describe, expect, it, vi } from 'vitest';
import { registerInstallable } from './installable';

describe('registerInstallable', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('registers the service worker on a secure page', () => {
    vi.stubGlobal('isSecureContext', true);
    const register = vi.fn(() => Promise.resolve());
    expect(registerInstallable({ serviceWorker: { register } })).toBe(true);
    expect(register).toHaveBeenCalledWith('/sw.js');
  });

  it('does nothing on a plain home-network address', () => {
    vi.stubGlobal('isSecureContext', false);
    const register = vi.fn();
    expect(registerInstallable({ serviceWorker: { register } })).toBe(false);
    expect(register).not.toHaveBeenCalled();
  });
});
