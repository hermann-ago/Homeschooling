"""Edition-scoped book preparation, independent of any child's lifetime or work.

Only learner-neutral inputs enter shared scripts. The normal lesson engine binds
those scripts to each child's fresh session. Live answers, hints, assessment and
learning memory never enter this store. All generated versions remain available.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import uuid
from contextlib import nullcontext

from storage import RevisionConflict, layout
from storage.store import sha256_text

VERSION = "shared-book-2"
_locks_guard = threading.Lock()


def book_for(db, subject_id):
    reading = next(iter(db.find("library_readings", subject_id=subject_id)), None)
    return db.get("library_books", reading["book_id"]) if reading else None


def folder(book, kind=layout.LESSON_CONTENT):
    return f"Family Library/{book['id']}/{kind}"


def preparation_lock(ctx, topic):
    book = book_for(ctx.store, topic["subject_id"])
    if not book:
        return nullcontext()
    with _locks_guard:
        if not hasattr(ctx, "_library_material_locks"):
            ctx._library_material_locks = {}
        return ctx._library_material_locks.setdefault(book["id"], threading.RLock())


def reuse_enabled(ctx):
    """Whether a book lesson prepared for one child is saved for the next. Off by
    default: the family prefers a fresh lesson (better models, voices) for each child."""
    return bool((ctx.config.get('library') or {}).get('reuse_prepared_lessons', False))


def skill_packet(db, book):
    row = max(db.find("library_book_skills", book_id=book["id"]), key=lambda r: r["version"], default=None)
    if row:
        return row
    from .library import teaching_template
    content = teaching_template(book)
    return {"id": None, "book_id": book["id"], "version": 0, "content": content,
            "sha256": hashlib.sha256(content.encode()).hexdigest(), "file_path": None}


def save_skill(tx, book, content, expected_version):
    previous = skill_packet(tx, book)
    if previous["version"] != expected_version:
        raise RevisionConflict("These shared book instructions changed. Reload before saving.", previous)
    content = content.strip()
    if not 1 <= len(content) <= 30000:
        raise ValueError("Teaching instructions must contain 1–30,000 characters")
    if previous["version"] and previous["content"] == content:
        return previous
    version = previous["version"] + 1
    path, _ = tx.add_blob(content.encode(), folder(book, layout.TEACHING_SKILL), f"SKILL-v{version}.md", "text/markdown")
    saved = tx.insert("library_book_skills", {"id": "book-skill-" + uuid.uuid4().hex, "book_id": book["id"],
        "version": version, "content": content, "sha256": hashlib.sha256(content.encode()).hexdigest(), "file_path": path})
    # Child-bound skill rows preserve the existing engine's pinned-version FK.
    from .skills import current, save
    for reading in tx.find("library_readings", book_id=book["id"]):
        subject = tx.get("subjects", reading["subject_id"])
        prior = current(tx, subject["id"])
        save(tx, subject, content, prior["version"] if prior else 0)
    return saved


def neutral_context(ctx, data):
    """Whitelist source inputs; exclude names, ages, answers and all learner state."""
    from .family_skill import current, digest
    from .book_questions import VERSION as question_policy
    from .page_script import BOOK_TEACHING_POLICY
    family = current(ctx.store)
    sources = copy.deepcopy(data.get("subject_sources") or {})
    # A selected source concept may refer to another child's local topic.
    # Shared teaching uses the assigned original, not assumed prior learning.
    sources["earlier_concepts"] = []
    sources["connections"] = []
    sources.pop("selection", None)
    for concept in sources.get("current_concepts", []):
        concept.pop("topic_id", None)
    return {"subject_sources": sources, "source_requirements": copy.deepcopy(data["source_requirements"]),
            'selected_source_pages': copy.deepcopy(data.get('selected_source_pages') or []),
            "source_annotations": copy.deepcopy(data.get("source_annotations") or []),
            "family_tutoring": {"version": family["version"], "content": family["content"],
                "learner_profile": {}, "sha256": digest(family["content"], {})},
            "library_shared_policy": VERSION, 'book_question_policy': question_policy,
            'book_teaching_policy': BOOK_TEACHING_POLICY}


def key(ctx, topic, passage, language, skill, data):
    from . import guide, page_script as teaching_script, script_review, visual_source, material_skills
    from .source_annotations import packet as source_notes
    doc = ctx.store.get("documents", topic["document_id"])
    return sha256_text([VERSION, doc["sha256"],
        {k: topic.get(k) for k in ("title", "page_start", "page_end", "pdf_page_offset", "start_at", "stop_before")},
        passage["passage_sha256"], language, skill["sha256"], data["family_tutoring"]["sha256"], data.get('book_question_policy'), data.get('book_teaching_policy'),
        data["source_requirements"], data.get("subject_sources"), data.get("source_annotations"), data.get('selected_source_pages', []),
        # Assessment-only source notes matter to review even when not narrated.
        source_notes(ctx.store, topic, assessment=True),
        guide.GUIDE_VERSION, teaching_script.VERSION, script_review.VERSION, visual_source.VERSION,
        material_skills.packet(ctx, "script-review")["sha256"], material_skills.packet(ctx, "book-json")["sha256"]])


def latest(db, cache_key):
    return max(db.find("library_materials", cache_key=cache_key), key=lambda r: r["version"], default=None)


def save_material(tx, book, cache_key, kind, data):
    previous = latest(tx, cache_key)
    if previous and previous["data"] == data:
        return previous
    version = previous["version"] + 1 if previous else 1
    body = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1).encode()
    path, digest = tx.add_blob(body, folder(book), f"{kind}-{cache_key[:20]}-v{version}.json", "application/json")
    return tx.insert("library_materials", {"id": "book-material-" + uuid.uuid4().hex, "book_id": book["id"],
        "cache_key": cache_key, "kind": kind, "version": version, "data": data, "file_path": path, "sha256": digest})


def load(ctx, cache_key):
    row = latest(ctx.store, cache_key)
    if row:
        # Do not silently buy a replacement if the family archive is offline.
        stored = json.loads(ctx.file_bytes(row["file_path"], row["sha256"]))
        if stored != row["data"]:
            raise ValueError("The shared book preparation does not match its saved version")
    return row


def publish_guide(ctx, book, cache_key, row, built):
    from .script_review import latest as review
    report = review(ctx, row["id"])
    data = {"built": copy.deepcopy(built), "context": copy.deepcopy(row["context_snapshot"]),
            "model": row["model"], "language": row["language"],
            "review": {"status": report["status"], "data": report["data"], "method": report["method"]} if report else None}
    data["context"].pop("shared_material_id", None)
    data["context"].pop("workbook_fingerprint", None)
    with ctx.store.transaction(kind="library.guide", summary="Archived reusable book teaching and quiz content") as tx:
        return save_material(tx, book, cache_key, "guided_lesson", data)


def bind_guide(ctx, tx, material, topic, passage, skill, source_context):
    from . import guide, lesson_quality
    built = copy.deepcopy(material["data"]["built"])
    # Cache compatibility never substitutes for the normal source coverage check.
    built["source_coverage"] = lesson_quality.validate(built, source_context["source_requirements"])
    context = copy.deepcopy(material["data"]["context"])
    context["shared_material_id"] = material["id"]
    context["workbook_fingerprint"] = ctx.books.fingerprint(topic['subject_id'])
    return guide.save(tx, topic, passage, built, model=material["data"]["model"],
        language=material["data"]["language"], skill=skill, learner_context=context, folder=folder(book_for(tx, topic["subject_id"])))


def bind_review(ctx, row, material):
    from . import script_review
    review = material["data"]["review"]
    if review:
        # Carry forward the actual result, including a failed/blocked review;
        # never turn reuse into an unearned approval or a new paid request.
        return script_review.save(ctx, row, script_review.inputs(ctx, row), review["data"], "shared_book_review")


def topic_key(book, doc):
    from .books import scan_version
    return sha256_text(["book-topics-1", book["id"], doc["sha256"], scan_version("textbook")])


def passage_key(topic, document):
    from .passages import pdf_range, EXTRACTION_VERSION
    return sha256_text(['shared-book-passage-1', document['sha256'], pdf_range(topic),
        topic.get('start_at'), topic.get('stop_before'), EXTRACTION_VERSION])


def remember_passage(tx, topic, document, content):
    book = book_for(tx, topic['subject_id'])
    if not book:
        return
    # Source review is reusable. The reviewer's free-form note and local topic
    # identity stay in their original audit record, outside shared content.
    data = {k: copy.deepcopy(content[k]) for k in ('passage', 'passage_sha256', 'sentences', 'selected_images')}
    data['reviewed_pdf_pages'] = content['review']['pdf_pages']
    return save_material(tx, book, passage_key(topic, document), 'source_passage', data)


def remember_topics(tx, subject_id, document_id):
    book = book_for(tx, subject_id)
    if not book:
        return
    doc = tx.get("documents", document_id)
    rows = sorted((t for t in tx.find("topics", subject_id=subject_id, document_id=document_id) if not t.get("archived")), key=lambda t: (t["chapter_order"] or 0, t["id"]))
    from .navigation import persist
    chapters = [{'title': t['title'], 'page_start': t['page_start']+(t.get('pdf_page_offset') or 0),
                 'page_end': t['page_end']+(t.get('pdf_page_offset') or 0)} for t in rows]
    return persist(tx, doc, chapters, 'parent_checked')


def prepare_topics(service, resource, doc, *, allow_partial=False):
    """Compatibility entry point for chapter-map preparation; never scans pages."""
    from . import navigation
    return navigation.publish_topics(service, resource, doc, navigation.extract(service.ctx, doc))


def enrichment(ctx, topic, payload):
    """Share all four Practice products; only per-topic references are child-bound."""
    from services import ai_enrichment
    from app_context import request_operation as write
    book = book_for(ctx.store, topic["subject_id"])
    doc = ctx.store.get("documents", topic["document_id"])
    text = (payload.source_text or ctx.books.topic_text(topic) or "").strip()
    if not text:
        raise ValueError("Source text is required for this book's practice material")
    cache_key = sha256_text(["book-practice-1", doc["sha256"],
        {k: topic.get(k) for k in ("page_start", "page_end", "pdf_page_offset", "start_at", "stop_before")},
        payload.page_start, payload.page_end, payload.language, payload.content_type, text])
    with preparation_lock(ctx, topic):
        material = load(ctx, cache_key)
        reused = bool(material)
        if not material:
            result = ai_enrichment.generate_content(payload.content_type, text, payload.language or "en")
            content = json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)
        with write("library.practice", "Saved or reused source-only book practice for present and future readers") as tx:
            if not material:
                path, digest = tx.add_blob(content.encode(), folder(book), f"practice-{cache_key[:24]}.txt", "text/plain")
                material = save_material(tx, book, cache_key, payload.content_type, {"content_path": path, "content_sha256": digest})
            data = material["data"]
            # Verify the actual result before any new learner reference is made.
            ctx.file_bytes(data["content_path"], data["content_sha256"])
            existing = next(iter(tx.find("enrichment", topic_id=topic["id"], page_start=payload.page_start,
                page_end=payload.page_end, content_type=payload.content_type)), None)
            values = {"topic_id": topic["id"], "page_start": payload.page_start, "page_end": payload.page_end,
                "content_type": payload.content_type, **data}
            row = tx.update("enrichment", existing["id"], values) if existing else tx.insert("enrichment", values)
        return ctx.store.get("enrichment", row["id"]), reused


def remember_audio(ctx, topic, track_id):
    book = book_for(ctx.store, topic['subject_id'])
    row = ctx.store.get('audio_tracks', track_id)
    if not book or not row or (row.get('note') or '').startswith('feedback:'):
        return
    track = {k: row.get(k) for k in ('id', 'passage_sha256', 'provider', 'voice', 'speaking_rate', 'manifest_path',
        'status', 'characters', 'sentence_count', 'timing', 'note')}
    with ctx.store.transaction(kind='library.narration', summary='Archived reusable book narration independently of its first reader') as tx:
        save_material(tx, book, sha256_text(['book-audio-1', book['id'], track_id]), 'narration', {'track': track})


def audio_rows(db, book):
    # Retain all voice/rate variants; choose the newest archive for each identity.
    result = {}
    for row in sorted(db.find('library_materials', book_id=book['id'], kind='narration'), key=lambda r: r['version']):
        track = row['data']['track']
        result[track['id']] = track
    return list(result.values())


def audio_track(db, track_id, topic=None):
    existing = db.get('audio_tracks', track_id)
    if existing:
        if topic and existing['topic_id'] != topic['id']:
            book = book_for(db, topic['subject_id'])
            if not book or not any(r['id'] == track_id for r in audio_rows(db, book)):
                return None
        return existing
    for row in db.find('library_materials', kind='narration'):
        if row['data']['track']['id'] != track_id:
            continue
        if topic and (book_for(db, topic['subject_id']) or {}).get('id') != row['book_id']:
            continue
        return row['data']['track']
    return None


def refresh_review(ctx, row, report):
    """A later successful review is reusable; keep earlier blocked versions too."""
    frozen = row.get('context_snapshot') or {}
    cache_key = frozen.get('library_material_key')
    material = latest(ctx.store, cache_key) if cache_key else None
    if not material:
        return
    from . import guide, skills, passages
    from .lesson_context import preparation
    topic = ctx.store.get('topics', row['topic_id'])
    book = book_for(ctx.store, topic['subject_id'])
    if not book or guide.guide_sha(material['data']['built']['sentences']) != row['guide_sha256']:
        return
    subject = ctx.store.get('subjects', topic['subject_id'])
    passage = passages.load(ctx, topic)
    source = neutral_context(ctx, preparation(ctx, subject['child_id'], topic, passage))
    if frozen.get('visual_source'):
        source['subject_sources'].pop('page_structure', None)
    if key(ctx, topic, passage, row['language'], skills.packet(ctx.store, subject), source) != cache_key:
        return
    data = copy.deepcopy(material['data'])
    data['review'] = {k: report[k] for k in ('status', 'data', 'method')}
    with ctx.store.transaction(kind='library.review', summary='Saved another version of the shared book review') as tx:
        save_material(tx, book, cache_key, 'guided_lesson', data)
