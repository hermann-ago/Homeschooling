import { lazy, Suspense, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { booksApi, bookRoles } from '../api/books';
import { request } from '../api/client';
import { Button, Dialog, Field } from '../ui';
import { inputClasses } from '../ui/classes';

const OriginalPdf = lazy(() => import('./OriginalSourcePage'));
const tabs = ['Overview', 'Books', 'Reading order', 'Timeline', 'Concepts', 'Connections', 'Exercises', 'Review items', 'History'];
const reviewLabel = { approved: 'Parent checked', corrected: 'Parent corrected', rejected: 'Parent rejected', unreviewed: 'Not reviewed' };
const year = (n) => n == null ? 'Unknown date' : n < 0 ? `${Math.abs(n)} BCE` : String(n);
const range = (pages = []) => [...new Set(pages)].join(', ');
const bookName = (map, document) => map.books?.find((b) => b.document_id === document)?.name || 'Original reading';
const conceptName = (map, id) => map.concepts.find((c) => c.id === id)?.title || 'Unavailable concept';
const status = (item) => item.parent_review && item.parent_review.status !== 'unreviewed'
  ? reviewLabel[item.parent_review.status] : item.status === 'pending' ? 'Pending link' : item.status === 'needs_review' ? 'Needs source review' : 'AI proposal';

async function download(endpoint, filename) {
  const response = await request(endpoint);
  if (!response.ok) throw new Error('The saved file could not be opened. Check the home server and try again.');
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function Evidence({ map, item, onSource }) {
  const citations = Array.isArray(item.evidence) ? item.evidence : item.evidence ? [item.evidence] : [];
  return <div className="flex flex-col gap-3">{citations.map((cite, i) => {
    const unit = cite.unit_id || item.unit_id;
    const section = map.sections?.find((s) => s.id === unit);
    return <div key={i} className="rounded-xl bg-paper p-3">
      <blockquote className="whitespace-pre-wrap border-l-2 border-action pl-3">“{cite.quote}”</blockquote>
      <p className="mt-2 text-muted">{bookName(map, section?.document_id || item.document_id)} · PDF page {cite.page}{cite.page_end ? `–${cite.page_end}` : ''}</p>
      {unit && <Button size="sm" variant="quiet" onClick={() => onSource(unit, cite)}>Inspect original reading</Button>}
      {(cite.unit_ids || []).filter((id) => id !== unit).map((id) => <Button key={id} size="sm" variant="quiet" onClick={() => onSource(id, cite)}>Inspect continuation section</Button>)}
    </div>;
  })}</div>;
}

function ReadingSource({ map, source, onClose }) {
  const { data, error, isPending } = useQuery({ queryKey: ['map-reading', map.id, source.unit], queryFn: () => booksApi.mapReading(map.id, source.unit) });
  const [pdf, setPdf] = useState(null);
  const sorted = data?.pages ? [...data.pages].sort((a, b) => (a.page === source.cite?.page ? -1 : b.page === source.cite?.page ? 1 : a.page - b.page)) : [];
  return <><Dialog open title="Original reading evidence" width={850} onClose={onClose} footer={<Button onClick={onClose}>Back to map</Button>}
    description="Saved source text. Opening it does not call the AI. Page numbers here refer to the PDF, including its front matter.">
    {isPending && <p role="status">Loading saved reading…</p>}
    {error && <p role="alert">{error.message}</p>}
    {data && <div className="flex flex-col gap-5 text-sm">
      <p className="font-semibold">{data.name}</p>
      {source.cite && <blockquote className="border-l-2 border-action pl-3 bg-action-soft p-3">“{source.cite.quote}”</blockquote>}
      {!sorted.length && <p>This section has no checked reading excerpts. It needs source review.</p>}
      {sorted.map((p) => <section key={p.page} className="border-t border-line pt-3">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3"><h3 className="font-semibold">PDF page {p.page}</h3>
          {p.pdf_available && <Button size="sm" onClick={() => setPdf(p.page)}>Open original PDF page {p.page}</Button>}</div>
        <p className="whitespace-pre-wrap leading-relaxed">{p.text}</p>
      </section>)}
      <p className="text-muted">Combined books show checked reading excerpts so teacher answers on the same page stay private.</p>
    </div>}
  </Dialog>{pdf && <Suspense fallback={<p role="status">Loading original page reader…</p>}><OriginalPdf map={map} document={data.document_id} page={pdf} onClose={() => setPdf(null)} /></Suspense>}</>;
}

function ReviewEditor({ map, subject, selected, onClose, onSaved, onSource, onConflict }) {
  const { kind, item } = selected;
  const [choice, setChoice] = useState(item.parent_review?.status || 'approved');
  const [note, setNote] = useState(item.parent_review?.note || '');
  const [values, setValues] = useState({ ...item });
  const [quotes, setQuotes] = useState((item.evidence || []).map?.((q) => ({ unit_id: q.unit_id, page: q.page, quote: q.quote,
    ...(q.page_end ? { page_end: q.page_end } : {}), ...(q.unit_ids ? { unit_ids: q.unit_ids } : {}) })) || []);
  const [changed, setChanged] = useState({});
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');
  const title = item.title || item.text || (kind === 'connection' ? `${conceptName(map, item.from_concept)} → ${conceptName(map, item.to_concept)}` : selected.title);
  const change = (key, value) => { setValues((v) => ({ ...v, [key]: value })); setChanged((v) => ({ ...v, [key]: value })); };
  const save = async () => {
    setBusy(true); setProblem('');
    try {
      // An existing parent correction is carried forward when its reviewed
      // content is unchanged; selecting unreviewed restores the saved proposal.
      const previous = map.review_history?.filter((r) => r.kind === kind && r.target_id === item.review_id).at(-1);
      const changes = choice === 'corrected' ? { ...(previous?.status === 'corrected' ? previous.changes : {}), ...changed } : {};
      const updated = await booksApi.reviewMap(map.id, { expected_revision: map.review_revision, kind, target_id: item.review_id, status: choice, note, changes }, ...(subject ? [subject] : []));
      onSaved(updated); onClose();
    } catch (e) { if (e.status === 409) await onConflict(); setProblem(e.message); }
    finally { setBusy(false); }
  };
  const text = (key, label, multiline = false) => <Field label={label} key={key}>{multiline
    ? <textarea className={`${inputClasses} h-24 py-2`} value={values[key] || ''} onChange={(e) => change(key, e.target.value)} />
    : <input className={inputClasses} value={values[key] || ''} onChange={(e) => change(key, e.target.value)} />}</Field>;
  return <Dialog open title="Parent review" width={780} onClose={busy ? undefined : onClose}
    description="Your review is saved separately from the AI proposal. It changes no student work, grades, current lessons, or audio."
    footer={<><Button disabled={busy} onClick={onClose}>Cancel</Button><Button variant="primary" disabled={busy} onClick={save}>{busy ? 'Saving…' : 'Save parent review'}</Button></>}>
    <div className="flex flex-col gap-4 text-sm">
      <h3 className="font-semibold">{title}</h3>
      {item.objective && <p>Learning goal: {item.objective}</p>}
      {(item.explanation || item.reason) && <p>{item.explanation || item.reason}</p>}
      {kind === 'event' && <p>{year(item.start_year)}{item.end_year != null && item.end_year !== item.start_year ? `–${year(item.end_year)}` : ''} · {item.date_text}</p>}
      {item.ai_proposal && <details><summary className="cursor-pointer font-semibold">Compare the saved AI proposal</summary><div className="mt-2 flex flex-col gap-2">
        <p>{item.ai_proposal.title || item.ai_proposal.text || item.ai_proposal.relationship}</p>
        <p>{item.ai_proposal.objective}</p><p>{item.ai_proposal.explanation || item.ai_proposal.reason}</p>
        {kind === 'event' && <p>{year(item.ai_proposal.start_year)} · {item.ai_proposal.date_text}</p>}
        <Evidence map={map} item={item.ai_proposal} onSource={onSource} />
      </div></details>}
      <Evidence map={map} item={item} onSource={onSource} />
      {kind === 'connection' && <div className="flex flex-col gap-3">{[item.from_concept, item.to_concept].map((id, i) => {
        const c = map.concepts.find((v) => v.id === id);
        return c && <section key={i}><h4 className="font-semibold mb-2">{c.title}</h4><Evidence map={map} item={c} onSource={onSource} /></section>;
      })}</div>}
      <Field label="Review decision"><select className={inputClasses} value={choice} onChange={(e) => setChoice(e.target.value)}>
        <option value="approved">Accept original proposal</option><option value="corrected">Corrected by parent</option>
        <option value="rejected">Rejected by parent</option><option value="unreviewed">Restore original proposal</option>
      </select></Field>
      {choice === 'corrected' && <div className="flex flex-col gap-3 rounded-xl border border-line p-3">
        {['concept', 'event'].includes(kind) && text('title', 'Title')}
        {kind === 'concept' && <>{text('objective', 'Learning goal')}{text('explanation', 'Explanation', true)}</>}
        {kind === 'event' && <>{text('date_text', 'Date as described in the source')}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">{['start_year', 'end_year'].map((key) => <Field key={key} label={key === 'start_year' ? 'Start year (negative for BCE)' : 'End year (leave blank if unknown)'}
            type="number" min={-10000} max={10000} value={values[key] ?? ''} onChange={(e) => change(key, e.target.value === '' ? null : Number(e.target.value))} />)}</div>
          <label className="flex gap-2 items-center"><input type="checkbox" checked={Boolean(values.approximate)} onChange={(e) => change('approximate', e.target.checked)} />Approximate date</label></>}
        {kind === 'connection' && <>{['from_concept', 'to_concept'].map((key) => <Field key={key} label={key === 'from_concept' ? 'From concept' : 'To concept'}>
          <select className={inputClasses} value={values[key]} onChange={(e) => change(key, e.target.value)}>{map.concepts.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}</select></Field>)}
          {text('relationship', 'Relationship')}{text('explanation', 'Explanation', true)}</>}
        {kind === 'exercise_link' && <>{text('reason', 'Reason for the reading link', true)}
          <p>Choose a reading section, then copy a quotation from its original page. The server checks the quotation before saving.</p>
          {quotes.map((q, i) => <div key={i} className="flex flex-col gap-2 border-t border-line pt-3">
            <Field label={`Reading section ${i + 1}`}><select className={inputClasses} value={q.unit_id} onChange={(e) => {
              const next = quotes.map((v, n) => n === i ? { ...v, unit_id: e.target.value, page: map.sections.find((s) => s.id === e.target.value).pages[0], quote: '' } : v);
              setQuotes(next); change('evidence', next);
            }}>{map.sections.map((s) => <option key={s.id} value={s.id}>{bookName(map, s.document_id)} · PDF {range(s.pages)}</option>)}</select></Field>
            <Button size="sm" onClick={() => onSource(q.unit_id)}>Inspect selected section</Button>
            <Field label={`PDF page ${i + 1}`} type="number" min={1} value={q.page} onChange={(e) => { const next = quotes.map((v, n) => n === i ? { ...v, page: Number(e.target.value) } : v); setQuotes(next); change('evidence', next); }} />
            <Field label={`Exact quotation ${i + 1}`}><textarea className={`${inputClasses} h-24 py-2`} maxLength={800} value={q.quote} onChange={(e) => {
              const next = quotes.map((v, n) => n === i ? { ...v, quote: e.target.value } : v); setQuotes(next); change('evidence', next);
            }} /></Field>
            <Button size="sm" onClick={() => { const next = quotes.filter((_, n) => n !== i); setQuotes(next); change('evidence', next); }}>Remove quotation {i + 1}</Button>
          </div>)}
          <Button size="sm" disabled={!map.sections.length || quotes.length >= 5} onClick={() => {
            const first = map.sections[0]; const next = [...quotes, { unit_id: first.id, page: first.pages[0], quote: '' }]; setQuotes(next); change('evidence', next);
          }}>Add reading evidence</Button></>}
        {kind === 'issue' && <p>Describe your finding below. The original warning remains in the history.</p>}
      </div>}
      <Field label="Parent note" hint="Required for a correction or rejection."><textarea aria-label="Parent note" className={`${inputClasses} h-24 py-2`} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      {map.review_history?.some((r) => r.target_id === item.review_id) && <details><summary className="cursor-pointer font-semibold">Earlier parent reviews</summary>
        {map.review_history.filter((r) => r.kind === kind && r.target_id === item.review_id).map((r) => <p key={r.id} className="mt-2">{reviewLabel[r.status]} · {r.created_at} · {r.note || 'No note'}</p>)}</details>}
      {problem && <p role="alert" className="text-problem">{problem}</p>}
      <p className="text-muted">Saving uses no AI allowance. Reopening or continuing the same source analysis preserves your review; changed sources are flagged for inspection.</p>
    </div>
  </Dialog>;
}

