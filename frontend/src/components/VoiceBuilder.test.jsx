/* @vitest-environment jsdom */
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const buildNarration = vi.hoisted(() => vi.fn());
vi.mock('../api/tutor', () => ({ tutorApi: { buildNarration } }));

import VoiceBuilder from './VoiceBuilder';

describe('VoiceBuilder', () => {
  afterEach(() => {
    cleanup();
    buildNarration.mockReset();
  });

  it('shows the cost first and builds only after confirmation', async () => {
    buildNarration.mockResolvedValueOnce({ dry_run: true, characters: 4200, used_this_month: 10000, monthly_limit: 150000 })
      .mockResolvedValueOnce({ reused: false });
    const onBuilt = vi.fn();
    render(<VoiceBuilder learner="1" topic="372" onBuilt={onBuilt} />);

    fireEvent.click(screen.getByRole('button', { name: /create read-along voice/i }));
    await screen.findByText(/uses 4[.,\s]200 of the 140[.,\s]000 characters left/i); // any locale's separator
    expect(buildNarration).toHaveBeenCalledWith('1', '372', true, false);
    expect(onBuilt).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /^create voice$/i }));
    await waitFor(() => expect(onBuilt).toHaveBeenCalled());
    expect(buildNarration).toHaveBeenLastCalledWith('1', '372', false, false);
  });

  it('will not build past the monthly allowance', async () => {
    buildNarration.mockResolvedValueOnce({ dry_run: true, characters: 5000, used_this_month: 148000, monthly_limit: 150000 });
    render(<VoiceBuilder learner="1" topic="372" onBuilt={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /create read-along voice/i }));
    expect((await screen.findByRole('button', { name: /^create voice$/i })).disabled).toBe(true);
    expect(screen.getByText(/renews next month/i)).toBeTruthy();
  });

  it('explains a failure without building', async () => {
    buildNarration.mockRejectedValueOnce(new Error('/tutor/reader/narration: gcloud is not signed in on the host computer'));
    render(<VoiceBuilder learner="1" topic="372" onBuilt={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /create read-along voice/i }));
    expect(await screen.findByText('gcloud is not signed in on the host computer')).toBeTruthy();
  });
});
