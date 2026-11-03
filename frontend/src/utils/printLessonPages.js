import { pdfjs } from 'react-pdf';
import { arrangeLessonPrintSides, lessonPrintLayout } from './lessonPrintOptions';

const PRINT_DPI = 150;
let printFrame = null;

/** Print a selected, pre-arranged set of book pages without opening another tab. */
// `base` is the book PDF page held as page 1 of `data` (1 for a whole book).
export async function printLessonPages({ data, first, last, title = 'Lesson pages', offset = 0, base = 1,
  selection, parity, reverse, pagesPerSheet = 1, paper = 'A4', orientation = 'portrait', onProgress, onReady }) {
  const sides = arrangeLessonPrintSides({ first, last, offset, selection, parity, reverse, pagesPerSheet, paper, orientation });
  const total = sides.flatMap(side => side.pages).filter(number => number !== null).length;
  const layout = lessonPrintLayout({ pagesPerSheet, paper, orientation });
  let loading, pdf, frame;
  try {
    loading = pdfjs.getDocument({ data: data.slice() });
    pdf = await loading.promise;
    if (first < base || last - base + 1 > pdf.numPages) throw new Error('The lesson page range is outside this book.');
    printFrame?.remove();
    frame = document.createElement('iframe');
    frame.title = 'Lesson print document';
    frame.setAttribute('aria-hidden', 'true');
    frame.tabIndex = -1;
    Object.assign(frame.style, { position: 'fixed', left: '-10000px', top: '0', width: `${layout.width}mm`, height: `${layout.height}mm`, border: '0' });
    document.body.append(frame);
    printFrame = frame;
    const preview = frame.contentWindow, doc = frame.contentDocument;
    if (!preview || !doc) throw new Error('The browser could not prepare the print document.');
    doc.open();
    doc.write(`<!doctype html><html><head><meta charset="utf-8"><title>Lesson pages</title><style>
      * { box-sizing: border-box; }
      html, body { margin: 0; padding: 0; background: white; }
      @page { size: ${layout.width}mm ${layout.height}mm; margin: 8mm; }
      .sheet { width: ${layout.width - 16}mm; height: ${layout.height - 16 - .5}mm; margin: 0;
        display: grid; grid-template-columns: repeat(${layout.columns}, minmax(0, 1fr));
        grid-template-rows: repeat(${layout.rows}, minmax(0, 1fr)); gap: ${pagesPerSheet === 1 ? 0 : 4}mm;
        break-inside: avoid; break-after: page; }
      .sheet:last-child { break-after: auto; }
      .cell { min-width: 0; min-height: 0; display: flex; align-items: center; justify-content: center; }
      img { display: block; width: 100%; height: 100%; object-fit: contain; }
    </style></head><body></body></html>`);
    doc.close(); doc.title = title;
    let done = 0;
    for (const side of sides) {
      const sheet = doc.createElement('section'); sheet.className = 'sheet';
      sheet.dataset.side = side.number;
      doc.body.append(sheet);
      for (const number of side.pages) {
        const cell = doc.createElement('div'); cell.className = 'cell'; sheet.append(cell);
        if (number === null) continue;
        const page = await pdf.getPage(number - base + 1);
        const normal = page.getViewport({ scale: 1 });
        const scale = Math.min(PRINT_DPI / 72, Math.sqrt(8_000_000 / (normal.width * normal.height)));
        const viewport = page.getViewport({ scale });
        const canvas = document.createElement('canvas');
        canvas.width = Math.ceil(viewport.width); canvas.height = Math.ceil(viewport.height);
        try {
          await page.render({ canvasContext: canvas.getContext('2d'), viewport, intent: 'print', background: '#ffffff' }).promise;
          const image = doc.createElement('img'); image.alt = `Book page ${number - offset}`;
          image.src = canvas.toDataURL('image/png'); cell.append(image);
          if (image.decode) await image.decode();
        } finally { canvas.width = 0; canvas.height = 0; page.cleanup(); }
        onProgress?.({ done: ++done, total });
      }
    }
    onReady?.();
    preview.addEventListener('afterprint', () => { frame.remove(); if (printFrame === frame) printFrame = null; }, { once: true });
    await new Promise(resolve => window.setTimeout(resolve, 0));
    preview.focus(); preview.print();
  } catch (error) {
    frame?.remove(); if (printFrame === frame) printFrame = null;
    throw error;
  } finally {
    if (pdf) await pdf.destroy(); else if (loading) await loading.destroy();
  }
}
