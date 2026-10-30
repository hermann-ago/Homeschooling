/* @vitest-environment jsdom */
import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ conversation: vi.fn(), interactiveAction: vi.fn(), attachWork: vi.fn(), startInteractive: vi.fn(), audioManifest: vi.fn(), audioPart: vi.fn() }));
vi.mock('../api/tutor', () => ({ tutorApi: api }));
import InteractiveGuidedLesson from './InteractiveGuidedLesson';

const guide = { guide_id: 'guide-1', audio: [], sentences: [
  { text: 'What do you notice?', kind: 'teacher', pause_after: 'a1' }, { text: 'The next reading.' },
], actions: [{ id: 'a1', prompt: 'What do you notice?', end_sentence: 0, resume_index: 1 }] };
const paused = { session_id: 's1', revision: 3, status: 'active', can_finish: false,
  playback: { action_id: 'a1', sentence_index: 1, resume_index: 1, reading_finished: false },
  actions: [{ action_id: 'a1', prompt: 'What do you notice?', kind: 'answer', status: 'pending' }], messages: [] };

function Student() {
  const [index, setIndex] = useState(null);
  return <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <InteractiveGuidedLesson guide={guide} learner="1" topic="2" session="s1" activeIndex={index}
      onActiveIndex={setIndex} onStarted={() => {}} onFinished={() => {}} />
  </QueryClientProvider>;
}

