/* @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import WorkCamera from './WorkCamera';
import ResponseCapture from './ResponseCapture';

let stop;
let media;
beforeEach(() => {
  window.localStorage.clear();
  stop = vi.fn();
  media = { getTracks: () => [{ stop }] };
  vi.stubGlobal('navigator', { ...navigator, mediaDevices: { getUserMedia: vi.fn().mockResolvedValue(media) } });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('opens the webcam with no microphone and cancels without uploading', async () => {
  const upload = vi.fn(); const close = vi.fn();
  const view = render(<WorkCamera onPhoto={upload} onClose={close} />);
  await waitFor(() => expect(screen.getByLabelText('Webcam preview').srcObject).toBe(media));
  expect(navigator.mediaDevices.getUserMedia.mock.calls[0][0]).toMatchObject({ audio: false });
  expect(screen.getByRole('button', { name: 'Take photo', exact: true }).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(close).toHaveBeenCalledOnce();
  view.unmount();
  expect(stop).toHaveBeenCalledOnce();
  expect(upload).not.toHaveBeenCalled();
});

it('releases a camera even if permission resolves after the preview was closed', async () => {
  let resolve;
  navigator.mediaDevices.getUserMedia.mockReturnValue(new Promise((done) => { resolve = done; }));
  const view = render(<WorkCamera onPhoto={vi.fn()} onClose={vi.fn()} />);
  view.unmount(); resolve(media);
  await waitFor(() => expect(stop).toHaveBeenCalledOnce());
});

it('captures a readable frame, stops the webcam, and uploads only after confirmation', async () => {
  const upload = vi.fn().mockResolvedValue(true); const close = vi.fn();
  const draw = vi.fn();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: draw });
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/jpeg;base64,aW52ZW50ZWQtaW1hZ2U=');
  render(<WorkCamera onPhoto={upload} onClose={close} />);
  const video = screen.getByLabelText('Webcam preview');
  await waitFor(() => expect(video.srcObject).toBe(media));
  Object.defineProperties(video, { videoWidth: { value: 1920 }, videoHeight: { value: 1080 } });
  fireEvent.loadedData(video);
  fireEvent.click(screen.getByRole('button', { name: 'Take photo', exact: true }));
  expect(draw).toHaveBeenCalledWith(video, 0, 0, 1920, 1080);
  expect(stop).toHaveBeenCalledOnce();
  expect(screen.getByAltText('Preview of your work')).toBeTruthy();
  expect(upload).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Use this photo' }));
  await waitFor(() => expect(close).toHaveBeenCalledOnce());
  const file = upload.mock.calls[0][0];
  expect(file).toBeInstanceOf(File);
  expect(file.type).toBe('image/jpeg');
});

it('keeps the captured picture available when saving fails', async () => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: vi.fn() });
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/jpeg;base64,aW1hZ2U=');
  const close = vi.fn();
  render(<WorkCamera onPhoto={vi.fn().mockResolvedValue(false)} onClose={close} />);
  const video = screen.getByLabelText('Webcam preview');
  await waitFor(() => expect(video.srcObject).toBe(media));
  Object.defineProperties(video, { videoWidth: { value: 640 }, videoHeight: { value: 480 } });
  fireEvent.loadedData(video); fireEvent.click(screen.getByRole('button', { name: 'Take photo', exact: true }));
  fireEvent.click(screen.getByRole('button', { name: 'Use this photo' }));
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('not saved'));
  expect(screen.getByAltText('Preview of your work')).toBeTruthy();
  expect(close).not.toHaveBeenCalled();
});

it('explains denied permission and never opens the file picker automatically', async () => {
  navigator.mediaDevices.getUserMedia.mockRejectedValue({ name: 'NotAllowedError' });
  const upload = vi.fn(); const picker = vi.spyOn(HTMLInputElement.prototype, 'click');
  render(<ResponseCapture sessionId="synthetic-camera" activity={{ id: 'one', interaction: { id: 'first' },
    content: { response_modes: ['text', 'photo'] } }} onUpload={upload} onSubmit={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: 'Take photo of my work' }));
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Camera permission'));
  expect(picker).not.toHaveBeenCalled();
  expect(upload).not.toHaveBeenCalled();
});
