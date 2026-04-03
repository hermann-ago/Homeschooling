from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import date, datetime

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
