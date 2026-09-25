/**
 * Align passage sentences with PDF.js text so the original page can be
 * followed and highlighted. Matching uses the actual page text; when a
 * sentence cannot be found, nothing is highlighted rather than guessing.
 */
const QUOTES = { '‘': "'", '’': "'", '“': '"', '”': '"', '—': '-', '–': '-' };

export function normalise(text) {
  return (text || '')
    .normalize('NFKC')
    .replace(/­/g, '')
    .replace(/[‘’“”—–]/g, (c) => QUOTES[c])
    .replace(/-\s+(?=[a-z])/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}

function probe(sentence) {
  const text = normalise(sentence);
  return text.length <= 40 ? text : text.slice(0, 40);
}

/** Page number (PDF) for each sentence, following reading order. */
export function locateSentences(pageTexts, sentences) {
  const pages = pageTexts.map(({ page, text }) => ({ page, text: normalise(text) }));
  const result = [];
  let pageIndex = 0;
  let offset = 0;
  sentences.forEach((sentence) => {
    const needle = probe(sentence.text);
    let found = null;
    for (let i = pageIndex; i < pages.length && found === null; i += 1) {
      const position = pages[i].text.indexOf(needle, i === pageIndex ? offset : 0);
      if (position >= 0) found = { index: i, position };
    }
    if (found) {
      pageIndex = found.index;
      offset = found.position + needle.length;
      result.push(pages[found.index].page);
    } else {
      result.push(pages[pageIndex]?.page ?? null);
    }
  });
  return result;
}

/** Indices of text items on this page that belong to the sentence. */
export function highlightItemIndices(items, sentence) {
  if (!sentence || !items?.length) return new Set();
  const ranges = [];
  let joined = '';
  items.forEach((item, index) => {
    const text = normalise(item.str);
    if (!text) return;
    if (joined) joined += ' ';
    ranges.push({ index, start: joined.length, end: joined.length + text.length });
    joined += text;
  });
  const full = normalise(sentence);
  let start = joined.indexOf(probe(sentence));
  let end;
  if (start >= 0) {
    end = start + full.length;
  } else {
    // The sentence began on the previous page: its end must open this page.
    let overlap = 0;
    for (let k = Math.min(full.length, joined.length); k >= 12; k -= 1) {
      if (full.endsWith(joined.slice(0, k))) {
        overlap = k;
        break;
      }
    }
    if (!overlap) return new Set();
    start = 0;
    end = overlap;
  }
  return new Set(ranges.filter((r) => r.end > start && r.start < end).map((r) => r.index));
}

/** Which sentence is being spoken at `time` seconds into a timed track part. */
export function sentenceAt(part, time) {
  const starts = part?.sentenceStarts || [];
  let index = -1;
  for (let i = 0; i < starts.length; i += 1) {
    if (starts[i] <= time + 0.05) index = i;
    else break;
  }
  return index < 0 ? null : part.startSentence + index;
}

export function partForSentence(parts, sentenceIndex) {
  return parts.findIndex((p) => sentenceIndex >= p.startSentence && sentenceIndex < p.startSentence + p.sentenceStarts.length);
}
