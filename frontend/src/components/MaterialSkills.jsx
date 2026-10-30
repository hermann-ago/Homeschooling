import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { booksApi } from '../api/books';
import { Button, Dialog } from '../ui';
import { MarkdownPreview } from './TeachingSkillEditor';

export default function MaterialSkills() {
  const client=useQueryClient();
  const {data,error}=useQuery({queryKey:['material-skills'],queryFn:booksApi.materialSkills});
  const [editing,setEditing]=useState(null);
  const [content,setContent]=useState('');
  const [past,setPast]=useState('');
  const [busy,setBusy]=useState(false);
  const [problem,setProblem]=useState('');
  const save=async()=>{
    setBusy(true);setProblem('');
    try { await booksApi.saveMaterialSkill(editing.key,content,editing.version); await client.invalidateQueries({queryKey:['material-skills']});setEditing(null); }
    catch(e) {setProblem(e.message);}
    finally {setBusy(false);}
  };
  const previous=editing?.history.find(v=>String(v.version)===past);
  return <details className="rounded-xl border border-line p-4">
    <summary className="font-semibold text-action cursor-pointer">Skills dos materiais</summary>
    <p className="text-sm text-muted mt-3">Estas skills orientam a conversão dos livros, as relações entre materiais e a revisão dos roteiros antes do áudio. São compartilhadas pela família. Alterações valem para novas análises; resultados anteriores mantêm seu histórico.</p>
    {error && <p role="alert">{error.message}</p>}
    <div className="flex flex-wrap gap-2 mt-3">{data?.skills.map(skill=><Button key={skill.key} size="sm" onClick={()=>{setEditing(skill);setContent(skill.content);setPast('');setProblem('');}}>{skill.title} · v{skill.version}</Button>)}</div>
    {editing && <Dialog open width={900} title={editing.title} onClose={busy?undefined:()=>setEditing(null)}
      footer={<><Button disabled={busy} onClick={()=>setEditing(null)}>Fechar</Button><Button variant="primary" disabled={busy || Boolean(past) || !content.trim() || content===editing.content} onClick={save}>Salvar nova versão</Button></>}>
      <p className="text-sm text-muted">{editing.description}. Editar estas instruções não gera análises nem aulas.</p>
      <label className="text-sm block my-3">Histórico de versões<select aria-label="Histórico da skill de materiais" className="ml-3 border border-line rounded-lg p-2" value={past} onChange={e=>setPast(e.target.value)}>
        <option value="">Versão atual · {editing.version}</option>{editing.history.filter(v=>v.version!==editing.version).map(v=><option key={v.id} value={v.version}>Versão {v.version}</option>)}
      </select></label>
      {previous ? <><MarkdownPreview content={previous.content}/><Button className="mt-4" onClick={()=>{setContent(previous.content);setPast('');}}>Usar como rascunho</Button></> : <>
        <label className="sr-only" htmlFor="material-skill-content">Instruções da skill de materiais</label>
        <textarea id="material-skill-content" value={content} onChange={e=>setContent(e.target.value)} maxLength={30000} className="w-full min-h-[460px] border border-line bg-paper rounded-xl p-4 text-sm leading-6"/>
      </>}
      {problem && <p role="alert" className="text-problem">{problem} Seu rascunho foi preservado; feche e reabra para carregar a versão salva.</p>}
    </Dialog>}
  </details>;
}
