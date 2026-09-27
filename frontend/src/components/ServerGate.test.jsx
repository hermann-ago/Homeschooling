/* @vitest-environment jsdom */
import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ session: vi.fn() }));
vi.mock('../api/system', () => ({ systemApi: api }));

import ServerGate from './ServerGate';

describe('ServerGate', () => {
  afterEach(() => { cleanup(); api.session.mockReset(); });

  it('opens the app straight away, with no pairing', async () => {
    api.session.mockResolvedValue({ device: { id: 'family', name: 'Home network device', role: 'family' }, host: false });
    render(<ServerGate><p>Family workspace</p></ServerGate>);
    expect(await screen.findByText('Family workspace')).toBeTruthy();
  });

  it('says when the home server is not answering and tries again', async () => {
    api.session.mockRejectedValueOnce(new Error('The home server could not be reached'))
      .mockResolvedValueOnce({ device: { id: 'family', role: 'family' }, host: false });
    render(<ServerGate><p>Family workspace</p></ServerGate>);
    fireEvent.click(await screen.findByText('Try again'));
    expect(await screen.findByText('Family workspace')).toBeTruthy();
  });
});
