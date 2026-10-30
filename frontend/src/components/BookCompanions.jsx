import { lazy, Suspense, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { booksApi } from '../api/books';
import { request } from '../api/client';
import { Button, Dialog } from '../ui';

const OriginalSourcePage = lazy(() => import('./OriginalSourcePage'));

function InspectPage({ subject, book, onClose }) {
  const [page, setPage] = useState(1);
  const [original, setOriginal] = useState(false);
  const { data, error, isPending } = useQuery({ queryKey: ['book-companion-page', subject, book.document_id, page, book.revision],
    queryFn: () => booksApi.companionPage(subject, book.document_id, page) });
  return <><Dialog open title={`Book JSON · ${book.name}`} width={900} onClose={onClose} footer={<Button onClick={onClose}>Close</Button>}>
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm font-semibold">PDF page<select aria-label="Inspect PDF page" value={page} onChange={(e) => setPage(Number(e.target.value))}
          className="ml-2 rounded-lg border border-line p-2 bg-surface">{Array.from({ length: book.page_count }, (_, i) => <option key={i + 1}>{i + 1}</option>)}</select></label>
        <Button size="sm" disabled={page === 1} onClick={() => setPage((n) => n - 1)}>Previous page</Button>
        <Button size="sm" disabled={page === book.page_count} onClick={() => setPage((n) => n + 1)}>Next page</Button>
        <Button size="sm" onClick={() => setOriginal(true)}>View original page</Button>
      </div>
      {isPending && <p role="status">Loading page representation…</p>}
      {error && <p role="alert">{error.message}</p>}
      {data && <>
        <p className="text-sm font-semibold">{data.status === 'checked' ? 'Source checked' : 'Needs source review'}{data.printed_page ? ` · printed page ${data.printed_page}` : ''}</p>
        {data.teacher_material && <p className="text-sm text-attention">Answer-key or teacher material · excluded from student narration.</p>}
        {data.issues.map((issue, i) => <p key={i} className="text-sm text-attention">{issue}</p>)}
        {data.notes?.length > 0 && <details className="text-sm text-muted"><summary className="cursor-pointer">Notas da conferência</summary>{data.notes.map((note,i)=><p key={i} className="mt-2">{note}</p>)}</details>}
        <div className="rounded-xl border border-line p-4"><h4 className="font-semibold">Page transcription</h4>
          <p className="whitespace-pre-wrap text-sm mt-2">{data.text || 'No readable text extracted. Inspect the original PDF.'}</p></div>
        <div><h4 className="font-semibold">Visual structure</h4>
          {!data.elements.length && <p className="text-sm text-muted mt-2">No visual elements described yet.</p>}
          {data.elements.map((e) => <div key={e.id} className="rounded-xl border border-line p-3 mt-2 text-sm">
            <p className="font-semibold">{e.kind}</p><p className="whitespace-pre-wrap">{e.description || e.text}</p>
            {e.expression && <p>{e.expression}</p>}
            {e.rows.length > 0 && <div className="overflow-auto"><table><tbody>{e.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className="border border-line p-2">{c}</td>)}</tr>)}</tbody></table></div>}
          </div>)}
        </div>
        <details><summary className="text-sm text-action cursor-pointer">Original automatic extraction</summary><p className="whitespace-pre-wrap text-sm mt-2">{data.native_text}</p></details>
      </>}
    </div>
  </Dialog>
    {original && <Suspense fallback={<p role="status">Opening original page…</p>}><OriginalSourcePage companionSubject={subject} document={book.document_id} page={page} onClose={() => setOriginal(false)} /></Suspense>}
  </>;
}

