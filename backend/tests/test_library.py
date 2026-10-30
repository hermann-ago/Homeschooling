"""Family library persistence, source reuse and isolation from scheduled curriculum."""
import io
from datetime import date

from pypdf import PdfReader, PdfWriter

from tests.pdf_fixture import make_pdf
from tutoring import books as book_engine


def child(h, name="Lucas"):
    with h.ctx.store.transaction() as tx:
        return tx.insert("children", {"name": name})


def get_book(h, book_id="library-02", learner=None):
    result = h.call("GET", f"/api/library/books/{book_id}", params={"child_id": learner} if learner else {})
    assert result.status_code == 200, result.text
    return result.json()


def upload(h, book_id="library-02", data=None, revision=None, key=None):
    revision = revision or get_book(h, book_id)["revision"]
    content = data or make_pdf([["A real source page. This text belongs to the uploaded book."]])
    # A network retry repeats the serialized upload, including its boundary.
    body = (f'--library-test\r\nContent-Disposition: form-data; name="expected_revision"\r\n\r\n{revision}\r\n'
            '--library-test\r\nContent-Disposition: form-data; name="file"; filename="Book.pdf"\r\n'
            'Content-Type: application/pdf\r\n\r\n').encode() + content + b'\r\n--library-test--\r\n'
    return h.client.request("POST", f"/api/library/books/{book_id}/file",
        content=body, headers={**h.headers(key=key), "Content-Type": "multipart/form-data; boundary=library-test"})


def enroll(h, learner, book_id="library-02", key=None):
    result = h.call("POST", f"/api/library/books/{book_id}/readings", json={"child_id": learner}, key=key)
    assert result.status_code == 200, result.text
    return result.json()


def index(h, learner, book_id="library-02"):
    result = h.call("POST", f"/api/library/books/{book_id}/prepare", json={"child_id": learner})
    assert result.status_code == 200, result.text
    h.ctx.books.process(result.json()["job"]["id"])
    return get_book(h, book_id, learner)["readings"][0]


def test_catalog_is_seeded_once_with_seven_stages_and_no_invented_sources(harness, monkeypatch):
    h = harness
    monkeypatch.setattr(h.ctx.ai, "generate", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("No AI for the catalog")))
    response = h.call("GET", "/api/library/books")
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["books"]) == 30 and len(body["stages"]) == 7
    assert [b["position"] for b in body["books"]] == list(range(1, 31))
    assert all(not b["document"] and not b["readings"] for b in body["books"])
    assert "different work" in body["books"][2]["source_note"]
    assert body["books"][6]["source_label"] == "TV series"
    before = h.ctx.store.all("library_books")
    h.restart()
    assert h.ctx.store.all("library_books") == before
    assert h.ctx.store.all("topics") == [] and h.ctx.store.all("book_imports") == []


def test_upload_enroll_and_restart_are_local_durable_and_idempotent(harness, monkeypatch):
    h = harness
    kid = child(h)
    monkeypatch.setattr(h.ctx.ai, "generate", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("No generation")))
    original_revision = get_book(h)["revision"]
    saved = upload(h, key="library-pdf", revision=original_revision)
    assert saved.status_code == 200, saved.text
    doc = saved.json()["document"]
    assert doc["file_path"].startswith("Family Library/Books/")
    assert (h.drive / doc["file_path"]).read_bytes().startswith(b"%PDF")
    assert upload(h, key="library-pdf", revision=original_revision).json() == saved.json()
    assert upload(h, revision=original_revision).status_code == 409
    reading = enroll(h, kid["id"], key="library-enroll")
    assert enroll(h, kid["id"], key="library-enroll") == reading
    assert enroll(h, kid["id"])["id"] == reading["id"]
    assert reading["topics"] == [] and reading["job"] is None
    assert h.ctx.store.all("book_imports") == []
    skill = h.call("GET", f"/api/subjects/{reading['subject_id']}/teaching-skill").json()["content"]
    assert "two or three quiz questions" in skill
    assert "Parents and human tutors choose and review" in skill
    assert "true/false or single-choice answers only" in skill
    h.restart()
    assert get_book(h, learner=kid["id"])["readings"][0]["id"] == reading["id"]
    assert len(h.ctx.store.all("documents")) == 1 and len(h.ctx.store.all("library_readings")) == 1


