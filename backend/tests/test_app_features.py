"""Existing app behaviour on the SQLite store: scheduling, completion, annotations, books."""
import hashlib
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from services.completion_tracking import mark_topic_completed, mark_topic_incomplete
from services.scheduler_engine import _clear_reschedulable_slots
from tests.pdf_fixture import make_pdf


def seed(harness, pages=12):
    ctx = harness.ctx
    pdf = make_pdf([[f"Page {n}"] for n in range(1, pages + 1)])
    book_path = harness.add_file(pdf, "Books/language-arts.pdf")
    with ctx.store.transaction() as tx:
        child = tx.insert("children", {"name": "Mila", "color": "#E986B4"})
        subject = tx.insert("subjects", {"child_id": child["id"], "name": "Language Arts"})
        document = tx.insert("documents", {"file_path": book_path, "original_filename": "language-arts.pdf",
                                           "size_bytes": len(pdf), "page_count": pages,
                                           "sha256": hashlib.sha256(pdf).hexdigest(), "source": "drive"})
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
    before = len(harness.ctx.store.all("operation_receipts"))
    r = harness.call("POST", f"/api/schedule/recalculate/{child['id']}", key="recalc-1")
    assert r.status_code == 200 and r.json()["slots_created"] == 3
    assert r.headers["x-sync-state"] == "saved"
    assert len(harness.ctx.store.all("operation_receipts")) == before + 1  # one transaction
    assert len(harness.ctx.store.all("scheduled_slots")) == 3


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
    # Strokes live in the Drive folder; the database only holds the reference.
    row = harness.ctx.store.all("annotations")[0]
    assert row["file_path"].startswith("Annotations/") and (harness.drive / row["file_path"]).is_file()
    assert "points" not in str(row)
    # Earlier revisions remain as their own files.
    assert len(list((harness.drive / "Annotations").glob("*.json"))) == 2


def test_annotation_page_bounds_and_size(harness):
    child, _, document = seed(harness)
    out_of_range = harness.call("GET", f"/api/annotations/children/{child['id']}/documents/{document['id']}/pages/13")
    assert out_of_range.status_code == 422
    too_many = harness.call("PUT", f"/api/annotations/children/{child['id']}/documents/{document['id']}/pages/1",
                            json={"base_revision": 0, "strokes": [stroke()] * 501})
    assert too_many.status_code == 422


def test_pdf_is_served_from_the_drive_folder(harness):
    _, _, document = seed(harness)
    r = harness.call("GET", f"/api/documents/{document['id']}/content", role="learner")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    # A book that is missing (or not yet downloaded while offline) gives a clear 503, not a crash.
    (harness.drive / document["file_path"]).unlink()
    missing = harness.call("GET", f"/api/documents/{document['id']}/content", role="learner")
    assert missing.status_code == 503 and "missing" in missing.json()["detail"]


def test_drive_folder_books_are_listed_and_linked_by_path(harness, monkeypatch):
    import routers.subjects
    monkeypatch.setattr(routers.subjects, "analyze_curriculum", lambda text, pages: {
        "topics": [{"title": "Chapter 1", "page_start": 1, "page_end": 2}], "language": "en"})
    child, subject, _ = seed(harness)
    harness.add_file(make_pdf([["Chapter 1"], ["Chapter 2"]]), "Science/Book.pdf")
    books = harness.call("GET", "/api/documents/drive/books").json()
    assert {b["path"]: b["linked"] for b in books} == {"Books/language-arts.pdf": True, "Science/Book.pdf": False}
    assert harness.call("GET", "/api/documents/drive/books", role="learner").status_code == 403
    r = harness.call("POST", f"/api/subjects/{subject['id']}/documents/from-drive", json={"path": "Science/Book.pdf"})
    assert r.status_code == 200, r.text
    linked = [d for d in harness.ctx.store.all("documents") if d["file_path"] == "Science/Book.pdf"]
    assert len(linked) == 1 and linked[0]["page_count"] == 2


def test_drive_files_outside_root_are_refused(harness):
    child, subject, _ = seed(harness)
    (harness.drive.parent / "tax.pdf").write_bytes(make_pdf([["Private"]]))
    for path in ("../tax.pdf", str(harness.drive.parent / "tax.pdf")):
        r = harness.call("POST", f"/api/subjects/{subject['id']}/documents/from-drive", json={"path": path})
        assert r.status_code == 403, path
