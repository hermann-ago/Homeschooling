/* @vitest-environment jsdom */
import React, { useState } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ audioManifest: vi.fn(), audioPart: vi.fn() }));
vi.mock('../api/tutor', () => ({ tutorApi: api }));

import ReadAlong from './ReadAlong';

const passage = { sentences: [{ text: 'First sentence.' }, { text: 'Second sentence.' }, { text: 'Third sentence.' }] };

function Harness({ tracks }) {
  const [active, setActive] = useState(null);
  return <ReadAlong passage={passage} tracks={tracks} activeIndex={active} onActiveIndex={setActive} disabled={false} />;
}

describe('ReadAlong', () => {
  beforeEach(() => {
    api.audioManifest.mockReset().mockResolvedValue({
      tracks: [{ index: 0, startSentence: 0, sentenceStarts: [0.0, 2.0, 4.5] }],
    });
    api.audioPart.mockReset().mockResolvedValue('blob:audio');
  });

  it('highlights the sentence from provider timepoints', async () => {
    const { container } = render(<Harness tracks={[{ track_id: 't1', voice: 'en-US-Neural2-J', status: 'ready', synchronized: true }]} />);
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    const audio = container.querySelector('audio');
    Object.defineProperty(audio, 'currentTime', { value: 2.3, writable: true });
    act(() => { fireEvent.timeUpdate(audio); });
    expect(screen.getByText('Second sentence.').getAttribute('aria-current')).toBe('true');
    Object.defineProperty(audio, 'currentTime', { value: 5, writable: true });
    act(() => { fireEvent.timeUpdate(audio); });
    expect(screen.getByText('Third sentence.').getAttribute('aria-current')).toBe('true');
  });

  it('never highlights a track without verified timings', async () => {
    const { container } = render(<Harness tracks={[{ track_id: 'legacy', voice: 'ElevenLabs', status: 'legacy', synchronized: false }]} />);
    expect(screen.getByText(/no verified timings/)).toBeTruthy();
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    const audio = container.querySelector('audio');
    Object.defineProperty(audio, 'currentTime', { value: 3, writable: true });
    act(() => { fireEvent.timeUpdate(audio); });
    expect(container.querySelector('[aria-current="true"]')).toBeNull();
  });
});
