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
    await screen.findByText(/generates 4[.,\s]200 characters/i); // any locale's separator
    expect(buildNarration).toHaveBeenCalledWith('1', '372', true, false);
    expect(onBuilt).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /^create voice$/i }));
    await waitFor(() => expect(onBuilt).toHaveBeenCalled());
    expect(buildNarration).toHaveBeenLastCalledWith('1', '372', false, false);
  });

  it('does not restrict generation using a legacy monthly allowance', async () => {
    buildNarration.mockResolvedValueOnce({ dry_run: true, characters: 5000, used_this_month: 148000, monthly_limit: 150000 });
    render(<VoiceBuilder learner="1" topic="372" onBuilt={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /create read-along voice/i }));
    expect((await screen.findByRole('button', { name: /^create voice$/i })).disabled).toBe(false);
    expect(screen.queryByText(/renews next month/i)).toBeNull();
  });

  it('explicitly retries missing blocks only after the cost confirmation',async()=>{
    buildNarration.mockResolvedValueOnce({estimated_cost_usd:.05,remaining_usd:1,allowed:true})
      .mockResolvedValueOnce({job_status:'ready'});
    render(<VoiceBuilder learner="1" topic="375" guide session="saved-session" retry retryMissing/>);
    fireEvent.click(screen.getByRole('button',{name:'Retry missing Google audio'}));
    await screen.findByText(/Ask Google to reconsider/);
    expect(buildNarration).toHaveBeenCalledWith('1','375',true,true,'saved-session',{retryMissing:true});
    fireEvent.click(screen.getByRole('button',{name:'Resume Google voice'}));
    await waitFor(()=>expect(buildNarration).toHaveBeenLastCalledWith('1','375',false,true,'saved-session',{retryMissing:true}));
  });

  it('explains a failure without building', async () => {
    buildNarration.mockRejectedValueOnce(new Error('/tutor/reader/narration: gcloud is not signed in on the host computer'));
    render(<VoiceBuilder learner="1" topic="372" onBuilt={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /create read-along voice/i }));
    expect(await screen.findByText('gcloud is not signed in on the host computer')).toBeTruthy();
  });

  it('previews a pinned retry before resuming and preserves a synchronization error', async () => {
    buildNarration.mockResolvedValueOnce({alignment:'local', parts:3, completed_parts:0,
      estimated_cost_usd:0.02, remaining_usd:1, allowed:true, job_status:'alignment_review'})
      .mockRejectedValueOnce(new Error('/tutor/reader/narration: Saved audio still needs synchronization review'));
    const onBuilt=vi.fn();
    const onBuildingChange=vi.fn();
    render(<VoiceBuilder learner="1" topic="1251" guide session="pinned-session" retry onBuilt={onBuilt} onBuildingChange={onBuildingChange}/>);
    expect(buildNarration).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Retry Google voice'}));
    await screen.findByText(/Saved audio will be reused/);
    expect(buildNarration).toHaveBeenCalledExactlyOnceWith('1','1251',true,true,'pinned-session');
    expect(onBuildingChange).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Resume Google voice'}));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent','Saved audio still needs synchronization review');
    expect(buildNarration).toHaveBeenLastCalledWith('1','1251',false,true,'pinned-session');
    expect(onBuildingChange.mock.calls).toEqual([[true],[false]]);
    expect(onBuilt).toHaveBeenCalledOnce();
  });
});
