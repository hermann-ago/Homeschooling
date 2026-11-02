"""Find a lesson's answer-key pages from PDF text layers. Local, no AI.

Two kinds of key are recognised:

- A labelled key section: a page headed "Answer Key" / "Respostas" /
  "Gabarito" (often at the end of a test booklet), with answers grouped under
  labels such as "Chapter 24 Test" or "Lição 3". The lesson's title or exercise
  pages carry the same label.
- A filled-in copy: a separate key PDF (role answer_key) whose pages reproduce
  the student pages with the answers written in. Each lesson page is matched to
  the key page that repeats its printed text.

Reading a large PDF's text can take minutes, so each book gets a small
fingerprint (headings, labels and phrase hashes per page), computed once when
the book is set up and cached by checksum. Only page numbers leave this module:
the key pages stay private teacher material for the writer, review and grading.
"""
import io
import json
import re
import zlib

KEY_HEADING = re.compile(
    r'^\s*(answer\s+key|answers|answer\s+sheet|teacher.?s\s+key|key\s+to\s+exercises|'
    r'gabarito|respostas|chave\s+de\s+respostas)\s*$', re.I | re.M)
LABEL = re.compile(r'\b(chapter|lesson|unit|cap[ií]tulo|li[cç][aã]o|unidade|aula)\s+(\d{1,3})\b', re.I)
CANONICAL = {'capítulo': 'chapter', 'capitulo': 'chapter', 'lição': 'lesson', 'licao': 'lesson',
             'licão': 'lesson', 'liçao': 'lesson', 'aula': 'lesson', 'unidade': 'unit'}
MAX_KEY_PAGES = 6
# Words allowed before a label for it to head a page (a page number, a running header).
OPENING = 4
# A key page repeats a student page when it contains this share of its phrases.
SAME_PAGE = 0.5
MIN_PHRASES = 20
VERSION = 1


def _label(word, number):
    word = word.casefold()
    return CANONICAL.get(word, word), int(number)


def labels(text):
    return [_label(*m.groups()) for m in LABEL.finditer(text or '')]


def phrases(text):
    words = re.findall(r'[^\W_]+', (text or '').casefold())
    return sorted({zlib.crc32(' '.join(words[i:i + 4]).encode()) for i in range(len(words) - 3)})


def fingerprint_of(texts):
    return {'version': VERSION,
            'heading': [bool(KEY_HEADING.search(t)) for t in texts],
            'labels': [[list(l) for l in labels(t)] for t in texts],
            'opens': [bool((m := LABEL.search(t)) and len(re.findall(r'\w+', t[:m.start()])) <= OPENING) for t in texts],
            'phrases': [phrases(t) for t in texts]}


def _read(data):
    try:  # PyMuPDF is several times faster on heavy, illustrated books.
        import pymupdf
        with pymupdf.open(stream=data, filetype='pdf') as pdf:
            return [page.get_text() for page in pdf]
    except ImportError:
        from pypdf import PdfReader
        from .navigation import page_text
        return [page_text(page) for page in PdfReader(io.BytesIO(data)).pages]


def fingerprint(ctx, document):
    path = ctx.config.cache_dir / 'answer-keys' / f"{document['sha256']}.json"
    if path.exists():
        cached = json.loads(path.read_text(encoding='utf-8'))
        if cached.get('version') == VERSION:
            return cached
    data = fingerprint_of(_read(ctx.file_bytes(document['file_path'], document['sha256'])))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding='utf-8')
    return data


def key_start(prints, whole_document=False):
    """0-based index where the key begins, or None."""
    if whole_document:
        return 0
    return next((i for i, heading in enumerate(prints['heading']) if heading), None)


