"""Find a lesson's answer-key pages from PDF text layers. Local, no AI.

A key is either a section of a book (an "ANSWER KEY" / "Respostas" /
"Gabarito" heading, usually at the end of a test booklet or workbook) or a
separate PDF the family linked with the answer_key role. Inside it, answers
are grouped under labels such as "Chapter 24 Test" or "Lição 3". The lesson's
own exercise pages (or its title) carry the same label, which selects the key
pages. Nothing is extracted or stored beyond page numbers: the pages stay
private teacher material for the writer, the reviewer and grading.
"""
import functools
import io
import re

KEY_HEADING = re.compile(
    r'^\s*(answer\s+key|answers|answer\s+sheet|teacher.?s\s+key|key\s+to\s+exercises|'
    r'gabarito|respostas|chave\s+de\s+respostas)\s*$', re.I | re.M)
LABEL = re.compile(r'\b(chapter|lesson|unit|cap[ií]tulo|li[cç][aã]o|unidade|aula)\s+(\d{1,3})\b', re.I)
CANONICAL = {'capítulo': 'chapter', 'capitulo': 'chapter', 'lição': 'lesson', 'licao': 'lesson',
             'lição': 'lesson', 'licão': 'lesson', 'liçao': 'lesson', 'aula': 'lesson', 'unidade': 'unit'}
MAX_KEY_PAGES = 6
# Characters allowed before a label for it to count as opening a page (page numbers, headers).
OPENING = 40


def _label(word, number):
    word = word.casefold()
    return CANONICAL.get(word, word), int(number)


def labels(text):
    return [_label(*m.groups()) for m in LABEL.finditer(text or '')]


@functools.lru_cache(maxsize=16)
def _texts(data):
    from pypdf import PdfReader
    return tuple((page.extract_text() or '') for page in PdfReader(io.BytesIO(data)).pages)


def page_texts(ctx, document):
    return _texts(ctx.file_bytes(document['file_path'], document['sha256']))


def key_start(texts, whole_document=False):
    """0-based index where the key begins, or None."""
    if whole_document:
        return 0
    return next((i for i, text in enumerate(texts) if KEY_HEADING.search(text)), None)


def key_pages(texts, start, label):
    """1-based pages of `label`'s answers: from its page up to the page where
    the next label begins (answers often continue onto the next page)."""
    found = []
    for i in range(start, len(texts)):
        marks = labels(texts[i])
        if label in marks:
            found.append(i)
            after = marks[marks.index(label) + 1:]
            j = i
            while not after and j + 1 < len(texts) and len(found) < MAX_KEY_PAGES:
                j += 1
                first = LABEL.search(texts[j])
                # A page opening with the next label (after at most a page number) holds none of ours.
                if first and first.start() <= OPENING:
                    break
                found.append(j)
                after = labels(texts[j])
            break
    return [i + 1 for i in found]


def lesson_labels(topic, exercise_texts):
    """Labels the lesson is about: its title first, then its exercise pages."""
    ordered = labels(topic.get('title'))
    for text in exercise_texts:
        ordered += labels(text)
    return list(dict.fromkeys(ordered))


def for_lesson(ctx, topic, selected):
    """Answer-key page ranges for a lesson, as page-selection rows with role
    answer_key. `selected` are the lesson's checked page selections."""
    from .navigation import sources
    books = {b['document_id']: b for b in sources(ctx.store, topic['subject_id'])}
    exercises = [s for s in selected if s['role'] in ('test', 'workbook', 'combined')]
    main = ctx.store.get('documents', topic['document_id']) if topic.get('document_id') else None
    candidates = []  # (document, whole_document, exercise page texts)
    for s in exercises:
        document = ctx.store.get('documents', s['document_id'])
        texts = page_texts(ctx, document)
        candidates.append((document, False, [texts[p - 1] for p in range(s['page_start'], s['page_end'] + 1)]))
    if main and topic.get('page_start'):
        texts = page_texts(ctx, main)
        offset = topic.get('pdf_page_offset') or 0
        pages = range(topic['page_start'] + offset, (topic.get('page_end') or topic['page_start']) + offset + 1)
        candidates.append((main, False, [texts[p - 1] for p in pages if 0 < p <= len(texts)]))
    for book in books.values():
        if book['role'] == 'answer_key':
            linked = [ctx.store.get('documents', d) for d in {c[0]['id'] for c in candidates}]
            candidates += [(ctx.store.get('documents', book['document_id']), True, c[2]) for c in candidates
                           if c[0]['id'] in {d['id'] for d in linked if d}]
    rows, seen = [], set()
    for document, whole, exercise_texts in candidates:
        texts = page_texts(ctx, document)
        start = key_start(texts, whole)
        if start is None:
            continue
        for label in lesson_labels(topic, exercise_texts):
            pages = [p for p in key_pages(texts, start, label) if (document['id'], p) not in seen]
            if pages:
                seen.update((document['id'], p) for p in pages)
                rows.append({'document_id': document['id'], 'page_start': min(pages), 'page_end': max(pages),
                             'role': 'answer_key', 'document_sha256': document['sha256'], 'detected': True})
                break
    return rows