function MapContent({ map, onReview, onSource }) {
  const [tab, setTab] = useState('Overview');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [page, setPage] = useState(0);
  const [problem, setProblem] = useState('');
  const chooseTab = (next) => { setTab(next); setSearch(''); setFilter('all'); setPage(0); };
  const byBook = (a, b) => (map.books.find((s) => s.document_id === a.document_id)?.position || 0) - (map.books.find((s) => s.document_id === b.document_id)?.position || 0) || (a.pages?.[0] || 0) - (b.pages?.[0] || 0);
  let rows = [];
  let kind = '';
  const exercises = (map.exercises || []).map((e) => ({ ...e, ...map.exercise_links.find((l) => l.exercise_id === e.id) }));
  if (tab === 'Concepts') { kind = 'concept'; rows = map.concepts; }
  if (tab === 'Timeline') { kind = 'event'; rows = [...map.events].sort((a, b) => (a.start_year ?? Infinity) - (b.start_year ?? Infinity)); }
  if (tab === 'Connections') { kind = 'connection'; rows = map.connections; }
  if (tab === 'Review items') { kind = 'issue'; rows = [
    ...(map.review_issues || map.issues.map((text) => ({ text }))).map((r) => ({ ...r, review_kind: 'issue' })),
    ...exercises.filter((r) => r.status === 'needs_review' || r.answer_link_status === 'needs_review').map((r) => ({ ...r, review_kind: 'exercise_link' })),
  ]; }
  if (tab === 'Exercises') { kind = 'exercise_link'; rows = exercises; }
  const title = (r) => r.title || r.text || (kind === 'connection' ? `${conceptName(map, r.from_concept)} → ${conceptName(map, r.to_concept)}` : `Chapter ${r.chapter ?? '?'} · ${r.section || 'Exercise'} · ${r.reference}`);
  rows = rows.filter((r) => `${title(r)} ${r.prompt || ''} ${r.reason || ''} ${r.parent_review?.note || ''}`.toLowerCase().includes(search.toLowerCase()) &&
    (filter === 'all' || (filter === 'reviewed' ? r.parent_review && r.parent_review.status !== 'unreviewed' : !r.parent_review || r.parent_review.status === 'unreviewed')));
  const end = Math.min((page + 1) * 25, rows.length);
  return <div className="flex flex-col gap-4 text-sm">
    <nav aria-label="Source map views" className="flex flex-wrap gap-1 border-b border-line pb-2">{tabs.map((name) => <Button key={name} size="sm" variant={tab === name ? 'primary' : 'quiet'} aria-pressed={tab === name} onClick={() => chooseTab(name)}>{name}</Button>)}</nav>
    {map.coverage.complete === false && <p role="status" className="rounded-xl bg-attention-soft p-3 text-attention">{map.coverage.pending_pages > 0
      ? 'Source review checkpoint saved. Page interpretation and exercise indexing are still incomplete.'
      : `The whole-book overview is saved. Exercise linking is unfinished; this snapshot still has ${map.coverage.pending_exercises} pending links.`}</p>}
    {map.unapplied_reviews?.length > 0 && <p role="status" className="text-attention">{map.unapplied_reviews.length} earlier parent reviews could not be applied to these sources. Inspect them in History before using this map.</p>}
    {tab === 'Overview' && <>
      <p>{map.coverage.books} books · {map.coverage.pages} pages processed · {map.concepts.length} proposed concepts · {map.coverage.exercises} exercises indexed.</p>
      {map.coverage.pending_pages > 0 && <p role="status" className="text-attention">{map.coverage.checked_pages} pages checked · {map.coverage.pending_pages} pages awaiting source review. Unchecked content is excluded from teaching evidence.</p>}
      <p className="whitespace-pre-wrap leading-relaxed">{map.overview}</p>
      <p>{map.connections.length} proposed connections · {map.events.length} source-linked timeline entries · {map.flagged_items} items flagged.</p>
      {map.review_counts && <p>{map.review_counts.approved + map.review_counts.corrected} items checked or corrected by a parent · {map.review_counts.rejected} rejected.</p>}
      <p className="text-muted">The overview paragraph is the saved AI summary. Parent corrections appear on the individual items. These proposals are not used in current lessons yet.</p>
      {map.issues.length > 0 && <details open><summary className="font-semibold">Items to inspect</summary><ul className="list-disc pl-5 mt-2">{map.issues.slice(0, 12).map((s, i) => <li key={i}>{s}</li>)}</ul></details>}
      <Button size="sm" onClick={() => chooseTab('Review items')}>Inspect review items</Button>
    </>}
    {tab === 'Books' && <div className="flex flex-col gap-3">{[...(map.books || [])].sort((a, b) => a.position - b.position).map((b) => <article key={b.id} className="rounded-xl border border-line p-4">
      <h3 className="font-semibold">{b.position + 1}. {b.name}{b.is_main ? ' · main book' : ''}</h3>
      <p>{bookRoles.find(([role]) => role === b.role)?.[1]} · {b.pages} PDF pages{b.edition ? ` · ${b.edition}` : ''}</p>
      {b.companion_id && <p>Reading companion: {map.books.find((v) => v.id === b.companion_id)?.name}</p>}
      {b.answer_for_id && <p>Answer key for: {(b.answer_for_ids || [b.answer_for_id]).map(id=>map.books.find(v=>v.id===id)?.name).filter(Boolean).join('; ')}</p>}
      {b.role === 'answer_key' && <p className="text-muted">Teacher answers remain private. Only source references appear in this map.</p>}
      {(map.book_relationships || []).filter(r=>r.from_document_id===b.document_id).map((r,i)=><div key={i} className="mt-3 border-t border-line pt-3">
        <p className="font-semibold">{r.relationship.replaceAll('_',' ')} · {bookName(map,r.to_document_id)}</p>
        <p>{r.explanation}</p><p className="text-muted">Source PDF page {r.source_page} · destination PDF pages {Math.min(...r.target_pages)}–{Math.max(...r.target_pages)}</p>
        <blockquote className="mt-2 border-l-2 border-action pl-3">“{r.source_quote}”</blockquote>
      </div>)}
    </article>)}</div>}
    {tab === 'Reading order' && <><p className="text-muted">Book order and PDF page order. Historical date order is shown separately in Timeline.</p>
      {[...(map.sections || [])].sort(byBook).map((s) => <article key={s.id} className="border-b border-line pb-3">
        <h3 className="font-semibold">{bookName(map, s.document_id)} · PDF pages {range(s.pages)}</h3><p className="mt-1">{s.overview}</p>
        <Button size="sm" variant="quiet" onClick={() => onSource(s.id)}>Inspect reading section</Button>
      </article>)}</>}
    {kind && <>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3"><Field label="Search this view" value={search} onChange={(e) => { setSearch(e.target.value); setPage(0); }} />
        <Field label="Parent review filter"><select className={inputClasses} value={filter} onChange={(e) => { setFilter(e.target.value); setPage(0); }}><option value="all">All items</option><option value="unreviewed">Not reviewed by a parent</option><option value="reviewed">Reviewed by a parent</option></select></Field></div>
      {kind === 'exercise_link' && <p className="text-muted">Original chapter and exercise numbering is retained. Reading links and answer-key references are separate; no answers are displayed.</p>}
      {tab === 'Review items' && <p className="text-muted">Source warnings and exercises needing source review. Unfinished links are listed separately in Exercises.</p>}
      <div className="overflow-x-auto"><table className="block sm:table w-full text-left"><caption className="block sm:table-caption text-left text-muted pb-2">{rows.length} items · {rows.length ? page * 25 + 1 : 0}–{end} shown</caption>
        <thead className="hidden sm:table-header-group"><tr className="border-b border-line"><th className="py-2 pr-3">{kind === 'event' ? 'Historical date / event' : tab === 'Exercises' ? 'Original exercise / reading' : 'Item'}</th><th className="p-2">Review</th><th className="p-2"><span className="sr-only">Action</span></th></tr></thead>
        <tbody className="block sm:table-row-group">{rows.slice(page * 25, end).map((r, i) => <tr key={`${r.review_id}:${i}`} className="grid sm:table-row border-b border-line align-top py-3 sm:py-0">
          <td className="block sm:table-cell py-3 sm:pr-3 min-w-0 sm:min-w-48 break-words">
            {kind === 'event' && <p className="text-action font-semibold">{year(r.start_year)}{r.end_year != null && r.end_year !== r.start_year ? `–${year(r.end_year)}` : ''}{r.approximate ? ' · approximate' : ''}</p>}
            <p className="font-semibold">{title(r)}</p>
            {r.document_id && <p className="text-muted">{bookName(map, r.document_id)}{r.pages ? ` · PDF ${range(r.pages)}` : ''}</p>}
            {kind === 'concept' && <p>{r.objective}</p>}
            {kind === 'connection' && <p>{r.relationship} · {r.explanation}</p>}
            {(r.review_kind || kind) === 'exercise_link' && <><p className="whitespace-pre-wrap mt-1">{r.student_safe ? r.prompt : 'Exercise text needs source review.'}</p><p className="text-muted mt-1">{r.reason}</p>
              <p className="text-muted">Answer source: {r.answer_link_status}{r.answer_source?.pages?.length ? ` · PDF ${range(r.answer_source.pages)}` : ''}</p></>}
            {r.parent_review?.note && <p className="mt-2 text-action">Parent: {r.parent_review.note}</p>}
          </td><td className="block sm:table-cell py-2 sm:p-2 sm:whitespace-nowrap">{status(r)}</td><td className="block sm:table-cell py-2 sm:p-2"><Button size="sm" onClick={() => onReview({ kind: r.review_kind || kind, item: r, title: title(r) })} aria-label={`Review ${title(r)}`}>Inspect / review</Button></td>
        </tr>)}</tbody>
      </table></div>
      {!rows.length && <p>No items match this view.</p>}
      <div className="flex flex-wrap gap-3"><Button size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous 25</Button><Button size="sm" disabled={end >= rows.length} onClick={() => setPage(page + 1)}>Next 25</Button></div>
    </>}
    {tab === 'History' && <>
      {!map.review_history?.length && <p>No parent corrections have been saved yet.</p>}
      {[...(map.review_history || [])].reverse().map((r) => <article key={r.id} className="border-b border-line pb-3"><p className="font-semibold">{reviewLabel[r.status]} · {r.kind.replace('_', ' ')} · revision {r.review_number}</p>
        <p>{r.original.title || r.original.text || r.original.exercise_id || r.original.relationship}</p><p className="text-muted">{r.created_at}</p><p>{r.note || 'No note'}</p>
        {Object.keys(r.changes).length > 0 && <details><summary>Saved changes</summary><pre className="whitespace-pre-wrap break-words text-xs mt-2">{JSON.stringify(r.changes, null, 2)}</pre></details>}
        {map.unapplied_reviews?.some((u) => u.id === r.id) && <p className="text-attention">Not applied: this item or its source evidence changed. Keep this review as a reference when reviewing the new item.</p>}
      </article>)}
    </>}
    <div className="border-t border-line pt-3 flex flex-wrap gap-3 items-center"><Button size="sm" onClick={async () => {
      try { await download(`/subject-maps/${map.id}/export`, 'subject-source-map.json'); } catch (e) { setProblem(e.message); }
    }}>Export saved map and reviews</Button><p className="text-muted">Viewing, reviewing, and exporting use no AI allowance.</p></div>
    {problem && <p role="alert" className="text-problem">{problem}</p>}
  </div>;
}

