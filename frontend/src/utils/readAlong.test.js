import { describe, expect, it } from 'vitest';
import { highlightItemIndices, locateSentences, partForSentence, sentenceAt } from './readAlong';

describe('read-along alignment', () => {
  const pages = [
    { page: 208, text: 'Genghis Khan, Emperor of All Men While Christian and Islamic armies were fighting. The Mongols came from the north.' },
    { page: 209, text: 'They lived in felt tents which they took down each morning. He was born around 1167.' },
  ];
  const sentences = [
    { text: 'While Christian and Islamic armies were fighting.' },
    { text: 'The Mongols came from the north.' },
    { text: 'They lived in felt tents which they took down each morning.' },
    { text: 'Missing sentence that is not on any page at all, really.' },
    { text: 'He was born around 1167.' },
  ];

  it('maps sentences to pages in reading order', () => {
    expect(locateSentences(pages, sentences)).toEqual([208, 208, 209, 209, 209]);
  });

  it('highlights only the items of the current sentence, tolerating curly quotes', () => {
    const items = [{ str: 'The Mongols' }, { str: 'came from the north.' }, { str: '“They said,”' }, { str: 'went home.' }];
    expect([...highlightItemIndices(items, 'The Mongols came from the north.')]).toEqual([0, 1]);
    expect([...highlightItemIndices(items, '"They said," went home.')]).toEqual([2, 3]);
    expect(highlightItemIndices(items, 'Not on this page at all, no match here.').size).toBe(0);
  });

  it('highlights the continuation of a sentence that started on the previous page', () => {
    const items = [{ str: 'the tribes together.' }, { str: 'Next one.' }];
    const sentence = 'Genghis Khan wanted to bring every one of the Mongol clans and the tribes together.';
    expect([...highlightItemIndices(items, sentence)]).toEqual([0]);
  });

  it('uses provider timings exactly', () => {
    const parts = [{ startSentence: 0, sentenceStarts: [0.01, 3.2, 10.5] }, { startSentence: 3, sentenceStarts: [0.01, 4.7] }];
    expect(sentenceAt(parts[0], 0)).toBe(0);
    expect(sentenceAt(parts[0], 5)).toBe(1);
    expect(sentenceAt(parts[1], 4.8)).toBe(4);
    expect(partForSentence(parts, 3)).toBe(1);
    expect(partForSentence(parts, 9)).toBe(-1);
  });
});
