from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, datetime, timezone
from database import get_db
from models import Subject, CurriculumTopic, Child, ScheduledSlot, Completion, Document
from schemas import (
    SubjectCreate, SubjectUpdate, SubjectResponse,
    TopicResponse, TopicUpdate, AIAnalysisResult, DocumentFinalizeRequest,
)
from services.ai_analyzer import analyze_curriculum
from auth import get_owned_child, require_family_user
from services.completion_tracking import mark_topic_completed, mark_topic_incomplete

router = APIRouter()


def _owned_subject(db: Session, subject_id: int, user_id: str) -> Subject | None:
    return (
        db.query(Subject)
        .join(Child, Subject.child_id == Child.id)
        .filter(Subject.id == subject_id, Child.owner_id == user_id)
        .first()
    )


# ─── Books Management ────────────────────────────────────────────────

@router.put("/{subject_id}/books/set-main-book", response_model=dict)
def set_main_book(subject_id: int, pdf_filename: str, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    subject = _owned_subject(db, subject_id, user_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    # Set all topics for this subject matching filename to True, others to False
    topics = db.query(CurriculumTopic).filter(CurriculumTopic.subject_id == subject_id).all()
    for topic in topics:
        topic.is_core = (topic.pdf_filename == pdf_filename)
        
    db.commit()
    return {"message": "Main book updated"}


@router.put("/{subject_id}/books/set-book-offset", response_model=dict)
def set_book_offset(subject_id: int, pdf_filename: str, offset: int, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    subject = _owned_subject(db, subject_id, user_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
        
    topics = db.query(CurriculumTopic).filter(
        CurriculumTopic.subject_id == subject_id,
        CurriculumTopic.pdf_filename == pdf_filename
    ).all()
    
    for topic in topics:
        topic.pdf_page_offset = offset
        
    db.commit()
    return {"message": "Book page offset updated", "updated_topics": len(topics)}


@router.delete("/{subject_id}/books", status_code=204)
def delete_book(subject_id: int, pdf_filename: str, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    subject = _owned_subject(db, subject_id, user_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
        
    topics = db.query(CurriculumTopic).filter(
        CurriculumTopic.subject_id == subject_id,
        CurriculumTopic.pdf_filename == pdf_filename
    ).all()
    
    for topic in topics:
        db.delete(topic)
        
    db.commit()
    return None



@router.get("/by-child/{child_id}", response_model=List[SubjectResponse])
def list_subjects(child_id: int, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    child = get_owned_child(db, child_id, user_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    return db.query(Subject).filter(Subject.child_id == child_id).order_by(Subject.name).all()


@router.post("", response_model=SubjectResponse, status_code=201)
def create_subject(subject: SubjectCreate, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    child = get_owned_child(db, subject.child_id, user_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    db_subject = Subject(**subject.model_dump())
    db.add(db_subject)
    db.commit()
    db.refresh(db_subject)
    return db_subject


@router.delete("/{subject_id}", status_code=204)
def delete_subject(subject_id: int, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    subject = _owned_subject(db, subject_id, user_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    db.delete(subject)
    db.commit()
    return None


@router.get("/{subject_id}", response_model=SubjectResponse)
def get_subject(subject_id: int, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    subject = _owned_subject(db, subject_id, user_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


@router.put("/{subject_id}", response_model=SubjectResponse)
def update_subject(subject_id: int, updates: SubjectUpdate, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    subject = _owned_subject(db, subject_id, user_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    for key, value in updates.model_dump(exclude_unset=True).items():
        setattr(subject, key, value)
    db.commit()
    db.refresh(subject)
    return subject





# ─── Topics ──────────────────────────────────────────────────────────

@router.get("/{subject_id}/topics", response_model=List[TopicResponse])
def list_topics(subject_id: int, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    subject = _owned_subject(db, subject_id, user_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return (
        db.query(CurriculumTopic)
        .filter(CurriculumTopic.subject_id == subject_id)
        .order_by(CurriculumTopic.chapter_order)
        .all()
    )



@router.post("/{subject_id}/generate-chapters", response_model=List[TopicResponse])
def generate_chapters(subject_id: int, count: int = Query(..., ge=1, le=100), user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    subject = _owned_subject(db, subject_id, user_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
        
    new_topics = []
    for i in range(1, count + 1):
        topic = CurriculumTopic(
            subject_id=subject_id,
            title=f"Chapter {i}",
            page_start=i,
            page_end=i,
            complexity=1,
            chapter_order=i,
            is_core=True
        )
        db.add(topic)
        new_topics.append(topic)
        
    db.commit()
    for t in new_topics:
        db.refresh(t)
    return new_topics


@router.put("/{subject_id}/topics/{topic_id}", response_model=TopicResponse)
def update_topic(subject_id: int, topic_id: int, updates: TopicUpdate, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    if not _owned_subject(db, subject_id, user_id):
        raise HTTPException(status_code=404, detail="Subject not found")
    topic = (
        db.query(CurriculumTopic)
        .filter(CurriculumTopic.id == topic_id, CurriculumTopic.subject_id == subject_id)
        .first()
    )
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    changes = updates.model_dump(exclude_unset=True)
    completed = changes.pop("completed", None)
    for key, value in changes.items():
        setattr(topic, key, value)
    if completed is True:
        mark_topic_completed(topic)
    elif completed is False:
        mark_topic_incomplete(topic)
    db.commit()
    db.refresh(topic)
    return topic


@router.delete("/{subject_id}/topics/{topic_id}", status_code=204)
def delete_topic(subject_id: int, topic_id: int, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    if not _owned_subject(db, subject_id, user_id):
        raise HTTPException(status_code=404, detail="Subject not found")
    topic = (
        db.query(CurriculumTopic)
        .filter(CurriculumTopic.id == topic_id, CurriculumTopic.subject_id == subject_id)
        .first()
    )
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    db.delete(topic)
    db.commit()
    return None


# ─── Topic Completion ────────────────────────────────────────────────

@router.post("/{subject_id}/topics/{topic_id}/toggle-complete", response_model=TopicResponse)
def toggle_topic_complete(subject_id: int, topic_id: int, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    if not _owned_subject(db, subject_id, user_id):
        raise HTTPException(status_code=404, detail="Subject not found")
    topic = (
        db.query(CurriculumTopic)
        .filter(CurriculumTopic.id == topic_id, CurriculumTopic.subject_id == subject_id)
        .first()
    )
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    if topic.completed:
        mark_topic_incomplete(topic)
    else:
        recorded_at = datetime.now(timezone.utc)
        mark_topic_completed(topic, recorded_at)

    if topic.completed:
        # Preserve completed study history without protecting future assignments.
        slots = db.query(ScheduledSlot).filter(
            ScheduledSlot.topic_id == topic_id,
            ScheduledSlot.date <= date.today(),
        ).all()
        for slot in slots:
            if not db.query(Completion).filter(Completion.slot_id == slot.id).first():
                db.add(Completion(slot_id=slot.id, completed_at=datetime.utcnow()))
    else:
        # Remove completions for this topic's slots
        slots = db.query(ScheduledSlot).filter(ScheduledSlot.topic_id == topic_id).all()
        for slot in slots:
            db.query(Completion).filter(Completion.slot_id == slot.id).delete()

    db.commit()
    db.refresh(topic)
    return topic


@router.post("/{subject_id}/topics/{topic_id}/complete-previous")
def complete_previous(subject_id: int, topic_id: int, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    if not _owned_subject(db, subject_id, user_id):
        raise HTTPException(status_code=404, detail="Subject not found")
    target_topic = (
        db.query(CurriculumTopic)
        .filter(CurriculumTopic.id == topic_id, CurriculumTopic.subject_id == subject_id)
        .first()
    )
    if not target_topic:
        raise HTTPException(status_code=404, detail="Topic not found")
        
    topics_to_complete = db.query(CurriculumTopic).filter(
        CurriculumTopic.subject_id == subject_id,
        CurriculumTopic.chapter_order <= target_topic.chapter_order
    ).all()

    recorded_at = datetime.now(timezone.utc)
    for topic in topics_to_complete:
        if not topic.completed:
            mark_topic_completed(topic, recorded_at)

    # Sync completed calendar history through today only.
    topic_ids = [t.id for t in topics_to_complete]
    slots = db.query(ScheduledSlot).filter(
        ScheduledSlot.topic_id.in_(topic_ids),
        ScheduledSlot.date <= date.today(),
    ).all()
    
    for slot in slots:
        if not db.query(Completion).filter(Completion.slot_id == slot.id).first():
            db.add(Completion(slot_id=slot.id, completed_at=datetime.utcnow()))
    
    db.commit()
    return {"message": "Updated previous topics"}


# ─── PDF Upload & AI Analysis ────────────────────────────────────────

@router.post("/{subject_id}/documents", response_model=AIAnalysisResult)
def finalize_document(
    subject_id: int,
    payload: DocumentFinalizeRequest,
    user_id: str = Depends(require_family_user),
    db: Session = Depends(get_db),
):
    """Persist a browser-uploaded Blob document and create its curriculum topics."""
    subject = _owned_subject(db, subject_id, user_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    if not payload.original_filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    if not payload.toc_text.strip():
        raise HTTPException(status_code=400, detail="No text could be extracted from the PDF")

    try:
        analysis = analyze_curriculum(payload.toc_text, payload.page_count)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {exc}") from exc

    document = Document(
        owner_id=user_id,
        blob_path=payload.blob_path,
        original_filename=payload.original_filename,
        size_bytes=payload.size_bytes,
        page_count=payload.page_count,
        sha256=payload.sha256,
    )
    db.add(document)
    db.flush()

    is_core_for_new = db.query(CurriculumTopic).filter(
        CurriculumTopic.subject_id == subject_id,
        CurriculumTopic.is_core.is_(True),
    ).first() is None
    created = []
    for index, topic_data in enumerate(analysis["topics"]):
        topic = CurriculumTopic(
            subject_id=subject_id,
            document_id=document.id,
            title=topic_data["title"],
            page_start=topic_data["page_start"],
            page_end=topic_data["page_end"],
            complexity=topic_data.get("complexity", 1),
            language=analysis.get("language", "unknown"),
            chapter_order=index,
            pdf_filename=payload.original_filename,
            pdf_page_offset=0,
            is_core=is_core_for_new,
        )
        db.add(topic)
        created.append(topic)
    db.commit()

    return AIAnalysisResult(
        language=analysis.get("language", "unknown"),
        topics=created,
        pdf_filename=payload.original_filename,
    )
