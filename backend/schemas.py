from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List
from datetime import date, datetime


# ─── Children ────────────────────────────────────────────────────────
class ChildBase(BaseModel):
    name: str = Field(..., max_length=100)
    nickname: Optional[str] = Field(None, max_length=50)
    color: str = Field(default="#6B9E8A", max_length=7)
    grade_year: Optional[str] = Field(None, max_length=20)

class ChildCreate(ChildBase):
    pass

class ChildUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    nickname: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=7)
    grade_year: Optional[str] = Field(None, max_length=20)

class ChildResponse(ChildBase):
    id: int
    created_at: datetime
    class Config:
        from_attributes = True


# ─── Subjects ────────────────────────────────────────────────────────
class SubjectBase(BaseModel):
    name: str = Field(..., max_length=100)
    weight: float = Field(default=1.0, ge=0)
    slot_type: str = Field(default="A", max_length=1)
    end_date: Optional[date] = None

    @field_validator('slot_type', mode='before')
    @classmethod
    def set_default_slot(cls, v):
        if v not in ['A', 'B', 'C']:
            return 'A'
        return v

class SubjectCreate(SubjectBase):
    child_id: int

class SubjectUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    weight: Optional[float] = Field(None, ge=0)
    slot_type: Optional[str] = Field(None, max_length=1)
    end_date: Optional[date] = None

class SubjectResponse(SubjectBase):
    id: int
    child_id: int
    created_at: datetime
    class Config:
        from_attributes = True


# ─── Curriculum Topics ──────────────────────────────────────────────
class TopicBase(BaseModel):
    title: str = Field(..., max_length=300)
    page_start: int = Field(..., ge=0)
    page_end: int = Field(..., ge=0)
    complexity: int = Field(default=1, ge=1, le=3)
    completed: bool = False
    language: Optional[str] = Field(None, max_length=10)
    chapter_order: int = Field(default=0)
    pdf_filename: Optional[str] = None
    pdf_path: Optional[str] = None
    pdf_page_offset: int = Field(default=0)
    is_core: bool = True

class TopicCreate(TopicBase):
    subject_id: int

class TopicUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=300)
    page_start: Optional[int] = Field(None, ge=0)
    page_end: Optional[int] = Field(None, ge=0)
    complexity: Optional[int] = Field(None, ge=1, le=3)
    completed: Optional[bool] = None
    chapter_order: Optional[int] = None

class TopicResponse(TopicBase):
    id: int
    subject_id: int
    created_at: datetime
    class Config:
        from_attributes = True

class TopicListUpdate(BaseModel):
    topics: List[TopicUpdate]


# ─── Time Windows ───────────────────────────────────────────────────
class TimeWindowBase(BaseModel):
    weekday: int = Field(..., ge=0, le=6)  # 0=Monday, 6=Sunday
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")

class TimeWindowCreate(TimeWindowBase):
    child_id: int

class TimeWindowResponse(TimeWindowBase):
    id: int
    child_id: int
    class Config:
        from_attributes = True


# ─── Blocked Days ───────────────────────────────────────────────────
class BlockedDayBase(BaseModel):
    date: date
    block_type: str = Field(..., pattern=r"^(holiday|sick|custom)$")
    note: Optional[str] = Field(None, max_length=255)

class BlockedDayCreate(BlockedDayBase):
    child_id: Optional[int] = None  # None = applies to all children

class BlockedDayResponse(BlockedDayBase):
    id: int
    child_id: Optional[int]
    created_at: datetime
    class Config:
        from_attributes = True


# ─── Scheduled Slots ────────────────────────────────────────────────
class ScheduledSlotResponse(BaseModel):
    id: int
    child_id: int
    subject_id: int
    topic_id: Optional[int]
    date: date
    time_start: str
    time_end: str
    page_from: Optional[int]
    page_to: Optional[int]
    subject_name: Optional[str] = None
    topic_title: Optional[str] = None
    pdf_path: Optional[str] = None
    pdf_page_offset: Optional[int] = 0
    is_completed: bool = False
    completed_at: Optional[datetime] = None
    class Config:
        from_attributes = True


# ─── Completions ────────────────────────────────────────────────────
class CompletionCreate(BaseModel):
    slot_id: int

class CompletionResponse(BaseModel):
    id: int
    slot_id: int
    completed_at: datetime
    class Config:
        from_attributes = True


# ─── Progress ───────────────────────────────────────────────────────
class SubjectProgress(BaseModel):
    subject_id: int
    subject_name: str
    total_pages: int
    completed_pages: int
    progress_percent: float
    status: str  # 'on_track', 'behind', 'at_risk'
    projected_finish_date: Optional[date] = None

class ChildProgress(BaseModel):
    child_id: int
    child_name: str
    child_color: str
    overall_progress: float
    overall_status: str
    subjects: List[SubjectProgress]

class FamilyProgress(BaseModel):
    children: List[ChildProgress]


# ─── Schedule Warnings ──────────────────────────────────────────────
class ScheduleWarning(BaseModel):
    message: str
    suggestion: Optional[str] = None

class ScheduleResult(BaseModel):
    slots_created: int
    warnings: List[ScheduleWarning] = []


# ─── School Year Settings ───────────────────────────────────────────
class SchoolYearSettings(BaseModel):
    start_date: date
    end_date: date


# ─── AI Analysis ─────────────────────────────────────────────────────
class AIAnalysisResult(BaseModel):
    language: str
    topics: List[TopicBase]
    pdf_filename: str


# ─── Canvas Inserts ──────────────────────────────────────────────────
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


# ─── Canvas AI Enrichment (Phase 2) ─────────────────────────────────────────

class CanvasAIRequest(BaseModel):
    """
    Request body for generating (or fetching from cache) AI enrichment content.

    Fields:
        topic_id:     The CurriculumTopic this content belongs to.
        page_start:   Logical (TOC) start page of the section.
        page_end:     Logical (TOC) end page of the section.
        content_type: One of 'quiz', 'audio', 'terms', 'explain'.
        pdf_path:     Relative path to the stored PDF (e.g. 'uploads/book.pdf').
        pdf_page_offset: Offset stored on the topic; maps TOC pages → physical pages.
        language:     'pt' or 'en'.  Defaults to 'en'.
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

    Fields:
        content:    Raw JSON string for 'quiz' and 'terms'; plain text for 'audio'/'explain'.
        from_cache: True if the content was returned from the DB cache (no Gemini call made).
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

