import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, ArrowUpRight, BookOpen, Check, Headphones, Plus, Search, Upload } from 'lucide-react';
import clsx from 'clsx';
import ScreenHeader from '../app/ScreenHeader';
import { useLearner } from '../app/learnerContext';
import { libraryApi } from '../api/library';
import { modeHref } from '../api/mode';
import { Button, Dialog, Field, ProgressBar } from '../ui';
import TeachingSkillEditor from '../components/TeachingSkillEditor';
import BookNavigation from '../components/BookNavigation';

const STAGES = ['The Gateway', 'Case Against the State', 'Practical Mechanics', 'Money & Banking', 'Fiction & Sci-Fi', 'Deep Philosophy & Ethics', 'The Heavyweights'];
const COLORS = ['#476859', '#596b86', '#91613f', '#867341', '#806481', '#546f78', '#6a615b'];
const active = job => ['queued', 'running'].includes(job?.status);
const status = book => {
  const reading = book.readings.find(r => r.active !== false);
  if (active(reading?.job)) return 'Indexing';
  if (reading?.job?.status === 'failed' || reading?.job?.status === 'waiting') return 'Preparation paused';
  if (reading?.total_topics) return reading.completed_topics === reading.total_topics ? 'Finished reading' : 'Ready to read';
  return book.document ? 'PDF saved' : 'Awaiting PDF';
};
const readerPath = (child, topic, session) => modeHref(`/lesson?${new URLSearchParams({ learner: child, topic, ...(session ? { session } : {}) })}`);

function BookMark({ book, large = false }) {
  return <div aria-hidden="true" style={{ backgroundColor: COLORS[book.stage - 1] }}
    className={clsx('relative overflow-hidden text-white shrink-0 border-l-4 border-black/15 shadow-sm flex flex-col justify-between', large ? 'w-28 h-40 sm:w-36 sm:h-48 md:w-44 md:h-60 rounded-r-xl p-4 md:p-5' : 'w-14 h-20 rounded-r-md p-2')}>
    <span className={clsx('font-display', large ? 'text-4xl' : 'text-xl')}>{String(book.position).padStart(2, '0')}</span>
    <span className={large ? 'text-xs tracking-wider uppercase opacity-85' : 'text-[9px] uppercase opacity-80'}>Stage {book.stage}</span>
    <div className="absolute inset-y-0 left-1 w-px bg-white/15" />
  </div>;
}

function AddBook({ onClose }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [form, setForm] = useState({ title: '', author: '', stage: 1, source_url: '', store_url: '' });
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');
  const save = async e => {
    e.preventDefault(); setBusy(true); setProblem('');
    try {
      const book = await libraryApi.add({ ...form, source_url: form.source_url || null, store_url: form.store_url || null });
      await client.invalidateQueries({ queryKey: ['library'] });
      onClose(); navigate(modeHref(`/books/${book.id}`));
    } catch (e) { setProblem(e.message); }
    finally { setBusy(false); }
  };
  return <Dialog open title="Add a book" onClose={busy ? undefined : onClose}
    footer={<><Button disabled={busy} onClick={onClose}>Cancel</Button><Button variant="primary" type="submit" form="new-library-book" disabled={busy || !form.title.trim() || !form.author.trim()}>{busy ? 'Saving…' : 'Add book'}</Button></>}>
    <form id="new-library-book" className="flex flex-col gap-4" onSubmit={save}>
      <Field label="Book title" value={form.title} maxLength={200} required onChange={e => setForm({ ...form, title: e.target.value })} />
      <Field label="Author" value={form.author} maxLength={200} required onChange={e => setForm({ ...form, author: e.target.value })} />
      <Field label="Reading stage"><select className="rounded-xl border border-line bg-surface p-3" value={form.stage} onChange={e => setForm({ ...form, stage: Number(e.target.value) })}>
        {STAGES.map((title, i) => <option value={i + 1} key={title}>{i + 1}. {title}</option>)}
      </select></Field>
      <Field label="Source link (optional)" type="url" value={form.source_url} onChange={e => setForm({ ...form, source_url: e.target.value })} />
      <Field label="Store link (optional)" type="url" value={form.store_url} onChange={e => setForm({ ...form, store_url: e.target.value })} />
      <p className="text-sm text-muted">Save the title now. You can upload its PDF later.</p>
      {problem && <p role="alert" className="text-sm text-problem">{problem}</p>}
    </form>
  </Dialog>;
}

