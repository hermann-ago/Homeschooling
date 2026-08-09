"""
Smart scheduler engine (Alternating Slot Version).

Behavior:
- Two independent slot sequences:
  Slot A (Mon start): Mon → Wed → Fri → Tue → Thu → ...
  Slot B (Tue start): Tue → Thu → Mon → Wed → Fri → ...
- Subjects are split between Slot A and Slot B
- Topics are assigned sequentially (no spreading to end date)
- Fills available days until all topics are scheduled
"""
import math
from datetime import date, timedelta
from sqlalchemy.orm import Session

from models import (
    Subject, CurriculumTopic, TimeWindow,
    BlockedDay, ScheduledSlot, Completion,
)
from schemas import ScheduleResult, ScheduleWarning
from utils import get_setting


def recalculate_schedule(child_id: int, owner_id: str, db: Session) -> ScheduleResult:
    warnings: list[ScheduleWarning] = []

    # ── 1. Gather subjects and remaining topics ─────────────────────
    subjects = db.query(Subject).filter(Subject.child_id == child_id).all()
    if not subjects:
        return ScheduleResult(slots_created=0, warnings=[
            ScheduleWarning(message="No subjects found.")
        ])

    subject_topics = {}
    subject_map = {}

    for subject in subjects:
        topics = (
            db.query(CurriculumTopic)
            .filter(
                CurriculumTopic.subject_id == subject.id,
                CurriculumTopic.is_core == True
            )
            .order_by(CurriculumTopic.chapter_order)
            .all()
        )

        remaining = []
        for topic in topics:
            if topic.completed:
                continue

            total_pages = topic.page_end - topic.page_start + 1
            completed_pages = _get_completed_pages(topic.id, subject.id, db)

            if total_pages - completed_pages > 0:
                remaining.append({
                    "topic": topic,
                    "start_page": topic.page_start + completed_pages,
                    "end_page": topic.page_end,
                })

        if remaining:
            subject_topics[subject.id] = remaining
            subject_map[subject.id] = subject

    if not subject_topics:
        return ScheduleResult(slots_created=0, warnings=[
            ScheduleWarning(message="All content completed 🎉")
        ])

    # ── 2. Time windows ─────────────────────────────────────────────
    time_windows = (
        db.query(TimeWindow)
        .filter(TimeWindow.child_id == child_id)
        .order_by(TimeWindow.weekday, TimeWindow.start_time)
        .all()
    )

    if not time_windows:
        return ScheduleResult(slots_created=0, warnings=[
            ScheduleWarning(message="No time windows configured.")
        ])

    windows_by_day = {}
    for tw in time_windows:
        windows_by_day.setdefault(tw.weekday, []).append(tw)

    # ── 3. Blocked days ─────────────────────────────────────────────
    school_year_end = date.fromisoformat(get_setting(db, "SCHOOL_YEAR_END", owner_id))
    today = date.today()

    blocked_dates = set(
        bd.date for bd in db.query(BlockedDay)
        .filter(
            BlockedDay.owner_id == owner_id,
            BlockedDay.date >= today, 
            BlockedDay.date <= school_year_end,
            (BlockedDay.child_id == child_id) | (BlockedDay.child_id.is_(None))
        )
        .all()
    )

    # ── 4. Available days ───────────────────────────────────────────
    available_days = []
    current = today

    while current <= school_year_end:
        wd = current.weekday()

        if current not in blocked_dates and wd in windows_by_day:
            windows = windows_by_day[wd]
            total_minutes = sum(
                _time_diff_minutes(w.start_time, w.end_time)
                for w in windows
            )

            if total_minutes > 0:
                available_days.append({
                    "date": current,
                    "windows": windows,
                    "total_minutes": total_minutes,
                })

        current += timedelta(days=1)

    if not available_days:
        return ScheduleResult(slots_created=0, warnings=[
            ScheduleWarning(message="No available study days.")
        ])

    # ── 5. Clear old schedule ───────────────────────────────────────
    old_slots = (
        db.query(ScheduledSlot)
        .outerjoin(Completion)
        .filter(ScheduledSlot.child_id == child_id, Completion.id.is_(None))
        .all()
    )

    for s in old_slots:
        db.delete(s)

    db.flush()

    # ── 6. Alternating slot scheduling ──────────────────────────────

    # ── 6. Alternating slot scheduling ──────────────────────────────

    # Gather existing completed slots for today onwards
    completed_slots = (
        db.query(ScheduledSlot)
        .join(Completion)
        .filter(ScheduledSlot.date >= today, ScheduledSlot.child_id == child_id)
        .all()
    )
    subject_completed_dates = {}
    for s in completed_slots:
        subject_completed_dates.setdefault(s.subject_id, set()).add(s.date)

    def get_subject_indices(subject_id: int, slot_type: str, total_needed: int, slot_a_start: int = 0):
        # Slot A: slot_a_start, slot_a_start+2... | Slot B: slot_a_start+1, slot_a_start+3... | Slot C: 0, 1, 2...
        stride = 1 if slot_type == 'C' else 2
        if slot_type == 'C':
            start_idx = 0
        elif slot_type == 'A':
            start_idx = slot_a_start
        else:  # B
            start_idx = (slot_a_start + 1) % 2  # opposite of A's start

        indices = []
        completed_dates = subject_completed_dates.get(subject_id, set())
        
        current_day_idx = start_idx
        while len(indices) < total_needed:
            if current_day_idx >= len(available_days):
                # Out of days, cap at the last one
                indices.append(len(available_days) - 1)
            else:
                day_date = available_days[current_day_idx]["date"]
                if day_date in completed_dates:
                    current_day_idx += stride
                    continue
                indices.append(current_day_idx)
                current_day_idx += stride
                
        return indices

    # Group subjects by Slot A / Slot B
    subjects_a = [s for s in subjects if getattr(s, 'slot_type', 'A') == 'A' and s.id in subject_topics]
    subjects_b = [s for s in subjects if getattr(s, 'slot_type', 'A') == 'B' and s.id in subject_topics]
    subjects_c = [s for s in subjects if getattr(s, 'slot_type', 'A') == 'C' and s.id in subject_topics]

    # ── Determine starting slot to avoid two consecutive Slot A / B days ──
    # Check if any Slot A subject ran most recently before today.
    # If so, today should start with Slot B (slot_a_start=1), otherwise A (slot_a_start=0).
    yesterday = today - timedelta(days=1)
    slot_a_ids = {s.id for s in subjects_a}

    # Look at the most recent completed day before today
    last_slot_a_completion = (
        db.query(ScheduledSlot)
        .join(Completion)
        .filter(
            ScheduledSlot.child_id == child_id,
            ScheduledSlot.date < today,
            ScheduledSlot.subject_id.in_(slot_a_ids) if slot_a_ids else False
        )
        .order_by(ScheduledSlot.date.desc())
        .first()
    )

    last_slot_b_completion = (
        db.query(ScheduledSlot)
        .join(Completion)
        .filter(
            ScheduledSlot.child_id == child_id,
            ScheduledSlot.date < today,
            ScheduledSlot.subject_id.notin_(slot_a_ids) if slot_a_ids else True
        )
        .order_by(ScheduledSlot.date.desc())
        .first()
    )

    # If Slot A ran more recently than Slot B, start today with Slot B offset (1)
    if last_slot_a_completion and last_slot_b_completion:
        if last_slot_a_completion.date >= last_slot_b_completion.date:
            slot_a_start = 1  # Slot A ran last → today starts with B-offset
        else:
            slot_a_start = 0
    elif last_slot_a_completion:
        slot_a_start = 1  # Only A has history, so today should be B
    else:
        slot_a_start = 0  # No history or only B history, start with A

    subject_assignments = []
    
    # Schedule Slot A subjects (Alt A)
    for subject in subjects_a:
        topics = subject_topics[subject.id]
        indices = get_subject_indices(subject.id, 'A', len(topics), slot_a_start)
        for i, topic_info in enumerate(topics):
            day_index = indices[i]
            subject_assignments.append({
                "day_index": day_index,
                "subject_id": subject.id,
                "topic_info": topic_info,
                "slot": "A"
            })

    # Schedule Slot B subjects (Alt B)
    for subject in subjects_b:
        topics = subject_topics[subject.id]
        indices = get_subject_indices(subject.id, 'B', len(topics), slot_a_start)
        for i, topic_info in enumerate(topics):
            day_index = indices[i]
            subject_assignments.append({
                "day_index": day_index,
                "subject_id": subject.id,
                "topic_info": topic_info,
                "slot": "B"
            })

    # Schedule Slot C subjects (Daily)
    for subject in subjects_c:
        topics = subject_topics[subject.id]
        indices = get_subject_indices(subject.id, 'C', len(topics))
        for i, topic_info in enumerate(topics):
            day_index = indices[i]
            subject_assignments.append({
                "day_index": day_index,
                "subject_id": subject.id,
                "topic_info": topic_info,
                "slot": "Both"
            })

    subject_assignments.sort(key=lambda x: x["day_index"])

    # Group by day
    day_assignments = {}
    for a in subject_assignments:
        day_assignments.setdefault(a["day_index"], []).append(a)

    # ── 7. Create slots ─────────────────────────────────────────────
    slots_created = 0
    total_days = len(available_days)

    for day_idx, assignments in day_assignments.items():
        if day_idx >= total_days:
            continue

        day = available_days[day_idx]
        total_minutes = day["total_minutes"]
        per_subject = total_minutes / len(assignments)

        cursor = 0

        for i, a in enumerate(assignments):
            subject = subject_map[a["subject_id"]]
            topic = a["topic_info"]["topic"]

            minutes = (
                total_minutes - cursor
                if i == len(assignments) - 1
                else int(per_subject)
            )

            start = _get_time_at_offset(day["windows"], cursor)
            end = _get_time_at_offset(day["windows"], cursor + minutes)

            db.add(ScheduledSlot(
                child_id=child_id,
                subject_id=subject.id,
                topic_id=topic.id,
                date=day["date"],
                time_start=start,
                time_end=end,
                page_from=a["topic_info"]["start_page"],
                page_to=a["topic_info"]["end_page"],
            ))

            cursor += minutes
            slots_created += 1

    db.commit()

    return ScheduleResult(slots_created=slots_created, warnings=warnings)


# ── Helpers ────────────────────────────────────────────────────────

def _get_completed_pages(topic_id, subject_id, db):
    slots = (
        db.query(ScheduledSlot)
        .join(Completion)
        .filter(
            ScheduledSlot.topic_id == topic_id,
            ScheduledSlot.subject_id == subject_id,
        )
        .all()
    )

    return sum(
        max(0, (s.page_to or 0) - (s.page_from or 0) + 1)
        for s in slots
    )


def _time_diff_minutes(start, end):
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    return (eh * 60 + em) - (sh * 60 + sm)


def _add_minutes(time_str, minutes):
    h, m = map(int, time_str.split(":"))
    total = h * 60 + m + minutes
    return f"{total // 60:02d}:{total % 60:02d}"


def _get_time_at_offset(windows, offset):
    remaining = offset

    for w in windows:
        duration = _time_diff_minutes(w.start_time, w.end_time)

        if remaining <= duration:
            return _add_minutes(w.start_time, remaining)

        remaining -= duration

    return windows[-1].end_time if windows else "23:59"

