import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { booksApi } from '../api/books';
import { Button, Dialog, Field } from '../ui';
import SubjectSourceMap from './SubjectSourceMap';

const money = (value) => `US$${Number(value || 0).toFixed(4)}`;
const statusText = { queued: 'Review queued', running: 'Reviewing the books', paused: 'Review paused', paused_allowance: 'Paused at a spending limit', failed: 'Review needs attention', ready: 'Overview saved', needs_review: 'Overview saved · items need review', snapshot: 'Saved source snapshot · test mode' };

function CostPreview({ subject, job, onClose }) {
  const client = useQueryClient();
  const { data: preview, error, isPending } = useQuery({ queryKey: ['subject-analysis-preview', subject.id, job?.id], queryFn: () => booksApi.analysisPreview(subject.id), staleTime: 0 });
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');
  const start = async () => {
    setBusy(true); setProblem('');
    try {
      if (job) await booksApi.continueAnalysis(job.id, .25);
      else await booksApi.analyze(subject.id, { fingerprint: preview.fingerprint, maximum_usd: .25 });
      await client.invalidateQueries({ queryKey: ['subject-analysis', subject.id] });
      await client.invalidateQueries({ queryKey: ['subject-collection', subject.id] });
      await client.invalidateQueries({ queryKey: ['book-companions', subject.id] });
      onClose();
    } catch (e) { setProblem(e.message); }
    finally { setBusy(false); }
  };
  return <Dialog open title={job ? 'Continue the saved review' : 'Review these books together'} onClose={busy ? undefined : onClose}
    description="The app saves section summaries, connects the books and exercises, and builds a reusable overview. Existing lessons and student records stay available."
    footer={<><Button disabled={busy} onClick={onClose}>Cancel</Button><Button variant="primary" onClick={start}
      disabled={busy || !preview}>{busy ? 'Saving…' : job ? 'Continue review' : 'Start review'}</Button></>}>
    <div className="flex flex-col gap-4">
      {isPending && <p role="status">Checking saved preparation…</p>}
      {preview && <>
        <p className="text-sm">{preview.books} books · {preview.pages} pages · {preview.reusable_pages} pages already scanned.</p>
        <p className="text-sm">Estimated new generation: <strong>{money(preview.estimate_low_usd)}–{money(preview.estimate_high_usd)}</strong>.</p>
        <p className="text-sm text-muted">{preview.estimate_note}</p>
        <p className="text-sm">Book preparation used or reserved this month: <strong>{money(preview.family_allowance.used_usd)}</strong>.</p>
        <p className="text-sm text-muted">Teaching provider: {preview.provider === 'openai' ? 'OpenAI' : 'Google'} · {preview.model}</p>
        {job && <p className="text-sm">This review has used or reserved {money(job.spending.used_usd)}.</p>}
        <p className="text-sm text-muted">Generation costs are tracked. Manage spending limits with your providers. Completed work is saved for later continuation.</p>
      </>}
      {(error || problem) && <p role="alert" className="text-sm text-problem">{problem || error.message}</p>}
    </div>
  </Dialog>;
}

