"""Source retrieval, combined books, key edition links and bounded recovery."""
import json

import pytest

from tests.pdf_fixture import make_pdf
from tests.test_tutoring import seed_history
from tests.test_workbooks import add_catalog
from tutoring import books, book_sources, passages


def test_combined_book_keeps_original_reading_and_exercises_but_hides_embedded_answers(harness, monkeypatch):
    s = seed_history(harness)
    text = "Rivers and Cities\nPeople built cities near rivers. The rivers supplied water."
    pdf = make_pdf([[text, "1. Why build near rivers?"], ["More Rivers", "River boats carried food."], ["Answer key", "1. PRIVATE ANSWER: water."]])
    path = harness.add_file(pdf, "Books/Combined.pdf")
    proposal = books.ScanResult.model_validate({"pages": [
        {"page": 1, "text": text + "\n1. Why build near rivers?", "student_safe": True, "native_reliable": False, "headings": ["Rivers and Cities"], "reading_blocks": [text]},
        {"page": 2, "text": "More Rivers\nRiver boats carried food.", "student_safe": True, "native_reliable": False, "headings": ["More Rivers"], "reading_blocks": ["More Rivers\nRiver boats carried food."]},
        {"page": 3, "text": "Answer key\n1. PRIVATE ANSWER: water.", "student_safe": False, "teacher_material": True, "native_reliable": False, "reading_blocks": ["PRIVATE ANSWER"]}],
        "exercises": [{"reference": "1", "chapter": 1, "pages": [1], "prompt": "Why build near rivers?"}],
        "answers": [{"reference": "1", "chapter": 1, "pages": [3], "answer": "PRIVATE ANSWER: water.", "evidence": "1. PRIVATE ANSWER: water."}]}).model_dump()
    def ask(ctx, prompt, schema, *args):
        if schema is books.ScanResult:
            return proposal
        exercises = json.loads(prompt.split("Exercises: ")[1].split("\nWhole reading outline:")[0])
        topic = next(t for t in ctx.store.all("topics") if t["title"] == "Rivers and Cities")
        return {"matches": [{"exercise_id": e["exercise_id"], "clear": True, "reason": "Verbatim support", "requirements": [{"topic_id": topic["id"], "evidence": "The rivers supplied water."}]} for e in exercises]}
    monkeypatch.setattr(books, "ask", ask)
    with harness.ctx.store.transaction() as tx:
        job = harness.ctx.books.begin(tx, s["history"]["id"], path, "combined")
    harness.ctx.books.process(job["id"])
    job = harness.ctx.store.get("book_imports", job["id"])
    assert job["status"] == "ready", job["error"]
    book = harness.ctx.store.get("subject_books", job["book_id"])
    assert book["companion_id"] == book["id"]
    topics = harness.ctx.store.find("topics", document_id=book["document_id"])
    assert len(topics) == 2 and max(t["page_end"] for t in topics) == 2
    topic = next(t for t in topics if t["title"] == "Rivers and Cities")
    public = passages.load(harness.ctx, topic)
    assert public["hide_pdf"] and "People built cities" in public["passage"]
    assert "PRIVATE ANSWER" not in json.dumps(public) and "Why build" not in public["passage"]
    exercise = harness.ctx.books.exercises(book["id"])[0]
    assert exercise["reference"] == "1" and exercise["answer_link_status"] == "linked" and "answer_source" not in exercise
    assert "PRIVATE ANSWER" not in json.dumps(exercise)
    private = harness.ctx.books.snapshot(harness.ctx.store.get("exercises", exercise["id"]))
    assert private["data"]["answer"] == "PRIVATE ANSWER: water."
    monkeypatch.setattr(books, "ask", lambda *args: pytest.fail("A restart must reuse complete units and accepted mappings"))
    harness.restart()
    with harness.ctx.store.transaction() as tx:
        repair = harness.ctx.books.rematch(tx, book["id"])
    harness.ctx.books.process(repair["id"])
    assert harness.ctx.store.get("book_imports", repair["id"])["status"] == "ready"


