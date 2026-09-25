/* @vitest-environment jsdom */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ syncStatus: vi.fn() }));
vi.mock('../api/system', () => ({ systemApi: api }));

import SyncIndicator from './SyncIndicator';

describe('SyncIndicator', () => {
  it('distinguishes saved, pending and reconciliation states', async () => {
    api.syncStatus.mockResolvedValueOnce({ state: 'pending', pending: 2, online: false, connected: true });
    const { unmount } = render(<SyncIndicator />);
    expect(await screen.findByText('Pending sync')).toBeTruthy();
    expect(screen.getByText('2 changes waiting (offline)')).toBeTruthy();
    unmount();
    api.syncStatus.mockResolvedValueOnce({ state: 'needs_reconciliation', needs_reconciliation: 1, connected: true });
    render(<SyncIndicator />);
    expect(await screen.findByText('Needs reconciliation')).toBeTruthy();
  });

  it('asks for a Google reconnect when authorization expired', async () => {
    api.syncStatus.mockResolvedValueOnce({ state: 'pending', pending: 1, auth_required: true, connected: true });
    render(<SyncIndicator />);
    expect(await screen.findByText('A parent must reconnect Google on the host computer')).toBeTruthy();
  });
});
