
import NarratorPicker from './NarratorPicker';
import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { LoaderCircle } from 'lucide-react';
import { curriculumPrepApi } from '../api/preparation';
import { currentMode } from '../api/mode';
import { Button, Dialog } from '../ui';
import { DEFAULT_SCRIPT_CAP_USD, DEFAULT_AUDIO_CAP_USD } from '../utils/preparationLimits';
import ScriptReview from './ScriptReview';
import PreparationProgress from './PreparationProgress';
import { reviewRecovered } from '../utils/preparationStatus';
import { operationId, readSaved, writeSaved } from './activities/durable';

const active = job => ['queued','running'].includes(job?.status);
const clean = e => e.message.replace(/^\/[^:]+: /,'');
const usd = value => `US$${(Math.ceil(value*1000)/1000).toFixed(3)}`;

export function CurriculumPreparationCells({topic,status,onPrepare}) {
  const working=active(status?.job);
  const scriptBusy=working&&['script','review'].includes(status.job.phase);
  const reviewBlocked=status?.review&&['failed','needs_changes','needs_source_review','outdated'].includes(status.review.status);
  const audioBusy=working&&status.job.phase==='audio'||['queued','running','aligning'].includes(status?.audio?.status);
  const scriptReady=status?.script_status==='ready';
  const audioReady=status?.audio?.status==='ready';
  const audioPartial=status?.audio?.status==='ready_with_fallback';
  const noAudio=audioPartial && status.audio.recorded_parts===0;
  const paused=status?.job?.status==='paused'&&!reviewRecovered(status);
  const narrator = status?.audio?.provider === 'inworld' ? 'Inworld TTS-2' : status?.audio?.provider === 'elevenlabs' ? 'ElevenLabs voice' : 'Google voice';
  const audioLabel=audioBusy ? status?.audio?.status==='aligning'?'Synchronizing…':'Preparing audio…'
    : noAudio?`${narrator} declined · no audio saved`:audioReady?`Ready · ${narrator}`:audioPartial?`${narrator} · some passages text-only`:status?.audio?.status==='missing'?'Not prepared':status?'Needs attention':'Checking…';
  return <>
    <div className="flex-1 min-w-24 flex flex-col gap-1 text-xs" aria-label={`Tutor script for ${topic.title}`}>
      <span className={scriptReady?'text-action font-semibold':'text-muted'}>
        <span className="font-medium text-muted">Tutor: </span>
        {scriptBusy?<><LoaderCircle className="inline mr-1 animate-spin" size={12}/>{status.job.phase==='review'?'Reviewing script…':'Preparing tutor…'}</>
          :scriptReady?'Ready':status?.script_status==='outdated'?'Saved · update available':status?'Not prepared':'Checking…'}
      </span>
      {!scriptBusy&&status?.review&&<span className={reviewBlocked?'text-attention':'text-muted'}>{status.review.summary}</span>}
      {!scriptBusy&&status?.can_prepare&&<button type="button" className="text-left text-action underline-offset-2 hover:underline disabled:opacity-50" disabled={working}
        aria-label={`${scriptReady?'Prepare options for':status.script_status==='outdated'?'Update tutor for':'Prepare tutor for'} ${topic.title}`}
        onClick={()=>onPrepare(scriptReady&&!reviewBlocked?'audio':'both')}>{scriptReady?'Preparation options':status.script_status==='outdated'?'Update tutor':'Prepare tutor'}</button>}
      {paused&&status.job.phase==='script'&&<span className="text-problem">Preparation paused</span>}
      {working&&<button type="button" className="text-left text-action underline" onClick={()=>onPrepare(status.job.target)}>View preparation progress</button>}
    </div>
    <div className="flex-1 min-w-24 flex flex-col gap-1 text-xs" aria-label={`Advanced audio for ${topic.title}`}>
      <span className={audioReady?'text-action font-semibold':'text-muted'}><span className="font-medium text-muted">Audio: </span>{audioBusy&&<LoaderCircle className="inline mr-1 animate-spin" size={12}/>}{audioLabel}</span>
      {audioBusy&&status?.audio?.parts&&<span className="text-muted">{status.audio.completed_parts||0}/{status.audio.parts} synchronized</span>}
      {!audioBusy&&scriptReady&&!reviewBlocked&&!audioReady&&!audioPartial&&<button type="button" className="text-left text-action hover:underline" disabled={working}
        aria-label={`Prepare advanced audio for ${topic.title}`} onClick={()=>onPrepare('audio')}>Prepare audio</button>}
      {status?.script_status==='outdated'&&!audioBusy&&<span className="text-muted">For the saved script</span>}
      {paused&&<button type="button" className="text-left text-problem hover:underline" onClick={()=>onPrepare(status.job.target)}>View issue / retry</button>}
      {paused&&status.job.error&&<span role="alert" className="text-problem break-words">{status.job.error}</span>}
    </div>
  </>;
}