def test_key_requires_exact_target_and_ambiguous_answers_wait_for_review(harness):
    s = seed_history(harness)
    add_catalog(harness, s, 1)
    target = next(b for b in harness.ctx.store.all("subject_books") if b["role"] == "test")
    path = harness.add_file(make_pdf([["Answer key", "1. PRIVATE KEY"]]), "Books/Key.pdf")
    with pytest.raises(ValueError, match="belongs to"):
        with harness.ctx.store.transaction() as tx:
            harness.ctx.books.begin(tx, s["history"]["id"], path, "answer_key")
    with harness.ctx.store.transaction() as tx:
        job = harness.ctx.books.begin(tx, s["history"]["id"], path, "answer_key", answer_for=target["id"])
        key = tx.get("subject_books", job["book_id"])
        tx.update("subject_books", key["id"], {"status": "ready"})
        sha = tx.get("documents", key["document_id"])["sha256"]
        tx.insert("answer_entries", {"id": "one-key", "book_id": key["id"], "source_sha256": sha, "reference": "1", "chapter": 21, "section": "Chapter Twenty-One", "pages": [1], "answer": "PRIVATE KEY", "evidence": "1. PRIVATE KEY"})
    book_sources.refresh_keys(harness.ctx.books, target["id"])
    version = harness.ctx.books.snapshot(harness.ctx.store.get("exercises", "exercise-test-0"))
    assert version["data"]["answer"] == "PRIVATE KEY"
    with harness.ctx.store.transaction() as tx:
        tx.insert("answer_entries", {"id": "conflicting-key", "book_id": key["id"], "source_sha256": sha, "reference": "1", "chapter": 21, "pages": [1], "answer": "OTHER KEY", "evidence": "1. OTHER KEY"})
    book_sources.refresh_keys(harness.ctx.books, target["id"])
    now = harness.ctx.books.snapshot(harness.ctx.store.get("exercises", "exercise-test-0"))
    assert now["data"]["answer"] is None and now["data"]["answer_link_status"] == "needs_review"
    assert harness.ctx.store.get("exercise_versions", version["id"])["data"]["answer"] == "PRIVATE KEY"
    with harness.ctx.store.transaction() as tx:
        tx.delete("answer_entries", "conflicting-key")
    book_sources.refresh_keys(harness.ctx.books, target["id"])
    with harness.ctx.store.transaction() as tx:
        # Unlink both the legacy primary field and the current multi-book targets.
        tx.update("subject_books", key["id"], {"answer_for_id": None, "answer_for_ids": []})
    book_sources.refresh_keys(harness.ctx.books, target["id"])
    assert harness.ctx.books.snapshot(harness.ctx.store.get("exercises", "exercise-test-0"))["data"]["answer_link_status"] == "missing"


def test_retrieval_fetches_requested_missing_section_and_never_trusts_an_invented_quote(harness, monkeypatch):
    s = seed_history(harness)
    add_catalog(harness, s, 1)
    book = next(b for b in harness.ctx.store.all("subject_books") if b["role"] == "test")
    doc = harness.ctx.store.get("documents", book["document_id"])
    topics = harness.ctx.store.all("topics")
    texts = {t["id"]: harness.ctx.books.topic_text(t) for t in topics}
    batch = [{"exercise_id": "new-exercise", "prompt": "Where did they live?", "reference": "1", "section": "", "pages": [1]}]
    monkeypatch.setattr(book_sources, "candidates", lambda *args: [s["rabbi"]])
    calls = []
    def propose(ctx, prompt, schema, *args):
        calls.append(prompt)
        assert schema.model_json_schema()["$defs"]["BoundExerciseMatch"]["properties"]["exercise_id"]["const"] == "new-exercise"
        if len(calls) == 1:
            return {"matches": [{"exercise_id": "new-exercise", "clear": False, "requirements": [], "needed_topic_ids": [s["genghis"]["id"]], "reason": "Need the missing reading"}]}
        return {"matches": [{"exercise_id": "new-exercise", "clear": True, "requirements": [{"topic_id": s["genghis"]["id"], "evidence": "They lived in felt tents."}], "reason": "Found support"}]}
    monkeypatch.setattr(books, "ask", propose)
    results = book_sources.match_remaining(harness.ctx.books, book, doc, topics, texts, batch, {})
    assert len(calls) == 2 and results["new-exercise"]["status"] == "matched"
    assert book_sources.match_remaining(harness.ctx.books, book, doc, topics, texts, batch, {}) == results and len(calls) == 2
    forged = {"matches": [{"exercise_id": "another", "clear": True, "requirements": [{"topic_id": s["genghis"]["id"], "evidence": "Invented supporting answer"}], "reason": "claimed"}]}
    monkeypatch.setattr(books, "ask", lambda *args: forged)
    results = book_sources.match_remaining(harness.ctx.books, book, doc, topics, texts, [{**batch[0], "exercise_id": "another"}], {})
    assert results["another"]["status"] == "needs_review" and not results["another"]["requirements"]