export default function SubjectAnalysis({ subject, collection }) {
  const client = useQueryClient();
  const { data, error } = useQuery({ queryKey: ['subject-analysis', subject.id], queryFn: () => booksApi.analysisStatus(subject.id), enabled: Boolean(collection.id),
    refetchInterval: (q) => q.state.data?.jobs.some((j) => j.in_flight || ['queued', 'running'].includes(j.status)) ? 3000 : false });
  const job = data?.jobs.find((j) => j.version_id === collection.version_id);
  useEffect(() => {
    client.invalidateQueries({ queryKey: ['book-companions', subject.id] });
    if (['ready', 'needs_review'].includes(job?.status)) {
      client.invalidateQueries({ queryKey: ['subject-collection', subject.id] });
      client.invalidateQueries({ queryKey: ['subject-knowledge-library'] });
      client.invalidateQueries({ queryKey: ['subject-analysis-preview', subject.id] });
    }
  }, [client, subject.id, job?.done, job?.status]);
  const earlier = !job && data?.jobs.find((j) => j.map_id);
  const [previewing, setPreviewing] = useState(false);
  const [viewing, setViewing] = useState(null);
  const [problem, setProblem] = useState('');
  const [importing,setImporting]=useState(false);
  const [importMessage,setImportMessage]=useState('');
  const sourceMapInput=useRef(null);
  const importSourceMap=async(file)=>{
    setImporting(true);setProblem('');setImportMessage('');
    try {
      await booksApi.importSourceMap(subject.id,file);
      await client.invalidateQueries({queryKey:['subject-analysis',subject.id]});
      await client.invalidateQueries({queryKey:['subject-collection',subject.id]});
      await client.invalidateQueries({queryKey:['subject-knowledge-library']});
      setImportMessage('Codex overview saved. No AI allowance was used.');
    } catch(e) {setProblem(e.message);}
    finally {setImporting(false);}
  };
  const [refreshing, setRefreshing] = useState(false);
  const refreshSources = async () => {
    setRefreshing(true); setProblem('');
    try {
      const sources = await booksApi.companions(subject.id);
      await booksApi.refreshSources(subject.id, {
        expected_map_id:job.map_id, expected_version_id:collection.version_id,
        expected_source_hashes:Object.fromEntries(sources.books.filter(b=>b.content_sha256).map(b=>[String(b.document_id),b.content_sha256])),
        note:'Fontes atualizadas pelos JSONs conferidos no aplicativo; propostas pedagógicas anteriores revalidadas sem nova geração.', decisions:[],
      });
      await client.invalidateQueries({queryKey:['subject-analysis',subject.id]});
      await client.invalidateQueries({queryKey:['subject-collection',subject.id]});
      await client.invalidateQueries({queryKey:['subject-knowledge-library']});
    } catch(e) { setProblem(e.message); }
    finally {setRefreshing(false);}
  };
  const pause = async () => {
    try { await booksApi.pauseAnalysis(job.id); await client.invalidateQueries({ queryKey: ['subject-analysis', subject.id] }); }
    catch (e) { setProblem(e.message); }
  };
  return <div className="border-t border-line-soft pt-3 flex flex-col items-start gap-3">
    {!job && <Button disabled={!collection.analysis_available || !collection.books.length} onClick={() => setPreviewing(true)}>Understand these books together</Button>}
    {!collection.analysis_available && <p className="text-sm text-muted">Save the collection first, then review the estimated cost.</p>}
    {job && <>
      <p role="status" className="text-sm font-semibold">{statusText[job.status] || job.status}</p>
      <p className="text-sm text-muted">{job.stage} · {job.done} of {job.total} source sections processed</p>
      <p className="text-sm">Used or reserved: {money(job.spending.used_usd)}</p>
      {job.spending.uncertain_usd > 0 && <p className="text-sm text-attention">{money(job.spending.uncertain_usd)} is reserved for charges awaiting confirmation.</p>}
      {job.error && <p className="text-sm text-attention">{job.error}</p>}
      {['queued', 'running'].includes(job.status) && <Button size="sm" onClick={pause}>Pause review</Button>}
      {['paused', 'paused_allowance', 'failed'].includes(job.status) && <Button size="sm" disabled={job.in_flight} onClick={() => setPreviewing(true)}>Continue preparation</Button>}
      {job.status === 'paused' && job.in_flight && <p className="text-sm text-muted">Saving the request already in progress. Continue becomes available when it finishes.</p>}
      {job.map_id && <Button size="sm" onClick={() => setViewing(job.map_id)}>View saved overview</Button>}
      {job.map_id && !job.read_only && job.provider !== 'codex' && ['ready','needs_review'].includes(job.status) && <>
        <Button size="sm" disabled={refreshing || job.in_flight} onClick={refreshSources}>{refreshing ? 'Atualizando fontes…' : 'Atualizar com JSONs revisados'}</Button>
        <p className="text-sm text-muted">Reusa fontes conferidas sem gastar com IA. Relações pendentes continuam disponíveis para revisão.</p>
      </>}
      {job.provider === 'codex' && <p className="text-sm text-muted">Prepared in Codex. To continue source review, import the revised book JSONs and then their matching Codex overview.</p>}
    </>}
    {earlier && <Button size="sm" onClick={() => setViewing(earlier.map_id)}>View earlier saved overview</Button>}
    {collection.id && <>
      <Button size="sm" disabled={importing || job?.in_flight || ['running','queued'].includes(job?.status)} onClick={()=>sourceMapInput.current.click()}>{importing ? 'Importing Codex overview…' : 'Import Codex overview'}</Button>
      <input ref={sourceMapInput} type="file" className="hidden" accept=".json,application/json" aria-label="Upload Codex source overview" onChange={e=>{
        const file=e.target.files?.[0];e.target.value='';if(file)importSourceMap(file);
      }}/>
      <p className="text-sm text-muted">Import source analysis prepared in Codex after saving the matching book JSON files. Importing starts no API requests.</p>
    </>}
    {importMessage && <p role="status" className="text-sm text-action">{importMessage}</p>}
    <p className="text-sm text-muted">Review costs are tracked under book preparation. Saved results are reused, and existing lessons remain available.</p>
    {(error || problem) && <p role="alert" className="text-sm text-problem">{problem || error.message}</p>}
    {previewing && <CostPreview subject={subject} job={job} onClose={() => setPreviewing(false)} />}
    {viewing && <SubjectSourceMap id={viewing} subject={subject.id} onClose={() => setViewing(null)} />}
  </div>;
}
