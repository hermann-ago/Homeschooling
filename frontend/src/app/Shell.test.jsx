/* @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router';
vi.mock('./learnerContext', () => ({ useLearner: () => ({ isLoading: false }) }));
vi.mock('../components/SyncIndicator', () => ({ default: () => <p>Home server available</p> }));
import Shell from './Shell';
afterEach(cleanup);

it('keeps every secondary page reachable from More and closes after navigation', async () => {
  render(<MemoryRouter><Routes><Route element={<Shell />}><Route path="*" element={<p>Screen content</p>} /></Route></Routes></MemoryRouter>);
  for (const name of ['Progress', 'Records', 'Settings']) {
    fireEvent.click(screen.getByRole('button', { name: 'More pages' }));
    const dialog = await screen.findByRole('dialog', { name: 'More pages' });
    expect(within(dialog).getByText('Home server available')).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('link', { name }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'More pages' })).toBeNull());
    expect(screen.getByRole('button', { name: 'More pages' }).getAttribute('aria-current')).toBe('page');
  }
});
