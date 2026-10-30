/** Select using the book's printed numbering; render using physical PDF pages. */
export function selectLessonPrintPages({ first, last, offset = 0, selection, parity = 'all', reverse = false }) {
  if (!Number.isInteger(first) || !Number.isInteger(last) || !Number.isInteger(offset) || first < 1 || last < first) {
    throw new Error('The lesson page range is invalid.');
  }
  if (!['all', 'odd', 'even'].includes(parity)) throw new Error('Choose all, odd or even book pages.');
  const lower = first - offset, upper = last - offset;
  const input = selection === undefined ? `${lower}-${upper}` : selection.trim();
  if (!input || input.length > 1000) throw new Error('Enter book pages, for example 12, 14–16.');
  const numbers = new Set();
  for (const part of input.replace(/[–—]/g, '-').split(',')) {
    const match = part.trim().match(/^(\d+)(?:\s*-\s*(\d+))?$/);
    if (!match) throw new Error('Use page numbers or ranges separated by commas, for example 12, 14–16.');
    const start = Number(match[1]), end = Number(match[2] || match[1]);
    if (start < lower || end > upper || end < start) throw new Error(`Choose book pages within this lesson: ${lower}–${upper}.`);
    for (let page = start; page <= end; page += 1) {
      if (parity === 'all' || (page % 2 === 0 ? parity === 'even' : parity === 'odd')) numbers.add(page + offset);
    }
  }
  const pages = [...numbers].sort((a, b) => reverse ? b - a : a - b);
  if (!pages.length) throw new Error(`No ${parity} book pages are included in this selection.`);
  return pages;
}

export function lessonPrintLayout({ pagesPerSheet = 1, paper = 'A4', orientation = 'portrait' } = {}) {
  if (![1, 2, 4].includes(pagesPerSheet) || !['A4', 'Letter'].includes(paper) || !['portrait', 'landscape'].includes(orientation)) {
    throw new Error('Choose a supported paper size, orientation and pages per sheet.');
  }
  const [short, long] = paper === 'A4' ? [210, 297] : [215.9, 279.4];
  const width = orientation === 'portrait' ? short : long, height = orientation === 'portrait' ? long : short;
  const columns = pagesPerSheet === 4 || pagesPerSheet === 2 && orientation === 'landscape' ? 2 : 1;
  return { pagesPerSheet, width, height, columns, rows: pagesPerSheet / columns };
}
