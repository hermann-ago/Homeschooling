"""Resource import and exercise editing for family devices."""
import io
from typing import Literal
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from pypdf import PdfReader, PdfWriter

from app_context import request_operation as write
from dependencies import context, require_family, store
from services.documents import MAX_PDF_BYTES
from storage import layout
from tutoring.books import Requirement, book_name, READING_ROLES, PRACTICE_ROLES
from tutoring.map_review import ParentReview
from tutoring.source_annotations import Annotation
from utils import get_or_404

router = APIRouter(dependencies=[Depends(require_family)])


@router.get('/subjects/{subject_id}/navigation')
def chapter_maps(subject_id: int):
    from tutoring.navigation import sources, saved
    get_or_404(store(), 'subjects', subject_id, 'Subject')
    return {'books': [{**b, 'navigation': saved(store(), store().get('documents', b['document_id']))}
                      for b in sources(store(), subject_id)]}


def navigation_document(subject_id, document_id):
    from tutoring.navigation import sources
    if not any(b['document_id'] == document_id for b in sources(store(), subject_id)):
        raise HTTPException(400, 'Choose a book belonging to this subject')
    return get_or_404(store(), 'documents', document_id, 'Book')


@router.post('/subjects/{subject_id}/navigation/{document_id}')
def extract_chapter_map(subject_id: int, document_id: int):
    from tutoring.navigation import extract
    return extract(context(), navigation_document(subject_id, document_id))


class NavigationSave(BaseModel):
    chapters: list[dict] = Field(max_length=1000)
    expected_revision: int = Field(ge=0)


@router.put('/subjects/{subject_id}/navigation/{document_id}')
def save_chapter_map(subject_id: int, document_id: int, payload: NavigationSave):
    from tutoring.navigation import persist
    doc = navigation_document(subject_id, document_id)
    try:
        with write('books.chapter_map.edit', 'Saved chapter titles and original PDF ranges') as tx:
            row = persist(tx, doc, payload.chapters, 'parent_checked', expected_revision=payload.expected_revision)
        from tutoring.navigation import publish_topics
        resource = next((b for b in store().find('subject_books', subject_id=subject_id, document_id=document_id) if not b['archived']), None)
        if resource and resource['role'] != 'answer_key':
            publish_topics(context().books, resource, doc, row)
        return store().get('book_navigation', row['id'])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class SourcePages(BaseModel):
    document_id: int = Field(ge=1)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)


class NarratorChoice(BaseModel):
    voice: str = Field(min_length=1, max_length=100)


@router.get('/topics/{topic_id}/narrator')
def topic_narrator(topic_id: int):
    from tutoring.voice_choices import selected
    from tutoring.elevenlabs_audio import narrator
    from tutoring.audio import language_of
    topic = get_or_404(store(), 'topics', topic_id, 'Lesson')
    subject = store().get('subjects', topic['subject_id'])
    if context().config.get('tts', {}).get('provider') == 'inworld':
        from tutoring.inworld_voices import narrator, selected
        return {'provider': 'inworld', 'language': language_of(store(), subject), 'voice': selected(store(), topic_id) or narrator(context(), language_of(store(), subject), subject['child_id'])}
    return {'voice': selected(store(), topic_id) or narrator(context(), language_of(store(), subject), subject['child_id'])}


@router.put('/topics/{topic_id}/narrator')
def save_topic_narrator(topic_id: int, payload: NarratorChoice):
    from tutoring.voice_choices import catalog
    topic = get_or_404(store(), 'topics', topic_id, 'Lesson')
    provider = context().config.get('tts', {}).get('provider', 'elevenlabs')
    try:
        if provider == 'inworld':
            from tutoring.inworld_voices import catalog
        choice = next((v for v in catalog(context()) if v['id'] == payload.voice), None)
        if not choice:
            raise ValueError('Choose a narrator available in your connected account.')
        if provider == 'inworld':
            from tutoring.audio import language_of
            if choice['language'] != language_of(store(), store().get('subjects', topic['subject_id'])):
                raise ValueError('Choose a narrator in the lesson language.')
        with write('lesson.narrator', 'Selected a narrator without generating or replacing recordings') as tx:
            old = tx.get('topic_narrators', str(topic_id))
            values = {'topic_id': topic_id, 'voice': 'inworld:' + payload.voice if provider == 'inworld' else payload.voice, 'voice_name': choice['name']}
            return tx.update('topic_narrators', old['id'], values) if old else tx.insert('topic_narrators', {'id': str(topic_id), **values})
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class LessonPagesSave(BaseModel):
    sources: list[SourcePages] = Field(max_length=40)
    expected_revision: int = Field(ge=0)


