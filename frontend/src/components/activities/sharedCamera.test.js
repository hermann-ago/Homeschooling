/* @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { KEEP_ON, STALLED, findFocus, openCamera, releaseCamera, sharpness, stopCamera, useWorkCamera } from './sharedCamera';

let stop;
let track;
beforeEach(() => {
  stop = vi.fn();
  track = { stop, getCapabilities: () => ({ focusMode: ['continuous', 'manual'] }), getSettings: () => ({ focusDistance: 0.3 }),
    applyConstraints: vi.fn().mockResolvedValue(undefined) };
  vi.stubGlobal('navigator', { ...navigator, mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track], getVideoTracks: () => [track] }) } });
});
afterEach(() => { stopCamera(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); window.localStorage.clear(); });

const frame = (width, height, value) => ({ width, height, values: Uint8Array.from({ length: width * height }, (_, i) => value(i % width, Math.floor(i / width))) });

it('scores crisp edges above the same pattern blurred', () => {
  const crisp = frame(40, 40, (x) => (x % 4 < 2 ? 0 : 255));
  const soft = frame(40, 40, (x) => [64, 128, 192, 128][x % 4]);
  expect(sharpness(crisp.values, 40, 40)).toBeGreaterThan(sharpness(soft.values, 40, 40) * 4);
});

it("never changes the camera's own focus", async () => {
  await openCamera().ready;
  expect(track.applyConstraints).not.toHaveBeenCalled();
});

it('shares one camera between photo steps and turns it off a while after the last one closes', async () => {
  vi.useFakeTimers();
  const first = openCamera();
  await first.ready;
  releaseCamera(first);
  const next = openCamera();
  expect(next).toBe(first);
  expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledOnce();
  releaseCamera(next);
  vi.advanceTimersByTime(KEEP_ON - 1);
  expect(stop).not.toHaveBeenCalled();
  vi.advanceTimersByTime(1);
  expect(stop).toHaveBeenCalledOnce();
  openCamera();
  expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledTimes(2);
});

const preview = () => { let frames = 0; return { readyState: 4, paused: false, srcObject: null, getVideoPlaybackQuality: () => ({ totalVideoFrames: frames }), next() { frames += 1; } }; };

it('starts a frozen camera again, and after repeated freezes says so instead of a stuck preview', async () => {
  vi.useFakeTimers();
  const view = renderHook(() => useWorkCamera(true));
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  const video = preview();
  act(() => view.result.current.attach(video));
  for (let i = 0; i < 3; i += 1) { video.next(); act(() => { vi.advanceTimersByTime(500); }); }
  expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledOnce();
  act(() => { vi.advanceTimersByTime(STALLED + 500); }); // the picture stopped moving
  expect(stop).toHaveBeenCalledOnce();
  expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledTimes(2);
  for (let round = 0; round < 2; round += 1) {
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    act(() => view.result.current.attach(video));
    video.next(); act(() => { vi.advanceTimersByTime(500); });
    act(() => { vi.advanceTimersByTime(STALLED + 500); });
  }
  expect(view.result.current.error?.name).toBe('StalledError');
  view.unmount();
});

// A lens that is sharpest at 0.42: the stripes it "sees" lose contrast away from there.
function lens() {
  let distance = 0;
  track.label = 'Desk camera';
  track.getCapabilities = () => ({ focusMode: ['continuous', 'manual'], focusDistance: { min: 0, max: 1, step: 0.01 } });
  track.applyConstraints = vi.fn(async ({ advanced: [setting] }) => { if (typeof setting.focusDistance === 'number') distance = setting.focusDistance; });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    drawImage() {},
    getImageData(x, y, width, height) {
      const contrast = 120 / (1 + 40 * Math.abs(distance - 0.42));
      const data = new Uint8ClampedArray(width * height * 4);
      for (let i = 0; i < width * height; i += 1) { const v = 128 + ((i % width) % 2 ? contrast : -contrast); data.set([v, v, v, 255], i * 4); }
      return { data };
    },
  });
  let frames = 0;
  return { videoWidth: 64, videoHeight: 36, getVideoPlaybackQuality: () => ({ totalVideoFrames: (frames += 1) }) };
}

it('finds the sharpest focus by stepping the lens, locks it and remembers it for this camera', async () => {
  vi.useFakeTimers();
  const video = lens();
  const entry = openCamera();
  await entry.ready;
  const found = findFocus(entry, video);
  await vi.runAllTimersAsync();
  const distance = await found;
  expect(Math.abs(distance - 0.42)).toBeLessThanOrEqual(0.05);
  expect(track.applyConstraints).toHaveBeenLastCalledWith({ advanced: [{ focusMode: 'manual', focusDistance: distance }] });
  expect(entry.locked).toBe(distance);
  expect(JSON.parse(window.localStorage.getItem('work-camera-focus'))['Desk camera']).toBe(distance);
  stopCamera();
  track.applyConstraints.mockClear();
  await openCamera().ready; // the camera started again: the same focus comes back without a new search
  expect(track.applyConstraints).toHaveBeenCalledOnce();
  expect(track.applyConstraints).toHaveBeenCalledWith({ advanced: [{ focusMode: 'manual', focusDistance: distance }] });
});

it('offers the Focus button only to a camera the app can focus', async () => {
  const shown = async () => {
    const view = renderHook(() => useWorkCamera(true));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    const available = view.result.current.focus.available;
    view.unmount(); stopCamera();
    return available;
  };
  track.getCapabilities = () => ({ focusMode: ['continuous'] });
  expect(await shown()).toBe(false);
  track.getCapabilities = () => ({ focusMode: ['continuous', 'single-shot'] });
  expect(await shown()).toBe(true);
  track.getCapabilities = () => ({ focusMode: ['continuous', 'manual'], focusDistance: { min: 0, max: 2 } });
  expect(await shown()).toBe(true);
});
