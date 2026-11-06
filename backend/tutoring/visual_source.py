"""PDF-first lesson inputs, shared by preparation and private script review.

Full-book companions are optional. This module selects original pages only;
it never derives mappings, answers, or learner evidence from a filename.
"""
import hashlib
import io
import re

from pypdf import PdfReader, PdfWriter

from .guide import GuideError, validate_source_references

MAX_PAGES = 20
MAX_BYTES = 20 * 1024 * 1024
VERSION = 2


def blank_page(page):
    """Only an empty content stream with no annotations proves an empty page.

    Missing selectable text alone says nothing about pictures or scanned pages.
    """
    contents = page.get_contents()
    return not page.get('/Annots') and (contents is None or not contents.get_data().strip())


def prefer_original_pages(learner_context):
    """Don't let duplicated, lossy visual descriptions compete with attached pages.

    Retain exact reading/task obligations, evidence, concepts and book links.
    The stored companion/inventory itself is untouched and remains usable in
    explicit text-only preparation and historical sessions.
    """
    if learner_context.get('visual_source'):
        learner_context.get('subject_sources', {}).pop('page_structure', None)


def requested(skill_content):
    """PDF is the default; an explicit text setting retains text-only preparation."""
    match = re.match(r'\A---\s*\n(.*?)\n---(?:\s*\n|$)', skill_content, re.S)
    return not bool(match and re.search(r'^lesson_source:\s*text\s*$', match[1], re.M))


def prepare(ctx, topic, package, skill_content):
    if not requested(skill_content):
        return None, None
    if package.get('hide_pdf'):
        # Mixed teacher/student pages cannot go to the child-facing planner.
        # Their already checked student text remains usable.
        return None, None
    first, last = package['pdf_pages']['start'], package['pdf_pages']['end']
    if not 1 <= first <= last or last - first + 1 > MAX_PAGES:
        raise GuideError(f'Visual preparation supports at most {MAX_PAGES} assigned pages per lesson.')
    document = ctx.store.get('documents', topic['document_id'])
    if (not document or not document.get('file_path') or package.get('document_id') != document['id']
            or not document.get('sha256') or package.get('document_sha256') != document['sha256']):
        raise GuideError('The visual source does not match the assigned book version.')
    pages = [{'attachment_page': i + 1, 'document_id': document['id'], 'page': page,
              'printed_page': page - (topic.get('pdf_page_offset') or 0)}
             for i, page in enumerate(range(first, last + 1))]
    validate_source_references(ctx, topic['subject_id'], pages)
    reader = PdfReader(io.BytesIO(ctx.file_bytes(document['file_path'], document['sha256'])))
    if last > len(reader.pages):
        raise GuideError('The visual page range is outside the assigned PDF.')
    writer = PdfWriter()
    for page in range(first, last + 1):
        if blank_page(reader.pages[page - 1]):
            pages[page - first]['blank'] = True
        if not topic.get('pdf_page_offset'):
            # No recorded offset: use the number printed on the page itself, when one is visible.
            from .exercise_assignment import printed_page
            printed = printed_page(reader.pages[page - 1], page)
            if printed:
                pages[page - first]['printed_page'] = printed
        writer.add_page(reader.pages[page - 1])
    # Only selected pages and their referenced resources go to the provider.
    writer.remove_links()
    output = io.BytesIO()
    writer.write(output)
    data = output.getvalue()
    if len(data) > MAX_BYTES:
        raise GuideError('The assigned visual pages exceed the preparation size limit.')
    return data, {'version': VERSION, 'mode': 'visual_pages', 'document_id': document['id'],
                  'document_sha256': document['sha256'],
                  'boundaries': {k: topic.get(k) for k in ('start_at', 'stop_before')},
                  'attachment_sha256': hashlib.sha256(data).hexdigest(), 'pages': pages}


def _append(ctx, writer, metadata, document, pages, role, *, exercise_id=None):
    """Select exact edition/pages; one physical page per role even for many tasks."""
    if not document or not document.get('file_path') or not document.get('sha256'):
        raise GuideError('A linked lesson source PDF is missing. Restore that book before preparing.')
    existing = {(p['document_id'], p['page'], p.get('role', 'assigned_reading')) for p in metadata}
    reader = None
    for page in pages:
        if (not isinstance(page, int) or isinstance(page, bool)
                or not 1 <= page <= document['page_count']):
            raise GuideError('A linked lesson source page is outside its PDF.')
        if (document['id'], page, role) in existing:
            continue
        if len(metadata) >= MAX_PAGES * 2:
            raise GuideError('The lesson and linked sources exceed 40 pages; split the preparation scope.')
        if reader is None:
            reader = PdfReader(io.BytesIO(ctx.file_bytes(document['file_path'], document['sha256'])))
        writer.add_page(reader.pages[page - 1])
        from .exercise_assignment import printed_page
        printed = printed_page(reader.pages[page - 1], page)
        metadata.append({'attachment_page': len(metadata) + 1, 'document_id': document['id'],
                         'document_sha256': document['sha256'], 'page': page, 'role': role,
                         # The number printed on the page, so a child can find it in a paper book.
                         **({'printed_page': printed} if printed else {}),
                         **({'blank': True} if blank_page(reader.pages[page - 1]) else {}),
                         **({'exercise_id': exercise_id} if exercise_id else {})})
        existing.add((document['id'], page, role))


