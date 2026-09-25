from datetime import date, timedelta

from fastapi import APIRouter, Depends

from dependencies import require_member, store
from schemas import ChildProgress, FamilyProgress, SubjectProgress
from utils import get_or_404, get_setting

router = APIRouter(dependencies=[Depends(require_member)])


def _pages(start, end):
    return max(0, end - start + 1)


def _calculate_subject_progress(db, subject: dict, school_year_end: date) -> SubjectProgress:
    topics = [t for t in db.find("topics", subject_id=subject["id"]) if t["is_core"]]
    if not topics:
        return SubjectProgress(subject_id=subject["id"], subject_name=subject["name"], total_pages=0,
                               completed_pages=0, progress_percent=0.0, status="on_track", projected_finish_date=None)

    total_pages = sum(_pages(t["page_start"], t["page_end"]) for t in topics)
    manually_completed_pages = sum(_pages(t["page_start"], t["page_end"]) for t in topics if t["completed"])

    completions = {c["slot_id"]: c for c in db.all("completions")}
    subject_slots = db.find("scheduled_slots", subject_id=subject["id"])
    uncompleted_topic_ids = {t["id"] for t in topics if not t["completed"]}
    completed_slots = [s for s in subject_slots if s["id"] in completions and s["topic_id"] in uncompleted_topic_ids]
    slot_completed_pages = sum(_pages(s["page_from"], s["page_to"]) for s in completed_slots
                               if s["page_from"] is not None and s["page_to"] is not None)
    completed_pages = manually_completed_pages + slot_completed_pages
    progress_percent = (completed_pages / total_pages * 100) if total_pages > 0 else 0.0

    today = date.today()
    school_year_start = date.fromisoformat(get_setting(db, "SCHOOL_YEAR_START"))
    total_days = (school_year_end - school_year_start).days
    elapsed_days = (today - school_year_start).days
    expected_percent = (elapsed_days / total_days * 100) if total_days > 0 else 0.0
    if progress_percent >= expected_percent - 5:
        status = "on_track"
    elif progress_percent >= expected_percent - 15:
        status = "behind"
    else:
        status = "at_risk"

    projected_finish_date = None
    if completed_pages > 0 and progress_percent < 100:
        subject_completions = [completions[s["id"]] for s in subject_slots if s["id"] in completions]
        if subject_completions:
            first = min(c["completed_at"] for c in subject_completions)
            days_active = (today - first.date()).days or 1
            pages_per_day = completed_pages / days_active
            remaining_pages = total_pages - completed_pages
            days_remaining = int(remaining_pages / pages_per_day) if pages_per_day > 0 else 999
            projected_finish_date = today + timedelta(days=days_remaining)

    return SubjectProgress(subject_id=subject["id"], subject_name=subject["name"], total_pages=total_pages,
                           completed_pages=completed_pages, progress_percent=round(progress_percent, 1),
                           status=status, projected_finish_date=projected_finish_date)


def _child_progress(db, child: dict, school_year_end: date) -> ChildProgress:
    subjects = sorted(db.find("subjects", child_id=child["id"]), key=lambda s: s["id"])
    subject_progress_list = [_calculate_subject_progress(db, s, school_year_end) for s in subjects]
    total_pages = sum(sp.total_pages for sp in subject_progress_list)
    completed_pages = sum(sp.completed_pages for sp in subject_progress_list)
    overall_progress = (completed_pages / total_pages * 100) if total_pages > 0 else 0.0
    statuses = [sp.status for sp in subject_progress_list]
    overall_status = "at_risk" if "at_risk" in statuses else "behind" if "behind" in statuses else "on_track"
    return ChildProgress(child_id=child["id"], child_name=child["name"], child_color=child["color"],
                         overall_progress=round(overall_progress, 1),
                         overall_status=overall_status if subject_progress_list else "on_track",
                         subjects=subject_progress_list)


@router.get("/{child_id}", response_model=ChildProgress)
def get_child_progress(child_id: int):
    child = get_or_404(store(), "children", child_id, "Child")
    return _child_progress(store(), child, date.fromisoformat(get_setting(store(), "SCHOOL_YEAR_END")))


@router.get("/family/overview", response_model=FamilyProgress)
def get_family_progress():
    end = date.fromisoformat(get_setting(store(), "SCHOOL_YEAR_END"))
    children = sorted(store().all("children"), key=lambda c: c["id"])
    return FamilyProgress(children=[_child_progress(store(), c, end) for c in children])
