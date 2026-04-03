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
