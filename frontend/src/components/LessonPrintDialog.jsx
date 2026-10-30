import { useState } from 'react';
import { Button, Dialog } from '../ui';
import { inputClasses } from '../ui/classes';
import { lessonPrintLayout, selectLessonPrintPages } from '../utils/lessonPrintOptions';

export default function LessonPrintDialog({ first, last, offset, busy, onClose, onPrint }) {
  const [selection, setSelection] = useState(`${first - offset}–${last - offset}`);
  const [parity, setParity] = useState('all');
  const [reverse, setReverse] = useState(false);
  const [pagesPerSheet, setPagesPerSheet] = useState(1);
  const [paper, setPaper] = useState('A4');
  const [orientation, setOrientation] = useState('portrait');
  const options = { selection, parity, reverse, pagesPerSheet, paper, orientation };
  let pages = [], error = '';
  try { pages = selectLessonPrintPages({ first, last, offset, ...options }); } catch (problem) { error = problem.message; }
  const layout = lessonPrintLayout(options);
  return <Dialog open onClose={busy ? undefined : onClose} title="Print lesson pages" width={540}
    description={`Choose from book pages ${first - offset}–${last - offset}. Your lesson stays open.`}
    footer={<><Button disabled={busy} onClick={onClose}>Cancel</Button><Button variant="primary" disabled={busy || Boolean(error)} onClick={() => onPrint(options)}>{busy ? 'Preparing pages…' : 'Open print dialog'}</Button></>}>
    <div className="flex flex-col gap-4 text-sm max-h-[60vh] overflow-auto">
      <label className="font-semibold">Book pages<input className={`${inputClasses} mt-1`} value={selection} disabled={busy} onChange={event => setSelection(event.target.value)} aria-describedby="print-page-help" /></label>
      <p id="print-page-help" className="-mt-3 text-xs text-muted">Use the numbers printed in the book, for example {first - offset}, {Math.min(last, first + 1) - offset}–{last - offset}.</p>
      <div className="grid grid-cols-2 gap-3">
        <label className="font-semibold">Page filter<select className={`${inputClasses} mt-1`} disabled={busy} value={parity} onChange={event => setParity(event.target.value)}><option value="all">All selected pages</option><option value="odd">Odd book pages only</option><option value="even">Even book pages only</option></select></label>
        <label className="font-semibold">Pages per sheet<select className={`${inputClasses} mt-1`} disabled={busy} value={pagesPerSheet} onChange={event => setPagesPerSheet(Number(event.target.value))}>{[1, 2, 4].map(number => <option key={number} value={number}>{number}</option>)}</select></label>
        <label className="font-semibold">Paper size<select className={`${inputClasses} mt-1`} disabled={busy} value={paper} onChange={event => setPaper(event.target.value)}><option>A4</option><option>Letter</option></select></label>
        <label className="font-semibold">Orientation<select className={`${inputClasses} mt-1`} disabled={busy} value={orientation} onChange={event => setOrientation(event.target.value)}><option value="portrait">Portrait</option><option value="landscape">Landscape</option></select></label>
      </div>
      <label className="flex items-start gap-2"><input type="checkbox" checked={reverse} disabled={busy} onChange={event => setReverse(event.target.checked)} />Reverse page order</label>
      {error ? <p role="alert" className="text-problem">{error}</p> : <section aria-label="Print layout preview" className="rounded-xl bg-paper p-3 flex gap-4 items-center">
        <div className="grid gap-1 bg-white border border-line p-1 shrink-0" style={{ width: 85, aspectRatio: `${layout.width}/${layout.height}`, gridTemplateColumns: `repeat(${layout.columns}, 1fr)`, gridTemplateRows: `repeat(${layout.rows}, 1fr)` }}>
          {Array.from({ length: pagesPerSheet }, (_, index) => <span key={index} className="border border-line text-xs flex items-center justify-center">{pages[index] ? pages[index] - offset : ''}</span>)}
        </div><p>{pages.length} book {pages.length === 1 ? 'page' : 'pages'} on {Math.ceil(pages.length / pagesPerSheet)} {Math.ceil(pages.length / pagesPerSheet) === 1 ? 'sheet' : 'sheets'}<span className="block mt-1 text-xs text-muted">Order: {pages.map(page => page - offset).join(', ')}</span></p>
      </section>}
      <p className="text-xs text-muted">{pagesPerSheet === 1 ? 'For manual two-sided printing, print odd pages, reload the paper, then print even pages. Reverse order if your printer needs it.' : 'For two-sided printing with multiple pages per sheet, use the printer’s two-sided option. The odd/even filter selects book pages, not sheet sides.'} This filter uses book page numbers.</p>
      <p className="text-xs text-muted">The app arranges pages per sheet. In the printer dialog, keep pages per sheet at 1, match the paper size and orientation above, and turn off headers and footers. Choose your printer, copies and colour there.</p>
    </div>
  </Dialog>;
}
