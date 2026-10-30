"""Import recovery, source isolation and individual workbook work using real SQLite/HTTP."""
import base64
import json
import pytest

from tests.pdf_fixture import make_pdf
from tests.test_interactive import prepare, start, change
from tutoring import books, interactive


def test_scan_accepts_single_chapter_qualified_numbers_but_rejects_missing_and_duplicate_questions(harness, monkeypatch):
    pdf = make_pdf([["Chapter 41 Test", "1. Where did they settle?", "2. Why did they leave?"]])
    result = {"pages": [{"page": 1, "text": "", "native_reliable": True,
        "student_safe": True, "teacher_material": False, "headings": []}], "exercises": [
        {"reference": "Chapter 41, 1", "chapter": 41, "pages": [1], "prompt": "Where did they settle?", "kind": "handwritten"},
        {"reference": "Chapter 41, 2", "chapter": 41, "pages": [1], "prompt": "Why did they leave?", "kind": "handwritten"}]}
    monkeypatch.setattr(books, "numbered_source", lambda *args: [(41, 1, 1), (41, 1, 2)])
    monkeypatch.setattr(books, "ask", lambda *args: result)
    assert len(books.scan_unit(harness.ctx, pdf, "test", 1, 1)["exercises"]) == 2
    result["exercises"].pop()
    with pytest.raises(ValueError, match="omitted original"):
        books.scan_unit(harness.ctx, pdf, "test", 1, 1)
    result["exercises"] += [{**result["exercises"][0], "reference": "2"}, dict(result["exercises"][0])]
    with pytest.raises(ValueError, match="duplicated"):
        books.scan_unit(harness.ctx, pdf, "test", 1, 1)
    assert books.question_number("Questions 1–3") is None


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


def test_import_units_survive_failure_restart_and_collision(harness, monkeypatch):
    with harness.ctx.store.transaction() as tx:
        child = tx.insert("children", {"name": "Lucas"})
        subject = tx.insert("subjects", {"child_id": child["id"], "name": "History", "folder": "Lucas/History"})
    pdf = make_pdf([[f"Page {n}", "A sufficiently long original teaching passage."] for n in range(1, 11)])
    harness.add_file(pdf, "Incoming Books/Textbook.pdf")
    harness.add_file(make_pdf([["A different book"]]), "Lucas/History/Books/Textbook.pdf")
    response = harness.call("POST", f"/api/subjects/{subject['id']}/book-imports", json={"books": [{"path": "Incoming Books/Textbook.pdf", "role": "textbook"}]}).json()
    job_id = response["jobs"][0]["id"]
    calls = []
    def scan(ctx, source, role, first, last):
        calls.append(first)
        if first == 9 and calls.count(9) == 1:
            raise ValueError("network failure")
        return {"pages": [{"page": n, "text": f"Page {n}\nA sufficiently long original teaching passage.", "headings": [f"Page {n}"], "student_safe": True} for n in range(first,last+1)], "exercises": []}
    monkeypatch.setattr(books, "scan_unit", scan)
    harness.ctx.books.process(job_id)
    assert harness.ctx.store.get("book_imports", job_id)["status"] == "failed"
    assert (harness.drive / "Incoming Books/Textbook.pdf").exists()
    harness.restart()
    assert harness.call("POST", f"/api/book-imports/{job_id}/retry").status_code == 200
    retried = harness.ctx.store.get("book_imports", job_id)
    assert retried["done"] == 8 and retried["stage"] == "Reading pages"
    harness.ctx.books.process(job_id)
    job = harness.ctx.store.get("book_imports", job_id)
    assert calls == [1, 9, 9]
    assert job["status"] == "ready" and job["destination_path"].endswith("Textbook-2.pdf")
    assert not (harness.drive / "Incoming Books/Textbook.pdf").exists()
    assert (harness.drive / job["destination_path"]).read_bytes() == pdf
    assert len(harness.ctx.store.all("topics")) == 10


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
    preview = harness.call("GET", "/api/exercises/exercise-test-0/preview")
    assert preview.status_code == 200 and b"PRIVATE ANSWERS" not in preview.content
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


