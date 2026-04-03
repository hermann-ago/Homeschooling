from pydantic import BaseModel
from typing import List, Optional
from datetime import date

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
