import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { driveBooks } from '../api/documents';

/** Choose a PDF already in the synced Homeschooling folder; it is linked by its path, not copied. */
export default function DriveBookPicker({ onPick, onClose }) {
  const [books, setBooks] = useState(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');

  useEffect(() => {
    driveBooks().then(setBooks).catch((e) => setError(e.message.replace(/^\/[^:]+: /, '')));
  }, []);

  const shown = (books || []).filter((b) => b.path.toLowerCase().includes(filter.toLowerCase()));
  return (
    <div className="fixed inset-0 z-50 bg-black/30 grid place-items-center p-4" role="dialog" aria-label="Books in Google Drive">
      <div className="bg-surface rounded-xl w-full max-w-lg max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between border-b p-4">
          <h2 className="font-semibold">Books in the Homeschooling folder</h2>
          <button type="button" onClick={onClose} aria-label="Close"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-4 space-y-3 overflow-y-auto">
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter by name" className="w-full rounded border p-2 text-sm" />
          {error && <p className="text-sm text-red-700">{error}</p>}
          {!books && !error && <p className="text-sm text-text-secondary">Listing the folder…</p>}
          {books && books.length === 0 && <p className="text-sm text-text-secondary">No PDFs in the Homeschooling folder yet.</p>}
          <ul className="divide-y text-sm">
            {shown.map((book) => (
              <li key={book.path} className="py-2 flex items-center justify-between gap-2">
                <span className="min-w-0">
                  <span className="block truncate">{book.name}</span>
                  <span className="block truncate text-xs text-text-secondary">{book.path}</span>
                </span>
                {book.linked ? <span className="text-xs text-text-secondary">Already linked</span> : (
                  <button type="button" onClick={() => onPick(book)} className="rounded bg-accent text-white px-3 py-1 text-xs">Use</button>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
