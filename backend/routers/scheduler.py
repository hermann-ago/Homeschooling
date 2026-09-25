from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app_context import request_operation as write
from dependencies import require_member, require_parent, store
from schemas import ScheduleResult, ScheduledSlotResponse
from services.scheduler_engine import recalculate_schedule
from utils import get_or_404, slots_response

router = APIRouter()


@router.post("/recalculate/{child_id}", response_model=ScheduleResult, dependencies=[Depends(require_parent)])
def recalculate(child_id: int):
    child = get_or_404(store(), "children", child_id, "Child")
    with write("schedule.recalculate", f"Recalculated {child['name']}'s schedule") as tx:
        result = recalculate_schedule(child_id, tx)
    return result


@router.get("/{child_id}", response_model=list[ScheduledSlotResponse], dependencies=[Depends(require_member)])
def get_schedule(child_id: int, start_date: Optional[date] = Query(None), end_date: Optional[date] = Query(None)):
    get_or_404(store(), "children", child_id, "Child")
    slots = store().find("scheduled_slots", child_id=child_id)
    if start_date:
        slots = [s for s in slots if s["date"] >= start_date]
    if end_date:
        slots = [s for s in slots if s["date"] <= end_date]
    return slots_response(store(), sorted(slots, key=lambda s: (s["date"], s["time_start"])))
