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


def _exercise_view(topic):
    from tutoring import exercise_assignment
    members = exercise_assignment.group(store(), topic)
    row = exercise_assignment.saved(store(), members)
    lessons = [{'topic_id': t, 'title': (store().get('topics', t) or {}).get('title')} for t in members['topics']] if members else []
    return {'shared': bool(members), 'lessons': lessons, 'pages': members['pages'] if members else [],
            'revision': row['revision'] if row else 0,
            'assignment': {k: row['data'][k] for k in ('items', 'method')} if row else None}


@router.get('/topics/{topic_id}/exercise-assignment')
def exercise_assignment_view(topic_id: int):
    """Which items on this lesson's shared exercise pages each lesson teaches."""
    return _exercise_view(get_or_404(store(), 'topics', topic_id, 'Lesson'))


class ExerciseAssignmentSave(BaseModel):
    items: list[dict] = Field(min_length=1, max_length=300)
    expected_revision: int = Field(ge=0)


@router.put('/topics/{topic_id}/exercise-assignment')
def save_exercise_assignment(topic_id: int, payload: ExerciseAssignmentSave):
    """A grown-up's assignment replaces the AI's for new preparations."""
    from tutoring import exercise_assignment
    topic = get_or_404(store(), 'topics', topic_id, 'Lesson')
    members = exercise_assignment.group(store(), topic)
    if not members:
        raise HTTPException(400, 'This lesson’s exercise pages are not shared with other lessons.')
    try:
        with write('lesson.exercise_assignment', 'Assigned shared exercise items to lessons') as tx:
            old = tx.get('exercise_assignments', members['id'])
            if (old['revision'] if old else 0) != payload.expected_revision:
                raise ValueError('Reload the exercise assignment before saving.')
            exercise_assignment.persist(tx, members, payload.items, 'family')
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _exercise_view(topic)


@router.post('/topics/{topic_id}/exercise-assignment')
def run_exercise_assignment(topic_id: int):
    """Ask the AI once for a shared page set; a saved assignment is returned as is."""
    from services.ai_budget import micros
    from tutoring import exercise_assignment
    topic = get_or_404(store(), 'topics', topic_id, 'Lesson')
    members = exercise_assignment.group(store(), topic)
    if not members:
        raise HTTPException(400, 'This lesson’s exercise pages are not shared with other lessons.')
    scope = 'exercise-assignment-' + members['id'].rsplit(':', 1)[-1]
    context().ai.ledger.configure_scope(scope, micros(exercise_assignment.MAXIMUM_USD), category='teaching')
    try:
        with context().ai.preparing_lesson(), context().ai.scoped(scope):
            exercise_assignment.assign(context(), members)
    except ValueError as exc:
        raise HTTPException(502, str(exc)) from exc
    return _exercise_view(topic)


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
            # New books get their chapter map and lessons in the background, locally.
            context().books.prepare_collection(tx, subject_id)
        return view(store(), subject_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(400, "This PDF is unavailable. Choose it again after checking the synced folder.") from exc




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
        return store().get("book_imports", job["id"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


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