def test_failed_rematch_preserves_book_readiness_and_progress_after_restart(harness, monkeypatch):
    s = seed_history(harness)
    add_catalog(harness, s, 1)
    book = next(b for b in harness.ctx.store.all("subject_books") if b["role"] == "test")
    doc = harness.ctx.store.get("documents", book["document_id"])
    raw = [{"reference": str(n), "chapter": None, "pages": [1], "section": "", "prompt": "Where did they live?", "optional": False, "kind": "handwritten"} for n in range(1, 8)]
    with harness.ctx.store.transaction() as tx:
        tx.insert("book_units", {"id": books.ident(doc["sha256"], "test", books.SCAN_VERSION, 1), "sha256": doc["sha256"], "role": "test", "version": books.SCAN_VERSION, "first_page": 1, "last_page": 2,
            "data": {"pages": [{"page": 1, "text": "Student exercises", "student_safe": True}, {"page": 2, "text": "PRIVATE ANSWERS", "student_safe": False}], "exercises": raw}})
        companion = next(b for b in tx.all("subject_books") if b["role"] == "textbook")
        tx.update("subject_books", book["id"], {"companion_id": companion["id"]})
        tx.update("book_imports", tx.find("book_imports", book_id=book["id"])[0]["id"], {"status": "ready"})
    catalog = harness.ctx.books._raw_exercises(book, doc)
    with harness.ctx.store.transaction() as tx:
        job = harness.ctx.books.rematch(tx, book["id"])
    calls = []
    def propose(ctx, prompt, schema, *args):
        calls.append(True)
        if len(calls) > 1:
            raise ValueError("Pilot spending limit reached")
        batch = json.loads(prompt.split("Exercises: ")[1].split("\nWhole reading outline:")[0])
        return {"matches": [{"exercise_id": e["exercise_id"], "clear": True, "reason": "Supported", "requirements": [{"topic_id": s["genghis"]["id"], "evidence": "They lived in felt tents."}]} for e in batch]}
    monkeypatch.setattr(books, "ask", propose)
    monkeypatch.setattr(harness.ctx.books, "_check_catalog", lambda *args: None)
    harness.ctx.books.process(job["id"])
    assert harness.ctx.store.get("book_imports", job["id"])["status"] == "failed"
    assert harness.ctx.store.get("subject_books", book["id"])["status"] == "ready"
    assert sum(harness.ctx.books.snapshot(harness.ctx.store.get("exercises", e["exercise_id"]))["data"]["status"] == "matched" for e in catalog) == 6
    harness.restart()
    assert harness.ctx.store.get("subject_books", book["id"])["status"] == "ready"
    assert all(harness.ctx.store.get("exercises", e["exercise_id"]) for e in catalog)


def test_malformed_paid_matches_are_reviewable_and_individual_results_survive_new_batching(harness, monkeypatch):
    from services.ai_provider import StructuredResponseError, validated
    with pytest.raises(StructuredResponseError) as error:
        validated('{"matches":[]} PRIVATE TRAILING TEXT', books.MatchResult)
    assert "PRIVATE TRAILING" not in str(error.value)
    s = seed_history(harness)
    add_catalog(harness, s, 1)
    book = next(b for b in harness.ctx.store.all("subject_books") if b["role"] == "test")
    doc = harness.ctx.store.get("documents", book["document_id"])
    topics = harness.ctx.store.all("topics")
    texts = {t["id"]: harness.ctx.books.topic_text(t) for t in topics}
    items = [{"exercise_id": f"new-{n}", "reference": str(n), "prompt": "Where did they live?", "section": "", "pages": [1]} for n in (1, 2)]
    calls = []
    def malformed(*args):
        calls.append(True)
        raise StructuredResponseError("The response is malformed")
    monkeypatch.setattr(books, "ask", malformed)
    results = book_sources.match_remaining(harness.ctx.books, book, doc, topics, texts, items, {})
    assert all(r["status"] == "needs_review" for r in results.values()) and len(calls) == 1
    harness.restart()
    assert book_sources.match_remaining(harness.ctx.books, book, doc, topics, texts, items[1:], {})["new-2"]["status"] == "needs_review"
    assert len(calls) == 1
