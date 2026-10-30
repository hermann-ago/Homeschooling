/* @vitest-environment jsdom */
import { useState } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ audioManifest: vi.fn(), audioPart: vi.fn() }));
vi.mock('../api/tutor', () => ({ tutorApi: api }));
import ReadAlong from './ReadAlong';
import { pauseNarration } from '../utils/narration';

const passage = { sentences: [{ text: 'Earlier source.' }, { text: 'Current passage first.' }, { text: 'Current passage second.' }, { text: 'Upcoming secret question.' }] };
const tracks = [{ track_id: 'saved-voice', status: 'ready', synchronized: true }];
function Reading(props) {
  const [index, setIndex] = useState(props.savedCursor?.sentence_index ?? 1);
  return <ReadAlong passage={passage} tracks={tracks} activeIndex={index} onActiveIndex={setIndex} rangeStart={1} rangeEnd={2} visibleThrough={2} {...props} />;
}
beforeEach(() => {
  vi.clearAllMocks();
  api.audioManifest.mockResolvedValue({ tracks: [{ index: 0, startSentence: 0, sentenceStarts: [0, 2, 4, 6] }] });
  api.audioPart.mockResolvedValue('blob:range-audio');
  vi.spyOn(window.HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockResolvedValue();
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('Activity reading boundaries and exact saved playback', () => {
  it('highlights locally aligned sentences and ends at the activity clip boundary', async () => {
    api.audioManifest.mockResolvedValue({ version: 4, timing: 'local-alignment', tracks: [
      { index: 0, startSentence: 1, sentenceCount: 2, sentenceStarts: [0, 1.2], duration: 2.4, timing: 'local-alignment' },
      { index: 1, startSentence: 3, sentenceCount: 1, sentenceStarts: [0], duration: 1, timing: 'local-alignment' },
    ] });
    const finish = vi.fn();
    const { container } = render(<Reading externalControls onReadingEnd={finish} />);
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    const audio = container.querySelector('audio');
    audio.currentTime = .3;
    fireEvent.timeUpdate(audio);
    expect(screen.getByText('Current passage first.').getAttribute('aria-current')).toBe('true');
    expect(screen.getByText('Current passage second.').getAttribute('aria-current')).toBeNull();
    audio.currentTime = 1.4;
    fireEvent.timeUpdate(audio);
    expect(screen.getByText('Current passage second.').getAttribute('aria-current')).toBe('true');
    fireEvent.ended(audio);
    expect(finish).toHaveBeenCalledTimes(1);
    expect(api.audioPart).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('Upcoming secret question.')).toBeNull();
  });

  it('restores a saved offset in a locally aligned recording without autoplay', async () => {
    api.audioManifest.mockResolvedValue({ timing: 'local-alignment', tracks: [
      { index: 0, startSentence: 1, sentenceCount: 2, sentenceStarts: [0, 1.2], duration: 2.4, timing: 'local-alignment' },
    ] });
    const { container } = render(<Reading externalControls savedCursor={{ track_id: 'saved-voice', part_index: 0, offset_seconds: 1.5, sentence_index: 2 }} />);
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    fireEvent.loadedMetadata(container.querySelector('audio'));
    expect(container.querySelector('audio').currentTime).toBe(1.5);
    expect(window.HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
  });

  it('renders only reading content when session settings are supplied by the top bar', async () => {
    const { container, rerender } = render(<Reading externalControls settingsInHeader selectedSource="saved-voice" selectedSpeed={1.3} />);
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    fireEvent.loadedMetadata(container.querySelector('audio'));
    expect(container.querySelector('audio').playbackRate).toBe(1.3);
    expect(screen.queryByLabelText('Voice')).toBeNull();
    expect(screen.queryByRole('group', { name: 'Speed' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Replay sentence' })).toBeNull();
    expect(screen.getByText('Current passage first.')).toBeTruthy();
    rerender(<Reading externalControls settingsInHeader selectedSource="saved-voice" selectedSpeed={0.9} />);
    expect(container.querySelector('audio').playbackRate).toBe(0.9);
    expect(window.HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
  });
  it('only autoplays a saved recording after an explicit advance request, once', async () => {
    const { container, rerender } = render(<Reading externalControls autoPlayRequest={0} />);
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    const audio = container.querySelector('audio');
    Object.defineProperty(audio, 'readyState', { configurable: true, value: 1 });
    expect(window.HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Play', exact: true })).toBeNull();
    rerender(<Reading externalControls autoPlayRequest={1} />);
    await waitFor(() => expect(window.HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1));
    rerender(<Reading externalControls autoPlayRequest={1} />);
    expect(window.HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
  });

  it('cancels a pending autoplay when minimized or interrupted before the recording loads', async () => {
    let deliver;
    api.audioManifest.mockImplementationOnce(() => new Promise((resolve) => { deliver = resolve; }));
    const { container } = render(<Reading externalControls autoPlayRequest={1} />);
    act(() => pauseNarration());
    await act(async () => deliver({ tracks: [{ index: 0, startSentence: 0, sentenceStarts: [0, 2, 4, 6] }] }));
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    fireEvent.loadedMetadata(container.querySelector('audio'));
    expect(window.HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
  });

  it('does not autoplay device speech for an unrecorded step', () => {
    const speak = vi.fn();
    vi.stubGlobal('SpeechSynthesisUtterance', class {});
    Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: { speak, cancel: vi.fn() } });
    render(<ReadAlong passage={passage} tracks={[]} activeIndex={1} onActiveIndex={vi.fn()} autoPlayRequest={1} externalControls />);
    expect(speak).not.toHaveBeenCalled();
    expect(api.audioManifest).not.toHaveBeenCalled();
  });

  it('stops at an unrecorded passage instead of automatically substituting device speech', async () => {
    const speak = vi.fn();
    vi.stubGlobal('SpeechSynthesisUtterance', class {});
    Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: { speak, cancel: vi.fn() } });
    api.audioManifest.mockResolvedValue({ timing: 'passage', fallback_parts: 1, tracks: [
      { index: 0, startSentence: 1, sentenceCount: 1, timing: 'passage' },
      { index: 1, startSentence: 2, sentenceCount: 1, fallback: true, timing: 'device' },
    ] });
    const finished = vi.fn();
    const { container } = render(<Reading externalControls onReadingEnd={finished} />);
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    fireEvent.ended(container.querySelector('audio'));
    await waitFor(() => expect(container.querySelector('audio')).toBeNull());
    expect(speak).not.toHaveBeenCalled();
    expect(finished).not.toHaveBeenCalled();
    expect(screen.getByText(/stay text-only/)).toBeTruthy();
  });

  it('offers explicit device playback for a missing passage, then returns to saved audio within the reading', async () => {
    const spoken = [];
    vi.stubGlobal('SpeechSynthesisUtterance', class { constructor(text) { this.text = text; } });
    vi.stubGlobal('speechSynthesis', { cancel: vi.fn(), getVoices: () => [], speak: (utterance) => { spoken.push(utterance); utterance.onstart?.(); } });
    api.audioManifest.mockResolvedValue({ timing: 'passage', tracks: [
      { index: 0, startSentence: 1, sentenceCount: 1, timing: 'passage' },
      { index: 1, startSentence: 2, sentenceCount: 1, fallback: true, timing: 'device' },
      { index: 2, startSentence: 3, sentenceCount: 1, timing: 'passage' },
      { index: 3, startSentence: 4, sentenceCount: 1, timing: 'passage' },
    ] });
    api.audioPart.mockImplementation(async (_, part) => `blob:part-${part}`);
    const transport = vi.fn(); const finished = vi.fn();
    const { container } = render(<Reading externalControls autoPlayRequest={1} rangeEnd={3} visibleThrough={3}
      passage={{ sentences: [...passage.sentences.slice(0, 3), { text: 'Last reading passage.' }, { text: 'Future task.' }] }} onTransport={transport} onReadingEnd={finished} />);
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    fireEvent.loadedMetadata(container.querySelector('audio'));
    fireEvent.play(container.querySelector('audio'));
    fireEvent.ended(container.querySelector('audio'));
    await waitFor(() => expect(transport.mock.lastCall[0]).toMatchObject({ unrecorded: true, available: true, playing: false }));
    expect(spoken).toHaveLength(0);
    expect(finished).not.toHaveBeenCalled();
    act(() => transport.mock.lastCall[0].toggle());
    expect(spoken.map((item) => item.text)).toEqual(['Current passage second.']);
    expect(screen.getByLabelText('Voice').value).toBe('saved-voice');
    act(() => spoken[0].onend());
    await waitFor(() => expect(container.querySelector('audio')?.getAttribute('src')).toBe('blob:part-2'));
    const next = container.querySelector('audio');
    fireEvent.pause(next); // A browser may pause while changing the source.
    const calls = window.HTMLMediaElement.prototype.play.mock.calls.length;
    fireEvent.loadedMetadata(next);
    expect(window.HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(calls + 1);
    fireEvent.play(next); fireEvent.ended(next);
    expect(finished).toHaveBeenCalledTimes(1);
    expect(api.audioPart).not.toHaveBeenCalledWith('saved-voice', 3);
  });

  it('marks the current missing passage with header controls, and clears the notice on recorded passages', async () => {
    api.audioManifest.mockResolvedValue({ timing: 'passage', fallback_parts: 1, tracks: [
      { index: 0, startSentence: 1, sentenceCount: 1, timing: 'passage' },
      { index: 1, startSentence: 2, sentenceCount: 1, fallback: true, timing: 'device' },
    ] });
    const { container, rerender } = render(<Reading externalControls settingsInHeader selectedSource="saved-voice" />);
    expect(screen.queryByRole('status')).toBeNull();
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    expect(screen.queryByText('No recorded audio for this passage')).toBeNull();
    fireEvent.ended(container.querySelector('audio'));
    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('No recorded audio for this passage'));
    expect(screen.getByLabelText('Passage').contains(screen.getByRole('status'))).toBe(true);
    expect(screen.getByText('Current passage second.')).toBeTruthy();
    fireEvent.click(screen.getByText('Current passage first.'));
    await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
    fireEvent.click(screen.getByText('Current passage second.'));
    await waitFor(() => expect(screen.getByRole('status')).toBeTruthy());
    rerender(<Reading externalControls settingsInHeader selectedSource="device" />);
    await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
  });

  it('continues between saved parts despite source-loading pause, but interruption cancels that continuation', async () => {
    api.audioManifest.mockResolvedValue({ timing: 'passage', tracks: [
      { index: 0, startSentence: 1, sentenceCount: 1, timing: 'passage' },
      { index: 1, startSentence: 2, sentenceCount: 1, timing: 'passage' },
    ] });
    api.audioPart.mockImplementation(async (_, part) => `blob:part-${part}`);
    const { container } = render(<Reading externalControls />);
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    fireEvent.play(container.querySelector('audio')); fireEvent.ended(container.querySelector('audio'));
    await waitFor(() => expect(container.querySelector('audio')?.getAttribute('src')).toBe('blob:part-1'));
    const audio = container.querySelector('audio');
    fireEvent.pause(audio); fireEvent.loadedMetadata(audio);
    expect(window.HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
    fireEvent.play(audio);
    // Replay the previous part, then interrupt the pending next-part load.
    fireEvent.click(screen.getByText('Current passage first.'));
    await waitFor(() => expect(container.querySelector('audio')?.getAttribute('src')).toBe('blob:part-0'));
    fireEvent.loadedMetadata(audio); fireEvent.play(audio); fireEvent.ended(audio);
    await waitFor(() => expect(container.querySelector('audio')?.getAttribute('src')).toBe('blob:part-1'));
    act(() => pauseNarration());
    const calls = window.HTMLMediaElement.prototype.play.mock.calls.length;
    fireEvent.loadedMetadata(audio);
    expect(window.HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(calls);
  });

  it('restores the unfinished device sentence within a missing recorded passage without replaying its title', async () => {
    const spoken = [];
    vi.stubGlobal('SpeechSynthesisUtterance', class { constructor(text) { this.text = text; } });
    vi.stubGlobal('speechSynthesis', { cancel: vi.fn(), speak: (utterance) => { spoken.push(utterance); utterance.onstart?.(); } });
    api.audioManifest.mockResolvedValue({ timing: 'passage', tracks: [
      { index: 0, startSentence: 1, sentenceCount: 1, timing: 'passage' },
      { index: 1, startSentence: 2, sentenceCount: 2, fallback: true, timing: 'device' },
    ] });
    const transport = vi.fn(); const cursor = vi.fn();
    render(<Reading externalControls rangeEnd={3} visibleThrough={3} onTransport={transport} onCursorChange={cursor}
      passage={{ sentences: [...passage.sentences.slice(0, 3), { text: 'Unfinished reading sentence.' }] }}
      savedCursor={{ track_id: 'saved-voice', part_index: 1, offset_seconds: 0, sentence_index: 3 }} />);
    await waitFor(() => expect(transport.mock.lastCall[0].unrecorded).toBe(true));
    expect(spoken).toHaveLength(0);
    act(() => transport.mock.lastCall[0].toggle());
    expect(spoken.map((item) => item.text)).toEqual(['Unfinished reading sentence.']);
    expect(cursor.mock.lastCall[0]).toMatchObject({ track_id: 'saved-voice', part_index: 1, sentence_index: 3 });
  });
  it('does not render earlier or upcoming source outside the active reading range', async () => {
    render(<Reading />);
    expect(screen.getByText('Current passage first.')).toBeTruthy();
    expect(screen.getByText('Current passage second.')).toBeTruthy();
    expect(screen.queryByText('Earlier source.')).toBeNull();
    expect(screen.queryByText('Upcoming secret question.')).toBeNull();
  });

  it('stops at a genuine sentence boundary without starting the upcoming question', async () => {
    const ended = vi.fn(); const cursor = vi.fn();
    const { container } = render(<Reading onReadingEnd={ended} onCursorChange={cursor} />);
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    const audio = container.querySelector('audio');
    audio.currentTime = 6;
    fireEvent.timeUpdate(audio);
    expect(ended).toHaveBeenCalledTimes(1);
    fireEvent.timeUpdate(audio);
    expect(ended).toHaveBeenCalledTimes(1);
    expect(api.audioPart).toHaveBeenCalledTimes(1);
  });

  it('restores the saved recording offset and resumes it without seeking to the passage beginning', async () => {
    api.audioManifest.mockResolvedValue({ timing: 'passage', tracks: [
      { index: 0, startSentence: 0, sentenceCount: 1, timing: 'passage' },
      { index: 1, startSentence: 1, sentenceCount: 2, timing: 'passage' },
      { index: 2, startSentence: 3, sentenceCount: 1, timing: 'passage' },
    ] });
    const { container } = render(<Reading savedCursor={{ track_id: 'saved-voice', part_index: 1, offset_seconds: 4.25, sentence_index: 1 }} />);
    await waitFor(() => expect(api.audioPart).toHaveBeenCalledWith('saved-voice', 1));
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    const audio = container.querySelector('audio');
    fireEvent.loadedMetadata(audio);
    expect(audio.currentTime).toBe(4.25);
    fireEvent.click(screen.getByRole('button', { name: 'Play' }));
    expect(audio.currentTime).toBe(4.25);
  });

  it('retains the saved nonpreferred narrator when reopening an exact cursor', async () => {
    render(<Reading tracks={[...tracks, { track_id: 'new-preferred', status: 'ready', synchronized: true, preferred: true }]} savedCursor={{ track_id: 'saved-voice', part_index: 0, offset_seconds: 3, sentence_index: 1 }} />);
    await waitFor(() => expect(api.audioManifest).toHaveBeenCalled());
    expect(screen.getByRole('option', { name: 'saved-voice' }).selected).toBe(true);
    expect(api.audioManifest).not.toHaveBeenCalledWith('new-preferred');
  });

  it('device narration stays inside the range and pauses synchronously for an interruption', async () => {
    const spoken = [];
    const cancel = vi.fn();
    vi.stubGlobal('SpeechSynthesisUtterance', class { constructor(text) { this.text = text; } });
    vi.stubGlobal('speechSynthesis', { cancel, speak: (utterance) => { spoken.push(utterance); utterance.onstart?.(); }, getVoices: () => [] });
    const ended = vi.fn(); render(<Reading tracks={[]} onReadingEnd={ended} />);
    fireEvent.click(screen.getByRole('button', { name: 'Play' }));
    expect(spoken.map((item) => item.text)).toEqual(['Current passage first.']);
    act(() => spoken[0].onend());
    expect(spoken.map((item) => item.text)).toEqual(['Current passage first.', 'Current passage second.']);
    act(() => pauseNarration());
    act(() => spoken[1].onend());
    expect(ended).not.toHaveBeenCalled();
    expect(spoken).toHaveLength(2);
    expect(cancel).toHaveBeenCalled();
  });
});
