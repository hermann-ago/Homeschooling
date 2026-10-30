import { useCallback, useState } from 'react';
import { Pause, Play } from 'lucide-react';
import ReadAlong from './ReadAlong';
import { Button } from '../ui';
import { pauseNarration } from '../utils/narration';
import SessionNarrationControls from './activities/SessionNarrationControls';

/** Listening has its own position; it never opens or changes a student activity. */
export default function LessonAudioReplay({ guide, language, onClose, onPassageModeChange }) {
  const [index, setIndex] = useState(0);
  const [restart, setRestart] = useState(0);
  const [step, setStep] = useState(0);
  const [continuous, setContinuous] = useState(false);
  const [finished, setFinished] = useState(false);
  const [playRequest, setPlayRequest] = useState(0);
  const [transport, setTransport] = useState(null);
  const tracks=(guide.audio||[]).filter(t=>['ready','legacy'].includes(t.status));
  const [source,setSource]=useState(()=>tracks.find(t=>t.preferred&&t.synchronized)?.track_id||tracks.find(t=>t.synchronized)?.track_id||tracks[0]?.track_id||'device');
  const [speed,setSpeed]=useState(1);
  const steps=(guide.activities||[]).filter(a=>Number.isInteger(a.start_sentence)&&Number.isInteger(a.end_sentence)&&a.end_sentence>=a.start_sentence);
  const current=steps[step]||{start_sentence:0,end_sentence:guide.sentences.length-1};
  const start=continuous?0:current.start_sentence;
  const end=continuous?guide.sentences.length-1:current.end_sentence;
  const ended=useCallback(()=>setFinished(true),[]);
  const reset=()=>{pauseNarration();setStep(0);setIndex(0);setFinished(false);setTransport(null);setPlayRequest(0);setRestart(v=>v+1);};
  const next=()=>{
    pauseNarration();setTransport(null);setFinished(false);setIndex(steps[step+1].start_sentence);
    setStep(v=>v+1);setPlayRequest(v=>v+1);
  };
  return <section aria-label="Audio replay" className="flex flex-col flex-1 min-h-0 overflow-hidden">
    <header className="p-3 border-b border-line flex flex-col gap-2 shrink-0">
      <div className="flex flex-wrap items-center gap-2"><p className="font-semibold text-action">{continuous?'Continuous listening':'Lesson preview'}</p>
        <SessionNarrationControls tracks={tracks} source={source} speed={speed}
          onChange={change=>{pauseNarration();if(change.source)setSource(change.source);if(change.speed)setSpeed(change.speed);}}
          onReplay={()=>transport?.replay?.()} canReplay={Boolean(transport?.available)} error={transport?.error}/>
      </div>
      <p className="text-xs text-muted">{continuous?'Plays through without activity pauses.':'Pauses after every lesson step. Continue when you are ready.'} This is a preview; return to the lesson to submit answers. Your saved progress stays unchanged.</p>
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex-1 min-w-40 text-xs"><span className="sr-only">Preview playback</span><select aria-label="Preview playback" value={continuous?'continuous':'steps'} className="border border-line rounded-lg p-2 bg-surface max-w-full" onChange={e=>{reset();setContinuous(e.target.value==='continuous');}}>
          <option value="steps">Pause after each step</option><option value="continuous">Continuous listening</option>
        </select></label>
        <Button size="sm" onClick={reset}>Restart audio</Button>
        <Button size="sm" onClick={()=>{pauseNarration();onClose();}}>Return to lesson</Button>
      </div>
    </header>
    <div role="region" aria-label="Replay content" tabIndex={0} className="flex-1 min-h-0 overflow-y-auto overscroll-contain">
      {!continuous&&<p className="px-4 pt-3 text-xs font-semibold text-muted">Step {step+1} of {steps.length||1}</p>}
      <ReadAlong key={`${restart}.${continuous}.${step}`} passage={guide} tracks={guide.audio} activeIndex={index}
        onActiveIndex={setIndex} language={language} onPassageModeChange={onPassageModeChange}
        rangeStart={start} rangeEnd={end} visibleThrough={end} onReadingEnd={ended}
        settingsInHeader selectedSource={source} selectedSpeed={speed} externalControls
        autoPlayRequest={playRequest} onTransport={setTransport}/>
    </div>
    <footer className="p-3 border-t border-line shrink-0 flex items-center gap-3 bg-surface">
      <div className="flex-1 min-w-0 flex flex-col gap-2">
        <p role="status" className="text-xs text-muted">{continuous?'Continuous replay · no activity pauses':finished?'Paused · this step is finished':'This step stops before the next one.'}</p>
        {!continuous&&step+1<steps.length&&<Button variant="primary" size="sm" onClick={next}>Continue preview</Button>}
        {!continuous&&finished&&step+1>=steps.length&&<p className="text-sm font-semibold">Preview finished</p>}
      </div>
      <button type="button" aria-label={transport?.playing?'Pause':'Play'} disabled={!transport?.available} onClick={()=>transport?.toggle?.()}
        className="w-11 h-11 shrink-0 rounded-full bg-action text-white grid place-items-center disabled:opacity-40">
        {transport?.playing?<Pause size={20} fill="currentColor"/>:<Play size={20} fill="currentColor"/>}
      </button>
    </footer>
  </section>;
}