@router.get('/topics/{topic_id}/source-pages')
def lesson_source_pages(topic_id: int):
    from tutoring.navigation import selections, sources, saved
    topic = get_or_404(store(), 'topics', topic_id, 'Lesson')
    row = store().get('lesson_page_selections', str(topic_id))
    books = sources(store(), topic['subject_id'])
    return {'revision': row['revision'] if row else 0, 'sources': selections(context(), topic),
            'books': [{**b, 'chapters': (saved(store(), store().get('documents', b['document_id'])) or {}).get('data', {}).get('chapters', [])} for b in books]}


@router.put('/topics/{topic_id}/source-pages')
def save_lesson_source_pages(topic_id: int, payload: LessonPagesSave):
    from tutoring.navigation import checked_selections
    topic = get_or_404(store(), 'topics', topic_id, 'Lesson')
    try:
        refs = checked_selections(store(), topic, [s.model_dump() for s in payload.sources])
        with write('lesson.source_pages', 'Selected original pages for lesson preparation') as tx:
            old = tx.get('lesson_page_selections', str(topic_id))
            if old:
                tx.update('lesson_page_selections', old['id'], {'sources': refs}, expected_revision=payload.expected_revision)
            else:
                if payload.expected_revision != 0:
                    raise ValueError('Reload the selected pages before saving.')
                tx.insert('lesson_page_selections', {'id': str(topic_id), 'topic_id': topic_id, 'sources': refs})
        return store().get('lesson_page_selections', str(topic_id))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get('/subjects/{subject_id}/source-notes')
def source_notes(subject_id:int):
    from tutoring import source_annotations as notes
    get_or_404(store(),'subjects',subject_id,'Subject')
    docs=notes.documents(store(),subject_id)
    hashes={d['sha256'] for d in docs}
    return {'documents':[{k:d[k] for k in ('id','sha256','original_filename','page_count')} for d in docs],
        'notes':[r for r in notes.latest(store()) if r['document_sha256'] in hashes],
        'history':[r for r in store().all('source_annotations') if r['document_sha256'] in hashes]}


@router.put('/subjects/{subject_id}/source-notes')
def save_source_note(subject_id:int,payload:Annotation):
    from tutoring.source_annotations import save
    get_or_404(store(),'subjects',subject_id,'Subject')
    try:
        with write('source_annotations.save','Saved an edition/page-scoped source note') as tx:
            return save(tx,subject_id,payload)
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc


class MaterialSkillSave(BaseModel):
    content: str = Field(min_length=1, max_length=30000)
    expected_version: int = Field(ge=0)


@router.get('/material-skills')
def material_skills():
    from tutoring.material_skills import inventory
    return {'skills': inventory(context())}


