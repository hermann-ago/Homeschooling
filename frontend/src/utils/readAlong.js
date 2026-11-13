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

/**
 * Letters and digits only. PDF text layers split words ("T he"), drop capitals,
 * hyphenate at line ends and mix in quotes and spaces; a transcription of the
 * same page does not. Comparing only letters and digits survives all of that.
 */
export function compact(text) {
  return normalise(text).replace(/[^\p{L}\p{N}]+/gu, '');
}

const PROBE = 32;
const MIN_PROBE = 6;

function probe(text) {
  const letters = compact(text);
  return letters.slice(0, PROBE);
}

/** Page (PDF) where text is found, searching forward from fromIndex; null when absent. */
export function locateText(pageTexts, text, fromIndex = 0) {
  const needle = probe(text);
  if (needle.length < MIN_PROBE) return null;
  for (let i = Math.max(0, fromIndex); i < pageTexts.length; i += 1) {
    if (compact(pageTexts[i].text).includes(needle)) return { index: i, page: pageTexts[i].page };
  }
  return null;
}

/**
 * True when the page's own text layer carries most of the passage, so the
 * highlighted page can stand in for the text in the tutor panel. A scan
 * without a text layer, or one that differs from the transcription, keeps it.
 */
export function passageOnPages(pageTexts, sentences, share = 0.6) {
  const text = (pageTexts || []).map((page) => compact(page.text)).join('');
  const probes = (sentences || []).map((sentence) => probe(sentence.text)).filter((needle) => needle.length >= MIN_PROBE);
  if (!text || !probes.length) return false;
  return probes.filter((needle) => text.includes(needle)).length >= probes.length * share;
}

/** Page number (PDF) for each sentence, following reading order. */
export function locateSentences(pageTexts, sentences) {
  const pages = pageTexts.map(({ page, text }) => ({ page, text: compact(text) }));
  const result = [];
  let pageIndex = 0;
  let offset = 0;
  sentences.forEach((sentence) => {
    const needle = probe(sentence.text);
    let found = null;
    for (let i = pageIndex; needle.length >= MIN_PROBE && i < pages.length && found === null; i += 1) {
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
export function highlightItemIndices(items, sentence, after = null) {
  if (!sentence || !items?.length) return new Set();
  const ranges = [];
  let joined = '';
  items.forEach((item, index) => {
    const text = compact(item.str);
    if (!text) return;
    ranges.push({ index, start: joined.length, end: joined.length + text.length });
    joined += text;
  });
  const full = compact(sentence);
  const needle = full.slice(0, PROBE);
  if (needle.length < MIN_PROBE) return new Set();
  // A book repeats phrases: the sentence being read comes after the one read just before it.
  const previous = after ? compact(after).slice(0, PROBE) : '';
  const from = previous.length >= MIN_PROBE ? joined.indexOf(previous) : -1;
  let start = from >= 0 ? joined.indexOf(needle, from + 1) : -1;
  if (start < 0) start = joined.indexOf(needle);
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
  if (part?.timing === 'passage') return part.startSentence;
  const starts = part?.sentenceStarts || [];
  let index = -1;
  for (let i = 0; i < starts.length; i += 1) {
    if (starts[i] <= time + 0.05) index = i;
    else break;
  }
  return index < 0 ? null : part.startSentence + index;
}

export function partForSentence(parts, sentenceIndex) {
  return parts.findIndex((p) => sentenceIndex >= p.startSentence && sentenceIndex < p.startSentence +
    (p.timing === 'passage' || p.fallback ? p.sentenceCount : (p.sentenceStarts?.length || 0)));
}

/**
 * Scroll offsets that bring the highlighted box into a zoomed page's view,
 * or null when it already shows. A sentence lands a third of the way down and
 * centred across; one larger than the view starts at its top-left corner.
 */
export function followScroll(view, box, scroll, margin = 32) {
  let { top, left } = scroll;
  if (box.top < view.top + margin || box.bottom > view.bottom - margin) {
    top += box.top - view.top - Math.max(margin, (view.bottom - view.top - (box.bottom - box.top)) / 3);
  }
  if (box.left < view.left + margin || box.right > view.right - margin) {
    left += box.left - view.left - Math.max(margin, (view.right - view.left - (box.right - box.left)) / 2);
  }
  top = Math.max(0, Math.round(top));
  left = Math.max(0, Math.round(left));
  return top === scroll.top && left === scroll.left ? null : { top, left };
}

/** The reading sentence a tapped piece of page text belongs to: the first candidate
 *  ({ key, text }) whose highlight on this page includes that text item, or null. */
export function sentenceForItem(items, itemIndex, candidates) {
  let previous = null;
  for (const candidate of candidates || []) {
    if (highlightItemIndices(items, candidate.text, previous).has(itemIndex)) return candidate.key;
    previous = candidate.text;
  }
  return null;
}

const READ_FROM = 'readalong:read-from';

/** Ask the reading in progress to read again from one of its sentences (a tap on the book page). */
export function requestReadFrom(index) {
  window.dispatchEvent(new CustomEvent(READ_FROM, { detail: { index } }));
}

export function onReadFrom(handler) {
  const listener = (event) => handler(event.detail.index);
  window.addEventListener(READ_FROM, listener);
  return () => window.removeEventListener(READ_FROM, listener);
}
