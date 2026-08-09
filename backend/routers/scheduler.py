from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date

from database import get_db
from models import Child, ScheduledSlot
from schemas import ScheduledSlotResponse, ScheduleResult
from services.scheduler_engine import recalculate_schedule
from utils import slot_to_response
from auth import get_owned_child, require_family_user

router = APIRouter()


@router.post("/recalculate/{child_id}", response_model=ScheduleResult)
def recalculate(child_id: int, user_id: str = Depends(require_family_user), db: Session = Depends(get_db)):
    child = get_owned_child(db, child_id, user_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    return recalculate_schedule(child_id, user_id, db)


@router.get("/{child_id}", response_model=list[ScheduledSlotResponse])
def get_schedule(
    child_id: int,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    user_id: str = Depends(require_family_user),
    db: Session = Depends(get_db),
):
    child = get_owned_child(db, child_id, user_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    query = db.query(ScheduledSlot).filter(ScheduledSlot.child_id == child_id)
    if start_date:
        query = query.filter(ScheduledSlot.date >= start_date)
    if end_date:
        query = query.filter(ScheduledSlot.date <= end_date)

    slots = query.order_by(ScheduledSlot.date, ScheduledSlot.time_start).all()
    return [slot_to_response(s) for s in slots]