@router.put('/material-skills/{key}')
def save_material_skill(key: str, payload: MaterialSkillSave):
    from tutoring.material_skills import save
    try:
        with write('material_skills.save', 'Saved material-analysis instructions as a new version') as tx:
            result = save(context(), tx, key, payload.content, payload.expected_version)
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get('/subjects/{subject_id}/book-companions/{document_id}/history')
def companion_review_history(subject_id: int, document_id: int):
    from tutoring.book_companion import source_for
    try:
        source, doc = source_for(context(), subject_id, document_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {'reviews':[{k:r[k] for k in ('id','version','content_sha256','previous_sha256','file_path','note','created_at')}
        for r in sorted(store().find('book_source_reviews', sha256=doc['sha256'], role=source['role']),key=lambda r:r['version'],reverse=True)]}


@router.get("/book-companion-schema")
def book_companion_schema():
    from tutoring.book_companion import Envelope
    return Envelope.model_json_schema()


@router.get("/subjects/{subject_id}/book-companions")
def book_companions(subject_id: int):
    get_or_404(store(), "subjects", subject_id, "Subject")
    from tutoring.book_companion import inventory
    return {"books": inventory(context(), subject_id)}


@router.post("/subjects/{subject_id}/book-companions/{document_id}")
def create_book_companion(subject_id: int, document_id: int):
    raise HTTPException(410, 'Whole-book scanning is retired. Use chapter maps and selected original lesson pages.')
    get_or_404(store(), "subjects", subject_id, "Subject")
    from tutoring.book_companion import source_for, from_scans, persist, summary, row_id
    try:
        source, doc = source_for(context(), subject_id, document_id)
        previous = store().get("book_companions", row_id(doc["sha256"], source["role"]))
        body = from_scans(context(), source, doc)
        with write("books.companion", "Saved a book JSON using local extraction and previously checked pages") as tx:
            result = persist(context(), tx, subject_id, doc, body, previous["revision"] if previous else 0)
        return summary(store().get("book_companions", result["id"]))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/subjects/{subject_id}/book-companions/{document_id}/export")
def export_book_companion(subject_id: int, document_id: int):
    import json
    from tutoring.book_companion import source_for, row_id
    try:
        source, doc = source_for(context(), subject_id, document_id)
        row = store().get("book_companions", row_id(doc["sha256"], source["role"]))
        if not row:
            raise ValueError("Create this book's JSON first")
        body = json.dumps({"content_sha256": row["content_sha256"], "contents": row["data"]}, ensure_ascii=False, indent=2)
        return Response(body, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="book-{document_id}.book.json"',
                                                                     "Cache-Control": "private, no-store"})
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/subjects/{subject_id}/book-companions/{document_id}/pages/{page}")
def inspect_book_companion(subject_id: int, document_id: int, page: int):
    from tutoring.book_companion import source_for, row_id
    try:
        source, doc = source_for(context(), subject_id, document_id)
        row = store().get("book_companions", row_id(doc["sha256"], source["role"]))
        if not row or page < 1 or page > doc["page_count"]:
            raise ValueError("Choose an available page in this book's JSON")
        return row["data"]["pages"][page - 1]
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/subjects/{subject_id}/book-companions/{document_id}/source-pdf/{page}")
def companion_source_page(subject_id: int, document_id: int, page: int):
    from tutoring.book_companion import source_for
    try:
        _, doc = source_for(context(), subject_id, document_id)
        if page < 1 or page > doc["page_count"]:
            raise ValueError("Choose a page in this book")
        reader = PdfReader(io.BytesIO(context().file_bytes(doc["file_path"], doc["sha256"])))
        writer = PdfWriter()
        writer.add_page(reader.pages[page - 1])
        body = io.BytesIO()
        writer.write(body)
        return Response(body.getvalue(), media_type="application/pdf", headers={"Cache-Control": "private, no-store"})
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/subjects/{subject_id}/book-companions/{document_id}/import")
async def import_book_companion(subject_id: int, document_id: int, file: UploadFile = File(...), expected_revision: int = Form(...),
                                source_review: bool = Form(False), note: str = Form('')):
    raise HTTPException(410, 'Whole-book scanning is retired. Use chapter maps and selected original lesson pages.')
    import json
    from pydantic import ValidationError
    from tutoring.book_companion import MAX_JSON_BYTES, source_for, import_file, summary
    get_or_404(store(), "subjects", subject_id, "Subject")
    try:
        if expected_revision < 0:
            raise ValueError("Reload the book before importing")
        data = await file.read(MAX_JSON_BYTES + 1)
        if len(data) > MAX_JSON_BYTES:
            raise ValueError("Choose a book JSON smaller than 32 MiB")
        payload = json.loads(data)
        # Verify availability outside the short persistence transaction.
        _, doc = source_for(context(), subject_id, document_id)
        context().file_bytes(doc["file_path"], doc["sha256"])
        with write("books.companion_import", "Imported a validated source-only book representation") as tx:
            row = import_file(context(), tx, subject_id, document_id, payload, expected_revision, source_review=source_review, note=note)
        return summary(store().get("book_companions", row["id"]))
    except (ValueError, ValidationError, UnicodeError) as exc:
        raise HTTPException(400, str(exc)[:1600]) from exc


class CollectionBook(BaseModel):
    key: str = Field(min_length=1, max_length=300)
    document_id: int | None = Field(default=None, ge=1)
    path: str | None = Field(default=None, min_length=1, max_length=1000)
    role: Literal["textbook", "combined", "workbook", "test", "answer_key", "reference"]
    edition: str = Field(default="", max_length=150)
    position: int = Field(ge=0, le=1000)
    is_main: bool = False
    companion_key: str | None = Field(default=None, max_length=300)
    answer_for_key: str | None = Field(default=None, max_length=300)
    answer_for_keys: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def source(self):
        if (self.document_id is None) == (self.path is None):
            raise ValueError("Choose an existing book or an uploaded PDF, not both")
        return self


