import { useCallback, useEffect, useRef, useState } from 'react';

/*
 * The camera for photos of book work. One stream is shared by every photo step
 * and stays on for a while after a step closes, so the next question needs no
 * new start-up or focusing. While the preview shows, frames are measured a few
 * times a second: once the page is still and sharp, the focus is locked (where
 * the camera allows it), and the photo is cropped to the page.
 */

const CONSTRAINTS = { audio: false, video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } } };
export const KEEP_ON = 120000;
const EVERY = 200;
const SMALL = 240; // width of the frame used to find the page and movement
const DETAIL = 480; // width of the centre patch, at full resolution, used for sharpness
const MAX_SIDE = 2048;
const SHARP = 0.8; // a frame this close to the sharpest seen is taken at once
const BLURRY = 0.45; // below this share of the sharpest seen, the photo is called blurry
const STILL = 4; // average grey change between frames below which the page is still

let current = null;

function stop(entry) {
  entry.dead = true;
  clearTimeout(entry.timer);
  entry.stream?.getTracks().forEach((track) => track.stop());
  if (current === entry) current = null;
}

/** Stops the shared camera at once (tests, and leaving the lesson). */
export function stopCamera() { if (current) stop(current); }

export function openCamera() {
  if (current && !current.dead) {
    current.users += 1;
    clearTimeout(current.timer);
    return current;
  }
  const entry = { users: 1, best: 0, focus: 'none', calm: 0, dim: 0, started: 0, stream: null, track: null, timer: null, dead: false };
  entry.ready = navigator.mediaDevices.getUserMedia(CONSTRAINTS).then((stream) => {
    if (entry.dead) {
      stream.getTracks().forEach((track) => track.stop());
      throw Object.assign(new Error('The camera was closed.'), { name: 'AbortError' });
    }
    entry.stream = stream;
    entry.track = stream.getVideoTracks?.()[0] || null;
    entry.track?.addEventListener?.('ended', () => stop(entry));
    startFocus(entry);
    return stream;
  }, (failure) => { stop(entry); throw failure; });
  current = entry;
  return entry;
}

export function releaseCamera(entry, keep = KEEP_ON) {
  if (!entry || entry.dead) return;
  entry.users = Math.max(0, entry.users - 1);
  if (entry.users) return;
  clearTimeout(entry.timer);
  if (keep > 0) entry.timer = setTimeout(() => stop(entry), keep);
  else stop(entry);
}

// Focus: let the camera find the page, then hold that distance.
function constrain(entry, setting) {
  try {
    Promise.resolve(entry.track.applyConstraints({ advanced: [setting] })).catch(() => { entry.focus = 'none'; });
  } catch { entry.focus = 'none'; }
}

function startFocus(entry) {
  let modes = [];
  try { modes = entry.track?.getCapabilities?.()?.focusMode || []; } catch { modes = []; }
  if (!modes.includes('continuous') || !modes.includes('manual')) return;
  entry.focus = 'searching';
  entry.started = Date.now();
  constrain(entry, { focusMode: 'continuous' });
}

export function refocus(entry) {
  if (!entry || entry.focus === 'none' || !entry.track) return;
  entry.focus = 'searching'; entry.calm = 0; entry.dim = 0; entry.started = Date.now();
  constrain(entry, { focusMode: 'continuous' });
}

function lockFocus(entry) {
  let distance;
  try { distance = entry.track.getSettings?.()?.focusDistance; } catch { distance = undefined; }
  entry.focus = 'locked'; entry.dim = 0;
  constrain(entry, typeof distance === 'number' ? { focusMode: 'manual', focusDistance: distance } : { focusMode: 'manual' });
}

export function focusStep(entry, score, still, now = Date.now()) {
  if (entry.focus === 'searching') {
    entry.calm = still && score >= 0.85 * entry.best ? entry.calm + 1 : 0;
    if (entry.calm >= 8 && now - entry.started > 2000) lockFocus(entry);
  } else if (entry.focus === 'locked') {
    // A page that stays blurry while still: the stand moved, so look again.
    entry.dim = still && score < 0.5 * entry.best ? entry.dim + 1 : 0;
    if (entry.dim >= 15) refocus(entry);
  }
}

