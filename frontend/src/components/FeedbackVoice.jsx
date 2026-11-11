import { useEffect, useRef, useState } from 'react';
import { tutorApi } from '../api/tutor';
import { Volume2 } from 'lucide-react';
import { Button } from '../ui';
import { beginNarration, isNarrating, registerNarrator } from '../utils/narration';

export default function FeedbackVoice({ session, message, language, action = false, trackId = null, autoPlay = false,speed=1 }) {
  const [busy, setBusy] = useState(false);
  const [urls, setUrls] = useState([]);
  const [index, setIndex] = useState(0);
  const [notice, setNotice] = useState('');
  const [deviceAvailable, setDeviceAvailable] = useState(false);
  const audio = useRef(null);
  const narratorId = useRef(Symbol('feedback'));
  const requestVersion = useRef(0);
  useEffect(()=>{if(audio.current)audio.current.playbackRate=speed;},[speed,urls,index]);
  useEffect(() => registerNarrator(narratorId.current, () => {
    requestVersion.current += 1;
    audio.current?.pause();
    if (isNarrating(narratorId.current)) window.speechSynthesis?.cancel();
  }), []);
  useEffect(() => () => { urls.forEach((url)=>URL.revokeObjectURL(url)); }, [urls]);
  const read = async () => {
    beginNarration(narratorId.current);
    const version = ++requestVersion.current;
    audio.current?.pause(); window.speechSynthesis?.cancel();
    setUrls([]);
    setBusy(true); setNotice(''); setDeviceAvailable(false);
    try {
      const requestAudio = action ? tutorApi.actionAudio : tutorApi.feedbackAudio;
      const estimate = await requestAudio(session, message.id, true, ...(trackId ? [trackId] : []));
      if (!estimate.allowed) throw new Error(estimate.reason || 'The voice provider is unavailable.');
      if (version !== requestVersion.current) return;
      const result = await requestAudio(session, message.id, false, ...(trackId ? [trackId] : []));
      const manifest = await tutorApi.audioManifest(result.track_id);
      if (manifest.tracks.some((part) => part.fallback)) throw new Error('This reply uses device speech.');
      const next = [];
      try {
        for (let part = 0; part < manifest.tracks.length; part += 1) next.push(await tutorApi.audioPart(result.track_id, part));
      } catch (e) { next.forEach((url)=>URL.revokeObjectURL(url)); throw e; }
      if (version !== requestVersion.current) { next.forEach((url)=>URL.revokeObjectURL(url)); return; }
      window.speechSynthesis?.cancel();
      setIndex(0); setUrls(next);
    } catch (e) {
      if (version !== requestVersion.current) return;
      setNotice(e.message);
      setDeviceAvailable(Boolean(window.speechSynthesis && typeof SpeechSynthesisUtterance !== 'undefined'));
    } finally { setBusy(false); }
  };
  useEffect(() => {
    if (autoPlay) void read();
    return () => { requestVersion.current += 1; audio.current?.pause(); };
    // A saved teacher message has immutable text. Polling the same reply must
    // neither repurchase nor restart it. Changing the selected voice is explicit.
  }, [autoPlay, message.id, trackId]);
  useEffect(() => () => { requestVersion.current += 1; audio.current?.pause(); }, []);
  // The tutor's reply is simply heard; a small speaker repeats it.
  return <div className="feedback-voice">
    <button type="button" className="feedback-voice-button" data-busy={busy || undefined} disabled={busy} onClick={read}
      aria-label={busy ? 'Preparing voice…' : 'Read aloud'} title={busy ? 'Preparing voice…' : 'Read aloud (AI-generated voice)'}><Volume2 size={15} aria-hidden="true" /></button>
    {urls.length > 0 && <audio ref={audio} src={urls[index]} autoPlay onPlay={() => beginNarration(narratorId.current)} onEnded={() => { if (index + 1 < urls.length) setIndex(index + 1); }} />}
    {notice && <p className="text-xs text-muted">{notice}</p>}
    {deviceAvailable && <Button size="sm" variant="quiet" onClick={() => {
      beginNarration(narratorId.current);
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(message.text);
      utterance.lang = language; utterance.rate = 0.9;
      window.speechSynthesis.speak(utterance); setNotice('Using the device voice.');
    }}>Use device voice</Button>}
  </div>;
}
