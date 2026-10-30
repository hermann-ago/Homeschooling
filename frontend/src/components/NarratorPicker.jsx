import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { booksApi } from '../api/books';
import { Button } from '../ui';
import { voiceLabel } from '../utils/narratorVoices';

export default function NarratorPicker({topic,onChanged}) {
  const client=useQueryClient();
  const {data,error}=useQuery({queryKey:['narrator-voices'],queryFn:()=>booksApi.voices(),staleTime:300000,retry:false});
  const {data:current}=useQuery({queryKey:['lesson-narrator',topic],queryFn:()=>booksApi.narrator(topic)});
  const [chosen,setChosen]=useState('');
  const [filter,setFilter]=useState('');
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const voices=(data?.voices||[]).filter(v=>!current?.language || !v.language || v.language===current.language);
  const value=chosen||current?.voice||'';
  const voice=voices.find(v=>v.id===value);
  const visible=voices.filter(v=>v.id===value||`${v.name} ${v.description} ${Object.values(v.labels).join(' ')}`.toLowerCase().includes(filter.toLowerCase()));
  const save=async()=>{
    setBusy(true);setMessage('');
    try{await booksApi.saveNarrator(topic,value);await client.invalidateQueries({queryKey:['lesson-narrator',topic]});await client.invalidateQueries({queryKey:['reader']});await client.invalidateQueries({queryKey:['curriculum-preparation']});onChanged?.();setMessage('Narrator selected. Create the recorded voice to hear this lesson with it.');}
    catch(e){setMessage(e.message);}finally{setBusy(false);}
  };
  return <div className="flex flex-col gap-3 text-sm">
    <p className="text-muted">Listen to sample voices, then choose a narrator for this lesson. Samples use existing recordings. Creating the lesson voice incurs provider costs and keeps earlier recordings.</p>
    <label>Find a voice<input aria-label="Find a narrator" value={filter} onChange={e=>setFilter(e.target.value)} placeholder="Name, accent, gender or style" className="block w-full border border-line rounded-lg p-2 bg-surface"/></label>
    <label>Lesson narrator<select aria-label="Lesson narrator" value={value} onChange={e=>{setChosen(e.target.value);setMessage('');}} className="block w-full border border-line rounded-lg p-2 bg-surface">
      {!voices.some(v=>v.id===value)&&<option value={value}>Current narrator</option>}
      {visible.map(v=><option key={v.id} value={v.id}>{voiceLabel(v)}</option>)}
    </select></label>
    {voice?.description&&<p className="text-muted">{voice.description}</p>}
    {voice?.preview_url&&<audio key={voice.id} controls preload="none" src={voice.preview_url} aria-label={`Preview ${voice.name}`} className="w-full"/>}
    <Button size="sm" disabled={busy||!voice} onClick={save}>Use narrator for this lesson</Button>
    {(message||error)&&<p role="status">{message||error.message}</p>}
  </div>;
}
