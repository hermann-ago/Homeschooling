from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

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
    document_id: Optional[int] = None
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

class AIAnalysisResult(BaseModel):
    language: str
    topics: List[TopicBase]
    pdf_filename: str


class DocumentFinalizeRequest(BaseModel):
    blob_path: str = Field(..., min_length=5, max_length=600)
    original_filename: str = Field(..., min_length=1, max_length=255)
    size_bytes: int = Field(..., gt=0, le=262_144_000)
    page_count: int = Field(..., gt=0, le=20_000)
    toc_text: str = Field(..., min_length=1, max_length=500_000)
    sha256: Optional[str] = Field(None, pattern=r"^[a-fA-F0-9]{64}$")
