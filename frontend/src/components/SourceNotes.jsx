import {useState} from 'react';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {booksApi} from '../api/books';
import {Button,Dialog,Field} from '../ui';

export default function SourceNotes({subject}) {
  const client=useQueryClient();
  const {data,error}=useQuery({queryKey:['source-notes',subject.id],queryFn:()=>booksApi.sourceNotes(subject.id)});
  const [draft,setDraft]=useState(null);
  const [busy,setBusy]=useState(false);
  const [problem,setProblem]=useState('');
  const edit=note=>{
    const doc=data.documents.find(d=>d.sha256===note?.document_sha256)||data.documents[0];
    setDraft({document_id:doc.id,expected_sha256:doc.sha256,expected_version:note?.version||0,
      first_page:note?.first_page||1,last_page:note?.last_page||1,title:note?.title||'',
      teaching_note:note?.teaching_note||'',assessment_note:note?.assessment_note||'',
      references:(note?.references||[]).join('\n'),active:note?.active??true});setProblem('');
  };
  const update=(key,value)=>setDraft(d=>({...d,[key]:value}));
  const save=async()=>{
    setBusy(true);setProblem('');
    try {
      await booksApi.saveSourceNote(subject.id,{...draft,references:draft.references.split('\n').map(s=>s.trim()).filter(Boolean)});
      await Promise.all([client.invalidateQueries({queryKey:['source-notes']}),client.invalidateQueries({queryKey:['curriculum-preparation']})]);
      setDraft(null);
    } catch(e){setProblem(e.message);} finally{setBusy(false);}
  };
  const locked=Boolean(draft?.expected_version);
  return <details className="border border-line rounded-xl p-4 mt-4">
    <summary className="cursor-pointer font-semibold text-action">Book source notes</summary>
    <p className="text-sm text-muted mt-3">Corrections and clarifications belong to a PDF edition and page range. Other subjects using that same edition can reuse them. Earlier lessons keep their saved instructions.</p>
    {error&&<p role="alert">{error.message}</p>}
    <div className="flex flex-col gap-2 mt-3">{data?.notes.map(note=><div key={note.id} className="rounded-lg bg-paper p-3 text-sm">
      <p className="font-semibold">{note.title} · PDF {note.first_page}–{note.last_page} · v{note.version}{!note.active?' · Archived':''}</p>
      <p className="text-muted">{data.documents.find(d=>d.sha256===note.document_sha256)?.original_filename}</p>
      <p className="whitespace-pre-wrap mt-2">{note.teaching_note}</p>
      <details className="mt-2"><summary>Source history and assessment guidance</summary>
        <p className="whitespace-pre-wrap mt-2">{note.assessment_note||'No separate assessment exception.'}</p>
        {note.references.map(url=><a className="block text-action underline break-all" key={url} href={url} target="_blank" rel="noreferrer">{url}</a>)}
        <p className="text-muted mt-2">Saved versions: {data.history.filter(r=>r.key===note.key).map(r=>`v${r.version}`).join(', ')}</p>
      </details>
      <Button size="sm" className="mt-2" onClick={()=>edit(note)}>Edit source note</Button>
    </div>)}</div>
    <Button className="mt-3" size="sm" disabled={!data?.documents.length} onClick={()=>edit(null)}>Add source note</Button>
    {draft&&<Dialog open title="Source note" onClose={busy?undefined:()=>setDraft(null)} footer={<><Button disabled={busy} onClick={()=>setDraft(null)}>Close</Button><Button variant="primary" disabled={busy||!draft.title.trim()} onClick={save}>Save new version</Button></>}>
      <div className="flex flex-col gap-3 text-sm">
        <label>Book edition<select aria-label="Book edition" disabled={locked||busy} className="block w-full border border-line rounded-lg p-2" value={draft.document_id} onChange={e=>{const doc=data.documents.find(d=>d.id===Number(e.target.value));setDraft(d=>({...d,document_id:doc.id,expected_sha256:doc.sha256}));}}>{data.documents.map(d=><option key={d.id} value={d.id}>{d.original_filename}</option>)}</select></label>
        <Field label="Note title" value={draft.title} disabled={locked||busy} maxLength={180} onChange={e=>update('title',e.target.value)}/>
        <div className="flex gap-3"><Field label="First PDF page" type="number" min="1" value={draft.first_page} disabled={locked||busy} onChange={e=>update('first_page',Number(e.target.value))}/><Field label="Last PDF page" type="number" min="1" value={draft.last_page} disabled={locked||busy} onChange={e=>update('last_page',Number(e.target.value))}/></div>
        {[['teaching_note','Teaching clarification',8000],['assessment_note','Assessment exception · stays out of learner payloads',4000],['references','Reference links · one per line',12000]].map(([key,label,max])=><label key={key}>{label}<textarea aria-label={label} disabled={busy} maxLength={max} value={draft[key]} onChange={e=>update(key,e.target.value)} className="block w-full min-h-28 border border-line rounded-lg p-2"/></label>)}
        <label><input type="checkbox" disabled={busy} checked={draft.active} onChange={e=>update('active',e.target.checked)}/> Use this note for new preparations</label>
        {problem&&<p role="alert" className="text-problem">{problem}</p>}
      </div>
    </Dialog>}
  </details>;
}
