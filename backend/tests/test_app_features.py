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
    assert topic == {"completed": True, "completed_at": recorded_at, "completion_source": "manual"}
    mark_topic_completed(topic, datetime(2026, 8, 11, tzinfo=timezone.utc))
    assert topic["completed_at"] == recorded_at  # the original time is kept
    mark_topic_incomplete(topic)
    assert topic == {"completed": False, "completed_at": None, "completion_source": None}


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


def test_clearing_keeps_completed_history_and_today_but_removes_future_completed_topics(harness):
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
        finished_today = add(done, today, True)  # today's lesson was done: the day stays used
        add(done, today + timedelta(days=1), True)
        add(remaining, today - timedelta(days=1), False)
        add(remaining, today + timedelta(days=1), False)
        future_progress = add(remaining, today + timedelta(days=2), True)
    with store.transaction() as tx:
        assert _clear_reschedulable_slots(child["id"], today, tx) == 3
    assert {s["id"] for s in store.all("scheduled_slots")} == {historical, finished_today, future_progress}
    assert len(store.all("completions")) == 3  # completions of removed slots were cascaded


def test_replanning_after_a_lesson_finished_today_does_not_add_another_today(harness):
    from services.scheduler_engine import recalculate_schedule
    child, subject, _ = seed(harness)
    today = date(2026, 11, 3)  # a Tuesday
    store = harness.ctx.store
    with store.transaction() as tx:
        tx.update("subjects", subject["id"], {"weekdays": [1, 3]})
        tx.insert("time_windows", {"child_id": child["id"], "weekday": 1, "start_time": "09:00", "end_time": "10:00"})
        tx.insert("time_windows", {"child_id": child["id"], "weekday": 3, "start_time": "09:00", "end_time": "10:00"})
        plague = tx.insert("topics", {"subject_id": subject["id"], "title": "The Plague", "page_start": 1, "page_end": 1,
                                      "chapter_order": 1, "completed": True})
        nxt = tx.insert("topics", {"subject_id": subject["id"], "title": "A New Way of Living", "page_start": 2,
                                   "page_end": 2, "chapter_order": 2})
        slot = tx.insert("scheduled_slots", {"child_id": child["id"], "subject_id": subject["id"], "topic_id": plague["id"],
                                             "date": today, "time_start": "09:00", "time_end": "10:00", "page_from": 1, "page_to": 1})
        tx.insert("completions", {"slot_id": slot["id"]})
    with store.transaction() as tx:
        recalculate_schedule(child["id"], tx, today=today)
    planned = {s["topic_id"]: s["date"] for s in store.all("scheduled_slots")}
    assert planned == {plague["id"]: today, nxt["id"]: date(2026, 11, 5)}
    # Even when today's slot is already gone, a lesson finished in the app today keeps the day used.
    with store.transaction() as tx:
        tx.delete("scheduled_slots", slot["id"])
        tx.insert("tutor_sessions", {"id": "plague-session", "child_id": child["id"], "subject_id": subject["id"], "topic_id": plague["id"],
            "date": today, "status": "completed", "finished_at": datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)})
    with store.transaction() as tx:
        recalculate_schedule(child["id"], tx, today=today)
    assert {s["topic_id"]: s["date"] for s in store.all("scheduled_slots")} == {nxt["id"]: date(2026, 11, 5)}


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


def test_lesson_lists_pages_added_from_other_books_in_order(harness):
    _, subject, document = seed(harness)
    with harness.ctx.store.transaction() as tx:
        lesson = tx.insert("topics", {"subject_id": subject["id"], "title": "Lesson", "page_start": 1, "page_end": 2,
                                      "document_id": document["id"]})
        extra = tx.insert("topics", {"subject_id": subject["id"], "title": "Map", "page_start": 5, "page_end": 6,
                                     "document_id": document["id"]})
        extra2 = tx.insert("topics", {"subject_id": subject["id"], "title": "Poem", "page_start": 7, "page_end": 7})
    for insert in (extra, extra2):
        r = harness.call("POST", "/api/canvas/insert", json={"parent_topic_id": lesson["id"], "insert_topic_id": insert["id"]})
        assert r.status_code == 201
    listed = harness.call("GET", f"/api/canvas/inserts/{lesson['id']}").json()
    assert [i["insert_topic_title"] for i in listed] == ["Map", "Poem"]
    assert listed[0]["insert_document_id"] == document["id"] and listed[0]["insert_page_start"] == 5
    assert harness.call("GET", "/api/canvas/inserts/99999").status_code == 404