@pytest.mark.parametrize("invalid_kind", ["unknown", "duplicate"])
def test_inconsistent_matches_wait_for_review_and_reuse_saved_response(harness, monkeypatch, invalid_kind):
    seeded, _ = prepare(harness, monkeypatch)
    book = add_catalog(harness, seeded, 1)
    doc = harness.ctx.store.get("documents", book["document_id"])
    catalog = [{"exercise_id": "original-exercise", "reference": "1", "chapter": None,
        "section": "", "pages": [1], "prompt": "Where did they live?"}]
    monkeypatch.setattr(harness.ctx.books, "_raw_exercises", lambda *args: catalog)
    monkeypatch.setattr(harness.ctx.books, "_check_catalog", lambda *args: None)
    calls = []
    def propose(*args):
        calls.append(True)
        item = {"exercise_id": "foreign-exercise" if invalid_kind == "unknown" else "original-exercise",
            "requirements": [{"topic_id": seeded["genghis"]["id"], "evidence": "They lived in felt tents."}],
            "clear": True, "reason": "A proposed link"}
        return {"matches": [item] if invalid_kind == "unknown" else [item, dict(item)]}
    monkeypatch.setattr(books, "ask", propose)
    companion = next(b for b in harness.ctx.store.all("subject_books") if b["role"] == "textbook")
    matches = harness.ctx.books._matches(book, doc, companion, {})
    assert set(matches) == {"original-exercise"}
    assert matches["original-exercise"]["status"] == "needs_review"
    assert matches["original-exercise"]["requirements"] == []
    assert harness.ctx.books._matches(book, doc, companion, {}) == matches
    assert len(calls) == 1


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


def test_one_photo_saves_separate_answers_and_missing_work_stays_pending(harness, monkeypatch):
    seeded, guide, state = workbook_guide(harness, monkeypatch)
    assert len(harness.ctx.store.all("assignment_items")) == 2
    photo = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZlUAAAAASUVORK5CYII=")
    uploaded = harness.call("POST", f"/api/tutor/sessions/{state['session_id']}/evidence", data={"expected_revision": state["revision"], "action_id": state["playback"]["action_id"]}, files={"file": ("answers.png", photo, "image/png")}).json()
    state = harness.call("GET", f"/api/tutor/sessions/{state['session_id']}/conversation").json()
    def assess(prompt, images, models, **kwargs):
        tasks = json.loads(prompt.split("Item context is teacher-only:\n")[1])
        return {"feedback": "One answer checked; one still missing.", "items": [{"item_id": t["item_id"], "feedback": "Correct." if i == 0 else "Please send the missing answer.", "result": "Correct" if i == 0 else "Unanswered", "transcription": "He united the tribes." if i == 0 else None, "ready_to_continue": i == 0} for i,t in enumerate(tasks)]}
    monkeypatch.setattr(interactive, "gemini_workbook", assess)
    payload = {"action_id": state["playback"]["action_id"], "message_id": "photo-items", "evidence_ids": [uploaded["evidence_id"]]}
    state = change(harness, state, "answer", **payload)
    statuses = [i["status"] for i in harness.ctx.store.all("assignment_items")]
    assert sorted(statuses) == ["pending", "reviewed"]
    attempts = harness.ctx.store.find("attempts", session_id=state["session_id"])
    assert len(attempts) == 2 and len({a["exercise_id"] for a in attempts}) == 2
    assert any(a["first_result"] == "Unanswered" and a["independence"] == "not_assessed" for a in attempts)
    change(harness, state, "answer", **payload)
    assert len(harness.ctx.store.find("attempts", session_id=state["session_id"])) == 2
    harness.restart()
    restored = harness.call("GET", f"/api/tutor/sessions/{state['session_id']}/conversation").json()
    assert restored["playback"]["action_id"] == state["playback"]["action_id"]
    assert "PRIVATE ANSWERS" not in json.dumps(restored)


