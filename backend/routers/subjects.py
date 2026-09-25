import hashlib
from datetime import date, datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app_context import request_operation as write
from dependencies import context, require_member, require_parent, store
from schemas import AIAnalysisResult, SubjectCreate, SubjectResponse, SubjectUpdate, TopicResponse, TopicUpdate
from services.ai_analyzer import analyze_curriculum
from services.completion_tracking import mark_topic_completed, mark_topic_incomplete, save_topic
from services.documents import MAX_PDF_BYTES, add_drive_document, add_uploaded_document, inspect_pdf
from storage.gateway import OutsideBoundary
from utils import get_or_404

router = APIRouter()


def _subject(subject_id: int) -> dict:
    return get_or_404(store(), "subjects", subject_id, "Subject")


def _topic(subject_id: int, topic_id: int) -> dict:
    _subject(subject_id)
    topic = store().get("topics", topic_id)
    if not topic or topic["subject_id"] != subject_id:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic


# ─── Books Management ────────────────────────────────────────────────

@router.put("/{subject_id}/books/set-main-book", response_model=dict, dependencies=[Depends(require_parent)])
def set_main_book(subject_id: int, pdf_filename: str):
    _subject(subject_id)
    with write("books.set_main") as tx:
        for topic in tx.find("topics", subject_id=subject_id):
            tx.update("topics", topic["id"], {"is_core": topic["pdf_filename"] == pdf_filename})
    return {"message": "Main book updated"}


@router.put("/{subject_id}/books/set-book-offset", response_model=dict, dependencies=[Depends(require_parent)])
def set_book_offset(subject_id: int, pdf_filename: str, offset: int):
    _subject(subject_id)
    with write("books.set_offset") as tx:
        topics = tx.find("topics", subject_id=subject_id, pdf_filename=pdf_filename)
        for topic in topics:
            tx.update("topics", topic["id"], {"pdf_page_offset": offset})
    return {"message": "Book page offset updated", "updated_topics": len(topics)}


@router.delete("/{subject_id}/books", status_code=204, dependencies=[Depends(require_parent)])
def delete_book(subject_id: int, pdf_filename: str):
    _subject(subject_id)
    with write("books.delete") as tx:
        for topic in tx.find("topics", subject_id=subject_id, pdf_filename=pdf_filename):
            tx.delete("topics", topic["id"])
    return None


@router.get("/by-child/{child_id}", response_model=List[SubjectResponse], dependencies=[Depends(require_member)])
def list_subjects(child_id: int):
    get_or_404(store(), "children", child_id, "Child")
    return sorted(store().find("subjects", child_id=child_id), key=lambda s: s["name"])


@router.post("", response_model=SubjectResponse, status_code=201, dependencies=[Depends(require_parent)])
def create_subject(subject: SubjectCreate):
    get_or_404(store(), "children", subject.child_id, "Child")
    with write("subjects.create") as tx:
        return tx.insert("subjects", subject.model_dump())


@router.delete("/{subject_id}", status_code=204, dependencies=[Depends(require_parent)])
def delete_subject(subject_id: int):
    _subject(subject_id)
    with write("subjects.delete") as tx:
        tx.delete("subjects", subject_id)
    return None


@router.get("/{subject_id}", response_model=SubjectResponse, dependencies=[Depends(require_member)])
def get_subject(subject_id: int):
    return _subject(subject_id)


@router.put("/{subject_id}", response_model=SubjectResponse, dependencies=[Depends(require_parent)])
def update_subject(subject_id: int, updates: SubjectUpdate):
    _subject(subject_id)
    with write("subjects.update") as tx:
        return tx.update("subjects", subject_id, updates.model_dump(exclude_unset=True))


# ─── Topics ──────────────────────────────────────────────────────────

@router.get("/{subject_id}/topics", response_model=List[TopicResponse], dependencies=[Depends(require_member)])
def list_topics(subject_id: int):
    _subject(subject_id)
    return sorted(store().find("topics", subject_id=subject_id), key=lambda t: t["chapter_order"] or 0)


@router.post("/{subject_id}/generate-chapters", response_model=List[TopicResponse], dependencies=[Depends(require_parent)])
def generate_chapters(subject_id: int, count: int = Query(..., ge=1, le=100)):
    _subject(subject_id)
    with write("topics.generate") as tx:
        return [tx.insert("topics", {"subject_id": subject_id, "title": f"Chapter {i}", "page_start": i, "page_end": i,
                                     "complexity": 1, "chapter_order": i, "is_core": True})
                for i in range(1, count + 1)]


@router.put("/{subject_id}/topics/{topic_id}", response_model=TopicResponse, dependencies=[Depends(require_parent)])
def update_topic(subject_id: int, topic_id: int, updates: TopicUpdate):
    topic = _topic(subject_id, topic_id)
    changes = updates.model_dump(exclude_unset=True)
    completed = changes.pop("completed", None)
    topic.update(changes)
    if completed is True:
        mark_topic_completed(topic)
    elif completed is False:
        mark_topic_incomplete(topic)
    with write("topics.update") as tx:
        return tx.update("topics", topic_id, {**changes, "completed": topic["completed"],
                                              "completed_at": topic["completed_at"]})


@router.delete("/{subject_id}/topics/{topic_id}", status_code=204, dependencies=[Depends(require_parent)])
def delete_topic(subject_id: int, topic_id: int):
    _topic(subject_id, topic_id)
    with write("topics.delete") as tx:
        tx.delete("topics", topic_id)
    return None


