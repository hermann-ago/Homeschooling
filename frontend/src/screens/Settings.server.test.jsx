/* @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { HomeServer } from './Settings';
import { FeedbackProvider } from '../ui';

vi.mock('../api/queries', async importOriginal => ({
  ...await importOriginal(),
  useStorageStatus: () => ({ data: { drive_folder: 'Family/Books', drive_folder_available: true } }),
  useNarrationUsage: () => ({ data: { characters: 1234, monthly_limit: null, tracking_only: true } }),
}));

afterEach(cleanup);

it('renders home server settings with tracking-only narration usage and no app limit', () => {
  render(<QueryClientProvider client={new QueryClient()}><FeedbackProvider><HomeServer /></FeedbackProvider></QueryClientProvider>);
  expect(screen.getByText(/characters this month · tracked only/)).toBeTruthy();
  expect(screen.getByText('Home server and backups')).toBeTruthy();
  expect(screen.queryByText(/of .* characters this month/)).toBeNull();
});
