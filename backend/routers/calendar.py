from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app_context import request_operation as write
from dependencies import require_member, require_parent, store
from schemas import BlockedDayCreate, BlockedDayResponse, SchoolYearSettings, TopicCompletionActivity
from utils import get_or_404, get_setting, set_setting

router = APIRouter()


def standalone_topic_completions(db, child_id: int) -> list[TopicCompletionActivity]:
    """Automatic topic timestamps not already represented by a completed slot."""
    completed_slot_ids = {c["slot_id"] for c in db.all("completions")}
    represented = {s["topic_id"] for s in db.all("scheduled_slots")
                   if s["id"] in completed_slot_ids and s["topic_id"] is not None}
    subjects = {s["id"]: s for s in db.find("subjects", child_id=child_id)}
    topics = [t for t in db.all("topics")
              if t["subject_id"] in subjects and t["completed"] and t["completed_at"] is not None
              and t["id"] not in represented]
    topics.sort(key=lambda t: (t["completed_at"], t["chapter_order"] or 0))
    return [TopicCompletionActivity(topic_id=t["id"], subject_id=t["subject_id"],
                                    subject_name=subjects[t["subject_id"]]["name"], topic_title=t["title"],
                                    completed_at=t["completed_at"]) for t in topics]


@router.get("/completed-topics/{child_id}", response_model=List[TopicCompletionActivity],
            dependencies=[Depends(require_member)])
def list_standalone_topic_completions(child_id: int):
    get_or_404(store(), "children", child_id, "Child")
    return standalone_topic_completions(store(), child_id)


@router.get("/blocked-days", response_model=List[BlockedDayResponse], dependencies=[Depends(require_member)])
def list_blocked_days(child_id: Optional[int] = Query(None), start_date: Optional[date] = Query(None),
                      end_date: Optional[date] = Query(None)):
    rows = store().all("blocked_days")
    if child_id is not None:
        # Include blocks for this child + blocks for all children (child_id=NULL)
        rows = [r for r in rows if r["child_id"] in (child_id, None)]
    if start_date:
        rows = [r for r in rows if r["date"] >= start_date]
    if end_date:
        rows = [r for r in rows if r["date"] <= end_date]
    return sorted(rows, key=lambda r: r["date"])


@router.post("/blocked-days", response_model=BlockedDayResponse, status_code=201,
             dependencies=[Depends(require_parent)])
def create_blocked_day(blocked: BlockedDayCreate):
    if blocked.child_id is not None:
        get_or_404(store(), "children", blocked.child_id, "Child")
    with write("blocked_days.create") as tx:
        return tx.insert("blocked_days", blocked.model_dump())


@router.delete("/blocked-days/{blocked_id}", status_code=204, dependencies=[Depends(require_parent)])
def delete_blocked_day(blocked_id: int):
    get_or_404(store(), "blocked_days", blocked_id, "Blocked day")
    with write("blocked_days.delete") as tx:
        tx.delete("blocked_days", blocked_id)
    return None


@router.get("/settings/school-year", response_model=SchoolYearSettings, dependencies=[Depends(require_member)])
def get_school_year():
    return SchoolYearSettings(start_date=date.fromisoformat(get_setting(store(), "SCHOOL_YEAR_START")),
                              end_date=date.fromisoformat(get_setting(store(), "SCHOOL_YEAR_END")))


@router.put("/settings/school-year", response_model=SchoolYearSettings, dependencies=[Depends(require_parent)])
def update_school_year(settings: SchoolYearSettings):
    with write("settings.school_year") as tx:
        set_setting(tx, "SCHOOL_YEAR_START", settings.start_date.isoformat())
        set_setting(tx, "SCHOOL_YEAR_END", settings.end_date.isoformat())
    return settings
