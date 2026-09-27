from datetime import date, datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, HTTPException

from app_context import request_operation as write
from dependencies import store
from schemas import CompletionResponse, ScheduledSlotResponse
from services.completion_tracking import mark_topic_completed, mark_topic_incomplete, save_topic
from utils import get_or_404, slots_response

router = APIRouter()


def _child_slots(child_id: int):
    get_or_404(store(), "children", child_id, "Child")
    return store().find("scheduled_slots", child_id=child_id)


@router.get("/{child_id}/today", response_model=List[ScheduledSlotResponse])
def get_today_checklist(child_id: int):
    today = date.today()
    slots = [s for s in _child_slots(child_id) if s["date"] == today]
    return slots_response(store(), sorted(slots, key=lambda s: s["time_start"]))


@router.get("/{child_id}/week", response_model=List[ScheduledSlotResponse])
def get_week_checklist(child_id: int):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    slots = [s for s in _child_slots(child_id) if week_start <= s["date"] <= week_end]
    return slots_response(store(), sorted(slots, key=lambda s: (s["date"], s["time_start"])))


@router.post("/complete/{slot_id}", response_model=CompletionResponse, status_code=201)
def complete_slot(slot_id: int):
    slot = store().get("scheduled_slots", slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Scheduled slot not found")
    existing = store().first("completions", slot_id=slot_id)
    if existing:
        return existing
    recorded_at = datetime.now(timezone.utc).replace(microsecond=0)
    with write("checklist.complete") as tx:
        completion = tx.insert("completions", {"slot_id": slot_id, "completed_at": recorded_at})
        # Sync with curriculum: if this slot has a topic, mark it as completed
        if slot["topic_id"]:
            topic = tx.get("topics", slot["topic_id"])
            if topic:
                save_topic(tx, mark_topic_completed(topic, recorded_at))
    return completion


@router.delete("/complete/{slot_id}", status_code=204)
def uncomplete_slot(slot_id: int):
    slot = store().get("scheduled_slots", slot_id)
    completion = store().first("completions", slot_id=slot_id)
    if not slot or not completion:
        raise HTTPException(status_code=404, detail="Completion not found")
    with write("checklist.uncomplete") as tx:
        if slot["topic_id"]:
            # Keep the topic complete when another slot for it is still complete.
            completed_ids = {c["slot_id"] for c in tx.all("completions")}
            others = [s for s in tx.find("scheduled_slots", topic_id=slot["topic_id"])
                      if s["id"] != slot_id and s["id"] in completed_ids]
            if not others:
                topic = tx.get("topics", slot["topic_id"])
                if topic:
                    save_topic(tx, mark_topic_incomplete(topic))
        tx.delete("completions", completion["id"])
    return None


@router.get("/{child_id}/missed", response_model=List[ScheduledSlotResponse])
def get_missed_items(child_id: int):
    today = date.today()
    completed = {c["slot_id"] for c in store().all("completions")}
    slots = [s for s in _child_slots(child_id) if s["date"] < today and s["id"] not in completed]
    slots.sort(key=lambda s: s["time_start"])
    slots.sort(key=lambda s: s["date"], reverse=True)
    return slots_response(store(), slots)
