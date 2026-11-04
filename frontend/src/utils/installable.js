/**
 * Lets the browser offer "Install app". Service workers only run on a secure
 * page (this computer's localhost, or the home HTTPS address once a device
 * trusts it), so elsewhere this does nothing and the app works as before.
 */
export function registerInstallable(nav = globalThis.navigator) {
  if (!nav?.serviceWorker || !globalThis.isSecureContext) return false;
  nav.serviceWorker.register('/sw.js').catch(() => {});
  return true;
}
