"""Small edition-bound chapter maps. No page transcription or full-book AI scan."""
import io
import json
import re
import unicodedata

from pypdf import PdfReader
from pydantic import BaseModel, Field
from storage.store import sha256_text
from .books import book_name

VERSION = 'chapter-map-1'


def normalized(text):
    return re.sub(r'\W+', '', unicodedata.normalize('NFKC', text).casefold())


class Chapter(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)


class ChapterMap(BaseModel):
    chapters: list[Chapter] = Field(max_length=1000)


def identity(doc):
    return VERSION + ':' + doc['sha256']


def saved(db, doc):
    return db.get('book_navigation', identity(doc))


def validate(doc, chapters):
    chapters = ChapterMap(chapters=chapters).model_dump()['chapters']
    previous = 0
    for row in chapters:
        if not previous < row['page_start'] <= row['page_end'] <= doc['page_count']:
            raise ValueError('Chapter ranges must be ordered, non-overlapping original PDF pages.')
        previous = row['page_end']
    return chapters


def persist(tx, doc, chapters, method, toc_pages=None, expected_revision=None):
    chapters = validate(doc, chapters)
    data = {'version': VERSION, 'document_sha256': doc['sha256'], 'page_count': doc['page_count'],
            'method': method, 'toc_pages': toc_pages or [], 'chapters': chapters}
    body = json.dumps(data, ensure_ascii=False, indent=2).encode()
    path, _ = tx.add_blob(body, 'Family Library/Chapter Maps/Lesson Content', f"{doc['sha256'][:16]}-{sha256_text(data)[:8]}.json", 'application/json')
    values = {'document_sha256': doc['sha256'], 'data': data, 'file_path': path}
    old = saved(tx, doc)
    if old:
        return tx.update('book_navigation', old['id'], values, expected_revision=expected_revision)
    if expected_revision not in (None, 0):
        raise ValueError('Reload the chapter map before saving.')
    return tx.insert('book_navigation', {'id': identity(doc), **values})


def extract(ctx, doc):
    """Read PDF bookmarks or local TOC text. Never send the book to a provider."""
    old = saved(ctx.store, doc)
    if old:
        return old
    reader = PdfReader(io.BytesIO(ctx.file_bytes(doc['file_path'], doc['sha256'])))
    starts = []
    # Top-level bookmarks define chapters; nested bookmarks remain navigation
    # inside a chapter and must not fragment the teaching sequence.
    for item in reader.outline:
        if isinstance(item, list):
            continue
        try:
            page = reader.get_destination_page_number(item) + 1
            if 1 <= page <= len(reader.pages):
                starts.append((str(item.title).strip(), page))
        except (ValueError, KeyError, TypeError):
            continue
    toc_pages = []
    if not starts:
        entries = []
        for i, page in enumerate(reader.pages[:min(24, len(reader.pages))]):
            text = unicodedata.normalize('NFKC', page.extract_text() or '')
            if not re.search(r'\b(contents|sumário|sumario|índice|indice)\b|Chapter\s+Page', text, re.I):
                continue
            toc_pages.append(i + 1)
            for line in text.splitlines():
                match = re.match(r'^\s*(?:\d+[.)]?\s+)?(.{3,290}?)\s*[.·…\s]+\s*(\d{1,4})\s*$', line)
                if match and not re.search(r'copyright|isbn', match[1], re.I):
                    title = re.split(r'(?:\s*\.\s*){3,}', match[1])[-1].strip(' .')
                    title = re.sub(r'^\d+[.)]?\s+', '', title)
                    if title:
                        entries.append((title, int(match[2])))
        # A constant page offset is established from actual printed page labels.
        # No model estimates ranges from the length of the book.
        offsets = []
        for i, page in enumerate(reader.pages[:min(40, len(reader.pages))]):
            lines = (page.extract_text() or '').strip().splitlines()
            for line in [*lines[:1], *lines[-1:]]:
                match = re.match(r'^\s*(\d{1,4})(?=\s|Chapter|Capítulo|$)', line) or re.search(r'(\d{1,4})\s*$', line)
                if match:
                    n = int(match[1])
                    if 1 <= n <= len(reader.pages):
                        offsets.append(i + 1 - n)
        if offsets and entries:
            offset = max(set(offsets), key=offsets.count)
            if offsets.count(offset) >= 2:
                starts = [(title, p + offset) for title, p in entries if 1 <= p + offset <= len(reader.pages)]
    if not starts and len(reader.pages) == 1:
        lines = (reader.pages[0].extract_text() or '').strip().splitlines()
        if lines:
            starts = [(lines[0].strip()[:300], 1)]
    # Repeated entries/page numbers are aliases, not separate zero-length lessons.
    distinct = {}
    for title, page in starts:
        if title and page not in distinct:
            distinct[page] = title
    starts = sorted(distinct.items())
    chapters = [{'title': title, 'page_start': page,
                 'page_end': starts[i+1][0]-1 if i+1 < len(starts) else len(reader.pages)}
                for i, (page, title) in enumerate(starts)]
    with ctx.store.transaction(kind='books.chapter_map') as tx:
        return persist(tx, doc, chapters, 'pdf_bookmarks' if not toc_pages else 'local_contents', toc_pages)


