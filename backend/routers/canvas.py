import json
import logging
from datetime import date
from typing import List

from fastapi import APIRouter, HTTPException

from app_context import request_operation as write
from dependencies import context, store
from schemas import CanvasAIRequest, CanvasAIResponse, CanvasInsertCreate, CanvasInsertResponse, CanvasSlotResponse
from services import ai_enrichment
from storage import FileUnavailable, layout
from utils import completion_by_slot, get_or_404

logger = logging.getLogger(__name__)
router = APIRouter()


def _topic(topic_id: int, label: str = "Topic") -> dict:
    return get_or_404(store(), "topics", topic_id, label)


def _insert_to_response(ci: dict) -> dict:
    topic = store().get("topics", ci["insert_topic_id"])
    subject = store().get("subjects", topic["subject_id"]) if topic else None
    return {
        "id": ci["id"], "parent_topic_id": ci["parent_topic_id"], "insert_topic_id": ci["insert_topic_id"],
        "position": ci["position"] or 0,
        "insert_subject_name": subject["name"] if subject else None,
        "insert_topic_title": topic["title"] if topic else None,
        "insert_page_start": topic["page_start"] if topic else None,
        "insert_page_end": topic["page_end"] if topic else None,
        "insert_document_id": topic["document_id"] if topic else None,
        "insert_pdf_page_offset": (topic["pdf_page_offset"] or 0) if topic else 0,
    }


@router.get("/{child_id}/today", response_model=List[CanvasSlotResponse])
def get_today_canvas(child_id: int):
    """Today's scheduled slots enriched with canvas inserts."""
    get_or_404(store(), "children", child_id, "Child")
    today = date.today()
    completions = completion_by_slot(store())
    slots = sorted((s for s in store().find("scheduled_slots", child_id=child_id) if s["date"] == today),
                   key=lambda s: s["time_start"])
    result = []
    for slot in slots:
        topic = store().get("topics", slot["topic_id"]) if slot["topic_id"] else None
        subject = store().get("subjects", slot["subject_id"])
        inserts = []
        if slot["topic_id"]:
            inserts = [_insert_to_response(ci) for ci in
                       sorted(store().find("canvas_inserts", parent_topic_id=slot["topic_id"]),
                              key=lambda ci: ci["position"] or 0)]
        result.append(CanvasSlotResponse(
            id=slot["id"], subject_name=subject["name"] if subject else "Unknown",
            topic_title=topic["title"] if topic else None, time_start=slot["time_start"], time_end=slot["time_end"],
            page_from=slot["page_from"], page_to=slot["page_to"],
            document_id=topic["document_id"] if topic else None,
            pdf_page_offset=(topic["pdf_page_offset"] or 0) if topic else 0,
            is_completed=slot["id"] in completions, topic_id=slot["topic_id"], inserts=inserts,
        ))
    return result


@router.post("/insert", response_model=CanvasInsertResponse, status_code=201)
def create_insert(payload: CanvasInsertCreate):
    _topic(payload.parent_topic_id, "Parent topic")
    _topic(payload.insert_topic_id, "Insert topic")
    position = payload.position or len(store().find("canvas_inserts", parent_topic_id=payload.parent_topic_id))
    with write("canvas.insert") as tx:
        ci = tx.insert("canvas_inserts", {"parent_topic_id": payload.parent_topic_id,
                                          "insert_topic_id": payload.insert_topic_id, "position": position})
    return _insert_to_response(ci)


@router.delete("/insert/{insert_id}", status_code=204)
def delete_insert(insert_id: int):
    get_or_404(store(), "canvas_inserts", insert_id, "Canvas insert")
    with write("canvas.delete_insert") as tx:
        tx.delete("canvas_inserts", insert_id)
    return None


@router.get("/{child_id}/available-topics")
def get_available_topics(child_id: int):
    """All subjects & topics for a child (for the insert picker)."""
    get_or_404(store(), "children", child_id, "Child")
    result = []
    for s in sorted(store().find("subjects", child_id=child_id), key=lambda s: s["name"]):
        topics = sorted(store().find("topics", subject_id=s["id"]), key=lambda t: t["chapter_order"] or 0)
        result.append({"subject_id": s["id"], "subject_name": s["name"], "topics": [
            {"id": t["id"], "title": t["title"], "page_start": t["page_start"], "page_end": t["page_end"],
             "document_id": t["document_id"], "pdf_filename": t["pdf_filename"]} for t in topics]})
    return result


# ─── AI Enrichment Endpoints ────────────────────────────────────────────────

def _content(row: dict) -> str:
    try:
        return context().file_bytes(row["content_path"], row["content_sha256"]).decode("utf-8")
    except FileUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Saved enrichment cannot be opened: {exc}") from exc


def _response(row: dict, from_cache: bool) -> CanvasAIResponse:
    return CanvasAIResponse(id=row["id"], topic_id=row["topic_id"], page_start=row["page_start"],
                            page_end=row["page_end"], content_type=row["content_type"], content=_content(row),
                            created_at=row["created_at"], from_cache=from_cache)


@router.post("/ai-content/generate", response_model=CanvasAIResponse, status_code=200)
def generate_ai_content(payload: CanvasAIRequest):
    """Generate (or return cached) AI enrichment content for a canvas section.

    Cached rows (same topic, pages and content type) are returned without a
    Gemini call. New content is saved as a file in the Drive folder's Tutor
    Content and indexed in the enrichment table.
    """
    _topic(payload.topic_id)
    cached = store().first("enrichment", topic_id=payload.topic_id, page_start=payload.page_start,
                           page_end=payload.page_end, content_type=payload.content_type)
    if cached:
        logger.info("[AI Enrichment] Cache hit: topic=%d type=%s", payload.topic_id, payload.content_type)
        return _response(cached, True)
    if not payload.source_text or not payload.source_text.strip():
        raise HTTPException(status_code=400, detail="Page text is required when this AI result is not already cached.")
    try:
        raw_result = ai_enrichment.generate_content(content_type=payload.content_type,
                                                    text=payload.source_text.strip(),
                                                    language=payload.language or "en")
    except ValueError as exc:
        logger.error("[AI Enrichment] Generation error: %s", exc)
        raise HTTPException(status_code=502, detail=f"AI generation failed: {exc}")
    # quiz and terms → JSON string; audio and explain → plain text string
    content = json.dumps(raw_result, ensure_ascii=False) if isinstance(raw_result, (list, dict)) else str(raw_result)
    with write("enrichment.generate") as tx:
        name = f"enrichment-topic{payload.topic_id}-p{payload.page_start}-{payload.page_end}-{payload.content_type}.txt"
        folder = layout.for_topic(tx, payload.topic_id, layout.LESSON_CONTENT)
        path, sha = tx.add_blob(content.encode("utf-8"), folder, name, "text/plain")
        row = tx.insert("enrichment", {"topic_id": payload.topic_id, "page_start": payload.page_start,
                                       "page_end": payload.page_end, "content_type": payload.content_type,
                                       "content_path": path, "content_sha256": sha})
    return _response(row, False)


@router.get("/ai-content/{topic_id}", response_model=List[CanvasAIResponse])
def get_ai_content_for_topic(topic_id: int):
    """All cached AI enrichment rows for a topic (shows ⚡ badges in the canvas)."""
    _topic(topic_id)
    rows = sorted(store().find("enrichment", topic_id=topic_id), key=lambda r: r["content_type"])
    return [_response(r, True) for r in rows]
