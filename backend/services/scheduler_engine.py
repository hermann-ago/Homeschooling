"""
Smart scheduler engine (Alternating Slot Version).

Behavior:
- Two independent slot sequences:
  Slot A (Mon start): Mon → Wed → Fri → Tue → Thu → ...
  Slot B (Tue start): Tue → Thu → Mon → Wed → Fri → ...
- Subjects are split between Slot A and Slot B
- Topics are assigned sequentially (no spreading to end date)
- Fills available days until all topics are scheduled

All reads and writes go through one store transaction, so a recalculation is
saved to Google Sheets as a single atomic batch.
"""
from datetime import date, timedelta

from schemas import ScheduleResult, ScheduleWarning
from utils import get_setting


def recalculate_schedule(child_id: int, tx, today: date | None = None) -> ScheduleResult:
    warnings: list[ScheduleWarning] = []
    today = today or date.today()

    # ── 1. Gather subjects and remaining topics ─────────────────────
    subjects = sorted(tx.find("subjects", child_id=child_id), key=lambda s: s["id"])
    if not subjects:
        return ScheduleResult(slots_created=0, warnings=[ScheduleWarning(message="No subjects found.")])

    completed_slot_ids = {c["slot_id"] for c in tx.all("completions")}
    subject_topics = {}
    subject_map = {}

    for subject in subjects:
        topics = sorted((t for t in tx.find("topics", subject_id=subject["id"]) if t["is_core"]),
                        key=lambda t: t["chapter_order"] or 0)
        remaining = []
        for topic in topics:
            if topic["completed"]:
                continue
            total_pages = topic["page_end"] - topic["page_start"] + 1
            completed_pages = _get_completed_pages(tx, topic["id"], subject["id"], completed_slot_ids)
            if total_pages - completed_pages > 0:
                remaining.append({
                    "topic": topic,
                    "start_page": topic["page_start"] + completed_pages,
                    "end_page": topic["page_end"],
                })
        if remaining:
            subject_topics[subject["id"]] = remaining
            subject_map[subject["id"]] = subject

    if not subject_topics:
        _clear_reschedulable_slots(child_id, today, tx)
        return ScheduleResult(slots_created=0, warnings=[ScheduleWarning(message="All content completed 🎉")])

    # ── 2. Time windows ─────────────────────────────────────────────
    time_windows = sorted(tx.find("time_windows", child_id=child_id), key=lambda w: (w["weekday"], w["start_time"]))
    if not time_windows:
        return ScheduleResult(slots_created=0, warnings=[ScheduleWarning(message="No time windows configured.")])

    windows_by_day = {}
    for tw in time_windows:
        windows_by_day.setdefault(tw["weekday"], []).append(tw)

    # ── 3. Blocked days ─────────────────────────────────────────────
    school_year_end = date.fromisoformat(get_setting(tx.store, "SCHOOL_YEAR_END"))
    blocked_dates = {
        bd["date"] for bd in tx.all("blocked_days")
        if today <= bd["date"] <= school_year_end and bd["child_id"] in (child_id, None)
    }

    # ── 4. Available days ───────────────────────────────────────────
    available_days = []
    current = today
    while current <= school_year_end:
        wd = current.weekday()
        if current not in blocked_dates and wd in windows_by_day:
            windows = windows_by_day[wd]
            total_minutes = sum(_time_diff_minutes(w["start_time"], w["end_time"]) for w in windows)
            if total_minutes > 0:
                available_days.append({"date": current, "windows": windows, "total_minutes": total_minutes})
        current += timedelta(days=1)

    if not available_days:
        return ScheduleResult(slots_created=0, warnings=[ScheduleWarning(message="No available study days.")])

    # ── 5. Clear old schedule ───────────────────────────────────────
    _clear_reschedulable_slots(child_id, today, tx)

    # ── 6. Alternating slot scheduling ──────────────────────────────
    child_slots = tx.find("scheduled_slots", child_id=child_id)
    completed_slots = [s for s in child_slots if s["date"] >= today and s["id"] in completed_slot_ids]
    subject_completed_dates = {}
    for s in completed_slots:
        subject_completed_dates.setdefault(s["subject_id"], set()).add(s["date"])

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

    subjects_a = [s for s in subjects if (s["slot_type"] or 'A') == 'A' and s["id"] in subject_topics]
    subjects_b = [s for s in subjects if (s["slot_type"] or 'A') == 'B' and s["id"] in subject_topics]
    subjects_c = [s for s in subjects if (s["slot_type"] or 'A') == 'C' and s["id"] in subject_topics]

    # ── Determine starting slot to avoid two consecutive Slot A / B days ──
    slot_a_ids = {s["id"] for s in subjects_a}
    history = sorted((s for s in child_slots if s["date"] < today and s["id"] in completed_slot_ids),
                     key=lambda s: s["date"], reverse=True)
    last_slot_a_completion = next((s for s in history if s["subject_id"] in slot_a_ids), None) if slot_a_ids else None
    last_slot_b_completion = next((s for s in history if s["subject_id"] not in slot_a_ids), None)

    # If Slot A ran more recently than Slot B, start today with Slot B offset (1)
    if last_slot_a_completion and last_slot_b_completion:
        slot_a_start = 1 if last_slot_a_completion["date"] >= last_slot_b_completion["date"] else 0
    elif last_slot_a_completion:
        slot_a_start = 1  # Only A has history, so today should be B
    else:
        slot_a_start = 0  # No history or only B history, start with A

    subject_assignments = []
    for group, slot_type, label in ((subjects_a, 'A', "A"), (subjects_b, 'B', "B"), (subjects_c, 'C', "Both")):
        for subject in group:
            topics = subject_topics[subject["id"]]
            if slot_type == 'C':
                indices = get_subject_indices(subject["id"], 'C', len(topics))
            else:
                indices = get_subject_indices(subject["id"], slot_type, len(topics), slot_a_start)
            for i, topic_info in enumerate(topics):
                subject_assignments.append({"day_index": indices[i], "subject_id": subject["id"],
                                            "topic_info": topic_info, "slot": label})

    subject_assignments.sort(key=lambda x: x["day_index"])
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
            minutes = total_minutes - cursor if i == len(assignments) - 1 else int(per_subject)
            tx.insert("scheduled_slots", {
                "child_id": child_id, "subject_id": subject["id"], "topic_id": topic["id"], "date": day["date"],
                "time_start": _get_time_at_offset(day["windows"], cursor),
                "time_end": _get_time_at_offset(day["windows"], cursor + minutes),
                "page_from": a["topic_info"]["start_page"], "page_to": a["topic_info"]["end_page"],
            })
            cursor += minutes
            slots_created += 1

    return ScheduleResult(slots_created=slots_created, warnings=warnings)