class SaveCollection(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    expected_revision: int = Field(ge=0)
    books: list[CollectionBook] = Field(max_length=100)


@router.get("/subjects/{subject_id}/book-collection")
def book_collection(subject_id: int):
    get_or_404(store(), "subjects", subject_id, "Subject")
    from tutoring.collections import view
    return view(store(), subject_id)


@router.put("/subjects/{subject_id}/book-collection")
def save_book_collection(subject_id: int, payload: SaveCollection):
    get_or_404(store(), "subjects", subject_id, "Subject")
    from tutoring.collections import inspect_sources, save, view
    try:
        name = payload.name.strip()
        if not name:
            raise ValueError("Give this book collection a name")
        inputs=[]
        for book in payload.books:
            value=book.model_dump()
            if 'answer_for_keys' not in book.model_fields_set:value.pop('answer_for_keys')
            inputs.append(value)
        inspected = inspect_sources(context(), inputs)
        with write("books.collection", "Saved a subject book collection without AI generation") as tx:
            save(tx, subject_id, name, payload.expected_revision, inspected)
        return view(store(), subject_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(400, "This PDF is unavailable. Choose it again after checking the synced folder.") from exc


class StartAnalysis(BaseModel):
    fingerprint: str = Field(min_length=1, max_length=100)
    maximum_usd: Decimal = Field(gt=0, le=10, decimal_places=6)


@router.get('/source-map-schema')
def offline_source_map_schema():
    from tutoring.offline_materials import SourceMap
    return SourceMap.model_json_schema()


@router.post('/subjects/{subject_id}/book-collection/import-map')
async def import_offline_source_map(subject_id:int,file:UploadFile=File(...)):
    raise HTTPException(410, 'Whole-book scanning is retired. Use chapter maps and selected original lesson pages.')
    import json
    from tutoring.offline_materials import SourceMap,save
    get_or_404(store(),'subjects',subject_id,'Subject')
    try:
        body=await file.read(33554433)
        if len(body)>33554432:raise ValueError('Choose a source map smaller than 32 MiB')
        payload=SourceMap.model_validate_json(body)
        with write('materials.import_codex','Imported a source-bound Codex material map without API generation') as tx:
            result=save(context(),tx,subject_id,payload)
        from tutoring.subject_knowledge import ensure
        ensure(context(),store().get('subject_maps',result['map_id'])['collection_id'])
        return result
    except ValueError as exc:
        raise HTTPException(400,str(exc)[:1800]) from exc


class ContinueAnalysis(BaseModel):
    maximum_usd: Decimal | None = Field(default=None, gt=0, le=10, decimal_places=6)


@router.get("/subjects/{subject_id}/book-collection/preview")
def preview_subject_analysis(subject_id: int):
    get_or_404(store(), "subjects", subject_id, "Subject")
    try:
        return context().subject_analysis.preview(subject_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/subjects/{subject_id}/book-collection/analyze")
def start_subject_analysis(subject_id: int, payload: StartAnalysis):
    raise HTTPException(410, 'Whole-book scanning is retired. Use chapter maps and selected original lesson pages.')
    get_or_404(store(), "subjects", subject_id, "Subject")
    from services.ai_budget import micros
    try:
        with write("subject_analysis.start", "Started a subject review within a parent-selected job limit") as tx:
            jid = context().subject_analysis.start(tx, subject_id, payload.fingerprint, micros(payload.maximum_usd))
        return context().subject_analysis.public_job(store().get("collection_analysis_jobs", jid))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/subjects/{subject_id}/book-collection/analysis")
def subject_analysis_status(subject_id: int):
    get_or_404(store(), "subjects", subject_id, "Subject")
    return {"jobs": context().subject_analysis.jobs(subject_id)}


from tutoring.material_review import MaterialReview


@router.post('/subjects/{subject_id}/book-collection/source-review')
def apply_material_source_review(subject_id: int, payload: MaterialReview):
    raise HTTPException(410, 'Whole-book scanning is retired. Use chapter maps and selected original lesson pages.')
    from tutoring.material_review import apply
    get_or_404(store(),'subjects',subject_id,'Subject')
    try:
        with write('materials.source_review','Saved a new source-map snapshot without AI generation') as tx:
            mid=apply(context(),tx,subject_id,payload)
        from tutoring.subject_knowledge import ensure
        ensure(context(),store().get('subject_maps',mid)['collection_id'])
        return {'map_id':mid,'ai_generation':False}
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from exc


@router.post("/subject-analysis/{job_id}/continue")
def continue_subject_analysis(job_id: str, payload: ContinueAnalysis):
    raise HTTPException(410, 'Whole-book scanning is retired. Use chapter maps and selected original lesson pages.')
    job = get_or_404(store(), "collection_analysis_jobs", job_id, "Subject review")
    from services.ai_budget import micros
    try:
        with write("subject_analysis.continue", "Continued a saved subject review") as tx:
            context().subject_analysis.resume(tx, store().get("collection_analysis_jobs", job_id),
                                             micros(payload.maximum_usd) if payload.maximum_usd is not None else None)
        return context().subject_analysis.public_job(store().get("collection_analysis_jobs", job_id))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/subject-analysis/{job_id}/pause")
def pause_subject_analysis(job_id: str):
    job = get_or_404(store(), "collection_analysis_jobs", job_id, "Subject review")
    if job.get("rehearsal_snapshot"):
        raise HTTPException(400, "This is a read-only test snapshot; the original analysis is protected")
    with write("subject_analysis.pause", "Paused a subject review") as tx:
        current = tx.get("collection_analysis_jobs", job_id)
        if current["status"] in ("queued", "running"):
            tx.update("collection_analysis_jobs", job_id, {"status": "paused", "error": "Paused by a parent. An in-flight request may finish and be saved."})
            context().ai.ledger.enable_scope(job_id, False)
    return context().subject_analysis.public_job(store().get("collection_analysis_jobs", job_id))


@router.get("/subject-maps/{map_id}")
def saved_subject_map(map_id: str, subject_id: int | None = None):
    row = get_or_404(store(), "subject_maps", map_id, "Subject map")
    from tutoring.map_review import effective_map
    from tutoring.lesson_context import status
    job = store().get("collection_analysis_jobs", row["job_id"])
    selected_subject = subject_id if subject_id is not None else job["subject_id"]
    from tutoring.collections import binding
    linked = binding(store(), selected_subject)
    if not linked or linked["collection_id"] != row["collection_id"]:
        raise HTTPException(400, "This saved map is not assigned to that subject")
    return {**effective_map(context(), row), "teaching_selection": status(context(), selected_subject)}


class SelectTeachingMap(BaseModel):
    subject_id: int | None = Field(default=None, ge=1)
    expected_revision: int = Field(ge=0)
    expected_review_revision: int = Field(ge=0)


@router.post("/subject-maps/{map_id}/select")
def select_teaching_map(map_id: str, payload: SelectTeachingMap):
    from tutoring.lesson_context import publish
    try:
        with write("subject_map.select", "Parent selected checked source context for new lessons") as tx:
            publish(context(), tx, map_id, payload.expected_revision, payload.expected_review_revision, payload.subject_id)
        return saved_subject_map(map_id, payload.subject_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.put("/subject-maps/{map_id}/review")
def review_subject_map(map_id: str, payload: ParentReview, subject_id: int | None = None):
    from tutoring.map_review import save, effective_map
    row = get_or_404(store(), "subject_maps", map_id, "Subject map")
    saved_subject_map(map_id, subject_id)  # validate the requested subject binding
    try:
        with write("subject_map.review", "Saved a parent source-map review without AI generation") as tx:
            save(context(), tx, row, payload)
        from tutoring.subject_knowledge import ensure
        ensure(context(), row["collection_id"])
        return saved_subject_map(map_id, subject_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/subject-maps/{map_id}/reading/{unit_id}")
def map_reading_source(map_id: str, unit_id: str):
    from tutoring.map_review import reading_source
    row = get_or_404(store(), "subject_maps", map_id, "Subject map")
    try:
        return reading_source(context(), row, unit_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/subject-maps/{map_id}/source-pdf/{document_id}/{page}")
def map_source_pdf(map_id: str, document_id: int, page: int):
    from tutoring.map_review import pdf_page
    row = get_or_404(store(), "subject_maps", map_id, "Subject map")
    try:
        reader = PdfReader(io.BytesIO(pdf_page(context(), row, document_id, page)))
        writer = PdfWriter()
        writer.add_page(reader.pages[page - 1])
        writer.add_metadata({"/Title": f"Original reading · PDF page {page}"})
        body = io.BytesIO()
        writer.write(body)
        return Response(body.getvalue(), media_type="application/pdf", headers={"Cache-Control": "private, no-store"})
    except ValueError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.get("/subject-maps/{map_id}/export")
def export_subject_map(map_id: str):
    import json
    from tutoring.map_review import effective_map
    row = get_or_404(store(), "subject_maps", map_id, "Subject map")
    return Response(json.dumps(effective_map(context(), row), ensure_ascii=False, indent=2, default=str),
        media_type="application/json", headers={"Content-Disposition": 'attachment; filename="subject-source-map.json"',
                                                "Cache-Control": "private, no-store"})


@router.get("/subject-knowledge")
def reusable_subject_knowledge():
    from tutoring.subject_knowledge import available
    return {"collections": available(context())}


@router.post("/subjects/{subject_id}/knowledge-file")
def save_knowledge_file(subject_id: int):
    get_or_404(store(), "subjects", subject_id, "Subject")
    from tutoring.subject_knowledge import save
    try:
        return save(context(), subject_id)
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


class ReuseKnowledge(BaseModel):
    source_subject_id: int = Field(ge=1)
    expected_revision: int = Field(ge=0)
    expected_version_id: str | None = None


@router.post("/subjects/{subject_id}/reuse-knowledge")
def reuse_subject_knowledge(subject_id: int, payload: ReuseKnowledge):
    get_or_404(store(), "subjects", subject_id, "Subject")
    get_or_404(store(), "subjects", payload.source_subject_id, "Source subject")
    from tutoring.subject_knowledge import save, reuse
    from tutoring.collections import view
    try:
        # Verify original bytes and save the archive before the short binding
        # transaction. This is entirely local; no analysis is requested.
        from tutoring.subject_knowledge import latest
        row = latest(context(), payload.source_subject_id)
        if not row:
            raise ValueError("Choose a collection with completed source analysis")
        for book in row["data"]["books"]:
            doc = store().get("documents", book["document_id"])
            context().file_bytes(doc["file_path"], book["sha256"])
        source_file = save(context(), payload.source_subject_id)
        context().files.read(source_file["path"], source_file["sha256"])
        with write("subject_knowledge.reuse", "Assigned saved source knowledge without copying learner records or generating analysis") as tx:
            reuse(context(), tx, subject_id, payload.source_subject_id, payload.expected_revision, payload.expected_version_id, row["version_id"])
        target_file = save(context(), subject_id)
        return {"collection": view(store(), subject_id), "knowledge_file": target_file}
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/books/incoming")
def incoming():
    return {"folder": layout.INCOMING_BOOKS, "books": [b for b in context().files.list_pdfs()
        if b["path"].startswith(layout.INCOMING_BOOKS + "/")]}


@router.post("/books/stage")
async def stage(file: UploadFile = File(...)):
    data = await file.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES or not data.startswith(b"%PDF"):
        raise HTTPException(400, "Choose a PDF smaller than 250 MiB")
    try:
        PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise HTTPException(400, "This PDF could not be read") from exc
    with write("books.stage", "Added an incoming book") as tx:
        path, sha = tx.add_blob(data, layout.INCOMING_BOOKS, file.filename or "book.pdf", "application/pdf")
    return {"path": path, "sha256": sha, "name": path.rsplit("/", 1)[-1]}


class ImportBook(BaseModel):
    path: str
    role: Literal["textbook", "combined", "workbook", "test", "answer_key", "reference"]
    companion_id: str | None = None
    companion_path: str | None = None
    answer_for_id: str | None = None
    answer_for_path: str | None = None


class ImportBooks(BaseModel):
    books: list[ImportBook] = Field(min_length=1, max_length=10)


@router.post("/subjects/{subject_id}/book-imports")
def import_books(subject_id: int, payload: ImportBooks):
    get_or_404(store(), "subjects", subject_id, "Subject")
    previous_targets = {b["answer_for_id"] for b in store().find("subject_books", subject_id=subject_id) if b.get("answer_for_id")}
    try:
        with write("books.import", "Prepared subject books") as tx:
            jobs = []
            companion = None
            selected_textbooks = {}
            selected_books = {}
            multiple_textbooks = sum(b.role in READING_ROLES for b in payload.books) > 1
            for book in sorted(payload.books, key=lambda b: 0 if b.role in READING_ROLES else 2 if b.role == "answer_key" else 1):
                linked = book.companion_id
                if book.companion_path:
                    linked = selected_textbooks.get(book.companion_path)
                    if not linked:
                        raise ValueError("Choose a selected textbook as this book's companion")
                if book.role in ("workbook", "test") and multiple_textbooks and not linked:
                    raise ValueError("Choose the companion textbook for each workbook")
                target = book.answer_for_id
                if book.answer_for_path:
                    target = selected_books.get(book.answer_for_path)
                    if not target:
                        raise ValueError("Choose the selected workbook this answer key belongs to")
                job = context().books.begin(tx, subject_id, book.path, book.role,
                    linked or (companion if book.role in ("workbook", "test") else None), target)
                jobs.append(job)
                selected_books[book.path] = job["book_id"]
                if book.role in READING_ROLES:
                    companion = job["book_id"]
                    selected_textbooks[book.path] = companion
        from tutoring.book_sources import refresh_keys
        for target in previous_targets:
            refresh_keys(context().books, target)
        return {"jobs": [store().get("book_imports", j["id"]) for j in jobs]}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/subjects/{subject_id}/resources")
def resources(subject_id: int):
    get_or_404(store(), "subjects", subject_id, "Subject")
    books = store().find("subject_books", subject_id=subject_id)
    return [{**b, "name": book_name(store().get("documents", b["document_id"])["original_filename"]),
        "jobs": sorted(store().find("book_imports", book_id=b["id"]), key=lambda j: j["created_at"], reverse=True),
        "exercises": context().books.exercises(b["id"])} for b in books if not b["archived"]]


@router.post("/book-imports/{job_id}/retry")
def retry(job_id: str):
    try:
        with write("books.retry") as tx:
            context().books.retry(tx, job_id)
        return store().get("book_imports", job_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class PrepareBook(BaseModel):
    role: Literal["textbook", "combined", "workbook", "test", "answer_key", "reference"]
    companion_id: str | None = None
    answer_for_id: str | None = None


@router.post("/subject-books/{book_id}/prepare")
def prepare(book_id: str, payload: PrepareBook):
    book = get_or_404(store(), "subject_books", book_id, "Book")
    doc = store().get("documents", book["document_id"])
    try:
        with write("books.prepare") as tx:
            job = context().books.begin(tx, book["subject_id"], doc["file_path"], payload.role, payload.companion_id, payload.answer_for_id)
        if book.get("answer_for_id"):
            from tutoring.book_sources import refresh_keys
            refresh_keys(context().books, book["answer_for_id"])
        return store().get("book_imports", job["id"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class RematchBook(BaseModel):
    topic_id: int | None = None


@router.post("/subject-books/{book_id}/rematch")
def rematch(book_id: str, payload: RematchBook):
    raise HTTPException(410, 'Whole-book scanning is retired. Use chapter maps and selected original lesson pages.')
    try:
        with write("books.rematch", "Improved remaining reading links") as tx:
            job = context().books.rematch(tx, book_id, payload.topic_id)
        return store().get("book_imports", job["id"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class ExerciseEdit(BaseModel):
    expected_revision: int
    requirements: list[Requirement]
    optional: bool = False
    prompt: str | None = Field(None, max_length=12000)
    source_reviewed: bool = False


@router.put("/exercises/{exercise_id}")
def edit(exercise_id: str, payload: ExerciseEdit):
    try:
        with write("books.exercise_edit") as tx:
            version_id = context().books.edit(tx, exercise_id, payload.expected_revision,
                [r.model_dump() for r in payload.requirements], payload.optional, payload.prompt, payload.source_reviewed)
        return {"version_id": version_id}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/exercises/{exercise_id}/history")
def history(exercise_id: str):
    get_or_404(store(), "exercises", exercise_id, "Exercise")
    return [{"id": v["id"], "created_at": v["created_at"], "parent_edited": v["parent_edited"],
        **context().books.public(v["data"])} for v in sorted(store().find("exercise_versions", exercise_id=exercise_id),
                                                          key=lambda x: x["created_at"], reverse=True)]


@router.get("/exercises/{exercise_id}/preview")
def preview(exercise_id: str, version_id: str | None = None):
    exercise = get_or_404(store(), "exercises", exercise_id, "Exercise")
    version = get_or_404(store(), "exercise_versions", version_id or exercise["active_version"], "Exercise version")
    if version["exercise_id"] != exercise_id or not version["data"].get("student_safe"):
        raise HTTPException(403, "This page includes private or unchecked material. Use the exercise instructions instead")
    book = store().get("subject_books", exercise["book_id"])
    if book["role"] == "answer_key":
        raise HTTPException(403, "Answer keys are private teacher material")
    doc = store().get("documents", book["document_id"])
    if version["data"]["source_sha256"] != doc["sha256"]:
        raise HTTPException(409, "The original source edition is unavailable")
    reader = PdfReader(io.BytesIO(context().file_bytes(doc["file_path"], doc["sha256"])))
    writer = PdfWriter()
    for number in version["data"]["pages"]:
        writer.add_page(reader.pages[number - 1])
    body = io.BytesIO()
    writer.write(body)
    return Response(body.getvalue(), media_type="application/pdf", headers={"Cache-Control": "private, no-store"})


@router.get("/workbook-progress/{child_id}")
def progress(child_id: int):
    get_or_404(store(), "children", child_id, "Learner")
    return [{"subject": {"id": s["id"], "name": s["name"]}, "books": resources(s["id"])}
            for s in store().find("subjects", child_id=child_id)]


@router.get("/student-work/{evidence_id}")
def evidence_content(evidence_id: str):
    evidence = get_or_404(store(), "evidence_files", evidence_id, "Student work")
    session = get_or_404(store(), "tutor_sessions", evidence["session_id"], "Session")
    if evidence["child_id"] != session["child_id"]:
        raise HTTPException(403, "This work does not belong to the session")
    return Response(context().file_bytes(evidence["file_path"], evidence["sha256"]), media_type=evidence["mime_type"],
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/exercises/{exercise_id}/practice")
def practice(exercise_id: str):
    from tutoring import guide, passages, skills
    exercise = get_or_404(store(), "exercises", exercise_id, "Exercise")
    book = store().get("subject_books", exercise["book_id"])
    if book["role"] not in PRACTICE_ROLES:
        raise HTTPException(400, "Choose a workbook or test-booklet exercise")
    subject = store().get("subjects", book["subject_id"])
    current = context().tutor.open_session(subject["child_id"], subject["id"])
    if current:
        return {"session_id": current["id"], "path": context().tutor.reader_path(current), "resumed": True}
    version = context().books.snapshot(exercise)
    data = version["data"]
    if data["status"] != "matched" or not data["requirements"] or not all(store().get("topics", r["topic_id"])["completed"] for r in data["requirements"]):
        raise HTTPException(400, "Complete the required reading before starting this exercise")
    topic = store().get("topics", data["requirements"][-1]["topic_id"])
    source = passages.load(context(), topic)
    prompt = f"{data['book_name']}, exercise {data['reference']}. Complete this exercise and send your answer or a photo."
    action = {"id": "practice", "prompt": prompt, "kind": data["kind"], "start_sentence": 0, "end_sentence": 0, "resume_index": 1,
        "exercise_id": exercise_id, "version_id": version["id"], "exercise": context().books.public(data)}
    built = {"mode": "practice", "segments": [{"type": "action", "text": prompt}],
        "sentences": [{"text": prompt, "kind": "teacher", "source": None, "paragraphIndex": 0, "pause_after": "practice"}], "actions": [action]}
    interactive = context().tutor.interactive
    with interactive.lock:
        with write("books.practice") as tx:
            row = guide.save(tx, topic, source, built, model="saved workbook", language="en-US", skill=skills.packet(store(), subject))
            session_id = interactive.start(tx, subject["child_id"], topic["id"], row["id"])
            tx.update("tutor_sessions", session_id, {"session_type": "workbook"})
            tx.update("lesson_playback", session_id, {"action_id": "practice", "reading_finished": True, "resume_index": 1})
    context().tutor.open_reader(session_id)
    return {"session_id": session_id, "path": context().tutor.reader_path(store().get("tutor_sessions", session_id)), "resumed": False}
