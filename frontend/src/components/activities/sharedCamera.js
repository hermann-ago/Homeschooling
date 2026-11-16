import { useCallback, useEffect, useRef, useState } from 'react';

/*
 * The camera for photos of book work. One stream is shared by every photo step
 * and stays on for a while after a step closes, so the next question needs no
 * new start-up. The camera keeps its own focus. The preview is left alone while
 * it shows: frames are measured only during a press, which waits briefly for a
 * sharp one, and a photo much softer than earlier ones is offered for a retake.
 * The whole frame is sent. A preview whose picture stops moving (the camera
 * froze, dropped out or slept) is started again instead of staying stuck.
 */

const CONSTRAINTS = { audio: false, video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } } };
export const KEEP_ON = 120000;
export const STALLED = 3000; // a running picture that stops this long: start the camera again
export const STARTING = 8000; // a camera may take this long to show its first picture
const RESTARTS = 2; // in a row without a moving picture; then the step offers a saved photo
const WATCH = 500;
const DETAIL = 480; // width of the centre patch, at full resolution, used for sharpness
const MAX_SIDE = 2048;
const WAIT_FOR_SHARP = 1200;
const SHARP = 0.8; // a frame this close to the sharpest seen is taken at once
const BLURRY = 0.45; // below this share of the sharpest seen, the photo is called blurry

let current = null;

function stop(entry) {
  if (entry.dead) return;
  entry.dead = true;
  clearTimeout(entry.timer);
  entry.stream?.getTracks().forEach((track) => track.stop());
  if (current === entry) current = null;
  [...entry.closed].forEach((closed) => closed());
}

/** Stops the shared camera at once (tests, and leaving the lesson). */
export function stopCamera() { if (current) stop(current); }

export function openCamera() {
  if (current && !current.dead) {
    current.users += 1;
    clearTimeout(current.timer);
    return current;
  }
  const entry = { users: 1, best: 0, stream: null, timer: null, dead: false, closed: new Set() };
  entry.ready = navigator.mediaDevices.getUserMedia(CONSTRAINTS).then((stream) => {
    if (entry.dead) {
      stream.getTracks().forEach((track) => track.stop());
      throw Object.assign(new Error('The camera was closed.'), { name: 'AbortError' });
    }
    entry.stream = stream;
    stream.getVideoTracks?.()[0]?.addEventListener?.('ended', () => stop(entry));
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

// Measuring frames.
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

/** The sharpness of a full-resolution patch from the middle of the frame, or null. */
export function measure(video) {
  const vw = video?.videoWidth; const vh = video?.videoHeight;
  if (!vw || !vh || typeof document === 'undefined') return null;
  try {
    detail ||= document.createElement('canvas');
    const pw = Math.min(DETAIL, Math.round(vw * 0.5)); const ph = Math.min(Math.round(pw * 9 / 16), vh);
    const patch = grey(detail, video, Math.round((vw - pw) / 2), Math.round((vh - ph) / 2), pw, ph, pw, ph);
    return patch ? sharpness(patch.values, patch.width, patch.height) : null;
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

/** The photo itself: the whole frame, no longer than MAX_SIDE. */
export function render(video) {
  const scale = Math.min(1, MAX_SIDE / Math.max(video.videoWidth, video.videoHeight));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(video.videoWidth * scale); canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas;
}

/** How many pictures the preview has drawn (its play time where the browser does not count frames). */
function framesShown(video) {
  const frames = video.getVideoPlaybackQuality?.().totalVideoFrames;
  return Number.isFinite(frames) && frames > 0 ? frames : video.currentTime;
}

const wait = (ms) => new Promise((done) => { setTimeout(done, ms); });

/**
 * The shared camera while `active`. `attach` is the preview video's ref;
 * `take()` waits briefly for a sharp frame and returns {canvas, blurry}.
 */
export function useWorkCamera(active, { keep = KEEP_ON } = {}) {
  const [stream, setStream] = useState(null);
  const [error, setError] = useState(null);
  const [attempt, setAttempt] = useState(0);
  const handle = useRef(null);
  const video = useRef(null);
  const restarts = useRef(0);

  useEffect(() => {
    if (!active) { restarts.current = 0; return undefined; }
    let cancelled = false;
    const entry = openCamera();
    handle.current = entry;
    setError(null);
    // The camera closed or froze under this step: open it again, a couple of times at most.
    const closed = () => {
      if (cancelled) return;
      setStream(null);
      if (restarts.current >= RESTARTS) { setError(Object.assign(new Error('The camera stopped sending pictures.'), { name: 'StalledError' })); return; }
      restarts.current += 1;
      setAttempt((count) => count + 1);
    };
    entry.closed.add(closed);
    entry.ready.then((opened) => { if (!cancelled) setStream(opened); }, (failure) => {
      if (!cancelled && failure?.name !== 'AbortError') setError(failure);
    });
    return () => {
      cancelled = true; handle.current = null;
      entry.closed.delete(closed);
      setStream(null);
      releaseCamera(entry, keep);
    };
  }, [active, keep, attempt]);

  const attach = useCallback((node) => {
    video.current = node;
    if (node && stream && node.srcObject !== stream) node.srcObject = stream;
  }, [stream]);

  // Watch the preview without touching its pixels: a picture that never starts or stops moving is a stuck camera.
  useEffect(() => {
    if (!stream) return undefined;
    let shown = -1; let since = Date.now(); let moved = 0;
    const timer = setInterval(() => {
      const entry = handle.current; const frame = video.current;
      // No live preview on screen (a photo is shown, or the page is hidden): nothing to judge.
      if (!entry || !frame || document.hidden || frame.paused && frame.readyState >= 2) { since = Date.now(); return; }
      const count = frame.readyState >= 2 ? framesShown(frame) : -1;
      if (count !== -1 && count !== shown) {
        shown = count; since = Date.now(); moved += 1;
        if (moved > 4) restarts.current = 0;
      } else if (Date.now() - since >= (shown === -1 ? STARTING : STALLED)) {
        stop(entry);
      }
    }, WATCH);
    return () => clearInterval(timer);
  }, [stream]);

  const take = useCallback(async () => {
    const frame = video.current; const entry = handle.current;
    if (!frame?.videoWidth || !frame?.videoHeight) return null;
    const started = Date.now();
    let chosen = null; let sharpest = entry?.best || 0;
    for (;;) {
      const score = measure(frame);
      if (score === null) return { canvas: render(frame), blurry: false };
      if (!chosen || score > chosen.score) chosen = { score, canvas: render(frame) };
      if (!sharpest && chosen && Date.now() - started >= 300) break; // the first photo: the best of a few frames
      if (sharpest && score >= SHARP * sharpest || Date.now() - started >= WAIT_FOR_SHARP) break;
      await wait(100);
    }
    const blurry = sharpest > 0 && chosen.score < BLURRY * sharpest;
    sharpest = Math.max(chosen.score, sharpest * 0.9);
    if (entry && !blurry) entry.best = sharpest;
    return { canvas: chosen.canvas, blurry };
  }, []);

  return { attach, stream, error, take };
}