# ── Helpers ────────────────────────────────────────────────────────

def _get_completed_pages(tx, topic_id, subject_id, completed_slot_ids):
    slots = [s for s in tx.find("scheduled_slots", topic_id=topic_id, subject_id=subject_id)
             if s["id"] in completed_slot_ids]
    return sum(max(0, (s["page_to"] or 0) - (s["page_from"] or 0) + 1) for s in slots)


def _clear_reschedulable_slots(child_id: int, today: date, tx) -> int:
    """Clear drafts and stale current/future slots for completed topics."""
    completed_slot_ids = {c["slot_id"] for c in tx.all("completions")}
    topics = {t["id"]: t for t in tx.all("topics")}
    old_slots = [
        s for s in tx.find("scheduled_slots", child_id=child_id)
        if s["id"] not in completed_slot_ids
        or (s["date"] >= today and s["topic_id"] in topics and topics[s["topic_id"]]["completed"])
    ]
    for slot in old_slots:
        tx.delete("scheduled_slots", slot["id"])
    return len(old_slots)


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
        duration = _time_diff_minutes(w["start_time"], w["end_time"])
        if remaining <= duration:
            return _add_minutes(w["start_time"], remaining)
        remaining -= duration
    return windows[-1]["end_time"] if windows else "23:59"
