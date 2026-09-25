"""Existing app behaviour on the Sheets store: scheduling, completion, annotations."""
import hashlib
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from services.completion_tracking import mark_topic_completed, mark_topic_incomplete
from services.scheduler_engine import _clear_reschedulable_slots
from tests.pdf_fixture import make_pdf


def seed(harness, pages=12):
    ctx = harness.ctx
    pdf = make_pdf([[f"Page {n}"] for n in range(1, pages + 1)])
    drive_id = harness.drive.add_file(pdf, "language-arts.pdf")
    with ctx.store.transaction() as tx:
        child = tx.insert("children", {"name": "Mila", "color": "#E986B4"})
        subject = tx.insert("subjects", {"child_id": child["id"], "name": "Language Arts"})
        document = tx.insert("documents", {"drive_file_id": drive_id, "original_filename": "language-arts.pdf",
                                           "size_bytes": len(pdf), "page_count": pages,
                                           "sha256": hashlib.sha256(pdf).hexdigest(), "source": "drive"})
    ctx.store.flush()
    return child, subject, document


def test_completion_time_is_automatic_and_cleared_when_undone():
    topic = {"completed": False, "completed_at": None}
    recorded_at = datetime(2026, 8, 10, 14, 30, tzinfo=timezone.utc)
    mark_topic_completed(topic, recorded_at)
    assert topic == {"completed": True, "completed_at": recorded_at}
    mark_topic_completed(topic, datetime(2026, 8, 11, tzinfo=timezone.utc))
    assert topic["completed_at"] == recorded_at  # the original time is kept
    mark_topic_incomplete(topic)
    assert topic == {"completed": False, "completed_at": None}


def test_calendar_lists_only_completions_without_slot_history(harness):
    child, subject, _ = seed(harness)
    recorded_at = datetime(2026, 8, 10, 14, 30, tzinfo=timezone.utc)
    with harness.ctx.store.transaction() as tx:
        standalone = tx.insert("topics", {"subject_id": subject["id"], "title": "Ahead chapter", "page_start": 1,
                                          "page_end": 2, "completed": True, "completed_at": recorded_at})
        represented = tx.insert("topics", {"subject_id": subject["id"], "title": "Scheduled chapter", "page_start": 3,
                                           "page_end": 4, "completed": True, "completed_at": recorded_at})
        slot = tx.insert("scheduled_slots", {"child_id": child["id"], "subject_id": subject["id"],
                                             "topic_id": represented["id"], "date": date(2026, 8, 10),
                                             "time_start": "09:00", "time_end": "09:30", "page_from": 3, "page_to": 4})
        tx.insert("completions", {"slot_id": slot["id"], "completed_at": recorded_at})
    body = harness.call("GET", f"/api/calendar/completed-topics/{child['id']}").json()
    assert [a["topic_title"] for a in body] == ["Ahead chapter"]
    assert body[0]["topic_id"] == standalone["id"]


def test_clearing_keeps_completed_history_but_removes_future_completed_topics(harness):
    child, subject, _ = seed(harness)
    today = date(2026, 8, 10)
    store = harness.ctx.store
    with store.transaction() as tx:
        done = tx.insert("topics", {"subject_id": subject["id"], "title": "Done", "page_start": 1, "page_end": 1,
                                    "completed": True})
        remaining = tx.insert("topics", {"subject_id": subject["id"], "title": "Remaining", "page_start": 2,
                                         "page_end": 2})

        def add(topic, day, completed):
            slot = tx.insert("scheduled_slots", {"child_id": child["id"], "subject_id": subject["id"],
                                                 "topic_id": topic["id"], "date": day, "time_start": "09:00",
                                                 "time_end": "09:30", "page_from": topic["page_start"],
                                                 "page_to": topic["page_end"]})
            if completed:
                tx.insert("completions", {"slot_id": slot["id"]})
            return slot["id"]

        historical = add(done, today - timedelta(days=1), True)
        add(done, today, True)
        add(done, today + timedelta(days=1), True)
        add(remaining, today - timedelta(days=1), False)
        add(remaining, today + timedelta(days=1), False)
        future_progress = add(remaining, today + timedelta(days=2), True)
    with store.transaction() as tx:
        assert _clear_reschedulable_slots(child["id"], today, tx) == 4
    assert {s["id"] for s in store.all("scheduled_slots")} == {historical, future_progress}
    assert len(store.all("completions")) == 2  # completions of removed slots were cascaded