# ─── Topic Completion ────────────────────────────────────────────────

def _complete_history(tx, topic_ids, recorded_at):
    """Preserve completed study history through today without protecting future assignments."""
    completed = {c["slot_id"] for c in tx.all("completions")}
    for slot in tx.all("scheduled_slots"):
        if slot["topic_id"] in topic_ids and slot["date"] <= date.today() and slot["id"] not in completed:
            tx.insert("completions", {"slot_id": slot["id"], "completed_at": recorded_at})


@router.post("/{subject_id}/topics/{topic_id}/toggle-complete", response_model=TopicResponse,
             dependencies=[Depends(require_member)])
def toggle_topic_complete(subject_id: int, topic_id: int):
    topic = _topic(subject_id, topic_id)
    recorded_at = datetime.now(timezone.utc).replace(microsecond=0)
    with write("topics.toggle_complete") as tx:
        if topic["completed"]:
            mark_topic_incomplete(topic)
            for slot in tx.find("scheduled_slots", topic_id=topic_id):
                for completion in tx.find("completions", slot_id=slot["id"]):
                    tx.delete("completions", completion["id"])
        else:
            mark_topic_completed(topic, recorded_at)
            _complete_history(tx, {topic_id}, recorded_at)
        return save_topic(tx, topic)


@router.post("/{subject_id}/topics/{topic_id}/complete-previous", dependencies=[Depends(require_parent)])
def complete_previous(subject_id: int, topic_id: int):
    target = _topic(subject_id, topic_id)
    recorded_at = datetime.now(timezone.utc).replace(microsecond=0)
    with write("topics.complete_previous") as tx:
        topics = [t for t in tx.find("topics", subject_id=subject_id)
                  if (t["chapter_order"] or 0) <= (target["chapter_order"] or 0)]
        for topic in topics:
            if not topic["completed"]:
                save_topic(tx, mark_topic_completed(topic, recorded_at))
        _complete_history(tx, {t["id"] for t in topics}, recorded_at)
    return {"message": "Updated previous topics"}


# ─── PDF Upload & AI Analysis ────────────────────────────────────────

def _create_topics(tx, subject_id: int, document: dict, analysis: dict, filename: str) -> AIAnalysisResult:
    is_core_for_new = not any(t["is_core"] for t in tx.find("topics", subject_id=subject_id))
    created = []
    for index, topic_data in enumerate(analysis["topics"]):
        created.append(tx.insert("topics", {
            "subject_id": subject_id, "document_id": document["id"], "title": topic_data["title"],
            "page_start": topic_data["page_start"], "page_end": topic_data["page_end"],
            "complexity": topic_data.get("complexity", 1), "language": analysis.get("language", "unknown"),
            "chapter_order": index, "pdf_filename": filename, "pdf_page_offset": 0, "is_core": is_core_for_new,
        }))
    return AIAnalysisResult(language=analysis.get("language", "unknown"), topics=created, pdf_filename=filename)


def _analyse(toc_text: str, page_count: int) -> dict:
    if not toc_text.strip():
        raise HTTPException(status_code=400, detail="No selectable text was found in the first 15 pages. "
                                                    "Scanned PDFs need OCR first.")
    try:
        return analyze_curriculum(toc_text, page_count)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {exc}") from exc


@router.post("/{subject_id}/documents", response_model=AIAnalysisResult, dependencies=[Depends(require_parent)])
async def upload_document(subject_id: int, file: UploadFile = File(...)):
    """Store a book in Drive ``Books`` (deduplicated by checksum) and create its topics."""
    _subject(subject_id)
    filename = (file.filename or "book.pdf").replace("/", "_").replace("\\", "_")
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    data = await file.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDFs are limited to 250 MiB.")
    try:
        page_count, toc_text = inspect_pdf(data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"This PDF could not be read: {exc}") from exc
    analysis = await run_in_threadpool(_analyse, toc_text, page_count)
    return await run_in_threadpool(_finish_upload, subject_id, data, filename, page_count, analysis)


def _finish_upload(subject_id, data, filename, page_count, analysis):
    with write("documents.upload", f"Added book {filename}") as tx:
        document = add_uploaded_document(tx, data, filename, page_count)
        return _create_topics(tx, subject_id, document, analysis, filename)


class DriveBookRequest(BaseModel):
    drive_file_id: str = Field(..., min_length=10, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")


@router.post("/{subject_id}/documents/from-drive", response_model=AIAnalysisResult,
             dependencies=[Depends(require_parent)])
def link_drive_document(subject_id: int, payload: DriveBookRequest):
    """Use a book already beneath the Homeschooling folder, referenced by Drive file ID."""
    _subject(subject_id)
    ctx = context()
    if ctx.drive is None:
        raise HTTPException(status_code=503, detail="Connect Google Drive first")
    try:
        metadata = ctx.drive.metadata(payload.drive_file_id)
        data = ctx.drive.download(payload.drive_file_id)
    except OutsideBoundary as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if metadata.get("mimeType") != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    sha = hashlib.sha256(data).hexdigest()
    ctx.store.blobs.put(data)
    page_count, toc_text = inspect_pdf(data)
    analysis = _analyse(toc_text, page_count)
    with write("documents.link", f"Linked Drive book {metadata['name']}") as tx:
        document = add_drive_document(tx, metadata, page_count, sha)
        return _create_topics(tx, subject_id, document, analysis, metadata["name"])
