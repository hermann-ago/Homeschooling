/* @vitest-environment jsdom */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ storageStatus: vi.fn() }));
vi.mock('../api/system', () => ({ systemApi: api }));

import SyncIndicator from './SyncIndicator';

describe('SyncIndicator', () => {
  it('shows saved work and warns when the Drive folder is unavailable', async () => {
    api.storageStatus.mockResolvedValueOnce({ state: 'saved', drive_folder_available: true });
    const { unmount } = render(<SyncIndicator />);
    expect(await screen.findByText('Saved on the home server')).toBeTruthy();
    expect(screen.queryByText(/Drive folder unavailable/)).toBeNull();
    unmount();
    api.storageStatus.mockResolvedValueOnce({ state: 'saved', drive_folder_available: false });
    render(<SyncIndicator />);
    expect(await screen.findByText('Drive folder unavailable: books and audio may not open')).toBeTruthy();
  });

  it('says when the home server cannot be reached', async () => {
    api.storageStatus.mockRejectedValueOnce(new Error('offline'));
    render(<SyncIndicator />);
    expect(await screen.findByText('Home server unreachable')).toBeTruthy();
  });
});
