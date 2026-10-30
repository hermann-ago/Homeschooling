/* @vitest-environment jsdom */
import { waitFor } from '@testing-library/dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const pdf = vi.hoisted(() => ({ getDocument: vi.fn() }));
vi.mock('react-pdf', () => ({ pdfjs: pdf }));
import { printLessonPages } from './printLessonPages';
import { lessonPrintLayout, selectLessonPrintPages } from './lessonPrintOptions';

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

it('applies book-number parity and reverse order, then arranges two pages per sheet including a partial last sheet', async () => {
  await printLessonPages({ data: new Uint8Array([1]), first: 10, last: 14, offset: 5,
    selection: '5–9', parity: 'odd', reverse: true, pagesPerSheet: 2, paper: 'Letter', orientation: 'landscape' });
  expect(loaded.getPage.mock.calls.map(([number]) => number)).toEqual([14, 12, 10]);
  const sheets = preview.document.querySelectorAll('.sheet');
  expect(sheets).toHaveLength(2);
  expect([...sheets[0].querySelectorAll('img')].map(image => image.alt)).toEqual(['Book page 9', 'Book page 7']);
  expect(sheets[1].querySelectorAll('img')).toHaveLength(1);
  expect(preview.document.querySelector('style').textContent).toContain('object-fit: contain');
  expect(preview.document.querySelector('style').textContent).toContain('repeat(2, minmax(0, 1fr))');
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