export default function Books() {
  const { single, learners } = useLearner();
  const [search, setSearch] = useState('');
  const [stage, setStage] = useState(0);
  const [filter, setFilter] = useState('all');
  const [adding, setAdding] = useState(false);
  const { data, error, isPending, refetch } = useQuery({ queryKey: ['library', single], queryFn: () => libraryApi.list(single), enabled: Boolean(single),
    refetchInterval: q => q.state.data?.books.some(b => b.readings.some(r => active(r.job))) ? 3000 : false });
  const child = learners.find(c => c.id === single);
  const books = data?.books || [];
  const visible = books.filter(b => (!stage || b.stage === stage) && `${b.title} ${b.author}`.toLowerCase().includes(search.toLowerCase())
    && (filter === 'all' || (filter === 'mine' && b.readings.some(r => r.active !== false)) || (filter === 'saved' && b.document) || (filter === 'missing' && !b.document)));
  return <>
    <ScreenHeader everyone={false} />
    <div className="max-w-7xl mx-auto px-4 md:px-10 py-7 md:py-10 flex flex-col gap-7">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><p className="text-xs font-bold uppercase tracking-[.18em] text-action mb-2">Beyond the school day</p>
          <h1 className="font-display text-4xl font-semibold">Books</h1>
          <p className="text-muted mt-3 max-w-xl">A shared book repository. Add a title to one child’s curriculum when they are ready, with their own lessons, answers, and progress.</p>
        </div>
        <Button icon={Plus} onClick={() => setAdding(true)}>Add a book</Button>
      </div>
      {data && <div className="flex flex-wrap gap-x-7 gap-y-2 text-sm text-muted border-y border-line py-4">
        <span><strong className="text-ink">{books.length}</strong> titles · 7 stages</span>
        <span><strong className="text-ink">{books.filter(b => b.document).length}</strong> PDFs saved</span>
        <span><strong className="text-ink">{books.filter(b => b.readings.some(r => r.active !== false)).length}</strong> in {child?.name}'s curriculum</span>
        <span className="md:ml-auto">Shared originals · individual curriculum</span>
      </div>}
      {!single ? <p>Add a learner in Settings to begin your family library.</p> : <>
        <div className="flex flex-wrap gap-3 items-end">
          <label className="relative flex-1 min-w-48"><span className="sr-only">Search books</span><Search aria-hidden="true" className="absolute left-3 top-3 w-5 h-5 text-muted" />
            <input type="search" className="w-full h-11 rounded-xl border border-line bg-surface pl-10 pr-3 text-sm" placeholder="Find a title or author" value={search} onChange={e => setSearch(e.target.value)} /></label>
          <Field label="Show"><select className="h-11 rounded-xl border border-line bg-surface px-3 text-sm" value={filter} onChange={e => setFilter(e.target.value)}>
            <option value="all">All books</option><option value="mine">In {child?.name}'s curriculum</option><option value="saved">PDF saved</option><option value="missing">Awaiting PDF</option>
          </select></Field>
        </div>
        <div aria-label="Reading stages" className="flex gap-2 overflow-x-auto pb-2">
          {[{ id: 0, title: 'All stages' }, ...(data?.stages || STAGES.map((title, i) => ({ id: i + 1, title })))].map(s =>
            <button type="button" key={s.id} aria-pressed={stage === s.id} onClick={() => setStage(s.id)}
              className={clsx('shrink-0 rounded-full px-4 py-2 text-sm border focus-visible:outline-action', stage === s.id ? 'bg-action text-white border-action' : 'bg-surface border-line text-muted hover:text-ink')}>
              {s.id ? `${s.id}. ${s.title}` : s.title}
            </button>)}
        </div>
        {isPending && <p role="status" className="text-muted">Loading the family shelf…</p>}
        {error && <div role="alert"><p className="text-problem">{error.message}</p><Button onClick={() => refetch()}>Try again</Button></div>}
        {!isPending && !error && !visible.length && <p className="py-10 text-muted text-center">No books match these filters.</p>}
        {(data?.stages || []).filter(s => visible.some(b => b.stage === s.id)).map(s => <section key={s.id} aria-labelledby={`stage-${s.id}`}>
          <div className="flex items-baseline gap-3 mb-4"><h2 id={`stage-${s.id}`} className="font-display text-2xl font-semibold">{s.title}</h2><span className="text-xs text-subtle">Stage {s.id}</span></div>
          <div className="grid grid-cols-1 xl:grid-cols-3 sm:grid-cols-2 gap-4">
            {visible.filter(b => b.stage === s.id).map(b => <Link key={b.id} to={modeHref(`/books/${b.id}`)}
              className="group flex flex-col rounded-2xl border border-line bg-surface p-5 hover:border-action/60 transition-colors focus-visible:outline-action">
              <div className="flex gap-4 flex-1"><BookMark book={b} /><div className="min-w-0"><h3 className="font-semibold text-[15px] leading-snug group-hover:text-action">{b.title}</h3><p className="text-sm text-muted mt-1.5">{b.author}</p><p className="text-xs text-subtle mt-2">{b.year} · {b.estimated_pages ? `~${b.estimated_pages} pages` : 'Length not recorded'}</p></div></div>
              <div className="flex items-center gap-2 pt-4 mt-4 border-t border-line-soft text-xs"><span className={b.document ? 'text-action font-semibold' : 'text-muted'}>{status(b)}</span>
                {b.readings.some(r => r.active !== false) && <span className="ml-auto flex items-center gap-1 text-action"><Check aria-hidden="true" className="w-3.5 h-3.5" />In curriculum</span>}
              </div>
            </Link>)}
          </div>
        </section>)}
        <p className="text-xs text-subtle max-w-3xl leading-relaxed">Titles, approximate lengths, availability notes and links come from your reading list. Links and download rights have not been checked. Each title waits for its actual PDF before chapter mapping or reading begins.</p>
      </>}
      {adding && <AddBook onClose={() => setAdding(false)} />}
    </div>
  </>;
}