def test_mapping_versions_pin_started_work_and_mark_future_guides_stale(harness, monkeypatch):
    seeded, guide, state = workbook_guide(harness, monkeypatch)
    ex = harness.ctx.store.get("exercises", "exercise-test-0")
    response = harness.call("PUT", "/api/exercises/exercise-test-0", json={"expected_revision": ex["revision"], "optional": True,
        "requirements": [{"topic_id": seeded["genghis"]["id"], "evidence": "They lived in felt tents."}]})
    assert response.status_code == 200, response.text
    assert len(harness.call("GET", "/api/exercises/exercise-test-0/history").json()) == 2
    assert harness.ctx.store.all("assignment_items")[0]["version_id"] == "version-test-0"
    params = {"learner": seeded["lucas"]["id"], "topic": seeded["genghis"]["id"]}
    assert not harness.call("GET", "/api/tutor/reader", params=params).json()["guide"]["current"]
    assert harness.call("GET", "/api/tutor/reader", params={**params,"session":state["session_id"]}).json()["guide"]["current"]


def test_failed_assessment_preserves_work_and_skip(harness, monkeypatch):
    _, _, state = workbook_guide(harness, monkeypatch)
    monkeypatch.setattr(interactive, "gemini_workbook", lambda *args: (_ for _ in ()).throw(ValueError("offline")))
    state = change(harness, state, "answer", action_id=state["playback"]["action_id"], message_id="saved-failure", text="He united the tribes.")
    assert state["error"] and state["playback"]["action_id"]
    assert harness.ctx.store.get("lesson_dialogue", "saved-failure")["text"] == "He united the tribes."
    assert not harness.ctx.store.all("attempts")
    state = change(harness, state, "skip")
    assert any(i["status"] == "skipped" for i in harness.ctx.store.all("assignment_items"))


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


@pytest.mark.parametrize("qualified_reference", [False, True])
def test_reviewed_maps_keys_and_old_answers_are_preserved(harness, monkeypatch, qualified_reference):
    seeded, _ = prepare(harness, monkeypatch)
    book = add_catalog(harness, seeded, 1)
    doc = harness.ctx.store.get("documents", book["document_id"])
    raw = [{"reference": f"Chapter 21, {q}" if qualified_reference and q == 1 else str(q), "section": "Mongols", "chapter": 21, "pages": [1], "printed_page": "79",
        "prompt": f"Original question {q}", "kind": "handwritten", "optional": False} for q in (1, 2, 4)]
    with harness.ctx.store.transaction() as tx:
        tx.update("chapters", f"{seeded['history']['id']}:21", {"test_document_id": doc["id"], "test_pdf_start": 1, "test_pdf_end": 1})
        tx.update("teacher_keys", f"{seeded['history']['id']}:21:1", {"exception": "Reviewed key exception"})
        tx.insert("book_units", {"id": "reviewed-source", "sha256": doc["sha256"], "role": "test", "version": books.SCAN_VERSION,
            "first_page": 1, "last_page": 2, "data": {"pages": [{"page": 1, "text": "Student exercises", "student_safe": True}, {"page": 2, "text": "PRIVATE ANSWERS", "student_safe": False}], "exercises": raw}})
        old = tx.insert("attempts", {"id": "old-Q1", "session_id": "2026-09-24-genghis", "child_id": seeded["lucas"]["id"],
            "topic_id": seeded["genghis"]["id"], "chapter": 21, "question_ref": "Q1 / book 79 (PDF 82)", "first_answer": "Original answer",
            "first_result": "Correct", "independence": "independent"})
    original = harness.ctx.store.get("attempts", old["id"])
    maps = harness.ctx.store.all("question_maps")
    catalog = harness.ctx.books._raw_exercises(book, doc)
    monkeypatch.setattr(books, "ask", lambda *args: {"matches": [{"exercise_id": e["exercise_id"], "requirements": [], "clear": False, "reason": "uncertain"} for e in catalog]})
    companion = next(b for b in harness.ctx.store.all("subject_books") if b["role"] == "textbook")
    matches = harness.ctx.books._matches(book, doc, companion, {})
    first = next(e for e in catalog if books.question_number(e["reference"]) == 1)
    assert matches[first["exercise_id"]]["answer"] == "SECRET-KEY-ANSWER"
    assert matches[first["exercise_id"]]["exception"] == "Reviewed key exception"
    assert next(m for e,m in matches.items() if e == first["exercise_id"])["requirements"][0]["topic_id"] == seeded["genghis"]["id"]
    harness.ctx.books._publish(book, doc, {"index_id": "reviewed-index"}, matches, "ready")
    assert harness.ctx.store.all("question_maps") == maps
    assert harness.ctx.store.get("attempts", old["id"]) == original
    assert len(harness.ctx.store.all("exercise_attempt_links")) == 1
    assert [e["reference"] for e in harness.ctx.books.eligible(seeded["genghis"])] == ["2"]
    public = harness.call("GET", f"/api/subjects/{seeded['history']['id']}/resources")
    assert "Original answer" in public.text and "SECRET-KEY" not in public.text
    with harness.ctx.store.transaction() as tx:
        tx.update("topics", seeded["genghis"]["id"], {"stop_before": None})
    changed = harness.ctx.books._matches(book, doc, companion, {})
    assert changed[first["exercise_id"]]["status"] == "needs_review"


