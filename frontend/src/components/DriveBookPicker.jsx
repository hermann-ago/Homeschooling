import { useEffect, useState } from 'react';
import { driveBooks } from '../api/documents';
import { Button, Dialog, Field } from '../ui';

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
    <Dialog open onClose={onClose} title="Books in the Homeschooling folder" width={560}
      description="The book stays where it is in Google Drive; the app links to it."
      footer={<Button onClick={onClose}>Cancel</Button>}>
      <div className="flex flex-col gap-3">
        <Field label="Filter" placeholder="Part of the name or folder" value={filter} onChange={(e) => setFilter(e.target.value)} autoFocus />
        {error && <p className="text-sm text-problem">{error}</p>}
        {!books && !error && <p className="text-sm text-muted">Listing the folder…</p>}
        {books && books.length === 0 && <p className="text-sm text-muted">No PDFs in the Homeschooling folder yet.</p>}
        <ul className="max-h-[50vh] overflow-y-auto divide-y divide-line-soft">
          {shown.map((book) => (
            <li key={book.path} className="py-2.5 flex items-center justify-between gap-3">
              <span className="min-w-0">
                <span className="block truncate text-[15px] font-semibold">{book.name}</span>
                <span className="block truncate text-[13px] text-muted">{book.path}</span>
              </span>
              {book.linked
                ? <span className="text-[13px] text-subtle whitespace-nowrap">Already linked</span>
                : <Button size="sm" variant="primary" onClick={() => onPick(book)}>Use</Button>}
            </li>
          ))}
        </ul>
      </div>
    </Dialog>
  );
}
