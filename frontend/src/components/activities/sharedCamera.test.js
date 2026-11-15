import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { focusStep, KEEP_ON, openCamera, pageBox, releaseCamera, sharpness, stopCamera } from './sharedCamera';

let stop;
let track;
beforeEach(() => {
  stop = vi.fn();
  track = { stop, getCapabilities: () => ({ focusMode: ['continuous', 'manual'] }), getSettings: () => ({ focusDistance: 0.3 }),
    applyConstraints: vi.fn().mockResolvedValue(undefined) };
  vi.stubGlobal('navigator', { mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track], getVideoTracks: () => [track] }) } });
});
afterEach(() => { stopCamera(); vi.useRealTimers(); vi.unstubAllGlobals(); });

const frame = (width, height, value) => ({ width, height, values: Uint8Array.from({ length: width * height }, (_, i) => value(i % width, Math.floor(i / width))) });

it('scores crisp edges above the same pattern blurred', () => {
  const crisp = frame(40, 40, (x) => (x % 4 < 2 ? 0 : 255));
  const soft = frame(40, 40, (x) => [64, 128, 192, 128][x % 4]);
  expect(sharpness(crisp.values, 40, 40)).toBeGreaterThan(sharpness(soft.values, 40, 40) * 4);
});

it('finds a bright upright page in a landscape frame and leaves a plain frame uncropped', () => {
  // A page across columns 80–159 with a few lines of writing, on a dark table.
  const page = frame(240, 135, (x, y) => (x < 80 || x >= 160 ? 50 : y % 12 === 0 && x > 90 && x < 150 ? 20 : 235));
  const box = pageBox(page);
  expect(box.x).toBeCloseTo(80 / 240 - 0.03, 2);
  expect(box.x + box.w).toBeCloseTo(160 / 240 + 0.03, 2);
  expect(box.h).toBeCloseTo(1, 2);
  expect(pageBox(frame(240, 135, () => 200))).toBeNull();
  // A page that already fills the picture needs no crop.
  expect(pageBox(frame(240, 135, (x) => (x < 4 ? 40 : 230)))).toBeNull();
});

it('locks the focus once the page is still and sharp, and looks again when it stays blurry', async () => {
  const entry = openCamera();
  await entry.ready;
  expect(track.applyConstraints).toHaveBeenLastCalledWith({ advanced: [{ focusMode: 'continuous' }] });
  entry.best = 100;
  const later = Date.now() + 3000;
  for (let i = 0; i < 7; i += 1) focusStep(entry, 95, true, later);
  expect(entry.focus).toBe('searching');
  focusStep(entry, 95, false, later); // the child's hand moved: start counting again
  for (let i = 0; i < 8; i += 1) focusStep(entry, 95, true, later);
  expect(entry.focus).toBe('locked');
  expect(track.applyConstraints).toHaveBeenLastCalledWith({ advanced: [{ focusMode: 'manual', focusDistance: 0.3 }] });
  for (let i = 0; i < 15; i += 1) focusStep(entry, 20, true, later);
  expect(entry.focus).toBe('searching');
  expect(track.applyConstraints).toHaveBeenLastCalledWith({ advanced: [{ focusMode: 'continuous' }] });
});

it('leaves the focus alone on a camera that cannot lock it', async () => {
  track.getCapabilities = () => ({});
  const entry = openCamera();
  await entry.ready;
  for (let i = 0; i < 20; i += 1) focusStep(entry, 100, true, Date.now() + 5000);
  expect(entry.focus).toBe('none');
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
