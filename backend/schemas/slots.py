from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime

class TimeWindowBase(BaseModel):
    weekday: int = Field(..., ge=0, le=6)
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")

class TimeWindowCreate(TimeWindowBase):
    child_id: int

class TimeWindowResponse(TimeWindowBase):
    id: int
    child_id: int
    class Config:
        from_attributes = True

class BlockedDayBase(BaseModel):
    date: date
    block_type: str = Field(..., pattern=r"^(holiday|sick|custom)$")
    note: Optional[str] = Field(None, max_length=255)

class BlockedDayCreate(BlockedDayBase):
    child_id: Optional[int] = None

class BlockedDayResponse(BlockedDayBase):
    id: int
    child_id: Optional[int]
    created_at: datetime
    class Config:
        from_attributes = True

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
    document_id: Optional[int] = None
    pdf_page_offset: Optional[int] = 0
    is_completed: bool = False
    completed_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class CompletionCreate(BaseModel):
    slot_id: int

class CompletionResponse(BaseModel):
    id: int
    slot_id: int
    completed_at: datetime
    class Config:
        from_attributes = True

class ScheduleWarning(BaseModel):
    message: str
    suggestion: Optional[str] = None

class ScheduleResult(BaseModel):
    slots_created: int
    warnings: List[ScheduleWarning] = []