describe('Interactive guided lesson', () => {
  beforeEach(() => {
    vi.clearAllMocks(); api.conversation.mockResolvedValue(structuredClone(paused));
    api.audioManifest.mockResolvedValue({ tracks: [{ index: 0, startSentence: 0, sentenceStarts: [0, 2] }] });
    api.audioPart.mockResolvedValue('blob:saved-preview');
  });
  afterEach(cleanup);
  it('pauses the saved preview at a question without writing learner records', async () => {
    api.audioManifest.mockResolvedValue({ timing: 'passage', tracks: [
      { index: 0, startSentence: 0, sentenceCount: 1, timing: 'passage' },
      { index: 1, startSentence: 1, sentenceCount: 1, timing: 'passage' },
    ] });
    const saved = { ...guide, audio: [{ track_id: 'saved', status: 'ready', synchronized: true }] };
    function Preview() {
      const [index, setIndex] = useState(null);
      return <QueryClientProvider client={new QueryClient()}><InteractiveGuidedLesson guide={saved} learner="1" topic="2"
        activeIndex={index} onActiveIndex={setIndex} onStarted={() => {}} onFinished={() => {}} /></QueryClientProvider>;
    }
    const { container } = render(<Preview />);
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    fireEvent.ended(container.querySelector('audio'));
    expect(await screen.findByRole('region', { name: 'Preview student activity' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Play' }).disabled).toBe(true);
    expect(screen.getByRole('button', { name: 'Start answering' })).toBeTruthy();
    expect(api.startInteractive).not.toHaveBeenCalled();
    expect(api.interactiveAction).not.toHaveBeenCalled();
    expect(api.audioPart).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Continue preview without answering' }));
    await waitFor(() => expect(api.audioPart).toHaveBeenCalledTimes(2));
    expect(api.interactiveAction).not.toHaveBeenCalled();
  });
  it('shows the dynamic follow-up and keeps reading stopped for another answer', async () => {
    api.conversation.mockResolvedValue({ ...paused, actions: [{ ...paused.actions[0], next_prompt: 'What evidence supports that answer?' }] });
    render(<Student />);
    expect(await screen.findByText('What evidence supports that answer?')).toBeTruthy();
    expect(screen.getByLabelText('Your answer or question')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Play' }).disabled).toBe(true);
  });
  it('restarts a paused preview without sending answers or skipping its activities', async () => {
    api.audioManifest.mockResolvedValue({ timing: 'passage', tracks: [
      { index: 0, startSentence: 0, sentenceCount: 1, timing: 'passage' },
      { index: 1, startSentence: 1, sentenceCount: 1, timing: 'passage' },
    ] });
    const saved = { ...guide, audio: [{ track_id: 'saved', status: 'ready', synchronized: true }] };
    const { container } = render(<QueryClientProvider client={new QueryClient()}>
      <InteractiveGuidedLesson guide={saved} learner="1" topic="2" activeIndex={null}
        onActiveIndex={() => {}} onStarted={() => {}} onFinished={() => {}} />
    </QueryClientProvider>);
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    fireEvent.ended(container.querySelector('audio'));
    expect(await screen.findByRole('region', { name: 'Preview student activity' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Restart audio' }));
    await waitFor(() => expect(api.audioPart).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('region', { name: 'Preview student activity' })).toBeNull();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Play' }).disabled).toBe(false));
    fireEvent.ended(container.querySelector('audio'));
    expect(await screen.findByRole('region', { name: 'Preview student activity' })).toBeTruthy();
    expect(api.interactiveAction).not.toHaveBeenCalled();
    expect(api.startInteractive).not.toHaveBeenCalled();
  });
  it('listens independently while an answer is pending and returns with the draft intact', async () => {
    api.audioManifest.mockResolvedValue({ timing: 'passage', tracks: [
      { index: 0, startSentence: 0, sentenceCount: 1, timing: 'passage' },
      { index: 1, startSentence: 1, sentenceCount: 1, timing: 'passage' },
    ] });
    const saved = { ...guide, audio: [{ track_id: 'saved', status: 'ready', synchronized: true }] };
    const finished = vi.fn();
    function SavedStudent() {
      const [index, setIndex] = useState(null);
      return <QueryClientProvider client={new QueryClient()}>
        <InteractiveGuidedLesson guide={saved} learner="1" topic="2" session="s1" activeIndex={index}
          onActiveIndex={setIndex} onStarted={() => {}} onFinished={finished} />
      </QueryClientProvider>;
    }
    const { container } = render(<SavedStudent />);
    fireEvent.change(await screen.findByLabelText('Your answer or question'), { target: { value: 'My unfinished answer.' } });
    expect(screen.getByRole('button', { name: 'Play' }).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Listen from beginning' }));
    expect(screen.getByRole('region', { name: 'Audio replay' })).toBeTruthy();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Play' }).disabled).toBe(false));
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    fireEvent.ended(container.querySelector('audio'));
    await waitFor(() => expect(api.audioPart).toHaveBeenCalledWith('saved', 1));
    fireEvent.ended(container.querySelector('audio'));
    expect(finished).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Restart audio' }));
    await waitFor(() => expect(api.audioPart.mock.calls.at(-1)).toEqual(['saved', 0]));
    fireEvent.click(screen.getByRole('button', { name: 'Return to lesson' }));
    expect(screen.getByLabelText('Your answer or question').value).toBe('My unfinished answer.');
    expect(screen.getByRole('button', { name: 'Play' }).disabled).toBe(true);
    expect(api.interactiveAction).not.toHaveBeenCalled();
    expect(api.startInteractive).not.toHaveBeenCalled();
  });
  it('shows saved playback and allows starting while another lesson stays unfinished', async () => {
    const saved = { ...guide, audio: [{ track_id: 'saved-recording', voice: 'Saved teacher', status: 'ready', synchronized: true }] };
    const { container } = render(<QueryClientProvider client={new QueryClient()}>
      <InteractiveGuidedLesson guide={saved} learner="1" topic="2" resumeLesson={{ title: 'Previous lesson' }}
        activeIndex={null} onActiveIndex={() => {}} onStarted={() => {}} onFinished={() => {}} />
    </QueryClientProvider>);
    expect(screen.getByText(/Guided lesson audio saved/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Play' }).disabled).toBe(false);
    expect(screen.getByRole('button', { name: 'Start lesson' }).disabled).toBe(false);
    await waitFor(() => expect(container.querySelector('audio')).not.toBeNull());
    expect(api.audioManifest).toHaveBeenCalledWith('saved-recording');
    fireEvent.click(screen.getByRole('button', { name: 'Hide reading preview' }));
    expect(screen.queryByRole('button', { name: 'Play' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Show reading preview' }));
    expect(screen.getByRole('button', { name: 'Play' }).disabled).toBe(false);
    expect(api.startInteractive).not.toHaveBeenCalled();
    expect(api.interactiveAction).not.toHaveBeenCalled();
    expect(api.conversation).not.toHaveBeenCalled();
  });
  it('keeps playback paused after feedback until the student explicitly continues', async () => {
    api.interactiveAction.mockResolvedValue({ ...paused, revision: 5,
      actions: [{ ...paused.actions[0], status: 'answered' }], messages: [{ id: 'reply', action_id: 'a1', role: 'teacher', text: 'That is right.', status: 'saved' }] });
    render(<Student />);
    fireEvent.change(await screen.findByLabelText('Your answer or question'), { target: { value: 'The tribes joined together.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send answer' }));
    expect(await screen.findByText('That is right.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Play' }).disabled).toBe(true);
    expect(api.interactiveAction).toHaveBeenCalledTimes(1);
    expect(api.interactiveAction.mock.calls[0][1]).toBe('answer');
    api.interactiveAction.mockResolvedValue({ ...paused, revision: 6,
      playback: { ...paused.playback, action_id: null }, actions: [{ ...paused.actions[0], status: 'answered' }] });
    fireEvent.click(screen.getByRole('button', { name: 'Continue lesson' }));
    await waitFor(() => expect(api.interactiveAction.mock.calls[1][1]).toBe('continue'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Play' }).disabled).toBe(false));
  });
  it('retains a saved answer when feedback fails and retries that same answer ID', async () => {
    api.interactiveAction.mockResolvedValue({ ...paused, revision: 4, error: 'Your answer is saved; feedback is pending.',
      messages: [{ id: 'saved-answer', action_id: 'a1', role: 'student', text: 'My original words.', status: 'failed' }] });
    render(<Student />);
    fireEvent.change(await screen.findByLabelText('Your answer or question'), { target: { value: 'My original words.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send answer' }));
    expect(await screen.findByText('My original words.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Retry feedback' }));
    await waitFor(() => expect(api.interactiveAction).toHaveBeenCalledTimes(2));
    expect(api.interactiveAction.mock.calls[1][2]).toMatchObject({ message_id: 'saved-answer', retry: true, expected_revision: 4 });
  });
  it('skips without starting the reading automatically', async () => {
    api.interactiveAction.mockResolvedValue({ ...paused, revision: 4, actions: [{ ...paused.actions[0], status: 'skipped' }] });
    render(<Student />);
    fireEvent.click(await screen.findByRole('button', { name: 'Skip for now' }));
    expect(await screen.findByText('Saved to revisit later.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Play' }).disabled).toBe(true);
    expect(api.interactiveAction.mock.calls[0][1]).toBe('skip');
  });
  it('restores an uploaded photo that has not been sent after reopening the lesson', async () => {
    api.conversation.mockResolvedValue({ ...paused, draft_evidence: [{ id: 'saved-photo', filename: 'work.png', size_bytes: 100 }] });
    api.interactiveAction.mockResolvedValue({ ...paused, revision: 5, draft_evidence: [], actions: [{ ...paused.actions[0], status: 'answered' }] });
    render(<Student />);
    expect(await screen.findByText('1 photo ready to send.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Send answer' }));
    await waitFor(() => expect(api.interactiveAction).toHaveBeenCalledTimes(1));
    expect(api.interactiveAction.mock.calls[0][2].evidence_ids).toEqual(['saved-photo']);
  });
});
