import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { booksApi } from '../api/books';
import { Button } from '../ui';

function Editor({topic,data,onSaved}) {
  const client=useQueryClient();
  const [rows,setRows]=useState(data.sources);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const edit=(i,changes)=>{setRows(old=>old.map((r,n)=>n===i?{...r,...changes}:r));setMessage('');};
  const save=async()=>{
    setBusy(true);setMessage('');
    try {await booksApi.saveSourcePages(topic,rows.map(({document_id,page_start,page_end})=>({document_id:Number(document_id),page_start:Number(page_start),page_end:Number(page_end)})),data.revision);onSaved?.();await client.invalidateQueries({queryKey:['lesson-source-pages',topic]});await client.invalidateQueries({queryKey:['reader']});await client.invalidateQueries({queryKey:['curriculum-preparation']});setMessage('Selected pages saved. Prepare a new script to use them.');}
    catch(e){setMessage(e.message);}finally{setBusy(false);}
  };
  return <div className="flex flex-col gap-3 text-sm">
    <p className="text-muted">The lesson’s main pages are included automatically. Add pages from other books below. Use original PDF page numbers. Answer-key pages are private review and assessment sources.</p>
    {rows.map((row,i)=>{
      const book=data.books.find(b=>b.document_id===Number(row.document_id));
      return <div key={i} className="rounded-xl border border-line p-3 flex flex-wrap gap-2 items-end">
        <label className="flex-1 min-w-40">Book<select aria-label={`Source book ${i+1}`} value={row.document_id} onChange={e=>edit(i,{document_id:Number(e.target.value),page_start:1,page_end:1})} className="block w-full border border-line rounded-lg p-2 bg-surface">
          {data.books.map(b=><option key={b.document_id} value={b.document_id}>{b.name}{b.role==='answer_key'?' · private answer key':''}</option>)}
        </select></label>
        {!!book?.chapters.length&&<label className="w-full">Chapter<select aria-label={`Source chapter ${i+1}`} value="" onChange={e=>{const ch=book.chapters[Number(e.target.value)];if(ch)edit(i,{page_start:ch.page_start,page_end:ch.page_end});}} className="block w-full border border-line rounded-lg p-2 bg-surface">
          <option value="">Choose a chapter range</option>{book.chapters.map((ch,n)=><option key={n} value={n}>{ch.title} · PDF {ch.page_start}–{ch.page_end}</option>)}
        </select></label>}
        {['page_start','page_end'].map((key,n)=><label key={key}>{n?'Last':'First'} PDF page<input aria-label={`Source ${i+1} ${n?'last':'first'} page`} type="number" min="1" max={book?.page_count} value={row[key]} onChange={e=>edit(i,{[key]:e.target.value})} className="block w-20 border border-line rounded-lg p-2 bg-surface"/></label>)}
        <Button size="sm" onClick={()=>setRows(old=>old.filter((_,n)=>n!==i))}>Remove</Button>
      </div>;
    })}
    <div className="flex gap-2"><Button size="sm" disabled={!data.books.length||busy} onClick={()=>setRows(old=>[...old,{document_id:data.books[0].document_id,page_start:1,page_end:1}])}>Add source pages</Button><Button size="sm" disabled={busy} onClick={save}>Save selected pages</Button></div>
    {message&&<p role="status">{message}</p>}
  </div>;
}

export default function LessonSourcePages({topic,onSaved}) {
  const {data,error}=useQuery({queryKey:['lesson-source-pages',topic],queryFn:()=>booksApi.sourcePages(topic)});
  return <details className="rounded-xl border border-line p-3"><summary className="font-semibold text-sm cursor-pointer">Books and pages for this lesson</summary>
    <div className="mt-3">{data&&<Editor key={`${topic}-${data.revision}`} topic={topic} data={data} onSaved={onSaved}/>} {error&&<p role="alert">{error.message}</p>}</div>
  </details>;
}
