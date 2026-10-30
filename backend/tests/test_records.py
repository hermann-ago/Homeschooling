"""Parent tables retain learning evidence, filter consistently, and never expose teacher storage."""
import csv
import io
from datetime import date

import pytest

from tests.test_tutoring import seed_history
from tests.test_workbooks import add_catalog


def seed_records(harness):
    s = seed_history(harness)
    with harness.ctx.store.transaction() as tx:
        child = tx.insert("children", {"name": "Mila"})
        subject = tx.insert("subjects", {"name": "Math", "child_id": child["id"]})
        topic = tx.insert("topics", {"subject_id": subject["id"], "title": "Numbers", "page_start": 1, "page_end": 1})
        tx.insert("tutor_sessions", {"id": "mila-lesson", "child_id": child["id"], "subject_id": subject["id"], "topic_id": topic["id"], "status": "completed", "date": date(2026, 9, 25)})
        for n in range(30):
            tx.insert("attempts", {"id": f"answer-{n:02}", "child_id": s["lucas"]["id"], "session_id": "2026-09-24-genghis", "topic_id": s["genghis"]["id"], "question_ref": f"Q{n+1}",
                "first_answer": "=1+1" if n == 0 else f"Original words {n}", "first_result": "Partly correct", "help_given": "Look at the map", "revised_answer": "The corrected answer", "after_help_result": "With help", "independence": "with_help"})
        tx.insert("attempts", {"id": "other-child", "child_id": child["id"], "session_id": "mila-lesson", "topic_id": topic["id"], "question_ref": "1", "first_answer": "2", "first_result": "Correct"})
        tx.insert("reviews", {"id": "review-map", "child_id": s["lucas"]["id"], "topic_id": s["genghis"]["id"], "concept": "Finding Mongolia", "status": "Open", "next_due": date(2026, 9, 26), "evidence": "Needed a map prompt", "last_practice": date(2026, 9, 24)})
    return s, subject


def test_parent_filters_pages_details_and_csv_are_consistent_and_read_only(harness):
    s, other = seed_records(harness)
    before = harness.ctx.store.all("attempts")
    query = {"view": "answers", "child_id": s["lucas"]["id"], "subject_id": s["history"]["id"], "date_from": "2026-09-24", "date_to": "2026-09-24", "sort": "reference", "order": "asc"}
    first = harness.call("GET", "/api/records", params=query)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["total"] == 30 and len(body["rows"]) == 25
    assert all(r["child"] == "Lucas" and r["date"] == "2026-09-24" and r["help"] == "Look at the map" for r in body["rows"])
    second = harness.call("GET", "/api/records", params={**query, "page": 2}).json()
    assert len(second["rows"]) == 5 and not {r["id"] for r in body["rows"]} & {r["id"] for r in second["rows"]}
    search = harness.call("GET", "/api/records", params={**query, "q": "Original words 29", "status": "Partly correct"}).json()
    assert search["total"] == 1 and search["rows"][0]["revised_answer"] == "The corrected answer"
    response = harness.call("GET", "/api/records/export", params=query)
    downloaded = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(downloaded) == 31 and "'=1+1" in downloaded[1]
    assert harness.call("GET", "/api/records", params={**query, "subject_id": other["id"]}).status_code == 400
    assert harness.call("POST", "/api/records", json={"first_answer": "changed"}).status_code == 405
    assert harness.ctx.store.all("attempts") == before
    harness.restart()
    assert harness.call("GET", "/api/records", params=query).json()["total"] == 30


@pytest.mark.parametrize("view", ["answers", "lessons", "reviews", "pending", "reading", "exercises", "preparation"])
def test_all_views_are_family_only_and_hide_private_teacher_content(harness, view):
    s, _ = seed_records(harness)
    add_catalog(harness, s)
    response = harness.call("GET", "/api/records", params={"view": view})
    assert response.status_code == 200, response.text
    assert "PRIVATE ANSWERS" not in response.text and "SECRET-KEY" not in response.text
    assert harness.call("GET", "/api/records", params={"view": view}, role="tutor").status_code == 403
    assert harness.call("GET", "/api/records/export", params={"view": view}, role="tutor").status_code == 403


def test_unfinished_checkpoint_reviews_and_reading_understanding_are_distinct(harness):
    s, _ = seed_records(harness)
    pending = harness.call("GET", "/api/records", params={"view": "pending", "child_id": s["lucas"]["id"]}).json()
    assert pending["rows"][0]["next"] == "What did the man who spoke up do next?"
    reviews = harness.call("GET", "/api/records", params={"view": "reviews", "status": "Open"}).json()
    assert reviews["rows"][0]["due"] == "2026-09-26"
    reading = harness.call("GET", "/api/records", params={"view": "reading", "status": "Completed"}).json()
    assert reading["rows"][0]["understanding"] == "Not checked"
    assert harness.call("GET", "/api/records", params={"view": "teacher_keys"}).status_code == 422
    assert harness.call("GET", "/api/records", params={"sort": "answer_source"}).status_code == 400
    assert harness.call("GET", "/api/records", params={"date_from": "2026-10-02", "date_to": "2026-10-01"}).status_code == 400
