from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime

class CanvasInsertCreate(BaseModel):
    parent_topic_id: int
    insert_topic_id: int
    position: int = 0

class CanvasInsertResponse(BaseModel):
    id: int
    parent_topic_id: int
    insert_topic_id: int
    position: int
    # Enriched fields for the frontend
    insert_subject_name: Optional[str] = None
    insert_topic_title: Optional[str] = None
    insert_page_start: Optional[int] = None
    insert_page_end: Optional[int] = None
    insert_pdf_path: Optional[str] = None
    insert_pdf_page_offset: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True)

class CanvasSlotResponse(BaseModel):
    """A scheduled slot enriched with its canvas inserts."""
    id: int
    subject_name: str
    topic_title: Optional[str] = None
    time_start: str
    time_end: str
    page_from: Optional[int] = None
    page_to: Optional[int] = None
    pdf_path: Optional[str] = None
    pdf_page_offset: Optional[int] = 0
    is_completed: bool = False
    topic_id: Optional[int] = None
    inserts: List[CanvasInsertResponse] = []

    model_config = ConfigDict(from_attributes=True)

class CanvasAIRequest(BaseModel):
    """
    Request body for generating (or fetching from cache) AI enrichment content.
    """
    topic_id: int
    page_start: int
    page_end: int
    content_type: str = Field(..., pattern=r"^(quiz|audio|terms|explain)$")
    pdf_path: Optional[str] = None
    pdf_page_offset: int = 0
    language: str = Field(default="en", max_length=10)

class CanvasAIResponse(BaseModel):
    """
    Response for a single AI enrichment content item.
    """
    id: int
    topic_id: int
    page_start: int
    page_end: int
    content_type: str
    content: str          # JSON string for quiz/terms; plain text for audio/explain
    created_at: datetime
    from_cache: bool = False

    model_config = ConfigDict(from_attributes=True)
