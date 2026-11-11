import { Info, RotateCcw } from 'lucide-react';
import { NARRATION_SPEEDS, narrationVoiceLabel } from '../../utils/narrationSettings';
import LessonOptions from './LessonOptions';

/** Voice and reading speed for the whole lesson. Inside the lesson menu (inMenu) they
 *  stand as two labelled choices; replay lives beside play in the control row. */
export default function SessionNarrationControls({ tracks, source, speed, onChange, onReplay, canReplay, voiceSetup, error, inMenu = false }) {
  const selected = tracks.find((track) => track.track_id === source);
  const voice = <select aria-label="Session voice" value={source} onChange={(event) => onChange({ source: event.target.value })}>
    {tracks.map((track) => <option key={track.track_id} value={track.track_id}>{narrationVoiceLabel(track, true)}</option>)}
    <option value="device">Device voice</option>
  </select>;
  const pace = <select aria-label="Session reading speed" value={speed} onChange={(event) => onChange({ speed: Number(event.target.value) })}>
    {NARRATION_SPEEDS.map((value) => <option key={value} value={value}>{value}×</option>)}
  </select>;
  const notes = <>
    {selected && <p className="text-xs text-muted">AI-generated voice · saved recording. Highlighting follows the recorded passage.</p>}
    {selected?.fallback_parts > 0 && <p className="text-xs text-attention">Some passages have no saved recording and stay text-only. You can choose Device voice to listen to them.</p>}
    {error && <p role="alert" className="text-xs text-problem">{error}</p>}
    {!tracks.length && voiceSetup && <><p className="text-xs text-muted">This lesson has no saved voice recording yet.</p>{voiceSetup}</>}
  </>;
  if (inMenu) return <div className="tutor-voice-settings" role="group" aria-label="Session narration settings">
    <label><span>Voice</span>{voice}</label>
    <label><span>Speed</span>{pace}</label>
    {notes}
  </div>;
  return <div className="tutor-session-controls" role="group" aria-label="Session narration settings">
    <label><span className="sr-only">Session voice</span>{voice}</label>
    <label><span className="sr-only">Session reading speed</span>{pace}</label>
    <button type="button" className="session-replay" aria-label="Replay current passage" title="Replay current passage" disabled={!canReplay} onClick={onReplay}><RotateCcw size={17} aria-hidden="true" /></button>
    <LessonOptions label="Voice information" icon={Info}>
      <p className="text-sm">Voice and reading speed apply throughout this lesson.</p>
      {notes}
    </LessonOptions>
  </div>;
}
