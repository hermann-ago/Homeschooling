import { useEffect, useRef, useState } from 'react';
import { Camera } from 'lucide-react';
import { Button } from '../../ui';

const SEND_AFTER = 1200;
const TYPES = ['image/jpeg', 'image/png', 'image/webp'];

/**
 * One-button photo of book work. The camera opens in place, Space takes the
 * picture, and it sends itself after a moment unless the child retakes it.
 * Without a live camera (plain HTTP, no webcam) the device's own camera or
 * photo picker stands in.
 */
export default function SnapWork({ onSnap, busy, label = 'Photo of my work' }) {
  const [stage, setStage] = useState('idle'); // idle | camera | taken | sending
  const [preview, setPreview] = useState(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const video = useRef(null);
  const stream = useRef(null);
  const picker = useRef(null);
  const main = useRef(null);
  const file = useRef(null);
  const live = Boolean(navigator.mediaDevices?.getUserMedia) && window.isSecureContext !== false;
  const cameraOn = stage === 'camera' || stage === 'taken';

  useEffect(() => {
    if (!cameraOn) return undefined;
    let cancelled = false;
    navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } } })
      .then((camera) => {
        if (cancelled) { camera.getTracks().forEach((track) => track.stop()); return; }
        stream.current = camera;
        if (video.current) video.current.srcObject = camera;
      })
      .catch((failure) => {
        if (cancelled) return;
        setError(failure.name === 'NotAllowedError' ? 'Allow camera access for this app, or choose a photo.' : 'The camera could not open. Choose a photo instead.');
        setStage('idle');
      });
    return () => { cancelled = true; stream.current?.getTracks().forEach((track) => track.stop()); stream.current = null; setReady(false); };
  }, [cameraOn]);

  const send = async () => {
    setStage('sending'); setError('');
    const sent = await Promise.resolve(onSnap(file.current)).catch(() => false);
    if (!sent) { setError('The photo was not sent. Please try again.'); setStage('idle'); }
  };
  const sendRef = useRef(send);
  useEffect(() => { sendRef.current = send; });
  useEffect(() => {
    if (stage !== 'taken') return undefined;
    const timer = setTimeout(() => sendRef.current(), SEND_AFTER);
    return () => clearTimeout(timer);
  }, [stage]);
  useEffect(() => { if (stage !== 'idle') main.current?.focus(); }, [stage, ready]);

  const take = () => {
    const frame = video.current;
    if (!ready || !frame?.videoWidth) return;
    const scale = Math.min(1, 2048 / Math.max(frame.videoWidth, frame.videoHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(frame.videoWidth * scale); canvas.height = Math.round(frame.videoHeight * scale);
    canvas.getContext('2d').drawImage(frame, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (!blob) { setError('The picture could not be taken. Please try again.'); return; }
      file.current = new File([blob], `work-${Date.now()}.jpg`, { type: 'image/jpeg' });
      setPreview(canvas.toDataURL('image/jpeg', 0.6)); setStage('taken');
    }, 'image/jpeg', 0.9);
  };
  const chosen = (picked) => {
    if (!picked) return;
    if (!TYPES.includes(picked.type) || picked.size > 10 * 1024 * 1024) { setError('Use a JPG, PNG or WebP photo smaller than 10 MB.'); return; }
    file.current = picked; setPreview(null); void send();
  };
  const repeat = (event) => { if (event.repeat && ['Enter', ' '].includes(event.key)) event.preventDefault(); };

  return <div className="snap-work flex flex-col gap-2">
    <input ref={picker} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" className="hidden" aria-label="Photo of my work"
      onChange={(event) => { chosen(event.target.files?.[0]); event.target.value = ''; }} />
    {cameraOn && <div className="snap-view">
      {stage === 'taken' && preview ? <img src={preview} alt="The photo you took" /> :
        <video ref={video} autoPlay muted playsInline aria-label="Camera" onLoadedData={() => setReady(true)} />}
    </div>}
    {error && <p role="alert" className="text-sm text-problem">{error}</p>}
    {stage === 'idle' && <Button ref={main} data-lesson-primary variant="primary" icon={Camera} disabled={busy} onKeyDown={repeat}
      onClick={() => { setError(''); if (live) setStage('camera'); else picker.current?.click(); }}>{label}</Button>}
    {stage === 'camera' && <div className="flex gap-2">
      <Button ref={main} data-lesson-primary variant="primary" className="flex-1" disabled={!ready} onKeyDown={repeat} onClick={take}>{ready ? 'Take the photo' : 'Opening the camera…'}</Button>
      <Button onClick={() => setStage('idle')}>Cancel</Button>
    </div>}
    {stage === 'taken' && <div className="flex items-center gap-2">
      <p role="status" className="flex-1 text-sm font-semibold text-action">Sending…</p>
      <Button onClick={() => { file.current = null; setStage('camera'); }}>Retake</Button>
    </div>}
    {stage === 'sending' && <p role="status" className="text-sm font-semibold text-action">Sending your photo…</p>}
    {stage === 'idle' && live && <button type="button" className="self-start text-xs text-action underline" disabled={busy} onClick={() => picker.current?.click()}>Choose a saved photo</button>}
  </div>;
}
