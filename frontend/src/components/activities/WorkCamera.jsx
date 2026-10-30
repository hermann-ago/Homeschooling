import { useEffect, useRef, useState } from 'react';
import { Button, Dialog } from '../../ui';

/** Preview stays on this device. Only “Use this photo” uploads evidence. */
export default function WorkCamera({ onPhoto, onClose }) {
  const video = useRef(null);
  const stream = useRef(null);
  const [photo, setPhoto] = useState(null);
  const [ready, setReady] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
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
        setError('The camera is unavailable in this browser. Open the app on localhost or a secure HTTPS address to use it.');
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
  }, [photo]);

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
      const file = new File([bytes], `work-${Date.now()}.jpg`, { type: 'image/jpeg' });
      if (await onPhoto(file)) onClose();
      else setError('The photo was not saved. Please try again.');
    } catch { setError('The photo could not be saved. Your preview is kept; please try again.'); }
    finally { setSaving(false); }
  };

  return <Dialog open title="Take a photo of your work" onClose={onClose} width={680}
    description="Hold the page in front of the webcam. Make sure the writing is clear."
    footer={<>
      <Button disabled={saving} onClick={onClose}>Cancel</Button>
      {photo ? <><Button disabled={saving} onClick={() => setPhoto(null)}>Retake photo</Button>
        <Button variant="primary" disabled={saving} onClick={usePhoto}>{saving ? 'Saving photo…' : 'Use this photo'}</Button></> :
        <Button variant="primary" disabled={!ready} onClick={takePhoto}>Take photo</Button>}
    </>}>
    {photo ? <img src={photo} alt="Preview of your work" className="w-full max-h-[55vh] object-contain rounded-xl" /> :
      <video ref={video} autoPlay muted playsInline aria-label="Webcam preview" className="w-full max-h-[55vh] rounded-xl bg-black"
        onLoadedData={() => setReady(true)} />}
    {!ready && !photo && !error && <p role="status" className="text-sm text-muted mt-3">Opening the webcam… Allow camera access if your browser asks.</p>}
    {error && <p role="alert" className="text-sm text-problem mt-3">{error}</p>}
  </Dialog>;
}
