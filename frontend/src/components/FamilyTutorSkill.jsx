import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { differenceInYears, format, parseISO } from 'date-fns';
import { tutorApi } from '../api/tutor';
import { Button, Dialog } from '../ui';
import { MarkdownPreview } from './TeachingSkillEditor';

function profileSummary(profile) {
  if(profile?.birth_date) {
    const born=parseISO(profile.birth_date);
    return `Born ${format(born,'dd/MM/yyyy')} · age ${differenceInYears(new Date(),born)}`;
  }
  if(profile?.birth_year) {
    const year=new Date().getFullYear(), oldest=year-profile.birth_year;
    return `Born ${profile.birth_year} · age ${Math.max(0,oldest-1)}–${oldest} in ${year} (birthday unknown)`;
  }
  return profile?.age != null ? `Age ${profile.age}` : 'Not set';
}

export default function FamilyTutorSkill() {
  const client=useQueryClient();
  const {data,error}=useQuery({queryKey:['family-tutor-skill'],queryFn:tutorApi.teachingStyle});
  const [draft,setDraft]=useState(null);
  const [past,setPast]=useState('');
  const [busy,setBusy]=useState(false);
  const [problem,setProblem]=useState('');
  const [saved,setSaved]=useState(false);
  const [editingText,setEditingText]=useState(false);
  const open=()=>{setDraft({...data.skill,profiles:{...data.skill.profiles}});setPast('');setProblem('');setSaved(false);setEditingText(false);};
  const previous=data?.history.find(row=>String(row.version)===past);
  const save=async()=>{
    setBusy(true);setProblem('');
    try {
      await tutorApi.saveTeachingStyle(draft.content,draft.profiles,draft.version);
      await client.invalidateQueries({queryKey:['family-tutor-skill']});
      setDraft(null);setSaved(true);
    } catch(e) {setProblem(e.message);}
    finally {setBusy(false);}
  };
  const profileValue=(id,field,value)=>setDraft(current=>{
    const profiles={...current.profiles};
    if(value==='')delete profiles[id];
    else profiles[id]={[field]:field==='birth_date'?value:Number(value),as_of:format(new Date(),'yyyy-MM-dd')};
    return {...current,profiles};
  });
  return <section id="tutor-skill" className="rounded-2xl border border-line bg-surface p-5">
    <h2 className="text-lg font-semibold">Shared tutoring skill</h2>
    <p className="text-sm text-muted mt-2">How the tutor speaks, teaches and responds in every subject. Ages help it choose its language and pacing.</p>
    <Button className="mt-3" disabled={!data} onClick={open}>View and edit tutoring skill{data ? ` · v${data.skill.version}` : ''}</Button>
    {error && <p role="alert" className="text-problem mt-2">{error.message}</p>}
    {saved && <p role="status" className="text-sm text-action mt-2">Saved. New lesson scripts will use these instructions. Lessons already started keep their prepared script.</p>}
    {draft && <Dialog open width={900} title="Shared tutoring skill" onClose={busy?undefined:()=>setDraft(null)}
      footer={<><Button disabled={busy} onClick={()=>setDraft(null)}>Close</Button><Button variant="primary" disabled={busy || Boolean(past) || !draft.content.trim() || draft.content===data.skill.content && JSON.stringify(draft.profiles)===JSON.stringify(data.skill.profiles)} onClick={save}>{busy?'Saving…':'Save new version'}</Button></>}>
      <p className="text-sm text-muted">Shared across subjects, alongside each subject’s teaching instructions. Saving does not generate a lesson or buy audio.</p>
      <label className="block my-4 text-sm">Previous versions <select aria-label="Shared tutoring skill versions" value={past} onChange={e=>setPast(e.target.value)} className="border border-line rounded-lg p-2 ml-2">
        <option value="">Current · v{draft.version}</option>{data.history.filter(row=>row.version!==draft.version).map(row=><option key={row.id} value={row.version}>Version {row.version}</option>)}
      </select></label>
      {previous ? <><MarkdownPreview content={previous.content}/><p className="text-sm text-muted mt-3">Profiles recorded in this version: {data.learners.map(c=>`${c.name}: ${profileSummary(previous.profiles[c.id])}`).join(' · ')}</p><Button className="mt-3" onClick={()=>{setDraft({...draft,content:previous.content,profiles:{...previous.profiles}});setPast('');setEditingText(true);}}>Use as draft</Button></> : <>
        <fieldset className="mb-4"><legend className="font-semibold text-sm mb-2">Learner birthdays and ages</legend><div className="grid gap-4 sm:grid-cols-2">{data.learners.map(child=><div key={child.id} className="flex flex-col gap-1 text-sm"><span className="font-semibold">{child.name}</span>
          <label>Date of birth <input aria-label={`${child.name} date of birth`} type="date" max={format(new Date(),'yyyy-MM-dd')} value={draft.profiles[child.id]?.birth_date ?? ''} onChange={e=>profileValue(child.id,'birth_date',e.target.value)} className="border border-line rounded-lg p-2"/></label>
          <details><summary className="cursor-pointer text-muted">Use a birth year or confirmed age instead</summary>
          <label className="block mt-2">Birth year <input aria-label={`${child.name} birth year`} type="number" min={new Date().getFullYear()-25} max={new Date().getFullYear()} value={draft.profiles[child.id]?.birth_year ?? ''} placeholder="Not set" onChange={e=>profileValue(child.id,'birth_year',e.target.value)} className="w-28 border border-line rounded-lg p-2"/></label>
          <label>Or confirmed age <input aria-label={`${child.name} age`} type="number" min="0" max="25" value={draft.profiles[child.id]?.age ?? ''} placeholder="Not set" onChange={e=>profileValue(child.id,'age',e.target.value)} className="w-28 border border-line rounded-lg p-2"/></label>
          </details>
          <span className="text-xs text-muted">{profileSummary(draft.profiles[child.id])}</span>
          {draft.profiles[child.id]?.as_of && <span className="text-xs text-muted">Confirmed {draft.profiles[child.id].as_of}</span>}
        </div>)}</div><p className="text-xs text-muted mt-2">A birthday keeps the tutor’s age information current automatically. If only the birth year is known, it uses an age range. Grade and observed understanding are considered separately.</p></fieldset>
        <Button size="sm" className="mb-4" onClick={()=>setEditingText(!editingText)}>{editingText?'Read instructions':'Edit instructions'}</Button>
        {editingText ? <><label className="sr-only" htmlFor="shared-tutor-content">Teaching instructions</label>
          <textarea id="shared-tutor-content" value={draft.content} onChange={e=>setDraft({...draft,content:e.target.value})} maxLength={30000} className="w-full min-h-[380px] border border-line bg-paper rounded-xl p-4 text-sm leading-6"/></> : <MarkdownPreview content={draft.content}/>}
      </>}
      {problem && <p role="alert" className="text-problem mt-3">{problem} Your draft is kept here.</p>}
    </Dialog>}
  </section>;
}
