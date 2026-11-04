import { useEffect, useRef, useState } from 'react';
import { Button, Dialog } from '../../ui';
import { modeHref } from '../../api/mode';

/** Preview stays on this device. Only “Use this photo” uploads evidence. */
export default function WorkCamera({ onPhoto, onClose }) {
  const video = useRef(null);
  const stream = useRef(null);
  const picker = useRef(null);
  const takeButton = useRef(null);
  const useButton = useRef(null);
  const [photo, setPhoto] = useState(null);
  const [ready, setReady] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const insecure = window.isSecureContext === false;
  const windows = /Windows/i.test(navigator.userAgent || '') || /Win/i.test(navigator.platform || '');
  const nativeCamera = windows && !navigator.mediaDevices?.getUserMedia;
  const stop = () => {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  };

  useEffect(() => {
    if (photo) return undefined;
    let cancelled = false;
    setReady(false);
    setError('');
    const open = async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        if (windows) return;
        setError(insecure ? 'This HTTP network connection blocks live webcam access. Set up the secure home connection on this computer, or choose a saved photo.'
          : 'This browser does not offer webcam access. Try Chrome or Edge, or choose a saved photo.');
        return;
      }
      try {
        const camera = await navigator.mediaDevices.getUserMedia({ audio: false,
          video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } } });
        if (cancelled) { camera.getTracks().forEach((track) => track.stop()); return; }
        stream.current = camera;
        video.current.srcObject = camera;
      } catch (failure) {
        if (cancelled) return;
        setError(failure.name === 'NotAllowedError' ? 'Camera permission was not granted. Allow camera access for this app in your browser, then try again.' :
          failure.name === 'NotFoundError' ? 'No webcam was found. Connect a camera and try again.' :
            'The webcam could not open. Close other apps using it, then try again.');
      }
    };
    void open();
    return () => { cancelled = true; stop(); };
  }, [photo, insecure, windows]);

  // Space presses the focused button: first Take photo, then Use this photo.
  useEffect(() => { if (ready && !photo) takeButton.current?.focus(); }, [ready, photo]);
  useEffect(() => { if (photo) useButton.current?.focus(); }, [photo]);
  const takePhoto = () => {
    const frame = video.current;
    if (!ready || !frame?.videoWidth || !frame?.videoHeight) return;
    try {
      const scale = Math.min(1, 2048 / Math.max(frame.videoWidth, frame.videoHeight));
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(frame.videoWidth * scale);
      canvas.height = Math.round(frame.videoHeight * scale);
      canvas.getContext('2d').drawImage(frame, 0, 0, canvas.width, canvas.height);
      const preview = canvas.toDataURL('image/jpeg', 0.9);
      stop();
      setPhoto(preview);
    } catch { setError('The picture could not be taken. Please try again.'); }
  };
  const usePhoto = async () => {
    if (saving || !photo) return;
    setSaving(true); setError('');
    try {
      const bytes = Uint8Array.from(atob(photo.split(',')[1]), (letter) => letter.charCodeAt(0));
      const type = photo.slice(5, photo.indexOf(';'));
      const extension = { 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp' }[type];
      const file = new File([bytes], `work-${Date.now()}.${extension}`, { type });
      if (await onPhoto(file)) onClose();
      else setError('The photo was not saved. Please try again.');
    } catch { setError('The photo could not be saved. Your preview is kept; please try again.'); }
    finally { setSaving(false); }
  };
  const choosePhoto = file => {
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024) {
      setError('Choose a JPG, PNG or WebP photo smaller than 10 MB.'); return;
    }
    const reader = new FileReader();
    reader.onload = () => { stop(); setPhoto(reader.result); setError(''); };
    reader.onerror = () => setError('The photo could not be opened. Please choose it again.');
    reader.readAsDataURL(file);
  };

  return <Dialog open title="Take a photo of your work" onClose={onClose} width={680}
    description={nativeCamera ? 'Use Windows Camera on this computer, then choose the photo you took.' : 'Hold the page close to the webcam so your writing fills the picture. Press Space to take the photo.'}
    footer={<div className="flex flex-wrap justify-end gap-2 w-full">
      <Button disabled={saving} onClick={onClose}>Cancel</Button>
      {!photo && nativeCamera && <Button as="a" href="microsoft.windows.camera:" variant="primary">Open Windows Camera</Button>}
      {!photo && <Button disabled={saving} onClick={() => picker.current?.click()}>Choose a saved photo</Button>}
      {photo ? <><Button disabled={saving} onClick={() => setPhoto(null)}>Retake photo</Button>
        <Button ref={useButton} variant="primary" disabled={saving} onClick={usePhoto}>{saving ? 'Saving photo…' : 'Use this photo'}</Button></> :
        !nativeCamera && <Button ref={takeButton} variant="primary" disabled={!ready} onClick={takePhoto}>Take photo</Button>}
    </div>}>
    <input ref={picker} type="file" accept="image/jpeg,image/png,image/webp" aria-label="Choose work photo" className="hidden" onChange={event => { choosePhoto(event.target.files?.[0]); event.target.value = ''; }} />
    {!photo && nativeCamera && <div className="rounded-xl bg-paper p-4 text-sm flex flex-col gap-3">
      <ol className="list-decimal pl-5 space-y-2">
        <li>Open Windows Camera. If the browser asks, allow it to open the Camera app.</li>
        <li>Take a clear picture of your work.</li>
        <li>Return here and choose the photo. Look in <strong>Pictures → Camera Roll</strong>, sometimes inside OneDrive.</li>
      </ol>
      <p className="text-muted">No certificate setup is needed. Your lesson stays open. You will see a preview before sending the photo.</p>
      <p className="text-xs text-muted">If the button does not open Camera, open it from the Windows Start menu.</p>
    </div>}
    {photo ? <img src={photo} alt="Preview of your work" className="w-full max-h-[55vh] object-contain rounded-xl" /> : !nativeCamera &&
      <video ref={video} autoPlay muted playsInline aria-label="Webcam preview" className={`w-full max-h-[55vh] rounded-xl bg-black${error ? ' hidden' : ''}`}
        onLoadedData={() => setReady(true)} />}
    {!ready && !photo && !error && !nativeCamera && <p role="status" className="text-sm text-muted mt-3">Opening the webcam… Allow camera access if your browser asks.</p>}
    {error && <p role="alert" className="text-sm text-problem mt-3">{error}</p>}
    {insecure && !photo && <details className="mt-3 text-sm text-muted"><summary className="cursor-pointer">Optional: show the camera preview inside the browser</summary>
      <a className="block mt-2 text-action underline" href={modeHref('/settings#camera-access')} target="_blank" rel="noreferrer">Set up the secure browser camera connection</a>
    </details>}
  </Dialog>;
}
