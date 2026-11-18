"""Starting a prepared lesson after its subject's books were reorganized."""
from tests.test_interactive import prepare, start


def test_a_lesson_without_mapped_exercises_starts_after_an_answer_key_is_added(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch)
    topic = harness.ctx.store.get("topics", seeded["genghis"]["id"])
    with harness.ctx.store.transaction() as tx:  # the family adds the book's answer key, with its chapter map
        tx.insert("subject_books", {"id": "book-key", "subject_id": topic["subject_id"], "document_id": topic["document_id"],
                                    "role": "answer_key", "status": "ready", "archived": False,
                                    "active_index": "chapter-map-1:key"})
    assert start(harness, seeded, guide)["session_id"]
