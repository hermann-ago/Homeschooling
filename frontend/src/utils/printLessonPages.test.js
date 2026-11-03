/* @vitest-environment jsdom */
import { waitFor } from '@testing-library/dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const pdf = vi.hoisted(() => ({ getDocument: vi.fn() }));
vi.mock('react-pdf', () => ({ pdfjs: pdf }));
import { printLessonPages } from './printLessonPages';
import { arrangeLessonPrintSides, lessonPrintLayout, selectLessonPrintPages } from './lessonPrintOptions';

let preview, loaded, page, decode;
beforeEach(() => {
  preview = null; decode = vi.fn().mockResolvedValue(undefined);
  page = { getViewport: vi.fn(({ scale }) => ({ width: 600 * scale, height: 800 * scale })),
    render: vi.fn(() => ({ promise: Promise.resolve() })), cleanup: vi.fn() };
  loaded = { numPages: 20, getPage: vi.fn().mockResolvedValue(page), destroy: vi.fn().mockResolvedValue(undefined) };
  pdf.getDocument.mockReset().mockReturnValue({ promise: Promise.resolve(loaded), destroy: vi.fn() });
  vi.spyOn(window, 'open');
  const append = document.body.append.bind(document.body);
  vi.spyOn(document.body, 'append').mockImplementation((...nodes) => {
    append(...nodes);
    const frame = nodes.find(node => node.tagName === 'IFRAME');
    if (frame) {
      preview = frame.contentWindow;
      vi.spyOn(preview, 'print').mockImplementation(() => {});
      vi.spyOn(preview, 'focus').mockImplementation(() => {});
      Object.defineProperty(preview.HTMLImageElement.prototype, 'decode', { configurable: true, value: decode });
    }
  });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({});
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/png;base64,cGFnZQ==');
});
afterEach(() => { vi.restoreAllMocks(); document.body.replaceChildren(); });

it('prints assigned pages in an invisible frame only after every image loads, without changing the reader PDF', async () => {
  let release;
  decode.mockResolvedValueOnce(undefined).mockImplementationOnce(() => new Promise(resolve => { release = resolve; }));
  const data = new Uint8Array([1, 2, 3]);
  const printing = printLessonPages({ data, first: 4, last: 5, title: '<Lesson & book>' });
  await waitFor(() => expect(decode).toHaveBeenCalledTimes(2));
  expect(preview.print).not.toHaveBeenCalled();
  release(); await printing;
  expect(loaded.getPage.mock.calls.map(([number]) => number)).toEqual([4, 5]);
  expect(preview.print).toHaveBeenCalledTimes(1);
  expect(window.open).not.toHaveBeenCalled();
  expect(preview.document.querySelectorAll('.sheet')).toHaveLength(2);
  expect(preview.document.title).toBe('<Lesson & book>');
  expect(preview.document.querySelectorAll('script')).toHaveLength(0);
  expect(pdf.getDocument.mock.calls[0][0].data).not.toBe(data);
  expect([...data]).toEqual([1, 2, 3]);
  expect(page.render.mock.calls[0][0]).toMatchObject({ intent: 'print', viewport: { width: 1250, height: 800 * 150 / 72 } });
  expect(loaded.destroy).toHaveBeenCalled();
  preview.dispatchEvent(new preview.Event('afterprint'));
  expect(document.querySelector('iframe')).toBeNull();
});

it('selects arranged front sides and reverses sides without reversing their book pages', async () => {
  await printLessonPages({ data: new Uint8Array([1]), first: 10, last: 14, offset: 5,
    selection: '5–9', parity: 'odd', reverse: true, pagesPerSheet: 2, paper: 'Letter', orientation: 'landscape' });
  expect(loaded.getPage.mock.calls.map(([number]) => number)).toEqual([14, 10, 11]);
  const sheets = preview.document.querySelectorAll('.sheet');
  expect(sheets).toHaveLength(2);
  expect([...sheets[0].querySelectorAll('img')].map(image => image.alt)).toEqual(['Book page 9']);
  expect([...sheets[1].querySelectorAll('img')].map(image => image.alt)).toEqual(['Book page 5', 'Book page 6']);
  expect([...sheets].map(sheet => sheet.dataset.side)).toEqual(['3', '1']);
  expect(sheets[0].querySelectorAll('.cell')).toHaveLength(2);
  expect(preview.document.querySelector('style').textContent).toContain('object-fit: contain');
  expect(preview.document.querySelector('style').textContent).toContain('repeat(2, minmax(0, 1fr))');
});

it('preserves a blank final back when reversing a manual two-sided print run', async () => {
  await printLessonPages({ data: new Uint8Array([1]), first: 1, last: 5, pagesPerSheet: 2, parity: 'even', reverse: true });
  expect(loaded.getPage.mock.calls.map(([number]) => number)).toEqual([3, 4]);
  const sheets = [...preview.document.querySelectorAll('.sheet')];
  expect(sheets.map(sheet => sheet.dataset.side)).toEqual(['4', '2']);
  expect(sheets[0].querySelectorAll('.cell')).toHaveLength(2);
  expect(sheets[0].querySelectorAll('img')).toHaveLength(0);
  expect([...sheets[1].querySelectorAll('img')].map(image => image.alt)).toEqual(['Book page 3', 'Book page 4']);
  expect(preview.print).toHaveBeenCalledTimes(1);
});