// Measuring frames.
let small = null;
let detail = null;
function grey(canvas, video, sx, sy, sw, sh, width, height) {
  canvas.width = width; canvas.height = height;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context?.getImageData) return null;
  context.drawImage(video, sx, sy, sw, sh, 0, 0, width, height);
  const { data } = context.getImageData(0, 0, width, height);
  const values = new Uint8Array(width * height);
  for (let i = 0, j = 0; j < values.length; i += 4, j += 1) values[j] = (data[i] * 77 + data[i + 1] * 150 + data[i + 2] * 29) >> 8;
  return { values, width, height };
}

/** A small grey frame (page and movement) and a full-resolution centre patch (sharpness), or null. */
export function measure(video) {
  const vw = video?.videoWidth; const vh = video?.videoHeight;
  if (!vw || !vh || typeof document === 'undefined') return null;
  try {
    small ||= document.createElement('canvas');
    detail ||= document.createElement('canvas');
    const frame = grey(small, video, 0, 0, vw, vh, SMALL, Math.max(1, Math.round(SMALL * vh / vw)));
    if (!frame) return null;
    const pw = Math.min(DETAIL, Math.round(vw * 0.5)); const ph = Math.min(Math.round(pw * 9 / 16), vh);
    const patch = grey(detail, video, Math.round((vw - pw) / 2), Math.round((vh - ph) / 2), pw, ph, pw, ph);
    return patch && { frame, score: sharpness(patch.values, patch.width, patch.height) };
  } catch { return null; }
}

/** Variance of the Laplacian: high when edges (pencil strokes, print) are crisp. */
export function sharpness(values, width, height) {
  let sum = 0; let squares = 0; let count = 0;
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1, i = y * width + 1; x < width - 1; x += 1, i += 1) {
      const edge = 4 * values[i] - values[i - 1] - values[i + 1] - values[i - width] - values[i + width];
      sum += edge; squares += edge * edge; count += 1;
    }
  }
  if (!count) return 0;
  const mean = sum / count;
  return squares / count - mean * mean;
}

export function movement(before, after) {
  if (!before || before.length !== after.length) return Infinity;
  let total = 0;
  for (let i = 0; i < after.length; i += 1) total += Math.abs(after[i] - before[i]);
  return total / after.length;
}

function longestRun(shares, limit, gap) {
  let best = null; let start = -1; let end = -1; let missed = 0;
  const close = () => { if (start >= 0 && (!best || end - start > best[1] - best[0])) best = [start, end]; };
  shares.forEach((share, i) => {
    if (share >= limit) {
      if (start < 0) start = i;
      end = i; missed = 0;
    } else if (start >= 0 && (missed += 1) > gap) { close(); start = -1; missed = 0; }
  });
  close();
  return best;
}

/**
 * The bright page in a grey frame, as fractions of the frame
 * ({x, y, w, h}), or null when no clear page stands out from its surroundings.
 */
