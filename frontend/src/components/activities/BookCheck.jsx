import { useEffect, useRef, useState } from 'react';
import { Button } from '../../ui';
import { readSaved, storageKey, writeSaved } from './durable';
import WorkCamera from './WorkCamera';

const MAX_PHOTOS = 8;
const RESULT = {
  looks_right: { label: 'Looks right', tone: 'text-action' },
  check_again: { label: 'Look again', tone: 'text-attention' },
  unclear: { label: 'Could not read', tone: 'text-attention' },
  not_found: { label: 'Not found in the photos', tone: 'text-muted' },
};

/** Paced lessons end with an optional photo check of the book pages. Nothing here is graded. */
export default function BookCheck({ check, sessionId, onUpload, onEvent, busy }) {
  const key = storageKey(sessionId, 'book-check-photos');
  const [photos, setPhotos] = useState(() => readSaved(key)?.ids || []);
  const [camera, setCamera] = useState(false);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);
  const picker = useRef(null);
  useEffect(() => { writeSaved(key, { ids: photos }); }, [key, photos]);
  const working = ['queued', 'checking'].includes(check.status);
  const upload = async (file) => {
    if (!file || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024) {
      setError('Use a JPG, PNG or WebP photo smaller than 10 MB.'); return false;
    }
    try {
      const id = await onUpload(file);
      if (!id) return false;
      setPhotos((previous) => [...new Set([...previous, id])]); setError(''); return true;
    } catch { setError('The photo was not saved. Please try again.'); return false; }
  };
  const send = async () => {
    const next = await onEvent('submit_book_check', { evidence_ids: photos });
    if (next?.book_check?.status === 'completed') { setPhotos([]); setOpen(false); }
  };
  const toCheck = (check.items || []).filter((item) => item.result !== 'looks_right');
  return <section aria-label="Check the book pages" className="rounded-xl border border-line p-3 flex flex-col gap-3">
    <div>
      <h2 className="font-semibold">Check my work</h2>
      <p className="text-sm text-muted">{check.count} exercise{check.count === 1 ? ' was' : 's were'} done in the book. Photograph the pages to see which answers to look at again. This is optional and nothing is marked wrong.</p>
    </div>
    {check.status === 'completed' && <div className="flex flex-col gap-2" role="status">
      {check.summary && <p className="text-sm font-semibold">{check.summary}</p>}
      {toCheck.length === 0 && <p className="text-sm text-action">Everything the photos showed looks right.</p>}
      {toCheck.map((item) => <article key={item.item_id} className="rounded-xl bg-paper p-3 text-sm">
        <p className={`font-semibold ${RESULT[item.result]?.tone || ''}`}>{RESULT[item.result]?.label || item.result}</p>
        <p className="mt-1 whitespace-pre-wrap">{item.prompt}</p>
        {item.answer && <p className="mt-1 text-muted">Read as: {item.answer}</p>}
        {item.note && <p className="mt-1">{item.note}</p>}
      </article>)}
      {(check.items || []).length > toCheck.length && <p className="text-xs text-muted">{(check.items || []).length - toCheck.length} other answer{(check.items || []).length - toCheck.length === 1 ? '' : 's'} looked right.</p>}
    </div>}
    {working && <p role="status" className="text-sm text-muted">Reading the pages in your photos…</p>}
    {check.status === 'failed' && <div className="flex flex-col gap-2"><p role="alert" className="text-sm text-attention">{check.error}</p>
      <Button disabled={busy} onClick={() => onEvent('retry_book_check')}>Try the check again</Button></div>}
    {!working && check.status !== 'failed' && (open || photos.length > 0 ? <>
      <Button disabled={busy || photos.length >= MAX_PHOTOS} onClick={() => setCamera(true)}>Take a photo of a page</Button>
      <Button variant="quiet" disabled={busy || photos.length >= MAX_PHOTOS} onClick={() => picker.current?.click()}>Choose an existing photo</Button>
      <input ref={picker} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" aria-label="Photo of a book page" onChange={(event) => { void upload(event.target.files?.[0]); event.target.value = ''; }} />
      {camera && <WorkCamera onPhoto={upload} onClose={() => setCamera(false)} />}
      {photos.length > 0 && <p role="status" className="text-sm text-action">{photos.length} page photo{photos.length === 1 ? '' : 's'} ready</p>}
      {error && <p role="alert" className="text-sm text-problem">{error}</p>}
      <Button variant="primary" disabled={busy || !photos.length} onClick={send}>Check {photos.length || ''} page photo{photos.length === 1 ? '' : 's'}</Button>
    </> : <Button onClick={() => setOpen(true)} disabled={busy}>{check.status === 'completed' ? 'Check again with new photos' : 'Photograph my pages'}</Button>)}
  </section>;
}