it('prints an intentionally blank back without requesting a nonexistent PDF page', async () => {
  await printLessonPages({ data: new Uint8Array([1]), first: 2, last: 2, parity: 'even', pagesPerSheet: 4 });
  expect(loaded.getPage).not.toHaveBeenCalled();
  expect(preview.document.querySelectorAll('.sheet')).toHaveLength(1);
  expect(preview.document.querySelector('.sheet').dataset.side).toBe('2');
  expect(preview.document.querySelectorAll('.cell')).toHaveLength(4);
  expect(preview.print).toHaveBeenCalledTimes(1);
  expect(loaded.destroy).toHaveBeenCalledTimes(1);
});

it.each([1, 2, 4])('pairs every front with its back and keeps blank slots at %i pages per side', pagesPerSheet => {
  const options = { first: 2, last: 10, offset: 1, pagesPerSheet };
  const fronts = arrangeLessonPrintSides({ ...options, parity: 'odd' });
  const backs = arrangeLessonPrintSides({ ...options, parity: 'even' });
  expect(fronts.length).toBe(backs.length);
  const combined = fronts.flatMap((front, index) => {
    expect(backs[index].number).toBe(front.number + 1);
    expect(front.pages).toHaveLength(pagesPerSheet);
    expect(backs[index].pages).toHaveLength(pagesPerSheet);
    return [...front.pages, ...backs[index].pages];
  });
  expect(combined.filter(page => page !== null)).toEqual([2, 3, 4, 5, 6, 7, 8, 9, 10]);
  expect(arrangeLessonPrintSides({ ...options, parity: 'even', reverse: true })).toEqual([...backs].reverse());
});

it('groups a sparse selection before splitting sides and does not add a blank side to all-sides printing', () => {
  const options = { first: 10, last: 20, selection: '10, 12, 15–17', pagesPerSheet: 2 };
  expect(arrangeLessonPrintSides({ ...options, parity: 'odd' }).map(side => side.pages)).toEqual([[10, 12], [17, null]]);
  expect(arrangeLessonPrintSides({ ...options, parity: 'even' }).map(side => side.pages)).toEqual([[15, 16], [null, null]]);
  expect(arrangeLessonPrintSides({ ...options, reverse: true }).map(side => side.pages)).toEqual([[17, null], [15, 16], [10, 12]]);
  expect(() => arrangeLessonPrintSides({ ...options, parity: 'unknown' })).toThrow('Choose all sides');
});

it('prints book pages from a PDF that holds only the lesson pages', async () => {
  loaded.numPages = 3;
  await printLessonPages({ data: new Uint8Array([1]), first: 59, last: 61, base: 59 });
  expect(loaded.getPage.mock.calls.map(([number]) => number)).toEqual([1, 2, 3]);
  expect(preview.document.querySelector('img').alt).toBe('Book page 59');
});

it('does not open a print dialog for an invalid range or a failed partial render', async () => {
  await expect(printLessonPages({ data: new Uint8Array([1]), first: 19, last: 21 })).rejects.toThrow('outside this book');
  expect(loaded.getPage).not.toHaveBeenCalled();
  expect(document.querySelector('iframe')).toBeNull();
  expect(loaded.destroy).toHaveBeenCalled();
  page.render.mockImplementationOnce(() => ({ promise: Promise.resolve() })).mockImplementationOnce(() => ({ promise: Promise.reject(new Error('Page unavailable')) }));
  await expect(printLessonPages({ data: new Uint8Array([1]), first: 1, last: 2 })).rejects.toThrow('Page unavailable');
  expect(preview.print).not.toHaveBeenCalled();
  expect(document.querySelector('iframe')).toBeNull();
});

it('deduplicates ranges, validates boundaries, and uses printed book numbering rather than PDF parity', () => {
  const range = { first: 14, last: 18, offset: 5 };
  expect(selectLessonPrintPages({ ...range, selection: '9, 10–13, 11', parity: 'even' })).toEqual([15, 17]);
  expect(() => selectLessonPrintPages({ ...range, selection: '8' })).toThrow('within this lesson');
  expect(() => selectLessonPrintPages({ ...range, selection: '9,,10' })).toThrow('separated by commas');
  expect(() => selectLessonPrintPages({ ...range, selection: '11-10' })).toThrow('within this lesson');
  expect(() => selectLessonPrintPages({ ...range, selection: '10', parity: 'odd' })).toThrow('No odd');
  expect(lessonPrintLayout({ pagesPerSheet: 4, paper: 'A4' })).toMatchObject({ columns: 2, rows: 2 });
});