export function pageBox({ values, width, height }) {
  const histogram = new Array(256).fill(0);
  values.forEach((value) => { histogram[value] += 1; });
  const total = values.length;
  let all = 0;
  histogram.forEach((count, value) => { all += count * value; });
  // Otsu's threshold between the page and what surrounds it.
  let dark = 0; let darkSum = 0; let best = -1; let threshold = 128; let means = [0, 0];
  for (let value = 0; value < 256; value += 1) {
    dark += histogram[value]; darkSum += histogram[value] * value;
    const light = total - dark;
    if (!dark || !light) continue;
    const m0 = darkSum / dark; const m1 = (all - darkSum) / light;
    const between = dark * light * (m0 - m1) ** 2;
    if (between > best) { best = between; threshold = value; means = [m0, m1]; }
  }
  if (means[1] - means[0] < 40) return null;
  const columns = new Array(width).fill(0);
  for (let y = 0; y < height; y += 1) for (let x = 0; x < width; x += 1) if (values[y * width + x] > threshold) columns[x] += 1;
  const across = longestRun(columns.map((count) => count / height), 0.35, Math.round(width * 0.04));
  if (!across) return null;
  const span = across[1] - across[0] + 1;
  const rows = new Array(height).fill(0);
  for (let y = 0; y < height; y += 1) for (let x = across[0]; x <= across[1]; x += 1) if (values[y * width + x] > threshold) rows[y] += 1;
  const down = longestRun(rows.map((count) => count / span), 0.5, Math.round(height * 0.04));
  if (!down) return null;
  const margin = 0.03;
  const x0 = Math.max(0, across[0] / width - margin); const x1 = Math.min(1, (across[1] + 1) / width + margin);
  const y0 = Math.max(0, down[0] / height - margin); const y1 = Math.min(1, (down[1] + 1) / height + margin);
  const box = { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
  const area = box.w * box.h;
  return area < 0.2 || area > 0.9 ? null : box;
}

/** The photo itself: the page (or the whole frame), no longer than MAX_SIDE. */
export function render(video, box) {
  const vw = video.videoWidth; const vh = video.videoHeight;
  const sx = box ? Math.round(box.x * vw) : 0; const sy = box ? Math.round(box.y * vh) : 0;
  const sw = box ? Math.round(box.w * vw) : vw; const sh = box ? Math.round(box.h * vh) : vh;
  const scale = Math.min(1, MAX_SIDE / Math.max(sw, sh));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(sw * scale); canvas.height = Math.round(sh * scale);
  const context = canvas.getContext('2d');
  if (box) context.drawImage(video, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
  else context.drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas;
}

/** Where the page outline sits over a video shown with object-fit: contain. */
export function outline(video, box) {
  if (!video?.videoWidth || !box || !video.clientWidth) return null;
  const width = video.clientWidth; const height = video.clientHeight; const ratio = video.videoWidth / video.videoHeight;
  let shownWidth = width; let shownHeight = width / ratio;
  if (shownHeight > height) { shownHeight = height; shownWidth = height * ratio; }
  const left = video.offsetLeft + (width - shownWidth) / 2; const top = video.offsetTop + (height - shownHeight) / 2;
  return { left: left + box.x * shownWidth, top: top + box.y * shownHeight, width: box.w * shownWidth, height: box.h * shownHeight };
}

const wait = (ms) => new Promise((done) => { setTimeout(done, ms); });
const moved = (a, b) => !a !== !b || Boolean(a && ['left', 'top', 'width', 'height'].some((key) => Math.abs(a[key] - b[key]) > 4));

/**
 * The shared camera while `active`. `attach` is the preview video's ref;
 * `page` is where the page outline sits over it (pixels), or null;
 * `take()` waits briefly for a sharp frame and returns {canvas, blurry}.
 */
export function useWorkCamera(active, { keep = KEEP_ON } = {}) {
  const [stream, setStream] = useState(null);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(null);
  const handle = useRef(null);
  const video = useRef(null);

  useEffect(() => {
    if (!active) return undefined;
    let cancelled = false;
    const entry = openCamera();
    handle.current = entry;
    setError(null);
    entry.ready.then((opened) => { if (!cancelled) setStream(opened); }, (failure) => { if (!cancelled) setError(failure); });
    return () => {
      cancelled = true; handle.current = null;
      setStream(null); setPage(null);
      releaseCamera(entry, keep);
    };
  }, [active, keep]);

  const attach = useCallback((node) => {
    video.current = node;
    if (node && stream && node.srcObject !== stream) node.srcObject = stream;
  }, [stream]);

  useEffect(() => {
    if (!stream) return undefined;
    let previous = null; let count = 0;
    const timer = setInterval(() => {
      const entry = handle.current; const frame = video.current;
      if (!entry || !frame || frame.readyState < 2) return;
      const seen = measure(frame);
      if (!seen) return;
      entry.best = Math.max(seen.score, entry.best * 0.998);
      focusStep(entry, seen.score, movement(previous, seen.frame.values) < STILL);
      previous = seen.frame.values;
      if ((count += 1) % 3 === 1) {
        const found = outline(frame, pageBox(seen.frame));
        setPage((shown) => (moved(shown, found) ? found : shown));
      }
    }, EVERY);
    return () => clearInterval(timer);
  }, [stream]);

  const take = useCallback(async () => {
    const frame = video.current; const entry = handle.current;
    if (!frame?.videoWidth || !frame?.videoHeight) return null;
    const sharpest = entry?.best || 0;
    const limit = entry?.focus === 'locked' ? 500 : 1500;
    const started = Date.now();
    let chosen = null;
    for (;;) {
      const seen = measure(frame);
      if (!seen) return { canvas: render(frame, null), blurry: false };
      if (!chosen || seen.score > chosen.score) chosen = { score: seen.score, canvas: render(frame, pageBox(seen.frame)) };
      if (!sharpest || seen.score >= SHARP * sharpest || Date.now() - started >= limit) break;
      await wait(80);
    }
    const blurry = sharpest > 0 && chosen.score < BLURRY * sharpest;
    if (blurry) refocus(entry);
    return { canvas: chosen.canvas, blurry };
  }, []);

  return { attach, stream, error, page, take };
}