export default function SubjectSourceMap({ id, subject, onClose }) {
  const client = useQueryClient();
  const queryKey = ['subject-map', id, ...(subject ? [subject] : [])];
  const { data: map, error, isPending } = useQuery({ queryKey, queryFn: () => booksApi.subjectMap(id, subject) });
  const [selected, setSelected] = useState(null);
  const [source, setSource] = useState(null);
  const [saved, setSaved] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const [selectionProblem, setSelectionProblem] = useState('');
  const selectMap = async () => {
    setSelecting(true); setSelectionProblem('');
    try {
      const updated = await booksApi.selectMap(id, { ...(subject ? { subject_id: subject } : {}), expected_revision: map.teaching_selection?.selection_number || 0, expected_review_revision: map.review_revision });
      client.setQueryData(queryKey, updated);
    } catch (e) { setSelectionProblem(e.message); client.invalidateQueries({ queryKey }); }
    finally { setSelecting(false); }
  };
  const inspect = (unit, cite) => setSource({ unit, cite });
  return <>
    <Dialog open title="Saved subject overview" width={1080} onClose={onClose} footer={<Button onClick={onClose}>Close map</Button>}
      description="Inspect source connections and save parent corrections. Current lessons and learner records stay unchanged.">
      {isPending && <p role="status">Loading saved overview…</p>}{error && <p role="alert" className="text-problem">{error.message}</p>}
      {saved && <p role="status" className="text-action mb-3">Parent review saved on the home server. No AI generation charge.</p>}
      {map && <><div className="rounded-xl bg-paper p-4 mb-4 text-sm flex flex-col gap-2">
        <p>{map.teaching_selection?.note || 'Inspect and approve source concepts before selecting them for new lessons.'}</p>
        <p className="text-muted">Only checked concepts and connections enter teaching context. Selecting them saves a fixed version without AI generation; started lessons keep their original context.</p>
        <Button size="sm" disabled={selecting || !((map.review_counts?.approved || 0) + (map.review_counts?.corrected || 0)) || (map.teaching_selection?.active && map.teaching_selection.map_id === id && map.teaching_selection.review_number === map.review_revision)} onClick={selectMap}>
          {selecting ? 'Selecting…' : 'Use checked portions for new lessons'}</Button>
        {selectionProblem && <p role="alert" className="text-problem">{selectionProblem}</p>}
      </div><MapContent map={map} onReview={setSelected} onSource={inspect} /></>}
    </Dialog>
    {map && selected && <ReviewEditor key={selected.item.review_id} map={map} selected={selected} onClose={() => setSelected(null)} onSource={inspect}
      subject={subject} onConflict={() => client.invalidateQueries({ queryKey })} onSaved={(updated) => { client.setQueryData(queryKey, updated); setSaved(true); }} />}
    {map && source && <ReadingSource map={map} source={source} onClose={() => setSource(null)} />}
  </>;
}
