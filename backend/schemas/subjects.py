from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional

# Monday = 0 … Sunday = 6. None: take turns by slot_type; []: paused, not planned.
Weekdays = Optional[list[int]]
# 'choice': the tutor's own added questions are true/false or single choice.
ExtraQuestions = Literal['open', 'choice']


def _weekdays(v):
    if v is not None and any(not isinstance(d, int) or not 0 <= d <= 6 for d in v):
        raise ValueError('Weekdays are numbers from 0 (Monday) to 6 (Sunday)')
    return sorted(set(v)) if v is not None else None
from datetime import date, datetime

class SubjectBase(BaseModel):
    name: str = Field(..., max_length=100)
    weight: float = Field(default=1.0, ge=0)
    slot_type: str = Field(default="A", max_length=1)
    end_date: Optional[date] = None
    grade: Optional[str] = Field(None, max_length=20)  # this subject's grade; empty: no grade level
    weekdays: Weekdays = None
    extra_questions: Optional[ExtraQuestions] = None

    @field_validator('slot_type', mode='before')
    @classmethod
    def set_default_slot(cls, v):
        if v not in ['A', 'B', 'C']:
            return 'A'
        return v

    _check_weekdays = field_validator('weekdays')(_weekdays)

class SubjectCreate(SubjectBase):
    child_id: int

class SubjectUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    weight: Optional[float] = Field(None, ge=0)
    slot_type: Optional[str] = Field(None, max_length=1)
    end_date: Optional[date] = None
    grade: Optional[str] = Field(None, max_length=20)
    weekdays: Weekdays = None
    extra_questions: Optional[ExtraQuestions] = None

    _check_weekdays = field_validator('weekdays')(_weekdays)

class SubjectResponse(SubjectBase):
    id: int
    child_id: int
    purpose: Optional[str] = None
    library_book_id: Optional[str] = None
    folder: Optional[str] = None  # Kid/Grade/Subject folder in the Homeschooling Drive folder
    video_pages: Optional[list[str]] = None  # the publisher's video lesson pages
    created_at: datetime
    class Config:
        from_attributes = True
