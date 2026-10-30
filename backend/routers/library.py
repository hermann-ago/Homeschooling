"""Local catalog, shared originals and per-child extracurricular reading."""
import hashlib
import io
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, HttpUrl, field_validator
from pypdf import PdfReader

from app_context import request_operation as write
from dependencies import context, require_family, store
from services.documents import MAX_PDF_BYTES, find_by_checksum
from storage import RevisionConflict
from tutoring.library import LIBRARY_FOLDER, STAGES, book_view, enroll, reading_view
from utils import get_or_404

router = APIRouter(dependencies=[Depends(require_family)])


class NewBook(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    author: str = Field(min_length=1, max_length=200)
    stage: int = Field(ge=1, le=7)
    year: int | None = Field(None, ge=0, le=3000)
    estimated_pages: int | None = Field(None, ge=1, le=50000)
    source_url: HttpUrl | None = None
    store_url: HttpUrl | None = None

    @field_validator("title", "author")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Enter a title and author")
        return value.strip()


class ReadingRequest(BaseModel):
    child_id: int = Field(ge=1)


class BookSourceUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    source_url: HttpUrl | None = None
    source_label: str | None = Field(None, max_length=100)
    source_note: str | None = Field(None, max_length=3000)
    availability: str | None = Field(None, max_length=160)


class BookSkillRequest(BaseModel):
    content: str = Field(min_length=1, max_length=30000)
    expected_version: int = Field(ge=0)


@router.get("/books/{book_id}/teaching-skill")
def teaching_skill(book_id: str):
    from tutoring.library_materials import skill_packet
    return skill_packet(store(), get_or_404(store(), "library_books", book_id, "Book"))


@router.get("/books/{book_id}/teaching-skill/history")
def skill_history(book_id: str):
    get_or_404(store(), "library_books", book_id, "Book")
    return sorted(store().find("library_book_skills", book_id=book_id), key=lambda r: r["version"], reverse=True)


@router.put("/books/{book_id}/teaching-skill")
def save_teaching_skill(book_id: str, payload: BookSkillRequest):
    from tutoring.library_materials import save_skill
    book = get_or_404(store(), "library_books", book_id, "Book")
    with write("library.skill", "Saved shared book teaching instructions for present and future readers") as tx:
        return save_skill(tx, book, payload.content, payload.expected_version)


@router.get("/books")
def books(child_id: int | None = None):
    if child_id is not None:
        get_or_404(store(), "children", child_id, "Learner")
    return {"folder": LIBRARY_FOLDER, "stages": [{"id": n, "title": title} for n, title in enumerate(STAGES, 1)],
            "books": [book_view(store(), b, child_id) for b in sorted(store().all("library_books"), key=lambda b: (b["stage"], b["position"]))]}


@router.post("/books", status_code=201)
def add_book(payload: NewBook):
    with write("library.add", "Added a family reading title") as tx:
        values = payload.model_dump()
        for key in ("source_url", "store_url"):
            values[key] = str(values[key]) if values[key] else None
        book = tx.insert("library_books", {**values, "id": "library-" + uuid.uuid4().hex,
            "position": max((b["position"] for b in tx.all("library_books")), default=0) + 1,
            "stage_title": STAGES[payload.stage - 1], "source_label": "Provided source", "availability": "Not checked"})
    return book_view(store(), book)


@router.get("/books/{book_id}")
def book(book_id: str, child_id: int | None = None):
    return book_view(store(), get_or_404(store(), "library_books", book_id, "Book"), child_id)


@router.patch("/books/{book_id}/source")
def update_source(book_id: str, payload: BookSourceUpdate):
    get_or_404(store(), "library_books", book_id, "Book")
    values = payload.model_dump(exclude_unset=True, exclude={"expected_revision"})
    if values.get("source_url"):
        values["source_url"] = str(values["source_url"])
    with write("library.source", "Recorded the verified source and exact edition of a library download") as tx:
        row = tx.update("library_books", book_id, values, expected_revision=payload.expected_revision)
    return book_view(store(), row)


@router.post("/books/{book_id}/file")
async def upload(book_id: str, file: UploadFile = File(...), expected_revision: int = Form(..., ge=1)):
    get_or_404(store(), "library_books", book_id, "Book")
    data = await file.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES or not data.startswith(b"%PDF"):
        raise HTTPException(400, "Choose a PDF book smaller than 250 MiB")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValueError("Encrypted PDF")
        pages = len(reader.pages)
        if not pages:
            raise ValueError("Empty PDF")
    except Exception as exc:
        raise HTTPException(400, "Choose a readable, unencrypted PDF with at least one page") from exc
    sha = hashlib.sha256(data).hexdigest()
    with write("library.upload", "Saved a shared library original without starting AI preparation") as tx:
        current = tx.get("library_books", book_id)
        if current["revision"] != expected_revision:
            raise RevisionConflict("This book changed. Reopen it before uploading.", current)
        old = tx.get("documents", current["document_id"]) if current.get("document_id") else None
        if old and old["sha256"] != sha:
            raise HTTPException(409, "This title already has an edition. Add another book entry for a different PDF so reading records keep their original source.")
        doc = find_by_checksum(tx, sha)
        if not doc:
            # The original is stored once for the family; filenames never overwrite a different file.
            name = (file.filename or "book.pdf").replace("\\", "/").rsplit("/", 1)[-1]
            path, _ = tx.add_blob(data, LIBRARY_FOLDER, name, "application/pdf")
            doc = tx.insert("documents", {"file_path": path, "original_filename": name, "page_count": pages,
                "size_bytes": len(data), "sha256": sha, "source": "family_library"})
        if current.get("document_id") != doc["id"]:
            tx.update("library_books", book_id, {"document_id": doc["id"]})
    return book_view(store(), store().get("library_books", book_id))


@router.post("/books/{book_id}/readings")
def add_reading(book_id: str, payload: ReadingRequest):
    selected = get_or_404(store(), "library_books", book_id, "Book")
    child = get_or_404(store(), "children", payload.child_id, "Learner")
    with write("library.enroll", "Added optional reading for a learner") as tx:
        reading = enroll(tx, selected, child)
    return reading_view(store(), reading)


@router.delete('/books/{book_id}/readings/{child_id}')
def pause_reading(book_id: str, child_id: int):
    reading = next(iter(store().find('library_readings', book_id=book_id, child_id=child_id)), None)
    if not reading:
        raise HTTPException(404, 'This book is not assigned to that learner')
    with write('library.pause', 'Removed a book from this learner’s curriculum; retained progress and shared materials') as tx:
        tx.update('subjects', reading['subject_id'], {'purpose': 'library_paused'})
    return reading_view(store(), reading)


@router.post("/books/{book_id}/prepare")
def prepare(book_id: str, payload: ReadingRequest):
    selected = get_or_404(store(), "library_books", book_id, "Book")
    reading = next(iter(store().find("library_readings", book_id=book_id, child_id=payload.child_id)), None)
    if not reading or store().get('subjects', reading['subject_id']).get('purpose') == 'library_paused':
        raise HTTPException(400, "Add this book to the learner's curriculum first")
    doc = store().get("documents", selected["document_id"]) if selected.get("document_id") else None
    if not doc:
        raise HTTPException(400, "Upload the book's PDF before preparing its chapter map")
    view = reading_view(store(), reading)
    if view['job'] and view['job']['status'] == 'ready':
        return view
    try:
        with write("library.prepare", "Prepared chapter navigation for optional reading") as tx:
            job = view["job"]
            if job and job["status"] in ("failed", "waiting"):
                context().books.retry(tx, job["id"])
            else:
                context().books.begin(tx, reading["subject_id"], doc["file_path"], "textbook")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return reading_view(store(), reading)
