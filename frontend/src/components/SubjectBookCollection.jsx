import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { booksApi, bookRoles, collectionPayload } from '../api/books';
import { Button, Dialog, Field } from '../ui';

const reading = (b) => ['textbook', 'combined'].includes(b.role);
const practice = (b) => ['workbook', 'test', 'combined'].includes(b.role);
const targets = (b) => b.answer_for_keys || (b.answer_for_key ? [b.answer_for_key] : []);

function CollectionEditor({ subject, collection, onClose }) {
  const client = useQueryClient();
  const [name, setName] = useState(collection.name);
  const [books, setBooks] = useState(collection.books.map((b) => ({ ...b })));
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');
  const tidy = (rows) => {
    const readings = rows.filter(reading);
    const main = readings.find((b) => b.is_main) || readings[0];
    return rows.map((b) => ({ ...b, is_main: b.key === main?.key,
      companion_key: ['workbook', 'test'].includes(b.role)
        ? readings.some((r) => r.key === b.companion_key) ? b.companion_key : readings.length === 1 ? readings[0].key : null : null,
      answer_for_key: b.role === 'answer_key' ? targets(b).find(k=>rows.some(r=>r.key===k && practice(r))) || null : null,
      answer_for_keys: b.role === 'answer_key' ? targets(b).filter(k=>rows.some(r=>r.key===k && practice(r))) : [],
    }));
  };
  const edit = (key, changes) => setBooks((rows) => tidy(rows.map((b) => b.key === key ? { ...b, ...changes } : b)));
  const move = (index, offset) => setBooks((rows) => {
    const changed = [...rows];
    [changed[index], changed[index + offset]] = [changed[index + offset], changed[index]];
    return changed;
  });
  const save = async () => {
    setBusy(true);
    setProblem('');
    try {
      await booksApi.saveCollection(subject.id, collectionPayload({ ...collection, name }, books));
      await client.invalidateQueries({ queryKey: ['subject-collection', subject.id] });
      onClose();
    } catch (e) { setProblem(e.message); }
    finally { setBusy(false); }
  };
  return <Dialog open title={`Organize ${subject.name} books`} width={820} onClose={busy ? undefined : onClose}
    description="Choose the main book, reading order, editions, and matching sources. These relationships help select the original sources for each lesson. Saving uses no AI allowance."
    footer={<><Button disabled={busy} onClick={onClose}>Cancel</Button><Button variant="primary" disabled={busy || !name.trim()} onClick={save}>{busy ? 'Saving…' : 'Save collection'}</Button></>}>
    <div className="flex flex-col gap-4">
      <Field label="Collection name" value={name} onChange={(e) => setName(e.target.value)} maxLength={150} />
      <p className="text-sm text-muted">The order here is the intended teaching sequence. Choose original pages separately for each lesson.</p>
      {books.map((book, i) => <article key={book.key} className="rounded-xl border border-line p-4 flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="font-semibold text-sm break-words">{i + 1}. {book.name}</p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={busy || i === 0} aria-label={`Move ${book.name} earlier`} onClick={() => move(i, -1)}>Earlier</Button>
            <Button size="sm" disabled={busy || i === books.length - 1} aria-label={`Move ${book.name} later`} onClick={() => move(i, 1)}>Later</Button>
            <Button size="sm" disabled={busy} aria-label={`Remove ${book.name} from collection`} onClick={() => setBooks((rows) => tidy(rows.filter((b) => b.key !== book.key)))}>Remove</Button>
          </div>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm font-semibold">Role<select aria-label={`Collection role for ${book.name}`} value={book.role} disabled={busy}
            className="block mt-1 rounded-lg border border-line p-2 bg-surface font-normal" onChange={(e) => edit(book.key, { role: e.target.value })}>
            {bookRoles.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></label>
          <Field label={`Edition for ${book.name}`} value={book.edition || ''} placeholder="Edition or volume (optional)" maxLength={150} disabled={busy}
            onChange={(e) => edit(book.key, { edition: e.target.value })} />
          {reading(book) && <label className="text-sm flex items-center gap-2 py-2"><input type="radio" name="collection-main-book" checked={book.is_main} disabled={busy}
            onChange={() => setBooks((rows) => rows.map((b) => ({ ...b, is_main: b.key === book.key })))} />Main book</label>}
        </div>
        {['workbook', 'test'].includes(book.role) && <label className="text-sm font-semibold">Companion textbook<select aria-label={`Collection companion for ${book.name}`} disabled={busy}
          value={book.companion_key || ''} onChange={(e) => edit(book.key, { companion_key: e.target.value || null })} className="block w-full mt-1 rounded-lg border border-line p-2 bg-surface font-normal">
          <option value="">Choose a textbook</option>{books.filter(reading).map((b) => <option key={b.key} value={b.key}>{b.name}{b.edition ? ` · ${b.edition}` : ''}</option>)}
        </select></label>}
        {book.role === 'answer_key' && <fieldset className="text-sm"><legend className="font-semibold">Matching workbooks and editions</legend>
          <p className="text-muted mb-2">Select every exact book covered by this answer key.</p>
          {books.filter(practice).map(b=><label key={b.key} className="flex items-center gap-2 py-1">
            <input type="checkbox" disabled={busy} checked={targets(book).includes(b.key)}
              aria-label={`Answers in ${book.name} for ${b.name}`} onChange={e=>{
                const selected=e.target.checked ? [...targets(book),b.key] : targets(book).filter(k=>k!==b.key);
                edit(book.key,{answer_for_key:selected[0] || null,answer_for_keys:selected});
              }}/>{b.name}{b.edition ? ` · ${b.edition}` : ''}
          </label>)}
        </fieldset>}
      </article>)}
      {!books.some(reading) && <p className="text-sm text-attention">Add a textbook or combined book to establish the reading sequence.</p>}
      <p className="text-sm text-muted">Removing a book from this collection keeps its saved lessons and student work available.</p>
      {problem && <p role="alert" className="text-sm text-problem">{problem}</p>}
    </div>
  </Dialog>;
}

export default function SubjectBookCollection({ subject, onAdd }) {
  const { data: collection, error, isPending } = useQuery({ queryKey: ['subject-collection', subject.id], queryFn: () => booksApi.collection(subject.id) });
  const [editing, setEditing] = useState(false);
  return <section aria-label="Subject book collection" className="rounded-2xl border border-line bg-surface p-4 md:p-5 flex flex-col gap-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h3 className="font-bold">Books to understand together</h3><p className="text-sm text-muted mt-1">Choose related books and their editions. Prepare each lesson directly from its selected original pages.</p></div>
      <div className="flex flex-wrap gap-2"><Button size="sm" onClick={onAdd}>Add books to collection</Button>
        <Button size="sm" disabled={!collection} onClick={() => setEditing(true)}>Organize books</Button></div>
    </div>
    {isPending && <p role="status" className="text-sm text-muted">Loading collection…</p>}
    {error && <p role="alert" className="text-sm text-problem">{error.message}</p>}
    {collection && <>
      <p className="text-sm font-semibold">{collection.name} · {collection.id ? `Saved · version ${collection.version}` : 'Suggested from existing books'}</p>
      <ol className="flex flex-col gap-3">
        {collection.books.map((b, i) => <li key={b.key} className="flex gap-3 text-sm">
          <span className="text-muted">{i + 1}.</span><div className="min-w-0"><p className="font-semibold break-words">{b.name}{b.is_main ? ' · main book' : ''}</p>
            <p className="text-muted">{bookRoles.find(([r]) => r === b.role)?.[1]}{b.edition ? ` · ${b.edition}` : ''} · {b.page_count} pages</p>
            {b.companion_key && <p className="text-muted">Reading: {collection.books.find((x) => x.key === b.companion_key)?.name || 'Choose a textbook'}</p>}
            {b.role === 'answer_key' && <p className="text-muted">Answers for: {targets(b).map(k=>collection.books.find(x=>x.key===k)?.name).filter(Boolean).join('; ') || 'Choose the exact workbook'}</p>}
          </div>
        </li>)}
      </ol>
      {!collection.books.length && <p className="text-sm text-muted">Add your textbook, workbooks, and answer keys here.</p>}
    </>}
    {editing && collection && <CollectionEditor subject={subject} collection={collection} onClose={() => setEditing(false)} />}
  </section>;
}