def publish_topics(service, book, doc, navigation):
    chapters = navigation['data']['chapters']
    if not chapters:
        return
    db = service.db
    with db.transaction(kind='books.chapter_topics') as tx:
        from .library_materials import book_for
        library = book_for(tx, book['subject_id'])
        prior = [t for t in tx.find('topics', subject_id=book['subject_id'], document_id=doc['id']) if not t.get('archived')]
        if prior and not library:
            return
        if library and not tx.find('tutor_sessions', subject_id=book['subject_id']) and not any(a['topic_id'] in {t['id'] for t in prior} for a in tx.all('attempts')):
            for topic in prior:
                if not (topic.get('source_key') or '').startswith('ch-'):
                    tx.update('topics', topic['id'], {'archived': True, 'is_core': False})
        for order, chapter in enumerate(chapters):
            key = 'ch-' + sha256_text([doc['sha256'], chapter])[:22]
            existing = next((t for t in tx.find('topics', subject_id=book['subject_id'], document_id=doc['id'])
                             if t.get('source_key') == key), None)
            if existing:
                continue
            # Existing curriculum divisions and saved progress remain authoritative.
            tx.insert('topics', {'subject_id': book['subject_id'], 'document_id': doc['id'], 'title': chapter['title'],
                'page_start': chapter['page_start'], 'page_end': chapter['page_end'], 'pdf_page_offset': 0,
                'chapter_order': order, 'source_key': key, 'is_core': True, 'completed': False})


def sources(db, subject_id):
    from .collections import view
    return view(db, subject_id)['books']


def selections(ctx, topic):
    row = ctx.store.get('lesson_page_selections', str(topic['id']))
    if row:
        return row['sources']
    return []


def migrate_page_links(ctx):
    """One-time local migration: keep page pointers, discard old content contracts."""
    db = ctx.store
    by_topic = {}
    for exercise in db.all('exercises'):
        version = db.get('exercise_versions', exercise.get('active_version')) if exercise.get('active_version') else None
        book = db.get('subject_books', exercise['book_id'])
        if not version or not book or book['archived'] or exercise.get('archived'):
            continue
        data = version['data']
        for requirement in data.get('requirements') or []:
            topic = db.get('topics', requirement['topic_id'])
            if not topic or topic['subject_id'] != book['subject_id'] or db.get('lesson_page_selections', str(topic['id'])):
                continue
            rows = by_topic.setdefault(topic['id'], {})
            for page in data['pages']:
                rows[(book['document_id'], page, book['role'])] = True
            key = data.get('answer_source') or {}
            kb = db.get('subject_books', key['book_id']) if key.get('book_id') else None
            if kb:
                for page in key.get('pages') or []:
                    rows[(kb['document_id'], page, 'answer_key')] = True
    if by_topic:
        with db.transaction(kind='lesson.migrate_page_links') as tx:
            for topic_id, refs in by_topic.items():
                rows = [{'document_id': d, 'page_start': p, 'page_end': p, 'role': role,
                         'document_sha256': db.get('documents', d)['sha256']} for d,p,role in refs]
                if len(rows) <= 40:
                    tx.insert('lesson_page_selections', {'id': str(topic_id), 'topic_id': topic_id, 'sources': rows})


def checked_selections(db, topic, rows):
    available = {b['document_id']: b for b in sources(db, topic['subject_id'])}
    result = []
    total = 0
    for row in rows:
        b = available.get(row['document_id'])
        if not b or not 1 <= row['page_start'] <= row['page_end'] <= b['page_count']:
            raise ValueError('Choose original PDF pages from this subject’s books.')
        if row.get('document_sha256') and row['document_sha256'] != b['sha256']:
            raise ValueError('The selected pages belong to an older edition. Select the current source pages again.')
        total += row['page_end'] - row['page_start'] + 1
        if total > 40:
            raise ValueError('Select at most 40 linked pages per lesson.')
        result.append({**row, 'role': b['role'], 'document_sha256': b['sha256']})
    return result


def attach(ctx, topic, pdf, metadata):
    import copy
    from .visual_source import _append, _bytes
    if pdf is None:
        return pdf, metadata, None
    writer = __import__('pypdf').PdfWriter()
    writer.append(PdfReader(io.BytesIO(pdf)), import_outline=False)
    public = copy.deepcopy(metadata)
    for p in public['pages']:
        p.update(role='assigned_reading', document_sha256=metadata['document_sha256'])
    selected = checked_selections(ctx.store, topic, selections(ctx, topic))
    for s in selected:
        if s['role'] == 'answer_key':
            continue
        doc = ctx.store.get('documents', s['document_id'])
        from .guide import validate_source_references
        validate_source_references(ctx, topic['subject_id'], [{'document_id': doc['id'], 'page': p}
            for p in range(s['page_start'], s['page_end']+1)])
        _append(ctx, writer, public['pages'], doc, range(s['page_start'], s['page_end']+1), s['role'])
    planner = _bytes(writer)
    import hashlib
    public['attachment_sha256'] = hashlib.sha256(planner).hexdigest()
    for page in public['pages']:
        doc = ctx.store.get('documents', page['document_id'])
        page['book_name'] = book_name(doc['original_filename'])
    review = copy.deepcopy(public)
    for s in selected:
        if s['role'] == 'answer_key':
            doc = ctx.store.get('documents', s['document_id'])
            _append(ctx, writer, review['pages'], doc, range(s['page_start'], s['page_end']+1), 'answer_key')
    private = _bytes(writer)
    review['attachment_sha256'] = hashlib.sha256(private).hexdigest()
    return planner, public, (private, review)