export function CurriculumPreparationDialog({learner,topic,status,target:initialTarget,onClose}) {
  const client=useQueryClient();
  const [target,setTarget]=useState(initialTarget);
  const [estimate,setEstimate]=useState(null);
  const [busy,setBusy]=useState(false);
  const [problem,setProblem]=useState('');
  const [operation,setOperation]=useState(null);
  const [replaceInvalid,setReplaceInvalid]=useState(status?.job?.recovery==='replace_script');
  const [repairAudio,setRepairAudio]=useState(false);
  const [teachingProvider,setTeachingProvider]=useState(status?.job?.teaching_provider||'configured');
  const [audioProvider,setAudioProvider]=useState(status?.job?.audio_provider||'configured');
  const [rewrite,setRewrite]=useState(false);
  const preparing=active(status?.job)||['queued','running','aligning'].includes(status?.audio?.status);
  const body={learner:Number(learner),topic:topic.id,target,maximum_guide_usd:DEFAULT_SCRIPT_CAP_USD,maximum_audio_usd:DEFAULT_AUDIO_CAP_USD,
    replace_invalid:target!=='audio'&&replaceInvalid,repair_audio:target!=='guide'&&repairAudio,teaching_provider:teachingProvider,audio_provider:audioProvider,rewrite:target!=='audio'&&rewrite};
  const reset=()=>{setEstimate(null);setProblem('');setOperation(null);};
  const preview=async()=>{
    setBusy(true);setProblem('');
    try{
      const result=await curriculumPrepApi.estimate(body);setEstimate(result);
      if(result.script?.cached_invalid_reply||result.script?.cached_failure?.replaceable)setReplaceInvalid(true);
    }
    catch(e){setProblem(clean(e));}finally{setBusy(false);}
  };
  const prepare=async()=>{
    setBusy(true);setProblem('');
    try{
      const key=`homeschooling.curriculum-preparation.${currentMode}.${learner}.${topic.id}`;
      let command=operation;
      if(!command){
        const stored=readSaved(key);
        if(stored&&JSON.stringify(stored.body)===JSON.stringify(body)) command=stored.command;
        command ||= {...body,operation_id:operationId()};
        setOperation(command);
        writeSaved(key,{body,command});
      }
      const job=await curriculumPrepApi.start(command);
      writeSaved(key,null);
      client.setQueryData(['curriculum-preparation',currentMode,learner,topic.id],previous=>({...status,...previous,job}));
      void client.invalidateQueries({queryKey:['curriculum-preparation']});
      void client.invalidateQueries({queryKey:['reader']});onClose();
    }catch(e){setProblem(clean(e));}finally{setBusy(false);}
  };
  return <Dialog open title="Prepare lesson" description={topic.title} onClose={busy?undefined:onClose} width={560}
    footer={<><Button disabled={busy} onClick={onClose}>Close</Button>{!preparing&&(estimate
      ?<Button variant="primary" disabled={busy||!estimate.allowed} onClick={prepare}>{busy?'Adding to preparation…':'Prepare in background'}</Button>
      :<Button variant="primary" disabled={busy} onClick={preview}>{busy?'Checking…':'Check cost and prepare'}</Button>)}</>}>
    <div className="flex flex-col gap-4 text-sm">

      <p className="text-muted">Prepare materials here, without starting a student session. Existing lessons and answers keep their saved version.</p>
      <PreparationProgress status={status}/>
      {!preparing&&<>
      {status?.job?.error&&!reviewRecovered(status)&&<p className="text-problem" role="note">Last preparation: {status.job.error}</p>}
      <label className="flex flex-col gap-1">What to prepare<select aria-label="What to prepare" className="border border-line rounded-lg p-2" disabled={busy} value={target} onChange={e=>{setTarget(e.target.value);reset();}}>
        <option value="both">Guided lesson and voice</option><option value="guide">Guided lesson only</option>
        <option value="audio" disabled={status?.script_status!=='ready'}>Voice only</option>
      </select></label>
      {target!=='guide'&&<details><summary className="cursor-pointer font-semibold">Change narrator</summary><div className="mt-3"><NarratorPicker topic={topic.id} onChanged={reset}/></div></details>}
      {status?.guide_id&&<ScriptReview guideId={status.guide_id}/>}
      {target!=='audio'&&<label className="flex flex-col gap-1">Script provider<select aria-label="Script provider" className="border border-line rounded-lg p-2" disabled={busy} value={teachingProvider} onChange={e=>{setTeachingProvider(e.target.value);setReplaceInvalid(false);reset();}}>
        <option value="configured">Use the family’s selected provider</option><option value="openai">OpenAI · high reasoning for this script</option><option value="google">Google for this script</option>
      </select><span className="text-xs text-muted">A different provider is used only when you select it here. The family’s default stays unchanged.</span></label>}
      {target!=='audio'&&status?.script_status==='ready'&&<label className="flex items-start gap-2"><input type="checkbox" checked={rewrite} disabled={busy} onChange={e=>{setRewrite(e.target.checked);reset();}}/>Generate a new tutor script. Existing sessions keep their saved version.</label>}
      {target!=='guide'&&<label className="flex flex-col gap-1">Audio provider<select aria-label="Audio provider" className="border border-line rounded-lg p-2" disabled={busy} value={audioProvider} onChange={e=>{setAudioProvider(e.target.value);setRepairAudio(false);reset();}}><option value="configured">Use the family’s selected narrator</option><option value="google-gemini">Google voice for this lesson</option></select><span className="text-xs text-muted">Keeps the family default unchanged. Saved matching recordings are reused.</span></label>}
      {replaceInvalid&&target!=='audio'&&<p className="rounded-xl bg-paper p-3">A saved reply could not be used. Preparing will request one replacement script; its cost is tracked. Repeated retries reuse that same replacement.</p>}
      {target!=='guide'&&(status?.job?.recovery==='repair_audio'||status?.audio?.status==='alignment_review')&&<div className="rounded-xl bg-paper p-3 flex flex-col gap-2">
        <p>The audio is saved, but its timing check stopped. Leave this unchecked to retry synchronization without buying the saved blocks again.</p>
        <label className="flex items-start gap-2"><input type="checkbox" checked={repairAudio} disabled={busy} onChange={e=>{setRepairAudio(e.target.checked);reset();}}/>Request one replacement for the failed audio block (may incur a provider charge)</label>
      </div>}
      {estimate&&<div className="rounded-xl bg-paper p-3 flex flex-col gap-2" aria-label="Preparation estimate">
        {estimate.script&&<p>Tutor script: {estimate.script.reused?'Already saved · no new script charge':`up to ${usd(estimate.script.estimated_cost_usd)}`}</p>}
        {estimate.script?.model&&<p className="text-xs text-muted">Script writer: {estimate.script.model}{estimate.script.reasoning_effort?` · ${estimate.script.reasoning_effort} reasoning`:''}</p>}
        {estimate.audio&&<p>Advanced audio: {estimate.audio.estimated_cost_usd==null?'estimated after the guide is saved':estimate.audio.reused?'Already saved · no new audio charge':`up to ${usd(estimate.audio.estimated_cost_usd)}`}</p>}
        {estimate.audio?.reason&&<p className="text-muted">{estimate.audio.reason}</p>}
        {estimate.script?.cached_failure?.replacement_used&&<p className="text-problem">The replacement reply also failed. It is saved for review; another automatic purchase is blocked.</p>}
        {estimate.script?.cached_failure?.code==='provider_refusal'&&<p role="alert" className="text-problem">The script provider declined this source. Repeating the same request will not fix it. Review the material or explicitly select another script provider above.</p>}
        {!estimate.allowed&&estimate.script?.cached_failure?.code!=='provider_refusal'&&<p role="alert" className="text-problem">Preparation needs attention. Check the source review and provider connection above.</p>}
      </div>}
      </>}
      <p className="text-xs text-muted">Generation costs are tracked. Spending limits are managed with your providers. Progress is saved and matching materials are reused.</p>
      {problem&&<p role="alert" className="text-problem">{problem}</p>}
    </div>
  </Dialog>;
}
