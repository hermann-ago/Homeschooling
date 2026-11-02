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

it('explains the HTTP network restriction and offers setup and a saved-photo preview without an automatic upload', async () => {
  vi.stubGlobal('isSecureContext', false);
  vi.stubGlobal('navigator', { ...navigator, mediaDevices: undefined });
  const upload = vi.fn().mockResolvedValue(true);
  render(<WorkCamera onPhoto={upload} onClose={vi.fn()} />);
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('HTTP network connection'));
  expect(screen.getByRole('link', { name: 'Set up the secure browser camera connection' }).getAttribute('href')).toMatch(/#camera-access$/);
  expect(screen.getByRole('button', { name: 'Choose a saved photo' }).disabled).toBe(false);
  expect(screen.getByRole('button', { name: 'Take photo', exact: true }).disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('Choose work photo'), { target: { files: [new File(['synthetic'], 'work.png', { type: 'image/png' })] } });
  await screen.findByAltText('Preview of your work');
  expect(upload).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Use this photo' }));
  await waitFor(() => expect(upload).toHaveBeenCalledOnce());
  expect(upload.mock.calls[0][0].type).toBe('image/png');
  expect(upload.mock.calls[0][0].name).toMatch(/\.png$/);
});

it('offers the local Windows Camera app on an HTTP network computer without requiring certificates or an embedded preview', async () => {
  vi.stubGlobal('isSecureContext', false);
  vi.stubGlobal('navigator', { platform: 'Win32', userAgent: 'Windows Chrome', mediaDevices: undefined });
  const upload = vi.fn();
  const picker = vi.spyOn(HTMLInputElement.prototype, 'click');
  render(<WorkCamera onPhoto={upload} onClose={vi.fn()} />);
  expect(screen.getByRole('link', { name: 'Open Windows Camera' }).getAttribute('href')).toBe('microsoft.windows.camera:');
  expect(screen.getByText(/No certificate setup is needed/)).toBeTruthy();
  expect(screen.queryByLabelText('Webcam preview')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Take photo', exact: true })).toBeNull();
  expect(screen.queryByRole('alert')).toBeNull();
  expect(upload).not.toHaveBeenCalled();
  expect(picker).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Choose a saved photo' }));
  expect(picker).toHaveBeenCalledOnce();
});
