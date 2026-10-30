export const PRINTED = 'Printed book';
const bookName = (topic) => topic.pdf_filename || PRINTED;
const bookKey = (topic) => topic.document_id != null ? `document:${topic.document_id}` : `name:${bookName(topic)}`;
export const bookTitle = (name) => name.replace(/\.pdf$/i, '');

export function curriculumBooks(topics) {
  const grouped = new Map();
  for (const topic of topics) {
    const key = bookKey(topic);
    const book = grouped.get(key) || {key, name:bookName(topic), core:false,
      offset:topic.pdf_page_offset || 0, document:topic.document_id, chapters:[]};
    book.core ||= Boolean(topic.is_core);
    book.chapters.push(topic);
    grouped.set(key,book);
  }
  const books=[...grouped.values()];
  for (const book of books) {
    book.chapters.sort((a,b)=>(a.chapter_order ?? 0)-(b.chapter_order ?? 0) || a.page_start-b.page_start || a.id-b.id);
    book.count=book.chapters.length;
    book.title=bookTitle(book.name);
    if (books.filter(b=>b.name===book.name).length>1) {
      const lessons=book.chapters.map(t=>/^Lesson\s+(\d+)\b/i.exec(t.title)?.[1]).filter(Boolean).map(Number);
      book.detail=lessons.length ? `Lessons ${Math.min(...lessons)}–${Math.max(...lessons)}` : `Separate import · book ${book.document}`;
    }
    book.label=book.detail ? `${book.title} · ${book.detail}` : book.title;
  }
  return books.sort((a,b)=>Number(b.core)-Number(a.core));
}
