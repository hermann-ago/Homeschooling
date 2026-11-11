import { currentMode } from '../../api/mode';

export const operationId = () => globalThis.crypto?.randomUUID?.() || `activity-${Date.now()}-${Math.random().toString(16).slice(2)}`;
export const storageKey = (session, suffix) => `homeschooling.activities.${currentMode}.${session}.${suffix}`;

export function readSaved(key, fallback = null) {
  try { return JSON.parse(window.localStorage.getItem(key)) ?? fallback; }
  catch { return fallback; }
}

export function writeSaved(key, value) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    // Server records remain canonical if this browser disallows draft storage.
    return false;
  }
}

export function operationCommitted(state, operation) {
  return Boolean(operation && (state?.events || []).some((event) => event.operation_id === operation.operation_id));
}