def test_scan_covers_scanned_pages_and_refuses_omissions(harness, monkeypatch):
    pdf = make_pdf([[], ["Student question"], ["Answer key", "SECRET ANSWER"]])
    proposed = {"pages": [
        {"page": 1, "text": "Faithfully transcribed scanned page", "student_safe": True, "headings": []},
        {"page": 2, "text": "Student question", "student_safe": True, "headings": []},
        {"page": 3, "text": "Answer key SECRET ANSWER", "student_safe": True, "headings": []},
    ], "exercises": [{"reference": "1", "section": "Practice", "pages": [1, 2], "prompt": "Original instructions continued on page two", "kind": "handwritten"}]}
    monkeypatch.setattr(books, "ask", lambda *args: books.ScanResult.model_validate(proposed).model_dump())
    result = books.scan_unit(harness.ctx, pdf, "workbook", 1, 3)
    assert result["pages"][0]["text"] == "Faithfully transcribed scanned page"
    assert not result["pages"][2]["student_safe"]
    assert result["exercises"][0]["pages"] == [1, 2]
    proposed["pages"].pop()
    with pytest.raises(ValueError, match="omitted"):
        books.scan_unit(harness.ctx, pdf, "workbook", 1, 3)


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


def test_answer_supplied_during_reading_cannot_be_independent_work(harness, monkeypatch):
    seeded, _ = prepare(harness, monkeypatch)
    add_catalog(harness, seeded, 1)
    guide = harness.call("POST", "/api/tutor/reader/guide", json={"learner": seeded["lucas"]["id"], "topic": seeded["genghis"]["id"], "rewrite": True}).json()
    state = start(harness, seeded, guide)
    state = change(harness, state, "playback", sentence_index=0, ask_question=True)
    monkeypatch.setattr(interactive, "gemini_turn", lambda *args: {"feedback": "The answer is: He united the tribes.", "result": "Unanswered", "ready_to_continue": True})
    state = change(harness, state, "answer", action_id=state["playback"]["action_id"], message_id="reading-help", text="Tell me what he did with the tribes.")
    state = change(harness, state, "continue")
    generic = guide["actions"][0]
    state = change(harness, state, "playback", sentence_index=generic["resume_index"], action_id=generic["id"])
    state = change(harness, state, "skip")
    state = change(harness, state, "continue")
    work = next(a for a in guide["actions"] if a.get("exercise_id"))
    state = change(harness, state, "playback", sentence_index=work["resume_index"], action_id=work["id"])
    def assess(prompt, images, models, **kwargs):
        tasks = json.loads(prompt.split("Item context is teacher-only:\n")[1])
        assert "Other help supplied during this lesson" in prompt
        return {"feedback": "Correct with the supplied answer.", "items": [{"item_id": t["item_id"], "feedback": "Correct.", "result": "Correct", "ready_to_continue": True} for t in tasks]}
    monkeypatch.setattr(interactive, "gemini_workbook", assess)
    state = change(harness, state, "answer", action_id=work["id"], message_id="assisted-item", text="He united the tribes.")
    attempt = harness.ctx.store.find("attempts", exercise_id="exercise-test-0")[0]
    assert attempt["independence"] == "with_help" and attempt["help_given"]
    review = harness.ctx.store.find("reviews", exercise_id="exercise-test-0")[0]
    assert review["status"] == "Open"
