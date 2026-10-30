/* @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { DeviceContext } from './deviceContext';
import TestModeSettings from './TestModeSettings';

const api = vi.hoisted(() => ({ testMode: vi.fn(), resumeTest: vi.fn(), switchBrowserMode: vi.fn() }));
vi.mock('../api/system', () => ({ systemApi: api }));
vi.mock('../api/mode', () => ({ currentMode: 'live', switchBrowserMode: api.switchBrowserMode }));
beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

it('opens a bookmarked rehearsal only after the explicit button', async () => {
  const token = 'a'.repeat(32);
  window.history.replaceState(null, '', '/settings?resume_test=' + token);
  api.resumeTest.mockResolvedValue({ token });
  render(<DeviceContext.Provider value={{ test_mode: false }}><TestModeSettings /></DeviceContext.Provider>);
  expect(api.resumeTest).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Continue saved test session' }));
  await waitFor(() => expect(api.switchBrowserMode).toHaveBeenCalledWith(token));
  window.history.replaceState(null, '', '/');
});

it('enables test mode and reloads into its isolated server session', async () => {
  api.testMode.mockResolvedValue({ test_mode: true, token: 'test-session-id' });
  render(<DeviceContext.Provider value={{ test_mode: false }}><TestModeSettings /></DeviceContext.Provider>);
  fireEvent.click(screen.getByRole('switch', { name: 'Test mode' }));
  await waitFor(() => expect(api.testMode).toHaveBeenCalledWith(true));
  expect(api.switchBrowserMode).toHaveBeenCalledWith('test-session-id');
});

it('turns off rehearsal and explicitly returns to normal records', async () => {
  api.testMode.mockResolvedValue({ test_mode: false, token: null });
  render(<DeviceContext.Provider value={{ test_mode: true }}><TestModeSettings /></DeviceContext.Provider>);
  expect(screen.getByRole('switch', { name: 'Test mode' }).getAttribute('aria-checked')).toBe('true');
  fireEvent.click(screen.getByRole('switch', { name: 'Test mode' }));
  await waitFor(() => expect(api.switchBrowserMode).toHaveBeenCalledWith(null));
  expect(api.testMode).toHaveBeenCalledWith(false);
});

it('keeps the current mode when switching fails', async () => {
  api.testMode.mockRejectedValue(new Error('Could not create safe test records'));
  render(<DeviceContext.Provider value={{ test_mode: false }}><TestModeSettings /></DeviceContext.Provider>);
  fireEvent.click(screen.getByRole('switch', { name: 'Test mode' }));
  expect(await screen.findByRole('alert')).toBeTruthy();
  expect(api.switchBrowserMode).not.toHaveBeenCalled();
  expect(screen.getByRole('switch', { name: 'Test mode' }).getAttribute('aria-checked')).toBe('false');
});
