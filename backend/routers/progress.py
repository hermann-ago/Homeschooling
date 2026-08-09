from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import date, timedelta

from database import get_db
from models import Child, Subject, CurriculumTopic, ScheduledSlot, Completion
from schemas import ChildProgress, SubjectProgress, FamilyProgress
from utils import get_setting
from auth import get_owned_child, require_family_user

router = APIRouter()


def _calculate_subject_progress(
    subject: Subject,
    db: Session,
    school_year_end: date,
    owner_id: str,
) -> SubjectProgress:
    """Calculate progress for a single subject."""
    topics = db.query(CurriculumTopic).filter(
        CurriculumTopic.subject_id == subject.id,
        CurriculumTopic.is_core == True
    ).all()

    if not topics:
        return SubjectProgress(
            subject_id=subject.id,
            subject_name=subject.name,
            total_pages=0,
            completed_pages=0,
            progress_percent=0.0,
            status="on_track",
            projected_finish_date=None,
        )

    # Calculate total pages across all core topics
    total_pages = sum(max(0, t.page_end - t.page_start + 1) for t in topics)

    # Calculate completed pages from manually completed topics
    manually_completed_pages = sum(
        max(0, t.page_end - t.page_start + 1) 
        for t in topics if t.completed
    )

    # Calculate completed pages from completions for uncompleted topics
    uncompleted_topic_ids = [t.id for t in topics if not t.completed]
    completed_slots = []
    if uncompleted_topic_ids:
        completed_slots = (
            db.query(ScheduledSlot)
            .join(Completion)
            .filter(
                ScheduledSlot.subject_id == subject.id,
                ScheduledSlot.topic_id.in_(uncompleted_topic_ids)
            )
            .all()
        )

    slot_completed_pages = sum(
        max(0, (s.page_to or 0) - (s.page_from or 0) + 1)
        for s in completed_slots
        if s.page_from is not None and s.page_to is not None
    )
    completed_pages = manually_completed_pages + slot_completed_pages

    progress_percent = (completed_pages / total_pages * 100) if total_pages > 0 else 0.0

    # Calculate expected progress based on time elapsed
    today = date.today()
    school_year_start = date.fromisoformat(get_setting(db, "SCHOOL_YEAR_START", owner_id))
    total_days = (school_year_end - school_year_start).days
    elapsed_days = (today - school_year_start).days
    expected_percent = (elapsed_days / total_days * 100) if total_days > 0 else 0.0

    # Determine status
    if progress_percent >= expected_percent - 5:
        status = "on_track"
    elif progress_percent >= expected_percent - 15:
        status = "behind"
    else:
        status = "at_risk"

    # Project finish date
    projected_finish_date = None
    if completed_pages > 0 and progress_percent < 100:
        # Find the first completion date
        first_completion = (
            db.query(Completion)
            .join(ScheduledSlot)
            .filter(ScheduledSlot.subject_id == subject.id)
            .order_by(Completion.completed_at)
            .first()
        )
        if first_completion:
            days_active = (today - first_completion.completed_at.date()).days or 1
            pages_per_day = completed_pages / days_active
            remaining_pages = total_pages - completed_pages
            days_remaining = int(remaining_pages / pages_per_day) if pages_per_day > 0 else 999
            projected_finish_date = today + timedelta(days=days_remaining)

    return SubjectProgress(
        subject_id=subject.id,
        subject_name=subject.name,
        total_pages=total_pages,
        completed_pages=completed_pages,
        progress_percent=round(progress_percent, 1),
        status=status,
        projected_finish_date=projected_finish_date,
    )


@router.get("/{child_id}", response_model=ChildProgress)
def get_child_progress(child_id: int, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    child = get_owned_child(db, child_id, user_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    school_year_end = date.fromisoformat(get_setting(db, "SCHOOL_YEAR_END", user_id))
    subjects = db.query(Subject).filter(Subject.child_id == child_id).all()

    subject_progress_list = [
        _calculate_subject_progress(s, db, school_year_end, user_id) for s in subjects
    ]

    # Overall progress
    total_pages = sum(sp.total_pages for sp in subject_progress_list)
    completed_pages = sum(sp.completed_pages for sp in subject_progress_list)
    overall_progress = (completed_pages / total_pages * 100) if total_pages > 0 else 0.0

    # Overall status
    statuses = [sp.status for sp in subject_progress_list]
    if "at_risk" in statuses:
        overall_status = "at_risk"
    elif "behind" in statuses:
        overall_status = "behind"
    else:
        overall_status = "on_track"

    return ChildProgress(
        child_id=child.id,
        child_name=child.name,
        child_color=child.color,
        overall_progress=round(overall_progress, 1),
        overall_status=overall_status if subject_progress_list else "on_track",
        subjects=subject_progress_list,
    )


@router.get("/family/overview", response_model=FamilyProgress)
def get_family_progress(user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    children = db.query(Child).filter(Child.owner_id == user_id).order_by(Child.id).all()
    school_year_end = date.fromisoformat(get_setting(db, "SCHOOL_YEAR_END", user_id))

    child_progress_list = []
    for child in children:
        subjects = db.query(Subject).filter(Subject.child_id == child.id).all()
        subject_progress_list = [
            _calculate_subject_progress(s, db, school_year_end, user_id) for s in subjects
        ]

        total_pages = sum(sp.total_pages for sp in subject_progress_list)
        completed_pages = sum(sp.completed_pages for sp in subject_progress_list)
        overall_progress = (completed_pages / total_pages * 100) if total_pages > 0 else 0.0

        statuses = [sp.status for sp in subject_progress_list]
        if "at_risk" in statuses:
            overall_status = "at_risk"
        elif "behind" in statuses:
            overall_status = "behind"
        else:
            overall_status = "on_track"

        child_progress_list.append(ChildProgress(
            child_id=child.id,
            child_name=child.name,
            child_color=child.color,
            overall_progress=round(overall_progress, 1),
            overall_status=overall_status if subject_progress_list else "on_track",
            subjects=subject_progress_list,
        ))

    return FamilyProgress(children=child_progress_list)