def key_pages(prints, start, label, opening_only=False):
    """1-based pages of `label`'s answers: from its page up to the page where
    the next label begins (answers often continue onto the next page)."""
    marks = [[tuple(l) for l in page] for page in prints['labels']]
    for i in range(start, len(marks)):
        # In a whole key PDF, only a label that heads its page marks a section.
        if label in marks[i] and (not opening_only or (prints['opens'][i] and marks[i][0] == label)):
            found, after, j = [i], marks[i][marks[i].index(label) + 1:], i
            while not after and j + 1 < len(marks) and len(found) < MAX_KEY_PAGES:
                j += 1
                if marks[j] and prints['opens'][j]:
                    break  # A page opening with the next label holds none of ours.
                found.append(j)
                after = marks[j]
            return [p + 1 for p in found]
    return []


def lesson_labels(topic, exercise_marks):
    """Labels the lesson is about: its title first, then its exercise pages."""
    ordered = labels(topic.get('title'))
    for page in exercise_marks:
        ordered += [tuple(l) for l in page]
    return list(dict.fromkeys(ordered))


def matching_pages(lesson, key):
    """1-based key pages that reproduce the lesson's pages (filled-in copies)."""
    found = []
    for wanted in lesson:
        wanted = set(wanted)
        if len(wanted) < MIN_PHRASES:
            continue
        share, page = max(((len(wanted & set(have)) / len(wanted), i + 1) for i, have in enumerate(key)), default=(0, 0))
        if share >= SAME_PAGE and page not in found:
            found.append(page)
    return sorted(found)[:MAX_KEY_PAGES]


def ranges(pages):
    rows = []
    for page in pages:
        if rows and page == rows[-1][1] + 1:
            rows[-1][1] = page
        else:
            rows.append([page, page])
    return rows


def for_lesson(ctx, topic, selected):
    """Answer-key page ranges for a lesson, as page-selection rows with role
    answer_key. `selected` are the lesson's checked page selections."""
    from .navigation import sources
    books = sources(ctx.store, topic['subject_id'])
    lesson = []  # (document, its pages for this lesson)
    for s in selected:
        if s['role'] in ('test', 'workbook', 'combined'):
            lesson.append((ctx.store.get('documents', s['document_id']), range(s['page_start'], s['page_end'] + 1)))
    main = ctx.store.get('documents', topic['document_id']) if topic.get('document_id') else None
    if main and topic.get('page_start'):
        offset = topic.get('pdf_page_offset') or 0
        lesson.append((main, range(topic['page_start'] + offset, (topic.get('page_end') or topic['page_start']) + offset + 1)))
    lesson = [(d, pages) for d, pages in lesson if d]
    keys = {b['document_id'] for b in books if b['role'] == 'answer_key'}
    rows = []

    def add(document, pages):
        for first, last in ranges(pages):
            rows.append({'document_id': document['id'], 'page_start': first, 'page_end': last,
                         'role': 'answer_key', 'document_sha256': document['sha256'], 'detected': True})

    # A labelled key section in the lesson's own books.
    for document, pages in lesson:
        prints = fingerprint(ctx, document)
        start = key_start(prints)
        if start is None:
            continue
        marks = [prints['labels'][p - 1] for p in pages if 0 < p <= len(prints['labels'])]
        for label in lesson_labels(topic, marks):
            found = key_pages(prints, start, label)
            if found:
                add(document, found)
                return rows
    # A separate key PDF: pages that repeat the lesson's pages, else its labels.
    # (Matching comes first: a "see Lesson 11" mention is not Lesson 11's key.)
    lesson_pages = [(fingerprint(ctx, d), pages) for d, pages in lesson]
    wanted = [prints['phrases'][p - 1] for prints, pages in lesson_pages for p in pages if 0 < p <= len(prints['phrases'])]
    marks = [prints['labels'][p - 1] for prints, pages in lesson_pages for p in pages if 0 < p <= len(prints['labels'])]
    for key_id in sorted(keys):
        document = ctx.store.get('documents', key_id)
        prints = fingerprint(ctx, document)
        found = matching_pages(wanted, prints['phrases'])
        for label in [] if found else lesson_labels(topic, marks):
            found = key_pages(prints, 0, label, opening_only=True)
            if found:
                break
        if found:
            add(document, found)
    return rows