def test_books_are_revalidated_by_checksum_and_only_text_is_compressed(harness):
    child, _, document = seed(harness)
    first = harness.call("GET", f"/api/documents/{document['id']}/content")
    assert first.status_code == 200 and first.content.startswith(b"%PDF")
    assert first.headers["etag"] == f'"{document["sha256"]}"'
    assert "content-encoding" not in first.headers  # book bytes pass through as they are
    again = harness.client.get(f"/api/documents/{document['id']}/content", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304 and again.content == b""
    listing = harness.client.get(f"/api/checklist/{child['id']}/week", headers={"Accept-Encoding": "gzip"})
    assert listing.status_code == 200


def test_json_responses_are_gzipped_when_large(harness):
    _, subject, _ = seed(harness)
    with harness.ctx.store.transaction() as tx:
        for n in range(60):
            tx.insert("topics", {"subject_id": subject["id"], "title": f"Chapter {n} with a longer title",
                                 "page_start": n, "page_end": n})
    response = harness.client.get(f"/api/subjects/{subject['id']}/topics", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200 and response.headers.get("content-encoding") == "gzip"
    assert len(response.json()) == 60


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
    # The book is not used by one of Mila's subjects yet, so her handwriting goes to her own folder.
    assert row["file_path"].startswith("Mila/Handwriting/") and (harness.drive / row["file_path"]).is_file()
    assert "points" not in str(row)
    # Earlier revisions remain as their own files.
    assert len(list((harness.drive / "Mila" / "Handwriting").glob("*.json"))) == 2


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


def test_lesson_pages_are_served_without_the_whole_book(harness):
    import io
    from pypdf import PdfReader
    _, _, document = seed(harness)
    path = f"/api/documents/{document['id']}/pages"
    r = harness.call("GET", path, role="learner", params={"first": 5, "last": 7})
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert [p.extract_text().strip() for p in PdfReader(io.BytesIO(r.content)).pages] == ["Page 5", "Page 6", "Page 7"]
    assert r.headers["etag"] == f'"{document["sha256"]}-5-7"'
    again = harness.client.get(path, params={"first": 5, "last": 7}, headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304
    # A cut range is kept, so it is served again without the book being read.
    (harness.drive / document["file_path"]).unlink()
    cached = harness.call("GET", path, role="learner", params={"first": 5, "last": 7})
    assert cached.status_code == 200 and cached.content == r.content
    for first, last in ((7, 5), (12, 13), (1, 101)):
        assert harness.call("GET", path, params={"first": first, "last": last}).status_code == 400


def test_drive_folder_books_are_listed_and_linked_by_path(harness, monkeypatch):
    import routers.subjects
    monkeypatch.setattr(routers.subjects, "analyze_curriculum", lambda text, pages: {
        "topics": [{"title": "Chapter 1", "page_start": 1, "page_end": 2}], "language": "en"})
    child, subject, _ = seed(harness)
    harness.add_file(make_pdf([["Chapter 1"], ["Chapter 2"]]), "Science/Book.pdf")
    books = harness.call("GET", "/api/documents/drive/books").json()
    assert {b["path"]: b["linked"] for b in books} == {"Books/language-arts.pdf": True, "Science/Book.pdf": False}
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


def test_subject_folder_is_fixed_at_creation_and_books_go_there(harness, monkeypatch):
    import routers.subjects
    monkeypatch.setattr(routers.subjects, "analyze_curriculum", lambda text, pages: {
        "topics": [{"title": "Chapter 1", "page_start": 1, "page_end": 2}], "language": "en"})
    child = harness.call("POST", "/api/children", json={"name": "Lucas", "grade_year": "3rd"}).json()
    subject = harness.call("POST", "/api/subjects", json={"child_id": child["id"], "name": "Science"}).json()
    assert subject["folder"] == "Lucas/3rd Grade/Science"
    pdf = make_pdf([["Chapter 1"], ["Chapter 2"]])
    r = harness.call("POST", f"/api/subjects/{subject['id']}/documents",
                     files={"file": ("Marine Biology.pdf", pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    document = harness.ctx.store.all("documents")[0]
    assert document["file_path"] == "Lucas/3rd Grade/Science/Books/Marine Biology.pdf"
    assert (harness.drive / document["file_path"]).read_bytes() == pdf
    # Moving up a grade later does not move this subject's folder.
    harness.call("PUT", f"/api/children/{child['id']}", json={"grade_year": "4th"})
    assert harness.ctx.store.get("subjects", subject["id"])["folder"] == "Lucas/3rd Grade/Science"


def test_each_subject_has_its_own_grade_and_folders_are_made_when_it_moves_up(harness, monkeypatch):
    import routers.subjects
    monkeypatch.setattr(routers.subjects, "analyze_curriculum", lambda text, pages: {
        "topics": [{"title": "Chapter 1", "page_start": 1, "page_end": 1}], "language": "en"})
    child = harness.call("POST", "/api/children", json={"name": "Lucas", "grade_year": "3rd"}).json()
    math = harness.call("POST", "/api/subjects", json={"child_id": child["id"], "name": "Math"}).json()
    history = harness.call("POST", "/api/subjects", json={"child_id": child["id"], "name": "History"}).json()
    assert (math["grade"], math["folder"]) == ("3rd", "Lucas/3rd Grade/Math")
    for kind in ("Books", "Handwriting", "Student Work", "Audio", "Lesson Content"):
        assert (harness.drive / "Lucas/3rd Grade/Math" / kind).is_dir()  # ready for books right away

    old_book = harness.call("POST", f"/api/subjects/{math['id']}/documents",
                            files={"file": ("Math 3.pdf", make_pdf([["Chapter 1"]]), "application/pdf")})
    assert old_book.status_code == 200, old_book.text

    # Lucas starts 4th grade Math while still finishing 3rd grade History.
    moved = harness.call("PUT", f"/api/subjects/{math['id']}", json={"grade": "4th"}).json()
    assert (moved["grade"], moved["folder"]) == ("4th", "Lucas/4th Grade/Math")
    assert (harness.drive / "Lucas/4th Grade/Math/Books").is_dir()
    assert harness.ctx.store.get("subjects", history["id"])["folder"] == "Lucas/3rd Grade/History"
    assert harness.ctx.store.all("documents")[0]["file_path"] == "Lucas/3rd Grade/Math/Books/Math 3.pdf"  # stays
    new_book = harness.call("POST", f"/api/subjects/{math['id']}/documents",
                            files={"file": ("Math 4.pdf", make_pdf([["Chapter 1", "Fractions"]]), "application/pdf")})
    assert new_book.status_code == 200, new_book.text
    assert any(d["file_path"] == "Lucas/4th Grade/Math/Books/Math 4.pdf" for d in harness.ctx.store.all("documents"))

    # Other edits keep the folder; a subject can also be started at another grade, or with none.
    assert harness.call("PUT", f"/api/subjects/{math['id']}", json={"weight": 1.5}).json()["folder"] == "Lucas/4th Grade/Math"
    ahead = harness.call("POST", "/api/subjects", json={"child_id": child["id"], "name": "Latin", "grade": "5th"}).json()
    assert ahead["folder"] == "Lucas/5th Grade/Latin"
    art = harness.call("POST", "/api/subjects", json={"child_id": child["id"], "name": "Art", "grade": ""}).json()
    assert (art["grade"], art["folder"]) == ("N/A", "Lucas/Art")


def test_subjects_get_their_grade_from_their_folder_at_start_once(harness):
    with harness.ctx.store.transaction() as tx:
        lucas = tx.insert("children", {"name": "Lucas", "grade_year": "4th"})
        joshua = tx.insert("children", {"name": "Joshua", "grade_year": "N/A"})
        tx.insert("subjects", {"child_id": lucas["id"], "name": "History", "folder": "Lucas/3rd Grade/History"})
        tx.insert("subjects", {"child_id": joshua["id"], "name": "Reading"})
    harness.restart()
    grades = {s["name"]: (s["grade"], s["folder"]) for s in harness.ctx.store.all("subjects")}
    assert grades == {"History": ("3rd", "Lucas/3rd Grade/History"), "Reading": ("N/A", "Joshua/Reading")}
    receipts = len(harness.ctx.store.all("operation_receipts"))
    harness.restart()
    assert len(harness.ctx.store.all("operation_receipts")) == receipts  # nothing left to fix


def test_subjects_without_a_folder_get_one_at_start(harness):
    with harness.ctx.store.transaction() as tx:
        mila = tx.insert("children", {"name": "Mila", "grade_year": "1st"})
        tx.insert("subjects", {"child_id": mila["id"], "name": "Math"})
    harness.restart()
    assert harness.ctx.store.all("subjects")[0]["folder"] == "Mila/1st Grade/Math"


def test_unfinished_lessons_move_forward_each_morning_only_when_the_family_turns_it_on(harness):
    child, subject, _ = seed(harness)
    today = date(2026, 9, 28)
    with harness.ctx.store.transaction() as tx:
        for weekday in range(5):
            tx.insert("time_windows", {"child_id": child["id"], "weekday": weekday, "start_time": "09:00",
                                       "end_time": "10:00"})
        topic = tx.insert("topics", {"subject_id": subject["id"], "title": "Missed", "page_start": 1, "page_end": 1})
        tx.insert("scheduled_slots", {"child_id": child["id"], "subject_id": subject["id"], "topic_id": topic["id"],
                                      "date": today - timedelta(days=3), "time_start": "09:00", "time_end": "10:00",
                                      "page_from": 1, "page_to": 1})
    early = datetime(2026, 9, 28, 7, 30)
    assert harness.ctx.move_unfinished_forward(early) == []  # off unless the family chooses it
    assert harness.call("PUT", "/api/calendar/settings/auto-replan", json={"enabled": True}).status_code == 200
    assert harness.call("GET", "/api/calendar/settings/auto-replan").json() == {"enabled": True}

    assert harness.ctx.move_unfinished_forward(early) == [child["id"]]
    dates = sorted(s["date"] for s in harness.ctx.store.find("scheduled_slots", child_id=child["id"]))
    assert dates and dates[0] >= today  # nothing left behind in the past
    assert harness.ctx.move_unfinished_forward(early) == []  # once a day


def test_moving_lessons_forward_waits_when_a_school_day_has_started(harness):
    child, subject, _ = seed(harness)
    today = date(2026, 9, 28)
    with harness.ctx.store.transaction() as tx:
        topic = tx.insert("topics", {"subject_id": subject["id"], "title": "Today", "page_start": 1, "page_end": 1})
        for day in (today - timedelta(days=1), today):
            tx.insert("scheduled_slots", {"child_id": child["id"], "subject_id": subject["id"], "topic_id": topic["id"],
                                          "date": day, "time_start": "09:00", "time_end": "10:00"})
    harness.call("PUT", "/api/calendar/settings/auto-replan", json={"enabled": True})
    assert harness.ctx.move_unfinished_forward(datetime(2026, 9, 28, 9, 15)) == []
    assert len(harness.ctx.store.find("scheduled_slots", child_id=child["id"])) == 2  # untouched


def test_subjects_with_chosen_weekdays_get_one_lesson_on_each_of_those_days(harness):
    from services.scheduler_engine import recalculate_schedule
    child, math, _ = seed(harness)
    monday = date(2026, 11, 2)
    with harness.ctx.store.transaction() as tx:
        for weekday in range(5):
            tx.insert("time_windows", {"child_id": child["id"], "weekday": weekday, "start_time": "08:00", "end_time": "11:00"})
        history = tx.insert("subjects", {"child_id": child["id"], "name": "History"})
        paused = tx.insert("subjects", {"child_id": child["id"], "name": "Old book"})
        for subject in (math, history, paused):
            for n in range(4):
                tx.insert("topics", {"subject_id": subject["id"], "title": f"Lesson {n}", "page_start": n + 1,
                                     "page_end": n + 1, "chapter_order": n, "is_core": True})
    assert harness.call("PUT", f"/api/subjects/{math['id']}", json={"weekdays": [0, 1, 2, 3, 4]}).status_code == 200
    assert harness.call("PUT", f"/api/subjects/{history['id']}", json={"weekdays": [3, 1]}).json()["weekdays"] == [1, 3]
    assert harness.call("PUT", f"/api/subjects/{paused['id']}", json={"weekdays": []}).status_code == 200
    assert harness.call("PUT", f"/api/subjects/{paused['id']}", json={"weekdays": [7]}).status_code == 422
    with harness.ctx.store.transaction() as tx:
        recalculate_schedule(child["id"], tx, monday)
    slots = harness.ctx.store.find("scheduled_slots", child_id=child["id"])
    days = lambda subject: sorted(s["date"] for s in slots if s["subject_id"] == subject["id"])
    assert days(math) == [monday + timedelta(days=n) for n in range(4)]
    assert days(history) == [monday + timedelta(days=n) for n in (1, 3, 8, 10)]
    assert days(paused) == []


def test_replanning_after_the_school_day_starts_tomorrow(harness):
    from services.scheduler_engine import recalculate_schedule
    child, subject, _ = seed(harness)
    with harness.ctx.store.transaction() as tx:
        tx.insert("time_windows", {"child_id": child["id"], "weekday": 0, "start_time": "08:00", "end_time": "11:00"})
        tx.insert("time_windows", {"child_id": child["id"], "weekday": 1, "start_time": "14:00", "end_time": "16:30"})
        tx.insert("topics", {"subject_id": subject["id"], "title": "Next", "page_start": 1, "page_end": 1, "is_core": True})
    for clock, first in ((datetime(2026, 11, 2, 9, 0), date(2026, 11, 2)), (datetime(2026, 11, 2, 20, 0), date(2026, 11, 3))):
        with harness.ctx.store.transaction() as tx:
            recalculate_schedule(child["id"], tx, now=clock)
        assert [s["date"] for s in harness.ctx.store.find("scheduled_slots", child_id=child["id"])] == [first]