def test_index_uses_existing_engine_reuses_scans_but_never_child_completion(harness, monkeypatch):
    h = harness
    first, second = child(h), child(h, "Mila")
    pdf = make_pdf([["An opening topic", "People exchange things because each expects to benefit."],
                    ["A second topic", "A person can ask whether an argument follows from its premises."]])
    # Chapter mapping now reads local PDF contents/bookmarks instead of scanning
    # every page with a paid provider.
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf)))
    writer.add_outline_item('An opening topic', 0)
    writer.add_outline_item('A second topic', 1)
    mapped = io.BytesIO()
    writer.write(mapped)
    pdf = mapped.getvalue()
    assert upload(h, data=pdf).status_code == 200
    first_reading = enroll(h, first["id"])
    assert h.call("POST", "/api/library/books/library-02/prepare", json={"child_id": second["id"]}).status_code == 400
    scans = []
    def scan(ctx, data, role, start, end):
        scans.append((start, end))
        reader = PdfReader(io.BytesIO(data))
        return {"pages": [{"page": n, "text": reader.pages[n-1].extract_text(), "native_reliable": True,
                "student_safe": True, "teacher_material": False,
                "headings": ["An opening topic" if n == 1 else "A second topic"]} for n in range(start, end + 1)], "exercises": [], "answers": []}
    monkeypatch.setattr(book_engine, "scan_unit", scan)
    ready = index(h, first["id"])
    assert ready["job"]["status"] == "ready", ready
    assert ready["total_topics"] == 2 and not scans, ready
    first_topic = ready["topics"][0]
    assert h.call("POST", f"/api/subjects/{first_reading['subject_id']}/topics/{first_topic['id']}/toggle-complete").status_code == 200
    second_reading = enroll(h, second["id"])
    other = index(h, second["id"])
    assert other["job"]["status"] == "ready" and not scans
    assert other["completed_topics"] == 0 and other["subject_id"] != ready["subject_id"]
    assert {t["id"] for t in ready["topics"]}.isdisjoint(t["id"] for t in other["topics"])
    assert all(t["document_id"] == first_topic["document_id"] for t in other["topics"])
    assert get_book(h)["document"]["file_path"].startswith("Family Library/Books/")
    # The normal reader can open these topics, but a different child's id is refused.
    reader = h.call("GET", "/api/tutor/reader", params={"learner": second["id"], "topic": other["topics"][0]["id"]})
    assert reader.status_code == 200, reader.text
    assert reader.json()["subject_name"] == "The Law"
    assert h.call("GET", "/api/tutor/reader", params={"learner": first["id"], "topic": other["topics"][0]["id"]}).status_code in (400, 403)
    # Explicit indexing of a ready book is a no-op; it creates no duplicate work.
    before = len(h.ctx.store.all("book_imports"))
    h.call("POST", "/api/library/books/library-02/prepare", json={"child_id": second["id"]})
    assert len(h.ctx.store.all("book_imports")) == before

    # The existing guided lesson and question engine also accept a library topic.
    # Provider replies are synthetic; source, HTTP, activities and records are real.
    from tutoring import guide, interactive
    from tests.test_activity_integration import http_event
    monkeypatch.setattr(guide, "write_plan", lambda *a, **kw: ({"mode": "expand", "segments": [
        {"type": "intro", "text": "Let us read the argument."},
        {"type": "read", "from": 0, "to": 999},
        {"type": "activity", "activity_kind": "ask_question", "content": {
            "prompt": "Who expects to benefit?", "choices": [{"id": "both", "label": "Both people"}, {"id": "none", "label": "Neither person"}],
            "response_modes": ["choice"], "answer_format": "single_choice", "require_reasoning": False}},
        {"type": "recap", "text": "We checked the author's explanation."}]}, "synthetic-library-tutor"))
    monkeypatch.setattr(h.ctx.ai, "generate", lambda *a, **kw: {"findings": []})
    made = h.call("POST", "/api/tutor/reader/guide", json={"learner": second["id"], "topic": other["topics"][0]["id"]})
    assert made.status_code == 200, made.text
    started = h.call("POST", "/api/tutor/interactive/start", json={"learner": second["id"],
        "topic": other["topics"][0]["id"], "guide_id": made.json()["guide_id"]})
    assert started.status_code == 200, started.text
    from tutoring.activity_engine import service
    state = service(h.ctx).state(started.json()["session_id"])
    for _ in range(10):
        activity = state["active_activity"]
        if activity["kind"] == "ask_question":
            break
        state = http_event(h, state, "reading_done" if activity["kind"] == "read_source" and activity["status"] == "pending" else "continue")
    assert state["active_activity"]["kind"] == "ask_question"
    assert not h.ctx.store.find("attempts", child_id=second["id"])
    monkeypatch.setattr(interactive, "gemini_turn", lambda *a, **kw: {"feedback": "Each person expects to benefit.",
        "result": "Correct", "ready_to_continue": True})
    state = http_event(h, state, "submit_response", {"response_id": "library-understanding-1", "method": "choice", "choice_ids": ["both"], "assess_after_save": True})
    attempts = h.ctx.store.find("attempts", child_id=second["id"])
    assert len(attempts) == 1 and attempts[0]["topic_id"] == other["topics"][0]["id"]
    assert "Both people" in attempts[0]["first_answer"]
    assert get_book(h, learner=second["id"])["readings"][0]["completed_topics"] == 0