export function BookDetail() {
  const { bookId } = useParams();
  const { single, learners } = useLearner();
  return <><ScreenHeader everyone={false} /><BookReading key={`${bookId}-${single}`} bookId={bookId} child={learners.find(c => c.id === single)} /></>;
}

export function BookReading({ bookId, child, embedded = false }) {
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');
  const [message, setMessage] = useState('');
  const [tools, setTools] = useState(false);
  const { data: book, error, isPending, refetch } = useQuery({ queryKey: ['library-book', bookId, child?.id], queryFn: () => libraryApi.book(bookId, child.id), enabled: Boolean(child),
    refetchInterval: q => q.state.data?.readings.some(r => active(r.job)) ? 2500 : false });
  const run = async (action, success) => {
    setBusy(true); setProblem(''); setMessage('');
    try { await action(); await refetch(); await Promise.all([
      client.invalidateQueries({ queryKey: ['library'] }), client.invalidateQueries({ queryKey: ['subjects'] }),
      client.invalidateQueries({ queryKey: ['progress'] }),
    ]); setMessage(success); }
    catch (e) { setProblem(e.message); }
    finally { setBusy(false); }
  };
  if (!child) return <p className="p-10">Add a learner in Settings to begin reading.</p>;
  if (isPending) return <p role="status" className="p-10 text-muted">Opening the book…</p>;
  if (error) return <div className="p-10"><Link to={modeHref('/books')}>Back to books</Link><p role="alert" className="text-problem mt-4">{error.message}</p><Button onClick={() => refetch()}>Try again</Button></div>;
  const reading = book.readings.find(r => r.active !== false);
  const pending = active(reading?.job);
  const next = reading?.topics.find(t => t.id === reading.resume_session?.topic_id) || reading?.topics.find(t => !t.completed) || reading?.topics[0];
  return <div className={clsx('min-w-0 flex flex-col gap-7', embedded ? 'flex-1' : 'max-w-5xl mx-auto px-4 md:px-10 py-7 md:py-10')}>
    <Link to={modeHref('/books')} className="text-sm font-semibold text-muted inline-flex items-center gap-2 self-start hover:text-action"><ArrowLeft aria-hidden="true" className="w-4 h-4" />Family books</Link>
    <div className="flex gap-6 md:gap-8 items-start"><BookMark book={book} large /><div className="min-w-0">
      <p className="text-xs uppercase tracking-wider font-semibold text-action mb-2">Stage {book.stage} · {book.stage_title}</p>
      <h1 className="font-display text-2xl md:text-4xl font-semibold leading-tight">{book.title}</h1>
      <p className="text-muted mt-3">{book.author}{book.year ? ` · ${book.year}` : ''}</p>
      <p className="text-sm text-muted mt-2">{[book.style, book.estimated_pages ? `Approximately ${book.estimated_pages} pages` : ''].filter(Boolean).join(' · ')}</p>
      <p className="text-sm font-semibold mt-4 text-action">{status(book)}</p>
    </div></div>
    {(problem || message) && <p role={problem ? 'alert' : 'status'} className={clsx('text-sm rounded-xl p-4 border', problem ? 'border-problem/30 text-problem' : 'border-action/30 text-action')}>{problem || message}</p>}
    <section aria-labelledby="reading-heading" className="rounded-2xl border border-line bg-surface p-5 md:p-6 flex flex-col gap-4">
      <div className="flex flex-wrap justify-between gap-3"><div><h2 id="reading-heading" className="font-display text-2xl font-semibold">Read with {child.name}</h2><p className="text-sm text-muted mt-2">Book preparation is shared for present and future readers. Each child keeps their own conversation, answers and progress.</p></div><Headphones aria-hidden="true" className="w-6 h-6 text-action" /></div>
      {book.shared_preparation?.guided_lesson > 0 && <p className="text-sm text-action">{book.shared_preparation.guided_lesson} shared lesson variant{book.shared_preparation.guided_lesson === 1 ? '' : 's'} saved, including explanations and quiz questions.</p>}
      {!reading ? <><Button variant="primary" icon={Plus} className="self-start" disabled={busy} onClick={() => run(() => libraryApi.enroll(book.id, child.id), `Added to ${child.name}'s curriculum.`)}>Add to {child.name}'s curriculum</Button>
        {book.readings.length > 0 && <p className="text-sm text-muted">Saved progress is retained and will resume when this book is added again.</p>}</> : <>
        <p className="text-sm text-action">A separate subject in {child.name}'s curriculum.</p>
        <Button size="sm" className="self-start" disabled={busy} onClick={() => run(() => libraryApi.pause(book.id, child.id), `Removed from ${child.name}'s curriculum. Progress is saved.`)}>Remove from {child.name}'s curriculum</Button>
        {reading.total_topics > 0 && <>
          <div className="flex items-center gap-4"><div className="flex-1"><ProgressBar value={reading.completed_topics / reading.total_topics * 100} /></div><span className="text-sm text-muted">{reading.completed_topics} of {reading.total_topics} topics read</span></div>
          {next && <Button as={Link} to={readerPath(child.id, next.id, reading.resume_session?.id)} variant="primary" icon={BookOpen} className="self-start">{reading.resume_session ? 'Resume reading session' : reading.completed_topics ? 'Continue reading' : 'Open reader'}</Button>}
          <p className="text-sm text-muted">The reader includes read-along and the AI companion. Create a guided lesson for explanations and topic quizzes. Listening alone does not establish understanding.</p>
        </>}
        {!book.document && <p className="text-sm text-muted">In {child.name}'s curriculum. Upload the PDF below to prepare its reading topics.</p>}
        {book.document && <>
          <Button className="self-start" variant="primary" disabled={busy || pending} onClick={() => run(() => libraryApi.prepare(book.id, child.id), 'Chapter map preparation queued. Original pages are used when preparing lessons.')}>{pending ? 'Reading table of contents…' : 'Prepare chapter map'}</Button>
          <p className="text-sm text-muted">Chapter maps use local contents or bookmarks. Prepared lessons and recordings can be reused when another child is ready. Book quizzes use true/false or single-choice answers.</p>
        </>}
        {reading.job && <div role="status" className="text-sm text-muted"><p>{reading.job.stage} · {reading.job.done} of {reading.job.total} contents pages read</p>{pending && <ProgressBar value={reading.job.total ? reading.job.done / reading.job.total * 100 : 0} className="mt-2" />}{reading.job.error && <p className="text-attention mt-2">{reading.job.error}</p>}</div>}
      </>}
    </section>
    <section aria-labelledby="original-heading" className="rounded-2xl border border-line p-5 md:p-6 flex flex-col gap-3">
      <h2 id="original-heading" className="font-display text-2xl font-semibold">The original book</h2>
      {book.document ? <>
        <p className="text-sm">{book.document.original_filename} · {book.document.page_count} PDF pages</p>
        <a href={modeHref(`/api/documents/${book.document.id}/content`)} target="_blank" rel="noreferrer" className="text-action text-sm font-semibold inline-flex items-center gap-1 self-start">View saved PDF<ArrowUpRight aria-hidden="true" className="w-4 h-4" /></a>
        <p className="text-xs text-muted break-all">Saved in Homeschooling/{book.document.file_path}</p>
      </> : <>
        <p className="text-sm text-muted">Add a PDF edition when you have it. The original is shared by the family and saved in the existing Drive-synced Homeschooling/Family Library/Books folder.</p>
        <label className={clsx('inline-flex items-center gap-2 self-start rounded-xl border border-line bg-surface px-4 py-3 font-semibold text-sm cursor-pointer focus-within:outline-2 focus-within:outline-action', busy && 'opacity-50')}>
          <Upload aria-hidden="true" className="w-4 h-4" />{busy ? 'Saving…' : 'Upload PDF'}<input type="file" accept=".pdf,application/pdf" className="sr-only" aria-label="Upload book PDF" disabled={busy} onChange={e => {
            const file = e.target.files?.[0]; e.target.value = ''; if (file) run(() => libraryApi.upload(book.id, file, book.revision), 'PDF saved. Add it to a reading list, then prepare its chapter map.');
          }} />
        </label><p className="text-xs text-subtle">PDF e-books up to 250 MB. Uploading starts no AI requests. EPUB files need a PDF edition for this reader.</p>
      </>}
    </section>
    {reading?.topics.length > 0 && <section aria-labelledby="topics-heading"><h2 id="topics-heading" className="font-display text-2xl font-semibold mb-4">Reading topics</h2>
      <ol className="divide-y divide-line rounded-2xl border border-line bg-surface overflow-hidden">{reading.topics.map((topic, i) => <li key={topic.id}>
        <Link to={readerPath(child.id, topic.id, reading.resume_session?.topic_id === topic.id ? reading.resume_session.id : null)} className="flex items-center gap-4 px-5 py-4 hover:bg-paper-deep focus-visible:outline-action">
          <span className="text-action shrink-0 w-6">{topic.completed ? <Check aria-label="Read" className="w-5 h-5" /> : String(i + 1).padStart(2, '0')}</span><div className="flex-1 min-w-0"><p className="font-semibold text-sm">{topic.title}</p><p className="text-xs text-muted mt-1">PDF pages {topic.page_start}–{topic.page_end}</p></div><ArrowUpRight aria-hidden="true" className="w-4 h-4 text-muted" />
        </Link></li>)}</ol>
    </section>}
    <section className="text-sm flex flex-col gap-3"><h2 className="font-semibold">Links from your reading list</h2>
      <div className="flex flex-wrap gap-5">{book.source_url && <a href={book.source_url} target="_blank" rel="noreferrer" className="text-action font-semibold inline-flex items-center gap-1">{book.source_label}<ArrowUpRight aria-hidden="true" className="w-4 h-4" /></a>}{book.store_url && <a href={book.store_url} target="_blank" rel="noreferrer" className="text-action font-semibold inline-flex items-center gap-1">Amazon listing<ArrowUpRight aria-hidden="true" className="w-4 h-4" /></a>}</div>
      {book.source_note && <p className="text-attention">{book.source_note}</p>}
      <p className="text-muted">Availability as supplied: {book.availability || 'Not checked'}. Links, editions and download rights have not been verified.</p>
    </section>
    {reading && <section className="border-t border-line pt-5"><button type="button" aria-expanded={tools} onClick={() => setTools(!tools)} className="text-sm font-semibold text-action">{tools ? 'Hide' : 'Show'} parent preparation tools</button>
      {tools && <div className="mt-5 flex flex-col gap-7"><TeachingSkillEditor subject={reading.subject} libraryBook={book.id} />{book.document && <BookNavigation subject={reading.subject} />}</div>}
    </section>}
  </div>;
}
