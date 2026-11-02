"""Source retrieval, combined books, key edition links and bounded recovery."""
import json

import pytest

from tests.pdf_fixture import make_pdf
from tests.test_tutoring import seed_history
from tests.test_workbooks import add_catalog
from tutoring import books, book_sources, passages


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
