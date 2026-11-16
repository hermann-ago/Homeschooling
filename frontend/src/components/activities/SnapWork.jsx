import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Camera, CameraOff, Focus, ImagePlus, Keyboard } from 'lucide-react';
import { Button } from '../../ui';
import { useWorkCamera } from './sharedCamera';

const SEND_AFTER = 1200;
const TYPES = ['image/jpeg', 'image/png', 'image/webp'];

/**
 * One-button photo of book work. With a live camera the preview opens as soon
 * as the tutor has finished reading the step (`holdCamera` until then, so the
 * preview does not cover the text; the photo button opens it early), and the
 * camera has found the page by the time the child finishes writing. One press
 * takes a sharp picture, and it sends itself after a moment unless the child
 * retakes it. Without a live
 * camera (plain HTTP, no webcam) the device's own camera or photo picker
 * stands in. Where the camera allows it, a Focus button finds the sharpest focus
 * and keeps it for the lesson, until it is pressed again.
 */
export default function SnapWork({ onSnap, busy, holdCamera = false, label = 'Photo of my work', viewSlot = null, onType, typeLabel = 'Answer here instead', TypeIcon = Keyboard }) {
  const live = Boolean(navigator.mediaDevices?.getUserMedia) && window.isSecureContext !== false;
  // idle | camera | focusing | taken | blurry | sending
  const [stage, setStage] = useState(live && !holdCamera ? 'camera' : 'idle');
  const [preview, setPreview] = useState(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const picker = useRef(null);
  const main = useRef(null);
  const acted = useRef(false);
  const opened = useRef(live && !holdCamera);
  const file = useRef(null);
  const cameraOn = ['camera', 'focusing', 'taken', 'blurry'].includes(stage);
  const { attach, take: shoot, error: cameraError, focus } = useWorkCamera(live && cameraOn);
  const [focusNote, setFocusNote] = useState('');
  const showVideo = stage === 'camera' || stage === 'focusing';

  useEffect(() => {
    if (!cameraError) return;
    setError(cameraError.name === 'NotAllowedError' ? 'Allow camera access for this app, or choose a photo.'
      : cameraError.name === 'StalledError' ? 'The camera stopped sending a picture. Press the photo button to try again, or choose a photo.'
      : 'The camera could not open. Choose a photo instead.');
    setStage('idle');
  }, [cameraError]);
  useEffect(() => { if (!showVideo) setReady(false); }, [showVideo]);
  // Once the tutor has finished reading, the camera opens by itself: once, and never after the child turned it off.
  useEffect(() => {
    if (!live || holdCamera || opened.current || acted.current) return;
    opened.current = true;
    setStage('camera');
  }, [live, holdCamera]);

  const send = async () => {
    setStage('sending'); setError('');
    const sent = await Promise.resolve(onSnap(file.current)).catch(() => false);
    if (!sent) { setError('The photo was not sent. Please try again.'); setStage(live ? 'camera' : 'idle'); }
  };
  const sendRef = useRef(send);
  useEffect(() => { sendRef.current = send; });
  useEffect(() => {
    if (stage !== 'taken') return undefined;
    const timer = setTimeout(() => sendRef.current(), SEND_AFTER);
    return () => clearTimeout(timer);
  }, [stage]);
  // Space reaches the step's main button by itself; focus follows only the child's own presses.
  useEffect(() => { if (acted.current && stage !== 'idle') main.current?.focus(); }, [stage, ready]);

  const act = (next) => { acted.current = true; setError(''); next(); };
  const take = async () => {
    if (!ready || stage !== 'camera') return;
    setStage('focusing');
    const shot = await shoot().catch(() => null);
    if (!shot) { setError('The picture could not be taken. Please try again.'); setStage('camera'); return; }
    shot.canvas.toBlob((blob) => {
      if (!blob) { setError('The picture could not be taken. Please try again.'); setStage('camera'); return; }
      file.current = new File([blob], `work-${Date.now()}.jpg`, { type: 'image/jpeg' });
      setPreview(shot.canvas.toDataURL('image/jpeg', 0.6));
      setStage(shot.blurry ? 'blurry' : 'taken');
    }, 'image/jpeg', 0.9);
  };
  const chosen = (picked) => {
    if (!picked) return;
    if (!TYPES.includes(picked.type) || picked.size > 10 * 1024 * 1024) { setError('Use a JPG, PNG or WebP photo smaller than 10 MB.'); return; }
    file.current = picked; setPreview(null); void send();
  };
  const lockFocus = async () => {
    setFocusNote('Finding the sharpest focus…');
    const found = await focus.find();
    setFocusNote(found ? 'Focus locked. It stays for the lesson; press Focus again to find it anew.' : 'The focus could not be set. The camera keeps focusing by itself.');
  };
  useEffect(() => {
    if (!focusNote || focus.focusing) return undefined;
    const timer = setTimeout(() => setFocusNote(''), 4000);
    return () => clearTimeout(timer);
  }, [focusNote, focus.focusing]);
  const repeat = (event) => { if (event.repeat && ['Enter', ' '].includes(event.key)) event.preventDefault(); };

  // The preview and any problem open above the text box; the buttons stay in the control row.
  const above = <>
    {cameraOn && <div className="snap-view">
      {!showVideo && preview ? <img src={preview} alt="The photo you took" /> :
        <video ref={attach} autoPlay muted playsInline aria-label="Camera" onLoadedData={() => setReady(true)} />}
    </div>}
    {showVideo && focusNote && <p role="status" className="text-sm font-semibold text-action">{focusNote}</p>}
    {error && <p role="alert" className="text-sm text-problem">{error}</p>}
  </>;
  const extras = <>
    {live && <button type="button" className="tutor-icon-button snap-extra" aria-label="Choose a saved photo" title="Choose a saved photo" disabled={busy} onClick={() => picker.current?.click()}><ImagePlus size={18} aria-hidden="true" /></button>}
    {onType && <button type="button" className="tutor-icon-button snap-extra" aria-label={typeLabel} title={typeLabel} disabled={busy} onClick={onType}><TypeIcon size={18} aria-hidden="true" /></button>}
  </>;
  return <div className="snap-work">
    {viewSlot ? createPortal(above, viewSlot) : above}
    <input ref={picker} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" className="hidden" aria-label="Photo of my work"
      onChange={(event) => { chosen(event.target.files?.[0]); event.target.value = ''; }} />
    {stage === 'idle' && <>
      <Button ref={main} data-lesson-primary variant="primary" icon={Camera} disabled={busy} onKeyDown={repeat}
        onClick={() => act(() => { if (live) setStage('camera'); else picker.current?.click(); })}>{label}</Button>
      {extras}
    </>}
    {showVideo && <>
      <button type="button" className="tutor-icon-button snap-extra" aria-label="Turn the camera off" title="Turn the camera off" disabled={focus.focusing} onClick={() => act(() => setStage('idle'))}><CameraOff size={18} aria-hidden="true" /></button>
      {focus.available && <button type="button" className="tutor-icon-button snap-extra" aria-pressed={focus.locked}
        aria-label={focus.locked ? 'Focus again' : 'Find the focus and lock it'} title={focus.locked ? 'Focus locked · press to find it again' : 'Find the sharpest focus and keep it'}
        disabled={!ready || focus.focusing || stage === 'focusing'} onClick={() => { setError(''); void lockFocus(); }}><Focus size={18} aria-hidden="true" /></button>}
      {extras}
      <Button ref={main} data-lesson-primary variant="primary" icon={Camera} disabled={busy || !ready || stage === 'focusing' || focus.focusing} onKeyDown={repeat} onClick={() => act(take)}>
        {stage === 'focusing' || focus.focusing ? 'Focusing…' : ready ? label : 'Opening the camera…'}</Button>
    </>}
    {stage === 'taken' && <>
      <p role="status" className="text-sm font-semibold text-action">Sending…</p>
      <Button onClick={() => act(() => { file.current = null; setStage('camera'); })}>Retake</Button>
    </>}
    {stage === 'blurry' && <>
      <p role="status" className="text-sm font-semibold text-problem">That photo looks blurry.</p>
      <Button onClick={() => act(() => void send())}>Send it anyway</Button>
      <Button ref={main} data-lesson-primary variant="primary" onKeyDown={repeat} onClick={() => act(() => { file.current = null; setStage('camera'); })}>Take it again</Button>
    </>}
    {stage === 'sending' && <p role="status" className="text-sm font-semibold text-action">Sending your photo…</p>}
  </div>;
}
