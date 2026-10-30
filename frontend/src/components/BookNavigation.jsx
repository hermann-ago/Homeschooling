import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { booksApi, bookRoles } from '../api/books';
import { Button, Dialog, Field } from '../ui';

function ChapterEditor({subject,book,onClose}) {
  const client=useQueryClient();
  const [rows,setRows]=useState(book.navigation?.data.chapters || []);
  const [problem,setProblem]=useState('');
  const [busy,setBusy]=useState(false);
  const edit=(i,key,value)=>setRows(old=>old.map((r,n)=>n===i?{...r,[key]:value}:r));
  const save=async()=>{
    setBusy(true);setProblem('');
    try {await booksApi.saveNavigation(subject.id,book.document_id,rows.map(r=>({...r,page_start:Number(r.page_start),page_end:Number(r.page_end)})),book.navigation?.revision||0);await client.invalidateQueries({queryKey:['book-navigation',subject.id]});onClose();}
    catch(e){setProblem(e.message);}finally{setBusy(false);}
  };
  return <Dialog open title={`Chapters · ${book.name}`} onClose={busy?undefined:onClose} width={800}
    description="Use titles and page ranges from the contents. Page numbers below refer to the original PDF."
    footer={<><Button onClick={onClose} disabled={busy}>Cancel</Button><Button variant="primary" onClick={save} disabled={busy}>Save chapter map</Button></>}>
    <div className="flex flex-col gap-3 max-h-[60vh] overflow-auto">
      {rows.map((row,i)=><div key={i} className="grid grid-cols-[1fr_5rem_5rem_auto] gap-2 items-end">
        <Field label={`Chapter ${i+1}`} value={row.title} onChange={e=>edit(i,'title',e.target.value)}/>
        <Field label="First page" type="number" min="1" max={book.page_count} value={row.page_start} onChange={e=>edit(i,'page_start',e.target.value)}/>
        <Field label="Last page" type="number" min="1" max={book.page_count} value={row.page_end} onChange={e=>edit(i,'page_end',e.target.value)}/>
        <Button onClick={()=>setRows(old=>old.filter((_,n)=>n!==i))} aria-label={`Remove chapter ${i+1}`}>Remove</Button>
      </div>)}
      <Button onClick={()=>setRows(old=>[...old,{title:'',page_start:old.length?Number(old.at(-1).page_end)+1:1,page_end:book.page_count}])}>Add chapter</Button>
      {problem&&<p role="alert" className="text-problem">{problem}</p>}
    </div>
  </Dialog>;
}

export default function BookNavigation({subject}) {
  const client=useQueryClient();
  const {data,error}=useQuery({queryKey:['book-navigation',subject.id],queryFn:()=>booksApi.navigation(subject.id)});
  const [editing,setEditing]=useState(null);
  const [busy,setBusy]=useState(null);
  const [problem,setProblem]=useState('');
  const extract=async(book)=>{
    setBusy(book.document_id);setProblem('');
    try{await booksApi.extractNavigation(subject.id,book.document_id);await client.invalidateQueries({queryKey:['book-navigation',subject.id]});}
    catch(e){setProblem(e.message);}finally{setBusy(null);}
  };
  return <section aria-label="Book chapter maps" className="rounded-2xl border border-line bg-surface p-4 flex flex-col gap-3">
    <h3 className="font-bold">Chapter maps</h3>
    <p className="text-sm text-muted">Keep the contents and page ranges here. Each lesson uses selected original pages from these books. Answer keys stay private.</p>
    {data?.books.map(book=><article key={book.key} className="border-t border-line pt-3 flex flex-wrap items-center gap-3">
      <div className="flex-1 min-w-40"><p className="font-semibold text-sm">{book.name}</p><p className="text-xs text-muted">{bookRoles.find(([id])=>id===book.role)?.[1]} · {book.page_count} PDF pages · {book.navigation?.data.chapters.length||0} chapters</p></div>
      {!book.navigation&&<Button size="sm" disabled={busy!==null} onClick={()=>extract(book)}>{busy===book.document_id?'Reading contents…':'Read table of contents'}</Button>}
      <Button size="sm" onClick={()=>setEditing(book)}>Edit chapter map</Button>
      {book.navigation&&!book.navigation.data.chapters.length&&<p className="text-xs text-muted w-full">No reliable contents found. Enter chapter ranges from the original PDF, or choose pages directly for a lesson.</p>}
    </article>)}
    {(problem||error)&&<p role="alert" className="text-problem text-sm">{problem||error.message}</p>}
    {editing&&<ChapterEditor key={editing.document_id} subject={subject} book={editing} onClose={()=>setEditing(null)}/>}
  </section>;
}
