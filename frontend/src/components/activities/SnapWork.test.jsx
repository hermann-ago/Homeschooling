/* @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import SnapWork from './SnapWork';
import { stopCamera } from './sharedCamera';

let stop;
let media;
beforeEach(() => {
  stop = vi.fn();
  media = { getTracks: () => [{ stop }] };
  vi.stubGlobal('navigator', { ...navigator, mediaDevices: { getUserMedia: vi.fn().mockResolvedValue(media) } });
});
afterEach(() => { cleanup(); stopCamera(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('opens the camera as soon as the step appears so one press takes the photo', async () => {
  const draw = vi.fn();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: draw });
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation((done) => done(new Blob(['synthetic'], { type: 'image/jpeg' })));
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/jpeg;base64,aW1hZ2U=');
  const onSnap = vi.fn().mockResolvedValue(true);
  render(<SnapWork onSnap={onSnap} label="Photo of all 3" />);
  const video = screen.getByLabelText('Camera');
  await waitFor(() => expect(video.srcObject).toBe(media));
  expect(screen.getByRole('button', { name: /Opening the camera/ }).disabled).toBe(true);
  Object.defineProperties(video, { videoWidth: { value: 1920 }, videoHeight: { value: 1080 } });
  fireEvent.loadedData(video);
  fireEvent.click(screen.getByRole('button', { name: /Photo of all 3/ }));
  expect(await screen.findByAltText('The photo you took')).toBeTruthy();
  expect(draw).toHaveBeenCalledWith(video, 0, 0, 1920, 1080);
  await waitFor(() => expect(onSnap).toHaveBeenCalledOnce(), { timeout: 3000 });
  expect(onSnap.mock.calls[0][0].type).toBe('image/jpeg');
  expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledOnce();
});

it('keeps the camera on for the next photo step instead of starting it again', async () => {
  const first = render(<SnapWork onSnap={vi.fn()} />);
  await waitFor(() => expect(screen.getByLabelText('Camera').srcObject).toBe(media));
  first.unmount();
  expect(stop).not.toHaveBeenCalled();
  render(<SnapWork onSnap={vi.fn()} />);
  await waitFor(() => expect(screen.getByLabelText('Camera').srcObject).toBe(media));
  expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledOnce();
});

it('turns the camera off on request and back on with the photo button', async () => {
  render(<SnapWork onSnap={vi.fn()} />);
  await waitFor(() => expect(screen.getByLabelText('Camera').srcObject).toBe(media));
  fireEvent.click(screen.getByRole('button', { name: 'Turn the camera off' }));
  expect(screen.queryByLabelText('Camera')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Photo of my work' }));
  await waitFor(() => expect(screen.getByLabelText('Camera').srcObject).toBe(media));
});
