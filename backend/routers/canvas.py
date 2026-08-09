from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import date
import json
import logging

from database import get_db
from models import (
    ScheduledSlot, Completion, Child, CurriculumTopic,
    CanvasInsert, Subject, CanvasAIContent
)
from schemas import (
    CanvasSlotResponse, CanvasInsertCreate, CanvasInsertResponse,
    CanvasAIRequest, CanvasAIResponse
)
from services import ai_enrichment
from auth import get_owned_child, require_family_user

logger = logging.getLogger(__name__)

router = APIRouter()


def _owned_topic(db: Session, topic_id: int, user_id: str) -> CurriculumTopic | None:
    return (
        db.query(CurriculumTopic)
        .join(Subject, CurriculumTopic.subject_id == Subject.id)
        .join(Child, Subject.child_id == Child.id)
        .filter(CurriculumTopic.id == topic_id, Child.owner_id == user_id)
        .first()
    )


def _insert_to_response(ci: CanvasInsert) -> dict:
    """Convert a CanvasInsert ORM to a response dict with enriched fields."""
    topic = ci.insert_topic
    return {
        "id": ci.id,
        "parent_topic_id": ci.parent_topic_id,
        "insert_topic_id": ci.insert_topic_id,
        "position": ci.position,
        "insert_subject_name": topic.subject.name if topic and topic.subject else None,
        "insert_topic_title": topic.title if topic else None,
        "insert_page_start": topic.page_start if topic else None,
        "insert_page_end": topic.page_end if topic else None,
        "insert_pdf_path": topic.pdf_path if topic else None,
        "insert_document_id": topic.document_id if topic else None,
        "insert_pdf_page_offset": topic.pdf_page_offset if topic else 0,
    }


