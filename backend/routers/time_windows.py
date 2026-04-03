from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from models import TimeWindow, Child
from schemas import TimeWindowCreate, TimeWindowResponse

router = APIRouter()


# Time windows are nested under children in the API but managed in Settings
@router.get("/by-child/{child_id}", response_model=List[TimeWindowResponse])
def list_time_windows(child_id: int, db: Session = Depends(get_db)):
    child = db.query(Child).filter(Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    return (
        db.query(TimeWindow)
        .filter(TimeWindow.child_id == child_id)
        .order_by(TimeWindow.weekday, TimeWindow.start_time)
        .all()
    )


@router.post("/", response_model=TimeWindowResponse, status_code=201)
def create_time_window(tw: TimeWindowCreate, db: Session = Depends(get_db)):
    child = db.query(Child).filter(Child.id == tw.child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    db_tw = TimeWindow(**tw.model_dump())
    db.add(db_tw)
    db.commit()
    db.refresh(db_tw)
    return db_tw


@router.delete("/{tw_id}", status_code=204)
def delete_time_window(tw_id: int, db: Session = Depends(get_db)):
    tw = db.query(TimeWindow).filter(TimeWindow.id == tw_id).first()
    if not tw:
        raise HTTPException(status_code=404, detail="Time window not found")
    db.delete(tw)
    db.commit()
    return None
