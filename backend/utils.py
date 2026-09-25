"""Shared helpers for routes backed by the store."""
from __future__ import annotations

from fastapi import HTTPException

from schemas import ScheduledSlotResponse

SETTING_DEFAULTS = {
    "SCHOOL_YEAR_START": "2026-02-01",
    "SCHOOL_YEAR_END": "2026-12-31",
}


def get_or_404(store, table: str, record_id, label: str | None = None) -> dict:
    record = store.get(table, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"{label or table.rstrip('s').replace('_', ' ').title()} not found")
    return record


def completion_by_slot(store) -> dict[int, dict]:
    return {c["slot_id"]: c for c in store.all("completions")}


def slot_to_response(store, slot: dict, completions: dict | None = None,
                     subjects: dict | None = None, topics: dict | None = None) -> ScheduledSlotResponse:
    completions = completions if completions is not None else completion_by_slot(store)
    subject = (subjects or {}).get(slot["subject_id"]) or store.get("subjects", slot["subject_id"])
    topic = None
    if slot["topic_id"] is not None:
        topic = (topics or {}).get(slot["topic_id"]) or store.get("topics", slot["topic_id"])
    completion = completions.get(slot["id"])
    return ScheduledSlotResponse(
        id=slot["id"], child_id=slot["child_id"], subject_id=slot["subject_id"], topic_id=slot["topic_id"],
        date=slot["date"], time_start=slot["time_start"], time_end=slot["time_end"],
        page_from=slot["page_from"], page_to=slot["page_to"],
        subject_name=subject["name"] if subject else None,
        topic_title=topic["title"] if topic else None,
        pdf_path=None,
        document_id=topic["document_id"] if topic else None,
        pdf_page_offset=(topic["pdf_page_offset"] or 0) if topic else 0,
        is_completed=completion is not None,
        completed_at=completion["completed_at"] if completion else None,
    )


def slots_response(store, slots: list[dict]) -> list[ScheduledSlotResponse]:
    completions = completion_by_slot(store)
    subjects = {s["id"]: s for s in store.all("subjects")}
    topics = {t["id"]: t for t in store.all("topics")}
    return [slot_to_response(store, s, completions, subjects, topics) for s in slots]


def get_setting(store, key: str) -> str:
    record = store.get("settings", key)
    return record["value"] if record and record["value"] is not None else SETTING_DEFAULTS.get(key, "")


def set_setting(tx, key: str, value: str) -> None:
    if tx.get("settings", key):
        tx.update("settings", key, {"value": value})
    else:
        tx.insert("settings", {"id": key, "value": value})
