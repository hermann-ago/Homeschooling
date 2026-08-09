import os
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date

from database import get_db
from models import BlockedDay, Child
from schemas import BlockedDayCreate, BlockedDayResponse, SchoolYearSettings
from utils import get_setting, set_setting
from auth import get_owned_child, require_family_user

router = APIRouter()


@router.get("/blocked-days", response_model=List[BlockedDayResponse])
def list_blocked_days(
    child_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    user_id: str = Depends(require_family_user),
    db: Session = Depends(get_db),
):
    query = db.query(BlockedDay).filter(BlockedDay.owner_id == user_id)
    if child_id is not None:
        # Include blocks for this child + blocks for all children (child_id=NULL)
        query = query.filter(
            (BlockedDay.child_id == child_id) | (BlockedDay.child_id.is_(None))
        )
    if start_date:
        query = query.filter(BlockedDay.date >= start_date)
    if end_date:
        query = query.filter(BlockedDay.date <= end_date)
    return query.order_by(BlockedDay.date).all()


@router.post("/blocked-days", response_model=BlockedDayResponse, status_code=201)
def create_blocked_day(blocked: BlockedDayCreate, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    if blocked.child_id is not None:
        child = get_owned_child(db, blocked.child_id, user_id)
        if not child:
            raise HTTPException(status_code=404, detail="Child not found")
    db_blocked = BlockedDay(**blocked.model_dump(), owner_id=user_id)
    db.add(db_blocked)
    db.commit()
    db.refresh(db_blocked)
    return db_blocked


@router.delete("/blocked-days/{blocked_id}", status_code=204)
def delete_blocked_day(blocked_id: int, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    blocked = db.query(BlockedDay).filter(BlockedDay.id == blocked_id, BlockedDay.owner_id == user_id).first()
    if not blocked:
        raise HTTPException(status_code=404, detail="Blocked day not found")
    db.delete(blocked)
    db.commit()
    return None


@router.get("/settings/school-year", response_model=SchoolYearSettings)
def get_school_year(user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    """Return current school year dates from database."""
    return SchoolYearSettings(
        start_date=date.fromisoformat(get_setting(db, "SCHOOL_YEAR_START", user_id)),
        end_date=date.fromisoformat(get_setting(db, "SCHOOL_YEAR_END", user_id)),
    )


@router.put("/settings/school-year", response_model=SchoolYearSettings)
def update_school_year(settings: SchoolYearSettings, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    """Update school year dates in database."""
    set_setting(db, "SCHOOL_YEAR_START", settings.start_date.isoformat(), user_id)
    set_setting(db, "SCHOOL_YEAR_END", settings.end_date.isoformat(), user_id)
    return settings
