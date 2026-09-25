/* @vitest-environment jsdom */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  session: vi.fn(), requestPairing: vi.fn(), pollPairing: vi.fn(), waitingPairings: vi.fn(),
}));
vi.mock('../api/system', () => ({ systemApi: api }));

import PairingGate from './PairingGate';

describe('PairingGate', () => {
  afterEach(() => { localStorage.clear(); sessionStorage.clear(); vi.useRealTimers(); });

  it('shows a pairing code and unlocks after host approval', async () => {
    api.waitingPairings.mockRejectedValue(new Error('not host'));
    api.requestPairing.mockResolvedValue({ request_id: 'r1', poll_secret: 's', code: '482913' });
    api.pollPairing.mockResolvedValue({ status: 'approved', token: 'hs_token', role: 'learner' });
    api.session.mockResolvedValue({ device: { id: 'd1', name: 'Tablet', role: 'learner' }, host: false });
    render(<PairingGate><p>Family workspace</p></PairingGate>);
    fireEvent.click(await screen.findByText('Get a pairing code'));
    expect((await screen.findByTestId('pairing-code')).textContent).toBe('482913');
    await waitFor(() => expect(screen.getByText('Family workspace')).toBeTruthy(), { timeout: 4000 });
    expect(localStorage.getItem('homeschool:device-token:v1')).toBe('hs_token');
  });
});