export default function BookCompanions({ subject, collection }) {
  const client = useQueryClient();
  const { data, error } = useQuery({ queryKey: ['book-companions', subject.id, collection.version_id],
    queryFn: () => booksApi.companions(subject.id), enabled: Boolean(collection.books.length),
    refetchInterval: collection.analysis_status === 'running' || collection.analysis_status === 'queued' ? 5000 : false });
  const [busy, setBusy] = useState(null);
  const [problem, setProblem] = useState('');
  const [message, setMessage] = useState('');
  const [inspecting, setInspecting] = useState(null);
  const [reviewing, setReviewing] = useState(null);
  const [reviewNote, setReviewNote] = useState('');
  const input = useRef(null);
  const target = useRef(null);
  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ['book-companions', subject.id] });
    await client.invalidateQueries({ queryKey: ['subject-analysis-preview', subject.id] });
    await client.invalidateQueries({ queryKey: ['book-companion-page', subject.id] });
  };
  const act = async (book, task) => {
    setBusy(book.document_id); setProblem(''); setMessage('');
    try { await task(); await refresh(); }
    catch (e) { setProblem(e.message); }
    finally { setBusy(null); }
  };
  const download = async (book) => {
    const response = await request(`/subjects/${subject.id}/book-companions/${book.document_id}/export`);
    if (!response.ok) throw new Error('The book JSON could not be downloaded. Refresh and try again.');
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url; link.download = `${book.name.replace(/\.pdf$/i, '')}.book.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  if (!collection.books.length) return null;
  return <section aria-label="Book JSON files" className="border-t border-line-soft pt-4 flex flex-col gap-3">
    <div><h4 className="font-semibold">Book JSON files</h4><p className="text-sm text-muted mt-1">One reusable representation per PDF: text, page locations, exercises and visual descriptions.</p></div>
    <p className="text-sm text-muted">Create a local draft without using AI. To interpret images and check exercises in the app, use “Understand these books together” below. You can also import a matching JSON prepared in Codex.</p>
    {data?.books.map((book) => <article key={book.document_id} className="rounded-xl border border-line p-3 flex flex-col gap-2">
      <p className="text-sm font-semibold break-words">{book.name}</p>
      <p className="text-sm text-muted">{book.status === 'not_created' ? 'No JSON created yet' : `${book.checked_pages} of ${book.page_count} pages checked · ${book.pending_pages} to review`}</p>
      {book.status !== 'not_created' && <p className="text-xs text-muted">{book.exercises} indexed exercises · {book.visual_elements} visual elements</p>}
      {(book.pending_exercises > 0 || book.pending_answers > 0) && <p className="text-xs text-attention">{book.pending_exercises || 0} exercise references and {book.pending_answers || 0} key entries need source review.</p>}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={busy !== null} onClick={() => act(book, async () => {
          await booksApi.createCompanion(subject.id, book.document_id);
          setMessage('Book JSON saved. Unchecked pages remain marked for review.');
        })}>{busy === book.document_id ? 'Working…' : book.status === 'not_created' ? 'Create local JSON' : 'Update from checked pages'}</Button>
        {book.status !== 'not_created' && <><Button size="sm" disabled={busy !== null} onClick={() => setInspecting(book)} aria-label={`Inspect JSON for ${book.name}`}>Inspect pages</Button>
          <Button size="sm" disabled={busy !== null} onClick={() => act(book, () => download(book))} aria-label={`Download JSON for ${book.name}`}>Download JSON</Button></>}
        <Button size="sm" disabled={busy !== null} onClick={() => { target.current = book; input.current.click(); }} aria-label={`Import JSON for ${book.name}`}>Import JSON</Button>
        {book.status !== 'not_created' && <Button size="sm" disabled={busy !== null} onClick={()=>{setReviewing(book);setReviewNote('');}}>Importar correção revisada</Button>}
      </div>
    </article>)}
    <input ref={input} type="file" accept=".json,application/json" className="hidden" aria-label="Upload book JSON" onChange={(e) => {
      const file = e.target.files?.[0]; const book = target.current; e.target.value = '';
      if (file && book) act(book, async () => {
        const args=[subject.id, book.document_id, file, book.revision];
        if (book.sourceReview) args.push(book.sourceReview);
        await booksApi.importCompanion(...args);
        setMessage('Matching book JSON imported. Checked pages can be reused by preparation.');
      });
    }} />
    {message && <p role="status" className="text-sm text-action">{message}</p>}
    {(problem || error) && <p role="alert" className="text-sm text-problem">{problem || error.message}</p>}
    {inspecting && <InspectPage subject={subject.id} book={inspecting} onClose={() => setInspecting(null)} />}
    {reviewing && <Dialog open title="Importar correção de fonte" onClose={()=>setReviewing(null)} footer={<><Button onClick={()=>setReviewing(null)}>Cancelar</Button><Button variant="primary" disabled={!reviewNote.trim()} onClick={()=>{target.current={...reviewing,sourceReview:{note:reviewNote}};setReviewing(null);input.current.click();}}>Escolher JSON revisado</Button></>}>
      <p className="text-sm">{reviewing.name}. A correção cria uma versão de fonte e conserva o JSON e a análise anteriores. Não altera respostas nem aulas iniciadas.</p>
      <label className="text-sm block mt-4">O que foi conferido e corrigido?<textarea aria-label="Nota da correção de fonte" className="w-full border border-line rounded-xl p-3 mt-2" value={reviewNote} maxLength={2000} onChange={e=>setReviewNote(e.target.value)}/></label>
    </Dialog>}
  </section>;
}
