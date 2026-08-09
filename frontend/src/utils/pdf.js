import { getDocument } from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

export async function inspectPdf(file) {
  const task = getDocument({ data: new Uint8Array(await file.arrayBuffer()) });
  const pdf = await task.promise;
  const pages = Math.min(pdf.numPages, 15);
  const text = [];
  for (let pageNumber = 1; pageNumber <= pages; pageNumber += 1) {
    const page = await pdf.getPage(pageNumber);
    const content = await page.getTextContent();
    text.push(content.items.map((item) => item.str || '').join(' '));
  }
  return { pageCount: pdf.numPages, tocText: text.join('\n\n').trim(), workerUrl };
}

export async function extractPdfPages(url, start, end, offset = 0) {
  const pdf = await getDocument(url).promise;
  const physicalStart = Math.max(1, start + offset);
  const physicalEnd = Math.min(pdf.numPages, end + offset);
  const text = [];
  for (let pageNumber = physicalStart; pageNumber <= physicalEnd; pageNumber += 1) {
    const page = await pdf.getPage(pageNumber);
    const content = await page.getTextContent();
    text.push(content.items.map((item) => item.str || '').join(' '));
  }
  return text.join('\n\n').trim();
}