def test_assigned_books_have_individual_curriculum_progress_without_automatic_schedule(harness):
    h = harness
    kid = child(h)
    reading = enroll(h, kid["id"])
    with h.ctx.store.transaction() as tx:
        subject = tx.insert("subjects", {"name": "Math", "child_id": kid["id"]})
        tx.insert("topics", {"subject_id": subject["id"], "title": "Addition", "page_start": 1, "page_end": 2})
        tx.insert("topics", {"subject_id": reading["subject_id"], "title": "Optional chapter", "page_start": 1, "page_end": 900})
        tx.insert("settings", {"id": "SCHOOL_YEAR_START", "value": "2026-01-01"})
        tx.insert("settings", {"id": "SCHOOL_YEAR_END", "value": "2026-12-31"})
        tx.insert("time_windows", {"child_id": kid["id"], "weekday": date.today().weekday(), "start_time": "09:00", "end_time": "10:00"})
    subjects = h.call("GET", f"/api/subjects/by-child/{kid['id']}").json()
    assert {s["name"] for s in subjects} == {"Math", "The Law"}
    assert next(s for s in subjects if s['name'] == 'The Law')['library_book_id'] == 'library-02'
    progress = h.call("GET", f"/api/progress/{kid['id']}").json()
    assert {s["subject_name"] for s in progress["subjects"]} == {"Math", "The Law"}
    book_progress = next(s for s in progress['subjects'] if s['subject_name'] == 'The Law')
    assert book_progress['status'] == 'on_track' and book_progress['projected_finish_date'] is None
    response = h.call("POST", f"/api/schedule/recalculate/{kid['id']}")
    assert response.status_code == 200, response.text
    assert all(s["subject_id"] == subject["id"] for s in h.ctx.store.all("scheduled_slots"))


def test_bad_files_and_replacement_editions_do_not_damage_original(harness):
    h = harness
    assert upload(h, data=b"not a PDF").status_code == 400
    assert upload(h, data=b"%PDF broken").status_code == 400
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("password")
    encrypted = io.BytesIO(); writer.write(encrypted)
    assert upload(h, data=encrypted.getvalue()).status_code == 400
    saved = upload(h)
    assert saved.status_code == 200
    original = get_book(h)["document"]
    assert upload(h, data=make_pdf([["Different edition"]])).status_code == 409
    assert get_book(h)["document"] == original and len(h.ctx.store.all("documents")) == 1
    # The same bytes are reused, even when another catalog entry names that source.
    assert upload(h, book_id="library-04").json()["document"]["id"] == original["id"]
    assert h.call("POST", "/api/library/books/library-01/prepare", json={"child_id": child(h)["id"]}).status_code == 400


def test_curriculum_membership_is_per_child_and_readding_preserves_progress(harness):
    h = harness
    lucas, mila = child(h), child(h, 'Mila')
    reading = enroll(h, lucas['id'])
    with h.ctx.store.transaction() as tx:
        topic = tx.insert('topics', {'subject_id': reading['subject_id'], 'title': 'Read chapter',
            'page_start': 1, 'page_end': 3, 'completed': True})
    assert h.call('GET', f"/api/subjects/by-child/{mila['id']}").json() == []
    paused = h.call('DELETE', f"/api/library/books/library-02/readings/{lucas['id']}")
    assert paused.status_code == 200 and not paused.json()['active']
    assert h.call('GET', f"/api/subjects/by-child/{lucas['id']}").json() == []
    assert h.call('GET', f"/api/progress/{lucas['id']}").json()['subjects'] == []
    assert h.call('POST', '/api/library/books/library-02/prepare', json={'child_id': lucas['id']}).status_code == 400
    h.restart()
    again = enroll(h, lucas['id'])
    assert again['active'] and again['subject_id'] == reading['subject_id']
    assert again['completed_topics'] == 1 and again['topics'][0]['id'] == topic['id']
    assert len(h.ctx.store.all('library_readings')) == 1


def test_custom_book_validates_links_and_tutor_cannot_mutate_library(harness):
    h = harness
    assert h.call("POST", "/api/library/books", json={"title": " ", "author": "A", "stage": 1}).status_code == 422
    assert h.call("POST", "/api/library/books", json={"title": "New", "author": "A", "stage": 1, "source_url": "javascript:alert(1)"}).status_code == 422
    result = h.call("POST", "/api/library/books", json={"title": "New title", "author": "Author", "stage": 5})
    assert result.status_code == 201 and result.json()["stage_title"] == "Fiction & Sci-Fi"
    assert h.call("POST", "/api/library/books", role="tutor", json={"title": "New", "author": "Author", "stage": 1}).status_code == 403


def test_download_provenance_updates_without_changing_source_or_reading_records(harness):
    h = harness
    assert upload(h, book_id='library-01').status_code == 200
    before = get_book(h, 'library-01')
    path = '/api/library/books/library-01/source'
    payload = {'expected_revision': before['revision'], 'source_url': 'https://www.jonathangullible.com/free-book',
               'source_label': 'Official complimentary PDF', 'availability': 'Complimentary commentary edition',
               'source_note': '2004 commentary edition, downloaded from the author website.'}
    response = h.call('PATCH', path, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['document'] == before['document']
    assert response.json()['source_url'] == payload['source_url']
    assert h.call('PATCH', path, json=payload).status_code == 409
    assert h.call('PATCH', path, json={**payload, 'expected_revision': response.json()['revision'], 'source_url': 'javascript:alert(1)'}).status_code == 422
    assert not h.ctx.store.all('book_imports') and not h.ctx.store.all('library_readings')