def test_schedule_recalculation_is_one_atomic_operation(harness):
    child, subject, _ = seed(harness)
    for weekday in range(5):
        harness.call("POST", "/api/time-windows", json={"child_id": child["id"], "weekday": weekday,
                                                        "start_time": "09:00", "end_time": "10:00"})
    with harness.ctx.store.transaction() as tx:
        for n in range(1, 4):
            tx.insert("topics", {"subject_id": subject["id"], "title": f"Lesson {n}", "page_start": n,
                                 "page_end": n, "chapter_order": n})
    harness.ctx.store.flush()
    before = len(harness.sheets.rows("Operation Receipts"))
    r = harness.call("POST", f"/api/schedule/recalculate/{child['id']}", key="recalc-1")
    assert r.status_code == 200 and r.json()["slots_created"] == 3
    assert r.headers["x-sync-state"] == "saved"
    assert len(harness.sheets.rows("Operation Receipts")) == before + 1
    assert len(harness.sheets.rows("Schedules")) == 4


def test_checklist_completion_marks_topic_and_undo_restores(harness):
    child, subject, _ = seed(harness)
    with harness.ctx.store.transaction() as tx:
        topic = tx.insert("topics", {"subject_id": subject["id"], "title": "Lesson", "page_start": 1, "page_end": 2})
        slot = tx.insert("scheduled_slots", {"child_id": child["id"], "subject_id": subject["id"],
                                             "topic_id": topic["id"], "date": date.today(), "time_start": "09:00",
                                             "time_end": "09:30", "page_from": 1, "page_to": 2})
    r = harness.call("POST", f"/api/checklist/complete/{slot['id']}", role="learner", key="c1")
    assert r.status_code == 201
    assert harness.ctx.store.get("topics", topic["id"])["completed_at"] is not None
    today = harness.call("GET", f"/api/checklist/{child['id']}/today", role="learner").json()
    assert today[0]["is_completed"] is True
    assert harness.call("DELETE", f"/api/checklist/complete/{slot['id']}", role="learner").status_code == 204
    assert harness.ctx.store.get("topics", topic["id"])["completed"] is False


def stroke(color="#1D4ED8"):
    return {"id": str(uuid4()), "color": color, "width": 0.004, "points": [[0.1, 0.2], [0.3, 0.4]]}


def test_annotations_create_update_conflict_and_drive_storage(harness):
    child, _, document = seed(harness)
    path = f"/api/annotations/children/{child['id']}/documents/{document['id']}/pages/3"
    empty = harness.call("GET", path, role="learner").json()
    assert empty["revision"] == 0 and empty["strokes"] == []
    created = harness.call("PUT", path, role="learner", json={"base_revision": 0, "strokes": [stroke()]})
    assert created.status_code == 200 and created.json()["revision"] == 1
    updated = harness.call("PUT", path, role="learner", json={"base_revision": 1, "strokes": [stroke("#DC2626")]})
    assert updated.json()["revision"] == 2 and updated.json()["strokes"][0]["color"] == "#DC2626"
    conflict = harness.call("PUT", path, role="learner", json={"base_revision": 1, "strokes": [stroke()]})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["current"]["revision"] == 2
    # Strokes live in Drive; Sheets only holds the reference.
    row = harness.sheets.rows("Annotation References")[1]
    assert row[6] in harness.drive.files and harness.drive.files[row[6]]["folder"] == "Annotations"
    assert all("points" not in cell for cell in row)
    # Earlier revisions remain as their own Drive files.
    assert sum(1 for f in harness.drive.files.values() if f["folder"] == "Annotations") == 2


def test_annotation_page_bounds_and_size(harness):
    child, _, document = seed(harness)
    out_of_range = harness.call("GET", f"/api/annotations/children/{child['id']}/documents/{document['id']}/pages/13")
    assert out_of_range.status_code == 422
    too_many = harness.call("PUT", f"/api/annotations/children/{child['id']}/documents/{document['id']}/pages/1",
                            json={"base_revision": 0, "strokes": [stroke()] * 501})
    assert too_many.status_code == 422


def test_pdf_is_proxied_from_drive_and_cached(harness):
    _, _, document = seed(harness)
    r = harness.call("GET", f"/api/documents/{document['id']}/content", role="learner")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    harness.drive.faults.append("offline")  # a cached book still opens offline
    again = harness.call("GET", f"/api/documents/{document['id']}/content", role="learner")
    assert again.status_code == 200 and again.content == r.content


def test_drive_files_outside_root_are_refused(harness):
    child, subject, _ = seed(harness)
    outside = harness.drive.add_file(make_pdf([["Private"]]), "tax.pdf", file_id="outsideFile12345")
    harness.drive.files[outside]["inside_root"] = False
    r = harness.call("POST", f"/api/subjects/{subject['id']}/documents/from-drive",
                     json={"drive_file_id": outside})
    assert r.status_code == 403
