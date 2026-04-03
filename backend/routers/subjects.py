from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import uuid

from database import get_db
from models import Subject, CurriculumTopic, Child
from schemas import (
    SubjectCreate, SubjectUpdate, SubjectResponse,
    TopicResponse, TopicUpdate, AIAnalysisResult,
)
from services.pdf_parser import extract_text_from_pdf
from services.ai_analyzer import analyze_curriculum

router = APIRouter()


# ─── Books Management ────────────────────────────────────────────────

@router.put("/{subject_id}/books/set-main-book", response_model=dict)
def set_main_book(subject_id: int, pdf_filename: str, db: Session = Depends(get_db)):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    # Set all topics for this subject matching filename to True, others to False
    topics = db.query(CurriculumTopic).filter(CurriculumTopic.subject_id == subject_id).all()
    for topic in topics:
        topic.is_core = (topic.pdf_filename == pdf_filename)
        
    db.commit()
    return {"message": "Main book updated"}


@router.put("/{subject_id}/books/set-book-offset", response_model=dict)
def set_book_offset(subject_id: int, pdf_filename: str, offset: int, db: Session = Depends(get_db)):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
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
def delete_book(subject_id: int, pdf_filename: str, db: Session = Depends(get_db)):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
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
def list_subjects(child_id: int, db: Session = Depends(get_db)):
    child = db.query(Child).filter(Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    return db.query(Subject).filter(Subject.child_id == child_id).order_by(Subject.name).all()


@router.post("/", response_model=SubjectResponse, status_code=201)
def create_subject(subject: SubjectCreate, db: Session = Depends(get_db)):
    child = db.query(Child).filter(Child.id == subject.child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    db_subject = Subject(**subject.model_dump())
    db.add(db_subject)
    db.commit()
    db.refresh(db_subject)
    return db_subject


@router.delete("/{subject_id}", status_code=204)
def delete_subject(subject_id: int, db: Session = Depends(get_db)):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    db.delete(subject)
    db.commit()
    return None


@router.get("/{subject_id}", response_model=SubjectResponse)
def get_subject(subject_id: int, db: Session = Depends(get_db)):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


@router.put("/{subject_id}", response_model=SubjectResponse)
def update_subject(subject_id: int, updates: SubjectUpdate, db: Session = Depends(get_db)):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    for key, value in updates.model_dump(exclude_unset=True).items():
        setattr(subject, key, value)
    db.commit()
    db.refresh(subject)
    return subject





# ─── Topics ──────────────────────────────────────────────────────────

@router.get("/{subject_id}/topics", response_model=List[TopicResponse])
def list_topics(subject_id: int, db: Session = Depends(get_db)):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return (
        db.query(CurriculumTopic)
        .filter(CurriculumTopic.subject_id == subject_id)
        .order_by(CurriculumTopic.chapter_order)
        .all()
    )



@router.post("/{subject_id}/generate-chapters", response_model=List[TopicResponse])
def generate_chapters(subject_id: int, count: int = Query(..., ge=1, le=100), db: Session = Depends(get_db)):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
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
def update_topic(subject_id: int, topic_id: int, updates: TopicUpdate, db: Session = Depends(get_db)):
    topic = (
        db.query(CurriculumTopic)
        .filter(CurriculumTopic.id == topic_id, CurriculumTopic.subject_id == subject_id)
        .first()
    )
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    for key, value in updates.model_dump(exclude_unset=True).items():
        setattr(topic, key, value)
    db.commit()
    db.refresh(topic)
    return topic


@router.delete("/{subject_id}/topics/{topic_id}", status_code=204)
def delete_topic(subject_id: int, topic_id: int, db: Session = Depends(get_db)):
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
def toggle_topic_complete(subject_id: int, topic_id: int, db: Session = Depends(get_db)):
    topic = (
        db.query(CurriculumTopic)
        .filter(CurriculumTopic.id == topic_id, CurriculumTopic.subject_id == subject_id)
        .first()
    )
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    topic.completed = not topic.completed
    db.commit()
    db.refresh(topic)
    return topic


@router.post("/{subject_id}/topics/{topic_id}/complete-previous")
def complete_previous(subject_id: int, topic_id: int, db: Session = Depends(get_db)):
    target_topic = (
        db.query(CurriculumTopic)
        .filter(CurriculumTopic.id == topic_id, CurriculumTopic.subject_id == subject_id)
        .first()
    )
    if not target_topic:
        raise HTTPException(status_code=404, detail="Topic not found")
        
    db.query(CurriculumTopic).filter(
        CurriculumTopic.subject_id == subject_id,
        CurriculumTopic.chapter_order <= target_topic.chapter_order
    ).update({"completed": True})
    
    db.commit()
    return {"message": "Updated previous topics"}


# ─── PDF Upload & AI Analysis ────────────────────────────────────────

@router.post("/{subject_id}/upload-pdf", response_model=AIAnalysisResult)
async def upload_pdf(
    subject_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Read file bytes
    file_bytes = await file.read()

    # Save PDF to disk
    upload_dir = os.path.join("uploads", str(subject_id))
    os.makedirs(upload_dir, exist_ok=True)
    
    # Generate a safe, unique filename
    safe_filename = f"{uuid.uuid4().hex}_{file.filename}"
    pdf_path = os.path.join(upload_dir, safe_filename)
    
    with open(pdf_path, "wb") as f:
        f.write(file_bytes)

    # Extract text using pdfplumber
    try:
        text, page_count = extract_text_from_pdf(file_bytes)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {str(e)}")

    if not text.strip():
        raise HTTPException(status_code=400, detail="No text could be extracted from the PDF")

    # Send to Gemini for analysis
    try:
        analysis = analyze_curriculum(text, page_count)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {str(e)}")

    # Check if this subject already has a core book
    has_core = db.query(CurriculumTopic).filter(
        CurriculumTopic.subject_id == subject_id, 
        CurriculumTopic.is_core == True
    ).first() is not None
    is_core_for_new = not has_core

    # Store topics in database
    for i, topic_data in enumerate(analysis["topics"]):
        topic = CurriculumTopic(
            subject_id=subject_id,
            title=topic_data["title"],
            page_start=topic_data["page_start"],
            page_end=topic_data["page_end"],
            complexity=topic_data.get("complexity", 1),
            language=analysis.get("language", "unknown"),
            chapter_order=i,
            pdf_filename=file.filename,
            pdf_path=pdf_path.replace("\\", "/"),  # store forward slashes for cross-platform ease
            pdf_page_offset=0,
            is_core=is_core_for_new,
        )
        db.add(topic)

    db.commit()

    return AIAnalysisResult(
        language=analysis.get("language", "unknown"),
        topics=[
            {
                "title": t["title"],
                "page_start": t["page_start"],
                "page_end": t["page_end"],
                "complexity": t.get("complexity", 1),
                "language": analysis.get("language", "unknown"),
                "chapter_order": i,
                "pdf_filename": file.filename,
                "pdf_path": pdf_path.replace("\\", "/"),
                "pdf_page_offset": 0,
                "is_core": is_core_for_new,
            }
            for i, t in enumerate(analysis["topics"])
        ],
        pdf_filename=file.filename,
        total_pages=page_count,
    )



