"""Import recovery, source isolation and individual workbook work using real SQLite/HTTP."""
import base64
import json
import pytest

from tests.pdf_fixture import make_pdf
from tests.test_interactive import prepare, start, change
from tutoring import books, interactive


def add_catalog(harness, seeded, count=2):
    harness.ctx.books.backfill()
    pdf = make_pdf([["Student exercises", "1. What did Genghis do?", "2. Where did they live?"], ["Answer key", "PRIVATE ANSWERS"]])
    path = harness.add_file(pdf, "Incoming Books/Tests.pdf")
    with harness.ctx.store.transaction() as tx:
        job = harness.ctx.books.begin(tx, seeded["history"]["id"], path, "test")
        book = tx.get("subject_books", job["book_id"])
        tx.update("subject_books", book["id"], {"status": "ready", "active_index": "test-index"})
        for i in range(count):
            eid, vid = f"exercise-test-{i}", f"version-test-{i}"
            data = {"reference": str(i + 1), "chapter": 21, "section": "Mongols", "pages": [1], "printed_page": "79",
                "prompt": "What did Genghis do?" if i == 0 else "Where did they live?", "kind": "handwritten", "optional": False,
                "answer": "PRIVATE ANSWERS", "status": "matched", "student_safe": True, "source_sha256": job["source_sha256"],
                "book_name": "Tests.pdf", "requirements": [{"topic_id": seeded["genghis"]["id"], "evidence": "They lived in felt tents."}]}
            tx.insert("exercises", {"id": eid, "book_id": book["id"], "active_version": vid})
            tx.insert("exercise_versions", {"id": vid, "exercise_id": eid, "index_id": "test-index", "data": data})
    return book


def test_incoming_stage_nested_picker_and_paired_import(harness):
    with harness.ctx.store.transaction() as tx:
        child = tx.insert("children", {"name": "Lucas"})
        subject = tx.insert("subjects", {"child_id": child["id"], "name": "History"})
    pdf = make_pdf([["A real lesson", "A sufficiently long sentence from the actual textbook."]])
    harness.add_file(pdf, "Incoming Books/Future/Textbook.pdf")
    assert harness.call("GET", "/api/books/incoming").json()["books"][0]["path"] == "Incoming Books/Future/Textbook.pdf"
    staged = harness.call("POST", "/api/books/stage", files={"file": ("Workbook.pdf", make_pdf([["Exercise one"]]), "application/pdf")}).json()
    payload = {"books": [{"path": "Incoming Books/Future/Textbook.pdf", "role": "textbook"}, {"path": staged["path"], "role": "workbook"}]}
    first = harness.call("POST", f"/api/subjects/{subject['id']}/book-imports", key="pair", json=payload)
    assert first.status_code == 200, first.text
    second = harness.call("POST", f"/api/subjects/{subject['id']}/book-imports", key="pair", json=payload)
    assert second.json() == first.json()
    assert len(harness.ctx.store.all("book_imports")) == 2
    links = harness.ctx.store.all("subject_books")
    assert next(b for b in links if b["role"] == "workbook")["companion_id"] == next(b for b in links if b["role"] == "textbook")["id"]
    assert harness.call("POST", f"/api/subjects/{subject['id']}/book-imports", json={"books": [{"path": "../evil.pdf", "role": "textbook"}]}).status_code == 403


def test_eligibility_uses_subsections_and_optional_status(harness, monkeypatch):
    seeded, _ = prepare(harness, monkeypatch)
    book = add_catalog(harness, seeded)
    with harness.ctx.store.transaction() as tx:
        v = tx.get("exercise_versions", "version-test-1")
        d = dict(v["data"])
        d["requirements"] += [{"topic_id": seeded["conquest"]["id"], "evidence": "Kublai Khan became emperor."}]
        tx.update("exercise_versions", v["id"], {"data": d})
    assert [e["id"] for e in harness.ctx.books.eligible(seeded["genghis"])] == ["exercise-test-0"]
    response = harness.call("GET", f"/api/subjects/{seeded['history']['id']}/resources")
    assert response.status_code == 200 and "PRIVATE ANSWERS" not in response.text
    with harness.ctx.store.transaction() as tx:
        d = dict(tx.get("exercise_versions", "version-test-1")["data"])
        d.update(optional=True, requirements=[{"topic_id": seeded["genghis"]["id"], "evidence": "They lived in felt tents."}])
        tx.update("exercise_versions", "version-test-1", {"data": d})
    assert len(harness.ctx.books.eligible(seeded["genghis"])) == 1
    assert len(harness.ctx.books.eligible(seeded["genghis"], True)) == 2
    assert harness.ctx.books.exercises(book["id"])[0]["work_status"] == "available"