def _bytes(writer):
    writer.remove_links()
    output = io.BytesIO()
    writer.write(output)
    data = output.getvalue()
    if len(data) > MAX_BYTES:
        raise GuideError('The lesson source PDF exceeds the preparation size limit.')
    return data


def linked(ctx, topic, assigned_pdf, metadata, exercises):
    """Planner sees student pages; reviewer additionally sees mapped private keys.

    Uses immutable exercise versions and explicit key provenance, never guessed
    chapter/page arithmetic. Legacy keys without a document remain textual.
    """
    if assigned_pdf is None:
        return None, None, None
    import copy
    public = copy.deepcopy(metadata)
    for p in public['pages']:
        p.update(role='assigned_reading', document_sha256=metadata['document_sha256'])
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(assigned_pdf)), import_outline=False)
    keys = []
    for item in exercises:
        version = ctx.store.get('exercise_versions', item['version_id'])
        exercise = ctx.store.get('exercises', item['id'])
        book = ctx.store.get('subject_books', exercise['book_id']) if exercise else None
        if (not version or version['exercise_id'] != item['id'] or not book
                or book['subject_id'] != topic['subject_id'] or book['archived']):
            raise GuideError('A linked exercise no longer belongs to this lesson source.')
        source = version['data']
        doc = ctx.store.get('documents', book['document_id'])
        if source.get('source_sha256') != (doc or {}).get('sha256'):
            raise GuideError('A linked exercise belongs to a different PDF edition.')
        refs = [{'document_id': doc['id'], 'page': p} for p in source['pages']]
        validate_source_references(ctx, topic['subject_id'], refs)
        _append(ctx, writer, public['pages'], doc, source['pages'], 'exercise', exercise_id=item['id'])
        key = source.get('answer_source') or {}
        key_book = ctx.store.get('subject_books', key['book_id']) if key.get('book_id') else None
        key_doc = ctx.store.get('documents', key_book['document_id']) if key_book else None
        if key.get('book_id') and not key_book:
            raise GuideError('The mapped answer-key book is missing. Restore or review its source link.')
        if key_book:
            if (key_book['subject_id'] != topic['subject_id'] or key_book['archived']
                    or key_book['role'] not in ('answer_key', 'combined')
                    or key.get('sha256') != (key_doc or {}).get('sha256')):
                raise GuideError('The linked answer key no longer matches its subject or PDF edition.')
            keys.append((key_doc, key.get('pages') or [], item['id']))
    planner_pdf = _bytes(writer)
    public['attachment_sha256'] = hashlib.sha256(planner_pdf).hexdigest()
    review = copy.deepcopy(public)
    for doc, pages, exercise_id in keys:
        _append(ctx, writer, review['pages'], doc, pages, 'answer_key', exercise_id=exercise_id)
    review_pdf = _bytes(writer) if keys else planner_pdf
    review['attachment_sha256'] = hashlib.sha256(review_pdf).hexdigest()
    return planner_pdf, public, (review_pdf, review)


def freeze(tx, topic, planner_pdf, metadata, review, *, folder=None):
    """Keep exact provider inputs as ordinary durable, private preparation files."""
    if planner_pdf is None:
        return {'version': VERSION, 'mode': 'text'}
    from storage import layout
    folder = folder or layout.for_topic(tx, topic['id'], layout.LESSON_CONTENT)
    def artifact(pdf, manifest, name):
        path, digest = tx.add_blob(pdf, folder, f'{name}-{manifest["attachment_sha256"][:16]}.pdf', 'application/pdf')
        return {**manifest, 'file_path': path, 'file_sha256': digest}
    planner = artifact(planner_pdf, metadata, 'lesson-sources')
    review_pdf, review_metadata = review
    reviewer = planner if review_pdf == planner_pdf else artifact(review_pdf, review_metadata, 'private-review-sources')
    return {'version': VERSION, 'mode': 'visual_pages', 'planner': planner, 'reviewer': reviewer}


def review_pdf(ctx, row):
    bundle = (row.get('context_snapshot') or {}).get('lesson_sources') or {}
    source = bundle.get('reviewer')
    if not source:
        return None
    data = ctx.file_bytes(source['file_path'], source['file_sha256'])
    if hashlib.sha256(data).hexdigest() != source['attachment_sha256']:
        raise GuideError('The saved review PDF no longer matches the prepared lesson.')
    return data


def current(ctx, row, topic):
    """New preparation must notice edition/layout changes even if text is equal."""
    bundle = (row.get('context_snapshot') or {}).get('lesson_sources') or {}
    planner = bundle.get('planner')
    if not planner:
        return True  # historical/text-only scripts retain their compatibility policy
    if (row.get('context_snapshot') or {}).get('preparation_policy', '').startswith('original-pages-'):
        from .navigation import checked_selections, selections
        try:
            current = checked_selections(ctx.store, topic, selections(ctx, topic))
        except ValueError:
            return False
        if current != (row.get('context_snapshot') or {}).get('selected_source_pages', []):
            return False
    if planner['boundaries'] != {k: topic.get(k) for k in ('start_at', 'stop_before')}:
        return False
    from .passages import pdf_range
    first, last = pdf_range(topic)
    main = [p for p in planner['pages'] if p['role'] == 'assigned_reading']
    if [(p['document_id'], p['page']) for p in main] != [(topic['document_id'], p) for p in range(first,last+1)]:
        return False
    return all((ctx.store.get('documents',p['document_id']) or {}).get('sha256') == p['document_sha256']
               for p in bundle['reviewer']['pages'])
