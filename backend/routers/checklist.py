from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import date, datetime, timedelta

from database import get_db
from models import ScheduledSlot, Completion, Child, CurriculumTopic
from schemas import ScheduledSlotResponse, CompletionResponse
from utils import slot_to_response

router = APIRouter()


@router.get("/{child_id}/today", response_model=List[ScheduledSlotResponse])
def get_today_checklist(child_id: int, db: Session = Depends(get_db)):
    child = db.query(Child).filter(Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    today = date.today()
    slots = (
        db.query(ScheduledSlot)
        .filter(ScheduledSlot.child_id == child_id, ScheduledSlot.date == today)
        .order_by(ScheduledSlot.time_start)
        .all()
    )
    return [slot_to_response(s) for s in slots]


@router.get("/{child_id}/week", response_model=List[ScheduledSlotResponse])
def get_week_checklist(child_id: int, db: Session = Depends(get_db)):
    child = db.query(Child).filter(Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    today = date.today()
    # Get Monday of current week
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    slots = (
        db.query(ScheduledSlot)
        .filter(
            ScheduledSlot.child_id == child_id,
            ScheduledSlot.date >= week_start,
            ScheduledSlot.date <= week_end,
        )
        .order_by(ScheduledSlot.date, ScheduledSlot.time_start)
        .all()
    )
    return [slot_to_response(s) for s in slots]


@router.post("/complete/{slot_id}", response_model=CompletionResponse, status_code=201)
def complete_slot(slot_id: int, db: Session = Depends(get_db)):
    slot = db.query(ScheduledSlot).filter(ScheduledSlot.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Scheduled slot not found")

    # Check if already completed
    existing = db.query(Completion).filter(Completion.slot_id == slot_id).first()
    if existing:
        return existing

    completion = Completion(slot_id=slot_id, completed_at=datetime.utcnow())
    db.add(completion)
    
    # Sync with curriculum: If this slot has a topic, mark it as completed
    if slot.topic_id:
        topic = db.query(CurriculumTopic).filter(CurriculumTopic.id == slot.topic_id).first()
        if topic:
            topic.completed = True

    db.commit()
    db.refresh(completion)
    return completion


@router.delete("/complete/{slot_id}", status_code=204)
def uncomplete_slot(slot_id: int, db: Session = Depends(get_db)):
    completion = db.query(Completion).filter(Completion.slot_id == slot_id).first()
    if not completion:
        raise HTTPException(status_code=404, detail="Completion not found")
    # Sync with curriculum: Before deleting, check if this was the last completed slot for the topic
    slot = completion.slot
    if slot and slot.topic_id:
        # Check if any other slots for this topic are completed
        other_completions = db.query(Completion).join(ScheduledSlot).filter(
            ScheduledSlot.topic_id == slot.topic_id,
            ScheduledSlot.id != slot.id
        ).first()
        if not other_completions:
            topic = db.query(CurriculumTopic).filter(CurriculumTopic.id == slot.topic_id).first()
            if topic:
                topic.completed = False

    db.delete(completion)
    db.commit()
    return None


@router.get("/{child_id}/missed", response_model=List[ScheduledSlotResponse])
def get_missed_items(child_id: int, db: Session = Depends(get_db)):
    child = db.query(Child).filter(Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    today = date.today()
    # Find past slots without completions
    slots = (
        db.query(ScheduledSlot)
        .outerjoin(Completion)
        .filter(
            ScheduledSlot.child_id == child_id,
            ScheduledSlot.date < today,
            Completion.id.is_(None),
        )
        .order_by(ScheduledSlot.date.desc(), ScheduledSlot.time_start)
        .all()
    )
    return [slot_to_response(s) for s in slots]
