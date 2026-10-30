/* @vitest-environment jsdom */
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ServerGate from './ServerGate';

const api = vi.hoisted(() => ({ session: vi.fn() }));
vi.mock('../api/system', () => ({ systemApi: api }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it('labels test mode on every screen and in the browser title', async () => {
  document.title = 'Homeschool';
  api.session.mockResolvedValue({ environment: 'test', test_mode: true, host: true });
  render(<ServerGate><main>Lesson controls</main></ServerGate>);
  expect(await screen.findByText('TEST MODE')).toBeTruthy();
  expect(screen.getByText(/AI provider costs are tracked/)).toBeTruthy();
  await waitFor(() => expect(document.title).toBe('TEST MODE · Homeschool'));
  expect(screen.getByText('Lesson controls').closest('.test-copy-content')).toBeTruthy();
});

it('never presents the real app as a safe test copy', async () => {
  api.session.mockResolvedValue({ environment: 'live', host: true });
  render(<ServerGate><main>Real lesson</main></ServerGate>);
  expect(await screen.findByText('Real lesson')).toBeTruthy();
  expect(screen.queryByText('TEST MODE')).toBeNull();
});
