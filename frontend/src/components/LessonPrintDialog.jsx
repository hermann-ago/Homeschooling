import { useState } from 'react';
import { Button, Dialog } from '../ui';
import { inputClasses } from '../ui/classes';
import { arrangeLessonPrintSides, lessonPrintLayout } from '../utils/lessonPrintOptions';

export default function LessonPrintDialog({ first, last, offset = 0, initialOptions, busy, onClose, onPrint }) {
  const [selection, setSelection] = useState(initialOptions?.selection ?? `${first - offset}–${last - offset}`);
  const [parity, setParity] = useState(initialOptions?.parity ?? 'all');
  const [reverse, setReverse] = useState(initialOptions?.reverse ?? false);
  const [pagesPerSheet, setPagesPerSheet] = useState(initialOptions?.pagesPerSheet ?? 1);
  const [paper, setPaper] = useState(initialOptions?.paper ?? 'A4');
  const [orientation, setOrientation] = useState(initialOptions?.orientation ?? 'portrait');
  const options = { selection, parity, reverse, pagesPerSheet, paper, orientation };
  let sides = [], error = '';
  try { sides = arrangeLessonPrintSides({ first, last, offset, ...options }); } catch (problem) { error = problem.message; }
  const pages = sides.flatMap(side => side.pages).filter(page => page !== null);
  const blankSides = sides.filter(side => side.pages.every(page => page === null)).length;
  const layout = lessonPrintLayout(options);
  return <Dialog open onClose={busy ? undefined : onClose} title="Print lesson pages" width={540}
    description={`Choose from book pages ${first - offset}–${last - offset}. Your lesson stays open.`}
    footer={<><Button disabled={busy} onClick={onClose}>Cancel</Button><Button variant="primary" disabled={busy || Boolean(error)} onClick={() => onPrint(options)}>{busy ? 'Preparing pages…' : 'Open print dialog'}</Button></>}>
    <div className="flex flex-col gap-4 text-sm max-h-[60vh] overflow-auto">
      <label className="font-semibold">Book pages<input className={`${inputClasses} mt-1`} value={selection} disabled={busy} onChange={event => setSelection(event.target.value)} aria-describedby="print-page-help" /></label>
      <p id="print-page-help" className="-mt-3 text-xs text-muted">Use the numbers printed in the book, for example {first - offset}, {Math.min(last, first + 1) - offset}–{last - offset}.</p>
      <div className="grid grid-cols-2 gap-3">
        <label className="font-semibold">Sides to print<select className={`${inputClasses} mt-1`} disabled={busy} value={parity} onChange={event => setParity(event.target.value)}><option value="all">All sides</option><option value="odd">Fronts (odd sides)</option><option value="even">Backs (even sides)</option></select></label>
        <label className="font-semibold">Pages per sheet<select className={`${inputClasses} mt-1`} disabled={busy} value={pagesPerSheet} onChange={event => setPagesPerSheet(Number(event.target.value))}>{[1, 2, 4].map(number => <option key={number} value={number}>{number}</option>)}</select></label>
        <label className="font-semibold">Paper size<select className={`${inputClasses} mt-1`} disabled={busy} value={paper} onChange={event => setPaper(event.target.value)}><option>A4</option><option>Letter</option></select></label>
        <label className="font-semibold">Orientation<select className={`${inputClasses} mt-1`} disabled={busy} value={orientation} onChange={event => setOrientation(event.target.value)}><option value="portrait">Portrait</option><option value="landscape">Landscape</option></select></label>
      </div>
      <label className="flex items-start gap-2"><input type="checkbox" checked={reverse} disabled={busy} onChange={event => setReverse(event.target.checked)} />Reverse side order</label>
      {error ? <p role="alert" className="text-problem">{error}</p> : <section aria-label="Print layout preview" className="rounded-xl bg-paper p-3 flex gap-4 items-center">
        <div className="grid gap-1 bg-white border border-line p-1 shrink-0" style={{ width: 85, aspectRatio: `${layout.width}/${layout.height}`, gridTemplateColumns: `repeat(${layout.columns}, 1fr)`, gridTemplateRows: `repeat(${layout.rows}, 1fr)` }}>
          {(sides[0]?.pages || []).map((page, index) => <span key={index} className="border border-line text-xs flex items-center justify-center">{page === null ? 'Blank' : page - offset}</span>)}
        </div><div className="min-w-0"><p>{pages.length} book {pages.length === 1 ? 'page' : 'pages'} on {sides.length} sheet {sides.length === 1 ? 'side' : 'sides'}</p>
          {blankSides > 0 && <p className="text-xs text-muted">Includes {blankSides} blank {blankSides === 1 ? 'side' : 'sides'} to keep the paper aligned.</p>}
          <ol aria-label="Side printing order" className="mt-1 text-xs text-muted">{sides.map(side => <li key={side.number}>{side.number % 2 ? 'Front' : 'Back'} of sheet {Math.ceil(side.number / 2)}: {side.pages.map(page => page === null ? 'blank' : page - offset).join(', ')}</li>)}</ol>
        </div>
      </section>}
      <p className="text-xs text-muted">For manual two-sided printing, print Fronts, reload the same stack, then print Backs with the same book pages and layout. Reverse side order if your printer needs it. Odd/even refers to arranged sheet sides; book pages stay together in reading order.</p>
      <p className="text-xs text-muted">The app arranges pages per sheet. In the printer dialog, keep pages per sheet at 1, match the paper size and orientation above, and turn off headers and footers. For separate Fronts and Backs passes, choose one-sided printing and all pages there. For automatic two-sided printing, choose All sides here and enable two-sided printing there.</p>
    </div>
  </Dialog>;
}