@router.get("/{child_id}/today", response_model=List[CanvasSlotResponse])
def get_today_canvas(child_id: int, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    """Get today's scheduled slots enriched with canvas inserts."""
    child = get_owned_child(db, child_id, user_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    today = date.today()
    slots = (
        db.query(ScheduledSlot)
        .filter(ScheduledSlot.child_id == child_id, ScheduledSlot.date == today)
        .order_by(ScheduledSlot.time_start)
        .all()
    )

    result = []
    for slot in slots:
        # Gather inserts for this slot's topic
        inserts = []
        if slot.topic_id:
            canvas_inserts = (
                db.query(CanvasInsert)
                .filter(CanvasInsert.parent_topic_id == slot.topic_id)
                .order_by(CanvasInsert.position)
                .all()
            )
            inserts = [_insert_to_response(ci) for ci in canvas_inserts]

        result.append(CanvasSlotResponse(
            id=slot.id,
            subject_name=slot.subject.name if slot.subject else "Unknown",
            topic_title=slot.topic.title if slot.topic else None,
            time_start=slot.time_start,
            time_end=slot.time_end,
            page_from=slot.page_from,
            page_to=slot.page_to,
            pdf_path=slot.topic.pdf_path if slot.topic else None,
            document_id=slot.topic.document_id if slot.topic else None,
            pdf_page_offset=slot.topic.pdf_page_offset if slot.topic else 0,
            is_completed=slot.completion is not None,
            topic_id=slot.topic_id,
            inserts=inserts,
        ))

    return result


@router.post("/insert", response_model=CanvasInsertResponse, status_code=201)
def create_insert(payload: CanvasInsertCreate, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    """Create a cross-book insert link."""
    # Validate both topics exist
    parent = _owned_topic(db, payload.parent_topic_id, user_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent topic not found")

    insert_topic = _owned_topic(db, payload.insert_topic_id, user_id)
    if not insert_topic:
        raise HTTPException(status_code=404, detail="Insert topic not found")

    # Auto-calculate position if not provided
    if payload.position == 0:
        max_pos = (
            db.query(CanvasInsert)
            .filter(CanvasInsert.parent_topic_id == payload.parent_topic_id)
            .count()
        )
        payload.position = max_pos

    ci = CanvasInsert(
        parent_topic_id=payload.parent_topic_id,
        insert_topic_id=payload.insert_topic_id,
        position=payload.position,
    )
    db.add(ci)
    db.commit()
    db.refresh(ci)

    return _insert_to_response(ci)


@router.delete("/insert/{insert_id}", status_code=204)
def delete_insert(insert_id: int, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    """Remove a canvas insert."""
    ci = db.query(CanvasInsert).filter(CanvasInsert.id == insert_id).first()
    if not ci:
        raise HTTPException(status_code=404, detail="Canvas insert not found")
    if not _owned_topic(db, ci.parent_topic_id, user_id):
        raise HTTPException(status_code=404, detail="Canvas insert not found")
    db.delete(ci)
    db.commit()
    return None


@router.get("/{child_id}/available-topics")
def get_available_topics(child_id: int, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    """List all subjects & topics for a child (for the insert picker)."""
    if not get_owned_child(db, child_id, user_id):
        raise HTTPException(status_code=404, detail="Child not found")
    subjects = (
        db.query(Subject)
        .filter(Subject.child_id == child_id)
        .order_by(Subject.name)
        .all()
    )

    result = []
    for s in subjects:
        topics = (
            db.query(CurriculumTopic)
            .filter(CurriculumTopic.subject_id == s.id)
            .order_by(CurriculumTopic.chapter_order)
            .all()
        )
        result.append({
            "subject_id": s.id,
            "subject_name": s.name,
            "topics": [
                {
                    "id": t.id,
                    "title": t.title,
                    "page_start": t.page_start,
                    "page_end": t.page_end,
                    "pdf_path": t.pdf_path,
                    "document_id": t.document_id,
                    "pdf_filename": t.pdf_filename,
                }
                for t in topics
            ]
        })

    return result


# ─── AI Enrichment Endpoints (Phase 2) ───────────────────────────────────────

@router.post("/ai-content/generate", response_model=CanvasAIResponse, status_code=200)
def generate_ai_content(payload: CanvasAIRequest, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    """
    Generate (or return cached) AI enrichment content for a canvas section.

    Flow:
      1. Check if an identical row already exists in canvas_ai_content
         (same topic_id + page_start + page_end + content_type).
      2. If found → return it with from_cache=True (no Gemini call).
      3. If not found → extract PDF text → call the appropriate AI generator
         → save to DB → return with from_cache=False.

    HTTP 400: Missing or invalid pdf_path.
    HTTP 404: Topic not found.
    HTTP 500: Gemini API error or PDF extraction problem.
    """
    # Validate the topic exists
    topic = _owned_topic(db, payload.topic_id, user_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    # ── 1. Check cache ────────────────────────────────────────────────────────
    cached = (
        db.query(CanvasAIContent)
        .filter(
            CanvasAIContent.topic_id == payload.topic_id,
            CanvasAIContent.page_start == payload.page_start,
            CanvasAIContent.page_end == payload.page_end,
            CanvasAIContent.content_type == payload.content_type,
        )
        .first()
    )
    if cached:
        logger.info(
            "[AI Enrichment] Cache hit: topic=%d type=%s pages=%d-%d",
            payload.topic_id, payload.content_type, payload.page_start, payload.page_end
        )
        return CanvasAIResponse(
            id=cached.id,
            topic_id=cached.topic_id,
            page_start=cached.page_start,
            page_end=cached.page_end,
            content_type=cached.content_type,
            content=cached.content,
            created_at=cached.created_at,
            from_cache=True,
        )

    # ── 2. Extract PDF text ───────────────────────────────────────────────────
    if not payload.source_text or not payload.source_text.strip():
        raise HTTPException(
            status_code=400,
            detail="Page text is required when this AI result is not already cached."
        )
    page_text = payload.source_text.strip()

    # ── 3. Generate via Gemini ────────────────────────────────────────────────
    try:
        raw_result = ai_enrichment.generate_content(
            content_type=payload.content_type,
            text=page_text,
            language=payload.language or "en",
        )
    except ValueError as exc:
        logger.error("[AI Enrichment] Generation error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"AI generation failed: {exc}"
        )

    # ── 4. Serialize and save to DB ───────────────────────────────────────────
    # quiz and terms → JSON string; audio and explain → plain text string
    if isinstance(raw_result, (list, dict)):
        content_str = json.dumps(raw_result, ensure_ascii=False)
    else:
        content_str = str(raw_result)

    new_row = CanvasAIContent(
        topic_id=payload.topic_id,
        page_start=payload.page_start,
        page_end=payload.page_end,
        content_type=payload.content_type,
        content=content_str,
    )
    db.add(new_row)
    db.commit()
    db.refresh(new_row)

    logger.info(
        "[AI Enrichment] Generated & cached: topic=%d type=%s pages=%d-%d (id=%d)",
        payload.topic_id, payload.content_type,
        payload.page_start, payload.page_end, new_row.id
    )

    return CanvasAIResponse(
        id=new_row.id,
        topic_id=new_row.topic_id,
        page_start=new_row.page_start,
        page_end=new_row.page_end,
        content_type=new_row.content_type,
        content=new_row.content,
        created_at=new_row.created_at,
        from_cache=False,
    )


@router.get("/ai-content/{topic_id}", response_model=List[CanvasAIResponse])
def get_ai_content_for_topic(topic_id: int, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    """
    Return all cached AI enrichment rows for a given topic.

    The frontend uses this to show ⚡ badges on tools that are already cached,
    so the child knows which tools are instant vs which need generation time.
    """
    if not _owned_topic(db, topic_id, user_id):
        raise HTTPException(status_code=404, detail="Topic not found")
    rows = (
        db.query(CanvasAIContent)
        .filter(CanvasAIContent.topic_id == topic_id)
        .order_by(CanvasAIContent.content_type)
        .all()
    )
    return [
        CanvasAIResponse(
            id=r.id,
            topic_id=r.topic_id,
            page_start=r.page_start,
            page_end=r.page_end,
            content_type=r.content_type,
            content=r.content,
            created_at=r.created_at,
            from_cache=True,  # everything returned here is, by definition, cached
        )
        for r in rows
    ]
