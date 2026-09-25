import { getDocument } from 'pdfjs-dist';

export async function extractPdfPages(data, start, end, offset = 0) {
  const pdf = await getDocument({ data: new Uint8Array(data) }).promise;
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
