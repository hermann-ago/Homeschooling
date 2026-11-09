/* @vitest-environment jsdom */
import React, { useState } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

const api = vi.hoisted(() => ({ audioManifest: vi.fn(), audioPart: vi.fn() }));
vi.mock('../api/tutor', () => ({ tutorApi: api }));

import ReadAlong from './ReadAlong';

const passage = { sentences: [{ text: 'First sentence.' }, { text: 'Second sentence.' }, { text: 'Third sentence.' }] };

function Harness({ tracks }) {
  const [active, setActive] = useState(null);
  return <ReadAlong passage={passage} tracks={tracks} activeIndex={active} onActiveIndex={setActive} disabled={false} />;
}

describe('ReadAlong', () => {
  it('leaves the book text to the highlighted page and keeps the teacher talking in the panel', () => {
    const lesson = { sentences: [
      { text: 'Let us read about the tribes.', kind: 'teacher' },
      { text: 'The Mongols came from the north.', kind: 'book' },
      { text: 'They lived in felt tents.', kind: 'book' },
    ] };
    render(<ReadAlong passage={lesson} tracks={[]} activeIndex={1} onActiveIndex={() => {}} bookOnPage />);
    expect(screen.getByText('Let us read about the tribes.')).toBeTruthy();
    expect(screen.queryByText('The Mongols came from the north.')).toBeNull();
    expect(screen.getByText('Follow the highlighted lines in the book.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Show the text here' }));
    expect(screen.getByText('The Mongols came from the north.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Hide the text here' }));
    expect(screen.queryByText('They lived in felt tents.')).toBeNull();
  });

  it('flows sentences inside their source paragraphs and keeps seeking keyboard accessible', () => {
    const changed = vi.fn();
    const source = { sentences: [
      { text: 'A Great Storm', paragraphIndex: 'read:0' },
      { text: 'The boat left.', paragraphIndex: 'read:1' },
      { text: 'Jonathan hoped for adventure.', paragraphIndex: 'read:1' },
      { text: 'A storm arrived.', paragraphIndex: 'read:2' },
    ] };
    const view = render(<ReadAlong passage={source} tracks={[]} activeIndex={1} onActiveIndex={changed} />);
    const paragraphs = view.container.querySelector('[aria-label="Passage"]').querySelectorAll('p');
    expect(paragraphs).toHaveLength(3);
    expect(paragraphs[1].textContent).toBe('The boat left. Jonathan hoped for adventure. ');
    const sentence = screen.getByRole('button', { name: 'Jonathan hoped for adventure.' });
    expect(sentence.tagName).toBe('SPAN'); // Native buttons wrap as atomic boxes.
    expect(sentence.tabIndex).toBe(0);
    fireEvent.keyDown(sentence, { key: 'Enter' });
    expect(changed).toHaveBeenCalledWith(2);
    changed.mockClear();
    view.rerender(<ReadAlong passage={source} tracks={[]} activeIndex={1} onActiveIndex={changed} disabled />);
    expect(sentence.getAttribute('aria-disabled')).toBe('true');
    expect(sentence.tabIndex).toBe(-1);
    fireEvent.click(sentence);
    fireEvent.keyDown(sentence, { key: ' ' });
    expect(changed).not.toHaveBeenCalled();
  });

  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
  beforeEach(() => {
    api.audioManifest.mockReset().mockResolvedValue({
      tracks: [{ index: 0, startSentence: 0, sentenceStarts: [0.0, 2.0, 4.5] }],
    });
    api.audioPart.mockReset().mockResolvedValue('blob:audio');
  });

  it('reloads the same track when missing recordings are filled in',async()=>{
    const track={track_id:'repaired',voice:'Achird',status:'ready',synchronized:true,preferred:true,fallback_parts:1};
    const props={passage,onActiveIndex:vi.fn(),activeIndex:0};
    const {rerender}=render(<ReadAlong {...props} tracks={[track]}/>);
    await waitFor(()=>expect(api.audioManifest).toHaveBeenCalledTimes(1));
    rerender(<ReadAlong {...props} tracks={[{...track,fallback_parts:0}]}/>);
    await waitFor(()=>expect(api.audioManifest).toHaveBeenCalledTimes(2));
  });

  it('explains a missing recording and offers preparation beside the voice controls', () => {
    const prepare = vi.fn();
    const { rerender } = render(<ReadAlong passage={passage} tracks={[]} onActiveIndex={vi.fn()} voiceSetup={<button onClick={prepare}>Create recording</button>} />);
    expect(screen.getByRole('option', { name: 'Device voice' })).toBeTruthy();
    expect(screen.getByText('This guided lesson has no saved voice recording yet.')).toBeTruthy();
    expect(prepare).not.toHaveBeenCalled();
    expect(api.audioManifest).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Prepare a recorded voice'));
    fireEvent.click(screen.getByRole('button', { name: 'Create recording' }));
    expect(prepare).toHaveBeenCalledTimes(1);
    rerender(<ReadAlong passage={passage} tracks={[{ track_id: 'google', voice: 'Achird', provider: 'google-gemini', status: 'ready', synchronized: true }]} onActiveIndex={vi.fn()} voiceSetup={<button>Create recording</button>} />);
    expect(screen.queryByText('This guided lesson has no saved voice recording yet.')).toBeNull();
    expect(screen.getByRole('option', { name: 'Achird' })).toBeTruthy();
  });

  it('selects a newly prepared recording when device speech was only a temporary fallback', async () => {
    const props = { passage, activeIndex: 0, onActiveIndex: vi.fn(), savedCursor: { track_id: 'device', sentence_index: 0 }, externalControls: true };
    const { rerender } = render(<ReadAlong {...props} tracks={[]} />);
    expect(screen.getByLabelText('Voice').value).toBe('device');
    rerender(<ReadAlong {...props} tracks={[{ track_id: 'google-ready', voice: 'Achird', status: 'ready', synchronized: true, preferred: true }]} />);
    await waitFor(() => expect(screen.getByLabelText('Voice').value).toBe('google-ready'));
    expect(api.audioManifest).toHaveBeenCalledWith('google-ready');
  });

  it('defaults to the explicitly selected local narrator while retaining Google recordings', async () => {
    render(<Harness tracks={[
      { track_id: 'google', voice: 'Achird', provider: 'google-gemini', status: 'ready', synchronized: true, preferred: false, fallback_parts: 1 },
      { track_id: 'local', voice: 'am_michael', provider: 'kokoro-local', status: 'ready', synchronized: true, preferred: true },
    ]} />);
    await waitFor(() => expect(api.audioManifest).toHaveBeenCalledWith('local'));
    expect(screen.getByRole('option', { name: 'Home voice · Michael' }).selected).toBe(true);
    expect(screen.getByRole('option', { name: 'Achird (includes device voice)' })).toBeTruthy();
  });

  it('plays a refused passage with device speech then resumes saved audio without a provider request', async () => {
    const spoken = [];
    vi.stubGlobal('SpeechSynthesisUtterance', class { constructor(text) { this.text = text; } });
    Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: {
      cancel: vi.fn(), speak: (utterance) => { spoken.push(utterance); utterance.onstart?.(); },
    } });
    api.audioManifest.mockResolvedValue({ timing: 'passage', fallback_parts: 1, tracks: [
      { index: 0, startSentence: 0, sentenceCount: 1, timing: 'passage', duration: 2 },
      { index: 1, startSentence: 1, sentenceCount: 1, timing: 'device', fallback: true, duration: 0 },
      { index: 2, startSentence: 2, sentenceCount: 1, timing: 'passage', duration: 2 },
    ] });
    const { container } = render(<Harness tracks={[{ track_id: 'mixed', provider: 'google-gemini', status: 'ready', synchronized: true }]} />);
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    fireEvent.play(container.querySelector('audio'));
    fireEvent.ended(container.querySelector('audio'));
    await waitFor(() => expect(spoken).toHaveLength(1));
    expect(spoken[0].text).toBe('Second sentence.');
    expect(api.audioPart).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Second sentence.').getAttribute('aria-current')).toBe('true');
    act(() => spoken[0].onend());
    await waitFor(() => expect(api.audioPart).toHaveBeenCalledWith('mixed', 2));
    expect(api.audioPart).toHaveBeenCalledTimes(2);
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

  it('seeks from a device passage back to a recording using the target passage boundary', async () => {
    api.audioManifest.mockResolvedValue({ timing: 'passage', fallback_parts: 1, tracks: [
      { index: 0, startSentence: 0, sentenceCount: 1, timing: 'device', fallback: true, duration: 0, sentenceStarts: null },
      { index: 1, startSentence: 1, sentenceCount: 2, timing: 'passage', duration: 5, sentenceStarts: null },
    ] });
    const { container } = render(<Harness tracks={[{ track_id: 'mixed-seek', status: 'ready', synchronized: true }]} />);
    await screen.findByText(/Some passages use device voice/);
    expect(api.audioPart).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Third sentence.'));
    await waitFor(() => expect(api.audioPart).toHaveBeenCalledWith('mixed-seek', 1));
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    const audio = container.querySelector('audio');
    Object.defineProperty(audio, 'currentTime', { value: 4, writable: true });
    fireEvent.loadedMetadata(audio);
    expect(audio.currentTime).toBe(0);
    expect(screen.getByText('Second sentence.').getAttribute('aria-current')).toBe('true');
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

  it('does not report a normal play cancellation as a playback failure', async () => {
    const cancelled = Object.assign(new Error('Playback cancelled by pause.'), { name: 'AbortError' });
    const play = vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockRejectedValue(cancelled);
    try {
      const { container } = render(<Harness tracks={[{ track_id: 'cancel', status: 'legacy', synchronized: false }]} />);
      await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
      await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Play' })); });
      expect(play).toHaveBeenCalled();
      expect(screen.queryByText(cancelled.message)).toBeNull();
    } finally { play.mockRestore(); }
  });

  it('highlights the whole recorded passage and seeks to its start without invented timings', async () => {
    api.audioManifest.mockResolvedValue({ timing: 'passage', tracks: [
      { index: 0, startSentence: 0, sentenceCount: 2, timing: 'passage', duration: 10 },
      { index: 1, startSentence: 2, sentenceCount: 1, timing: 'passage', duration: 5 },
    ] });
    const { container } = render(<Harness tracks={[{ track_id: 'expressive', provider: 'google-gemini', voice: 'Achird', status: 'ready', synchronized: true }]} />);
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    const audio = container.querySelector('audio');
    Object.defineProperty(audio, 'currentTime', { value: 8, writable: true });
    fireEvent.timeUpdate(audio);
    expect(screen.getByText('First sentence.').getAttribute('aria-current')).toBe('true');
    expect(screen.getByText('Second sentence.').getAttribute('aria-current')).toBe('true');
    expect(screen.getByText('Third sentence.').getAttribute('aria-current')).toBeNull();
    fireEvent.click(screen.getByText('Second sentence.'));
    expect(audio.currentTime).toBe(0);
    expect(screen.getByRole('button', { name: 'Replay passage' })).toBeTruthy();
  });

  it('a smooth recorded passage stops at its activity boundary', async () => {
    api.audioManifest.mockResolvedValue({ timing: 'passage', tracks: [
      { index: 0, startSentence: 0, sentenceCount: 2, timing: 'passage', duration: 10 },
      { index: 1, startSentence: 2, sentenceCount: 1, timing: 'passage', duration: 5 },
    ] });
    const onAction = vi.fn();
    const guided = { sentences: [{ text: 'Read this.' }, { text: 'Your turn.', pause_after: 'a1' }, { text: 'Next.' }] };
    const { container } = render(<ReadAlong passage={guided} tracks={[{ track_id: 'smooth', status: 'ready', synchronized: true }]}
      activeIndex={0} onActiveIndex={() => {}} onAction={onAction} pendingActions={['a1']} />);
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    fireEvent.ended(container.querySelector('audio'));
    expect(onAction).toHaveBeenCalledWith('a1', 2);
    expect(api.audioPart).toHaveBeenCalledTimes(1);
  });
  it('stops inside a legacy recording when genuine sentence timings locate the question', async () => {
    api.audioManifest.mockResolvedValue({ tracks: [{ index: 0, startSentence: 0, sentenceStarts: [0, 2, 4] }] });
    const onAction = vi.fn();
    const { container } = render(<ReadAlong passage={{ sentences: [{ text: 'Reading.' }, { text: 'Why?', kind: 'teacher', pause_after: 'a1' }, { text: 'Later.' }] }}
      tracks={[{ track_id: 'legacy', status: 'ready', synchronized: true }]} activeIndex={0} onActiveIndex={() => {}} onAction={onAction} pendingActions={['a1']} />);
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    container.querySelector('audio').currentTime = 4.1;
    fireEvent.timeUpdate(container.querySelector('audio'));
    expect(onAction).toHaveBeenCalledWith('a1', 2);
    expect(screen.getByRole('button', { name: 'Play' }).disabled).toBe(true);
  });

  it('device speech stops at a student action and resumes only on an explicit continue', async () => {
    const spoken = [];
    vi.stubGlobal('SpeechSynthesisUtterance', class { constructor(text) { this.text = text; } });
    Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: {
      cancel: vi.fn(), speak: (utterance) => { spoken.push(utterance); utterance.onstart?.(); },
    } });
    const reached = vi.fn();
    const guided = { sentences: [{ text: 'Read this.' }, { text: 'What do you notice?', kind: 'teacher', pause_after: 'a1' }, { text: 'Continue reading.' }] };
    function Student() {
      const [index, setIndex] = useState(null);
      const [blocked, setBlocked] = useState(false);
      const [resume, setResume] = useState(0);
      return <><ReadAlong passage={guided} tracks={[]} activeIndex={index} onActiveIndex={setIndex} disabled={blocked}
        pendingActions={['a1']} onAction={(id, next) => { reached(id, next); setBlocked(true); }} resumeToken={resume} />
        <button onClick={() => { setBlocked(false); setIndex(2); setResume((r) => r + 1); }}>Continue lesson</button></>;
    }
    render(<Student />);
    fireEvent.click(screen.getByRole('button', { name: 'Play' }));
    act(() => spoken[0].onend());
    act(() => spoken[1].onend());
    expect(reached).toHaveBeenCalledWith('a1', 2);
    expect(spoken).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Play' }).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Continue lesson' }));
    expect(spoken).toHaveLength(3);
    expect(spoken[2].text).toBe('Continue reading.');
  });

  it('a recorded part ending at an action does not automatically load the next part', async () => {
    api.audioManifest.mockResolvedValue({ tracks: [
      { index: 0, startSentence: 0, sentenceStarts: [0, 2] },
      { index: 1, startSentence: 2, sentenceStarts: [0] },
    ] });
    const onAction = vi.fn();
    const guided = { sentences: [{ text: 'Read this.' }, { text: 'Your turn.', kind: 'teacher', pause_after: 'a1' }, { text: 'Next passage.' }] };
    const { container } = render(<ReadAlong passage={guided} tracks={[{ track_id: 'guided', status: 'ready', synchronized: true }]}
      activeIndex={0} onActiveIndex={() => {}} onAction={onAction} pendingActions={['a1']} />);
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    fireEvent.ended(container.querySelector('audio'));
    expect(onAction).toHaveBeenCalledWith('a1', 2);
    expect(api.audioPart).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Play' })).toBeTruthy();
  });
});
