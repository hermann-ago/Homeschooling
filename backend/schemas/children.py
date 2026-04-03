from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

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
