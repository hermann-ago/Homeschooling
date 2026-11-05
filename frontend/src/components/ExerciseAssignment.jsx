import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { booksApi } from '../api/books';
import { Button } from '../ui';

/** Which items on exercise pages shared by several lessons each lesson teaches. */
function Editor({topic,data}) {
  const client=useQueryClient();
  const [items,setItems]=useState(data.assignment?.items||[]);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const refresh=()=>client.invalidateQueries({queryKey:['exercise-assignment']});
  const run=async(action,done)=>{
    setBusy(true);setMessage('');
    try {await action();await refresh();setMessage(done);}
    catch(e){setMessage(e.message);}finally{setBusy(false);}
  };
  const title=id=>data.lessons.find(l=>l.topic_id===id)?.title||`Lesson ${id}`;
  return <div className="flex flex-col gap-2 text-sm">
    <p className="text-muted">These exercise pages are shared by {data.lessons.map(l=>l.title).join(', ')}. Each lesson teaches only the items assigned to it.</p>
    {!data.assignment&&<div className="flex flex-col gap-2">
      <p>No items have been assigned yet. Preparing any of these lessons assigns them automatically.</p>
      <div><Button size="sm" disabled={busy} onClick={()=>run(()=>booksApi.assignExercises(topic),'Items assigned.')}>Assign items now</Button></div>
    </div>}
    {!!items.length&&<>
      <p className="text-muted">{data.assignment.method==='family'?'Set by your family.':'Assigned automatically.'} Changes apply to lessons prepared from now on.</p>
      <ul className="flex flex-col gap-1">
        {items.map((item,i)=><li key={`${item.page}-${item.label}`} className="flex flex-wrap items-center gap-2">
          <span className="w-28">Item {item.label} · PDF {item.page}</span>
          <select aria-label={`Lesson for item ${item.label}`} value={item.topic_id} onChange={e=>{const topic_id=Number(e.target.value);setItems(old=>old.map((x,n)=>n===i?{...x,topic_id}:x));setMessage('');}} className="border border-line rounded-lg p-1 bg-surface">
            {data.lessons.map(l=><option key={l.topic_id} value={l.topic_id}>{title(l.topic_id)}</option>)}
          </select>
        </li>)}
      </ul>
      <div><Button size="sm" disabled={busy} onClick={()=>run(()=>booksApi.saveExerciseAssignment(topic,items,data.revision),'Assignment saved. Prepare a new script to use it.')}>Save assignment</Button></div>
    </>}
    {message&&<p role="status">{message}</p>}
  </div>;
}

export default function ExerciseAssignment({topic}) {
  const {data,error}=useQuery({queryKey:['exercise-assignment',topic],queryFn:()=>booksApi.exerciseAssignment(topic)});
  if (error) return <p role="alert">{error.message}</p>;
  if (!data?.shared) return null;
  return <details className="rounded-xl border border-line p-3"><summary className="font-semibold text-sm cursor-pointer">Exercises shared with other lessons</summary>
    <div className="mt-3"><Editor key={`${topic}-${data.revision}-${data.assignment?'a':'n'}`} topic={topic} data={data}/></div>
  </details>;
}
