// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import FeedbackVoice from './FeedbackVoice';
import { tutorApi } from '../api/tutor';

vi.mock('../api/tutor', () => ({ tutorApi: { feedbackAudio: vi.fn(), actionAudio: vi.fn(), audioManifest: vi.fn(), audioPart: vi.fn() } }));
beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  window.speechSynthesis = { cancel: vi.fn(), speak: vi.fn() };
  vi.stubGlobal('SpeechSynthesisUtterance', class { constructor(text) { this.text = text; } });
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks(); vi.unstubAllGlobals(); });

it('requests saved feedback by message ID and plays its recording', async () => {
  tutorApi.feedbackAudio.mockResolvedValueOnce({ track_id: 'saved-track' });
  tutorApi.audioManifest.mockResolvedValue({ tracks: [{ index: 0 }] });
  tutorApi.audioPart.mockResolvedValue('blob:saved-feedback');
  const { container } = render(<FeedbackVoice session="lesson" message={{ id: 'reply', text: 'Well done.' }} language="en-US" />);
  fireEvent.click(screen.getByRole('button', { name: 'Read aloud' }));
  await waitFor(() => expect(container.querySelector('audio')?.src).toBe('blob:saved-feedback'));
  expect(tutorApi.feedbackAudio.mock.calls).toEqual([['lesson', 'reply', false]]);
  expect(window.speechSynthesis.speak).not.toHaveBeenCalled();
});

it('offers device speech when paid voice is paused without switching automatically', async () => {
  tutorApi.feedbackAudio.mockRejectedValue(new Error('Billing paused'));
  render(<FeedbackVoice session="lesson" message={{ id: 'reply', text: 'Muito bem.' }} language="pt-BR" />);
  fireEvent.click(screen.getByRole('button', { name: 'Read aloud' }));
  await screen.findByText('Billing paused');
  expect(tutorApi.feedbackAudio).toHaveBeenCalledTimes(1);
  expect(window.speechSynthesis.speak).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('Use device voice'));
  expect(window.speechSynthesis.speak.mock.calls[0][0]).toMatchObject({ text: 'Muito bem.', lang: 'pt-BR' });
});

it('retrieves saved recall narration by action ID', async () => {
  tutorApi.actionAudio.mockResolvedValueOnce({ allowed: true }).mockResolvedValueOnce({ track_id: 'recall' });
  tutorApi.audioManifest.mockResolvedValue({ tracks: [{ index: 0 }] }); tutorApi.audioPart.mockResolvedValue('blob:recall');
  const { container } = render(<FeedbackVoice session="lesson" message={{ id: 'warmup', text: 'What connected the places?' }} language="en-US" action />);
  fireEvent.click(screen.getByRole('button', { name: 'Read aloud' }));
  await waitFor(() => expect(container.querySelector('audio')?.src).toBe('blob:recall'));
  expect(tutorApi.actionAudio.mock.calls).toEqual([['lesson', 'warmup', true], ['lesson', 'warmup', false]]);
  expect(tutorApi.feedbackAudio).not.toHaveBeenCalled();
});

it('prepares a new reply once with the selected lesson voice and cancels late autoplay', async () => {
  let finish;
  tutorApi.feedbackAudio.mockImplementationOnce(()=>new Promise((resolve)=>{finish=resolve;}));
  tutorApi.audioManifest.mockResolvedValue({tracks:[{}]});tutorApi.audioPart.mockResolvedValue('blob:late');
  const view=render(<FeedbackVoice session="lesson" message={{id:'new-reply',text:'A clear answer.'}} trackId="lesson-google" autoPlay />);
  await waitFor(()=>expect(tutorApi.feedbackAudio).toHaveBeenCalledTimes(1));
  view.rerender(<FeedbackVoice session="lesson" message={{id:'new-reply',text:'A clear answer.'}} trackId="lesson-google" autoPlay />);
  expect(tutorApi.feedbackAudio).toHaveBeenCalledTimes(1);
  expect(tutorApi.feedbackAudio.mock.calls[0]).toEqual(['lesson','new-reply',false,'lesson-google']);
  view.unmount();finish({track_id:'late'});
  await waitFor(()=>expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:late'));
});

it('does not send a paid request for a saved task if the lesson moved on during its estimate', async () => {
  let finish;
  tutorApi.actionAudio.mockImplementationOnce(()=>new Promise((resolve)=>{finish=resolve;}));
  const view=render(<FeedbackVoice session="lesson" message={{id:'task',text:'A task.'}} action autoPlay />);
  await waitFor(()=>expect(tutorApi.actionAudio).toHaveBeenCalledTimes(1));
  view.unmount();finish({allowed:true});
  await Promise.resolve();await Promise.resolve();
  expect(tutorApi.actionAudio).toHaveBeenCalledTimes(1);
});

it('holds a new reply until its voice is ready, and never past the limit', async () => {
  let finish;
  tutorApi.feedbackAudio.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
  tutorApi.audioManifest.mockResolvedValue({ tracks: [{}] }); tutorApi.audioPart.mockResolvedValue('blob:ready');
  const { container } = render(<FeedbackVoice session="lesson" message={{ id: 'new', text: 'Nice.' }} autoPlay />);
  expect(container.querySelector('.feedback-voice').dataset.holding).toBe('true');
  expect(screen.getByRole('status', { name: 'Your tutor is answering' })).toBeTruthy();
  await waitFor(() => expect(tutorApi.feedbackAudio).toHaveBeenCalledTimes(1));
  finish({ track_id: 'ready' });
  await waitFor(() => expect(container.querySelector('audio')?.src).toBe('blob:ready'));
  expect(container.querySelector('.feedback-voice').dataset.holding).toBeUndefined();
});

it('shows the words at once when the voice cannot be prepared, and for earlier replies', async () => {
  tutorApi.feedbackAudio.mockRejectedValue(new Error('Billing paused'));
  const failed = render(<FeedbackVoice session="lesson" message={{ id: 'new', text: 'Nice.' }} autoPlay />);
  await screen.findByText('Billing paused');
  expect(failed.container.querySelector('.feedback-voice').dataset.holding).toBeUndefined();
  const earlier = render(<FeedbackVoice session="lesson" message={{ id: 'old', text: 'Before.' }} />);
  expect(earlier.container.querySelector('.feedback-voice').dataset.holding).toBeUndefined();
});
