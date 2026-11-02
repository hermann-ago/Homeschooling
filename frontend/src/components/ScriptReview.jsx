import {useState} from 'react';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {tutorApi} from '../api/tutor';
import {Button} from '../ui';

export default function ScriptReview({guideId}) {
  const client=useQueryClient();
  const {data,error,refetch}=useQuery({queryKey:['script-review',guideId],queryFn:()=>tutorApi.scriptReview(guideId)});
  const [busy,setBusy]=useState(false);
  const [problem,setProblem]=useState('');
  const retry=async()=>{
    setBusy(true);setProblem('');
    try {
      await tutorApi.retryScriptReview(guideId,{expected_input_sha256:data.input_sha256,maximum_usd:0.30});
      await refetch();await client.invalidateQueries({queryKey:['curriculum-preparation']});
    } catch(e){setProblem(e.message);} finally{setBusy(false);}
  };
  return <details className="bg-paper rounded-lg p-3 text-sm" open={data?.status.status==='failed' ? true : undefined}>
    <summary className="cursor-pointer font-semibold">Script review</summary>
    {data&&<><p className="mt-2">{data.status.summary}</p><p className="text-xs text-muted mt-1">A source-consistency and teaching review. It does not independently verify every fact.</p>
      {data.review?.data?.provider&&<p className="text-xs text-muted mt-1">Review provider: {data.review.data.provider==='google'?'Google':'OpenAI'}</p>}
      {data.review?.data?.findings?.map((f,i)=><div key={i} className="mt-3 border-t border-line pt-2"><p className="font-semibold">{f.severity==='blocking'?'Needs adjustment':'Suggestion'} · {f.category.replaceAll('_',' ')}</p><p>{f.detail}</p><p className="mt-1">{f.suggestion}</p></div>)}
      {data.review?.data?.error&&<p className="text-problem mt-2">{data.review.data.error}</p>}
      {data.answer_key?.some(item=>item.answer)&&<details className="mt-3 border-t border-line pt-2">
        <summary className="cursor-pointer font-semibold">Answer key (teacher only)</summary>
        <p className="text-xs text-muted mt-1">Copied from the book’s answer key while the lesson was written. The tutor uses it for grading; your child never sees it.</p>
        <ol className="mt-2 flex flex-col gap-2">
          {data.answer_key.map((item,i)=><li key={i}>
            <p className="whitespace-pre-line text-muted">{item.prompt}</p>
            <p className="font-semibold">{item.answer??'No answer in the key'}{item.answer_page?<span className="font-normal text-xs text-muted"> · key page {item.answer_page}</span>:null}</p>
          </li>)}
        </ol>
      </details>}
      {['failed','outdated','not_reviewed'].includes(data.status.status)&&<div className="flex flex-col gap-2 mt-3"><Button disabled={busy} onClick={retry}>{busy?'Reviewing…':'Review saved script'}</Button><p className="text-xs text-muted">Review costs are tracked with your teaching usage. Saved replies are reused. A failed or uncertain purchase is not automatically replaced.</p></div>}
      {['needs_changes','needs_source_review'].includes(data.status.status)&&<p className="mt-3">Update the relevant teaching skill or source note, then select “Generate a new tutor script” below. Saved lessons and audio remain available.</p>}
    </>}
    {(error||problem)&&<p role="alert" className="text-problem">{problem||error.message}</p>}
  </details>;
}