def test_eligible_numbered_exercises_keep_source_order_past_nine(harness,monkeypatch):
    seeded,_=prepare(harness,monkeypatch)
    add_catalog(harness,seeded,count=4)
    with harness.ctx.store.transaction() as tx:
        for i,reference in enumerate(('12','9','11','10')):
            row=tx.get('exercise_versions',f'version-test-{i}')
            tx.update('exercise_versions',row['id'],{'data':{**row['data'],'reference':reference}})
    assert [e['reference'] for e in harness.ctx.books.eligible(seeded['genghis'])]==['9','10','11','12']




def workbook_guide(harness, monkeypatch):
    seeded, _ = prepare(harness, monkeypatch)
    add_catalog(harness, seeded)
    response = harness.call("POST", "/api/tutor/reader/guide", json={"learner": seeded["lucas"]["id"], "topic": seeded["genghis"]["id"], "rewrite": True})
    assert response.status_code == 200, response.text
    guide = response.json()
    assert len([a for a in guide["actions"] if a.get("exercise_id")]) == 2
    assert not harness.ctx.store.all("assignment_items")
    state = start(harness, seeded, guide)
    first = next(a for a in guide["actions"] if a.get("exercise_id"))
    generic = guide["actions"][0]
    state = change(harness, state, "playback", sentence_index=generic["resume_index"], action_id=generic["id"])
    state = change(harness, state, "skip")
    state = change(harness, state, "continue")
    state = change(harness, state, "playback", sentence_index=first["resume_index"], action_id=first["id"])
    return seeded, guide, state


def test_practice_after_final_topic_does_not_change_reading_completion(harness, monkeypatch):
    seeded, _ = prepare(harness, monkeypatch)
    add_catalog(harness, seeded, 1)
    with harness.ctx.store.transaction() as tx:
        for topic in tx.all("topics"):
            tx.update("topics", topic["id"], {"completed": True})
    response = harness.call("POST", "/api/exercises/exercise-test-0/practice")
    assert response.status_code == 200, response.text
    sid = response.json()["session_id"]
    state = harness.call("GET", f"/api/tutor/sessions/{sid}/conversation").json()
    assert state["playback"]["reading_finished"] and state["playback"]["action_id"] == "practice"
    state = change(harness, state, "skip")
    state = change(harness, state, "continue")
    state = change(harness, state, "interactive-finish")
    assert state["status"] == "completed"
    assert all(t["completed"] for t in harness.ctx.store.all("topics"))
    assert harness.ctx.store.all("assignment_items")[0]["status"] == "skipped"




def test_new_sessions_cannot_start_guides_missing_new_core_exercises(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch)
    add_catalog(harness, seeded, 1)
    response = harness.call("POST", "/api/tutor/interactive/start", json={"learner": seeded["lucas"]["id"], "topic": seeded["genghis"]["id"], "guide_id": guide["guide_id"]})
    assert response.status_code == 400 and "update" in response.text.lower()
    assert not harness.ctx.store.all("assignment_items")


def test_changed_incoming_content_and_shared_learner_sources_are_retained(harness):
    pdf = make_pdf([["Original source book"]])
    replacement = make_pdf([["A different incoming book"]])
    path = harness.add_file(pdf, "Incoming Books/Source.pdf")
    with harness.ctx.store.transaction() as tx:
        first = tx.insert("children", {"name": "Lucas"})
        second = tx.insert("children", {"name": "Mila"})
        a = tx.insert("subjects", {"child_id": first["id"], "name": "History", "folder": "Lucas/History"})
        b = tx.insert("subjects", {"child_id": second["id"], "name": "History", "folder": "Mila/History"})
        one = harness.ctx.books.begin(tx, a["id"], path, "reference")
        two = harness.ctx.books.begin(tx, b["id"], path, "reference")
    book = harness.ctx.store.get("subject_books", one["book_id"])
    doc = harness.ctx.store.get("documents", book["document_id"])
    harness.add_file(replacement, path)
    harness.ctx.books._move(one, book, doc, pdf)
    filed = harness.ctx.store.get("documents", doc["id"])
    assert filed["file_path"] == "Lucas/History/Books/Source.pdf"
    assert (harness.drive / path).read_bytes() == replacement
    harness.ctx.books._move(two, harness.ctx.store.get("subject_books", two["book_id"]), filed, pdf)
    assert harness.ctx.store.get("documents", doc["id"])["file_path"] == filed["file_path"]
    assert not (harness.drive / "Mila/History/Books/Source.pdf").exists()


