import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { booksApi, bookRoles, collectionPayload } from '../api/books';
import { driveBooks } from '../api/documents';
import { subjectsApi } from '../api/subjects';
import { Button, Dialog, Field } from '../ui';

const guess = (name) => /answer.?key|gabarito|respostas/i.test(name) ? 'answer_key' : /tests|quiz/i.test(name) ? 'test' : /workbook|activity|journal|caderno.?de.?exerc/i.test(name) ? 'workbook' : 'textbook';

export default function BookImportDialog({ subject, onClose, onAdded }) {
  const [mode, setMode] = useState('incoming');
  const [books, setBooks] = useState([]);
  const [existingBooks, setExistingBooks] = useState([]);
  const [collection, setCollection] = useState(null);
  const [collectionProblem, setCollectionProblem] = useState('');
  const [selected, setSelected] = useState([]);
  const [filter, setFilter] = useState('');
  const [problem, setProblem] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [chapters, setChapters] = useState(10);
  const input = useRef(null);
  const client = useQueryClient();
  const refresh = async (source = mode) => {
    setLoading(true);
    setProblem('');
    try { setBooks(source === 'incoming' ? (await booksApi.incoming()).books : await driveBooks()); }
    catch (e) { setProblem(e.message); }
    finally { setLoading(false); }
  };
  useEffect(() => {
    refresh('incoming');
    booksApi.collection(subject.id).then((saved) => { setCollection(saved); setExistingBooks(saved.books); })
      .catch((e) => setCollectionProblem(e.message));
  }, [subject.id]);
  const existingTextbooks = existingBooks.filter((b) => ['textbook', 'combined'].includes(b.role));
  const chooseMode = (next) => { setMode(next); if (next === 'incoming' || next === 'existing') refresh(next); };
  const toggle = (book) => setSelected((current) => current.some((x) => x.path === book.path)
    ? current.filter((x) => x.path !== book.path) : [...current, { ...book, role: guess(book.name) }]);
  const upload = async (files) => {
    setBusy(true);
    setProblem('');
    try {
      const staged = [];
      for (const file of files) staged.push({ ...await booksApi.stage(file), role: guess(file.name) });
      setSelected((current) => [...current.filter((x) => !staged.some((s) => s.path === x.path)), ...staged]);
      chooseMode('incoming');
    } catch (e) { setProblem(e.message); }
    finally { setBusy(false); }
  };
  const prepare = async () => {
    setBusy(true);
    setProblem('');
    try {
      if (mode === 'printed') await subjectsApi.generateChapters(subject.id, chapters);
      else {
        const additions = selected.map(({ path, role, companion, answerFor, edition }) => ({ key: `selected:${path}`, path, role,
          edition: edition || '', is_main: false,
          companion_key: role === 'workbook' || role === 'test' ? companion || null : null,
          answer_for_key: role === 'answer_key' ? answerFor || null : null }));
        const combined = [...collection.books.map((b) => ({ ...b })), ...additions];
        if (!combined.some((b) => b.is_main)) {
          const main = combined.find((b) => ['textbook', 'combined'].includes(b.role));
          if (main) main.is_main = true;
        }
        await booksApi.saveCollection(subject.id, collectionPayload(collection, combined));
      }
      await client.invalidateQueries();
      onAdded?.();
      onClose();
    } catch (e) { setProblem(e.message); }
    finally { setBusy(false); }
  };
  return <Dialog open onClose={busy ? undefined : onClose} title={`Add books to ${subject.name}`} width={720}
    description="Add this subject's books and link each answer key to the book it answers. Saving reads each new book's contents to build its lessons, on this computer, with no AI."
    footer={<><Button onClick={onClose} disabled={busy}>Cancel</Button><Button variant="primary" disabled={busy || (mode !== 'printed' && (!selected.length || !collection))} onClick={prepare}>{busy ? 'Saving…' : mode === 'printed' ? 'Add chapters' : 'Save books to collection'}</Button></>}>
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant={mode === 'incoming' ? 'primary' : 'secondary'} onClick={() => chooseMode('incoming')}>Choose from Incoming Books</Button>
        <Button size="sm" onClick={() => input.current?.click()} disabled={busy}>Upload PDFs</Button>
        <Button size="sm" onClick={() => chooseMode('existing')}>Choose an existing book</Button>
        <Button size="sm" onClick={() => chooseMode('printed')}>Printed book</Button>
        <input ref={input} type="file" accept=".pdf,application/pdf" multiple className="hidden" aria-label="Upload books"
          onChange={(e) => { upload([...e.target.files]); e.target.value = ''; }} />
      </div>
      {mode === 'printed' ? <Field label="How many chapters?" type="number" min={1} max={100} value={chapters} onChange={(e) => setChapters(Number(e.target.value))} /> : <>
        <p className="text-sm text-muted">Drop future PDFs into Homeschooling / Incoming Books. You can also use subfolders.</p>
        <div className="flex items-end gap-2"><div className="flex-1"><Field label="Find a book" value={filter} onChange={(e) => setFilter(e.target.value)} /></div><Button size="sm" onClick={() => refresh()} disabled={loading}>Refresh</Button></div>
        {loading && <p role="status" className="text-sm text-muted">Listing books…</p>}
        {!loading && !books.length && <p className="text-sm text-muted">No PDFs here yet. Add files to Incoming Books or upload them.</p>}
        <div className="max-h-64 overflow-y-auto divide-y divide-line-soft">
          {books.filter((b) => b.path.toLowerCase().includes(filter.toLowerCase())).map((book) => <label key={book.path} className="flex items-center gap-3 py-3 text-sm cursor-pointer">
            <input type="checkbox" checked={selected.some((x) => x.path === book.path)} onChange={() => toggle(book)} disabled={busy || existingBooks.some((b) => b.path === book.path)} />
            <span className="min-w-0"><span className="block font-semibold break-words">{book.name}</span><span className="text-xs text-muted break-all">{existingBooks.some((b) => b.path === book.path) ? 'Already in this collection' : book.path}</span></span>
          </label>)}
        </div>
        {selected.length > 0 && <div className="rounded-xl border border-line p-3 flex flex-col gap-3">
          <p className="text-sm font-semibold">Selected books · check their roles</p>
          <p className="text-sm text-muted">Choose “Textbook + workbook” when a book includes both explanations and exercises. Match each answer key to its exact student book.</p>
          {selected.map((book) => <div key={book.path} className="flex flex-wrap gap-2 items-center text-sm">
            <span className="flex-1 min-w-40 break-words">{book.name}</span>
            <select aria-label={`Role for ${book.name}`} className="rounded-lg border border-line p-2 bg-surface" value={book.role}
              onChange={(e) => setSelected((current) => current.map((b) => b.path === book.path ? { ...b, role: e.target.value } : b))}>
              {bookRoles.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            {(book.role === 'workbook' || book.role === 'test') && (existingTextbooks.length > 0 || selected.filter((b) => ['textbook', 'combined'].includes(b.role)).length > 1) && <select
              aria-label={`Companion textbook for ${book.name}`} value={book.companion || ''} className="w-full rounded-lg border border-line p-2 bg-surface"
              onChange={(e) => setSelected((current) => current.map((b) => b.path === book.path ? { ...b, companion: e.target.value } : b))}>
              <option value="">{selected.filter((b) => ['textbook', 'combined'].includes(b.role)).length === 1 ? 'Use the selected textbook' : 'Choose a companion textbook'}</option>
              {selected.filter((b) => ['textbook', 'combined'].includes(b.role)).map((b) => <option key={b.path} value={`selected:${b.path}`}>{b.name} (selected)</option>)}
              {existingTextbooks.map((b) => <option key={b.key} value={b.key}>{b.name}</option>)}
            </select>}
            {book.role === 'answer_key' && <select aria-label={`Answer key belongs to ${book.name}`} value={book.answerFor || ''} className="w-full rounded-lg border border-line p-2 bg-surface"
              onChange={(e) => setSelected((current) => current.map((b) => b.path === book.path ? { ...b, answerFor: e.target.value } : b))}>
              <option value="">Choose the matching workbook and edition</option>
              {selected.filter((b) => ['workbook', 'test', 'combined'].includes(b.role)).map((b) => <option key={b.path} value={`selected:${b.path}`}>{b.name} (selected)</option>)}
              {existingBooks.filter((b) => ['workbook', 'test', 'combined'].includes(b.role)).map((b) => <option key={b.key} value={b.key}>{b.name}</option>)}
            </select>}
            <Field label={`Edition for ${book.name}`} placeholder="Edition or volume (optional)" value={book.edition || ''}
              onChange={(e) => setSelected((current) => current.map((b) => b.path === book.path ? { ...b, edition: e.target.value } : b))} />
          </div>)}
        </div>}
      </>}
      {(problem || collectionProblem) && <p role="alert" className="text-sm text-problem">{problem || collectionProblem}</p>}
    </div>
  </Dialog>;
}
