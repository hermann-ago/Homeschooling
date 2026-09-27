import hashlib
from datetime import date

import pytest

from tests.pdf_fixture import make_pdf
from tutoring import audio as audio_mod
from tutoring import passages

PAGES = [
    ["The Clever Rabbi of Cordova", "The rabbi ate the paper."],  # PDF 1 / book 1
    ["He was allowed to stay.", "Genghis Khan, Emperor of All Men", "The Mongols came from the north.",
     "They lived in felt tents."],  # PDF 2 / book 2: lesson starts partway down
    ["Genghis Khan united the tribes.", "One man spoke up.", "The Mongol Conquest of China",
     "Kublai Khan became emperor."],  # PDF 3 / book 3: lesson stops partway down
]


def seed_history(harness):
    pdf = make_pdf(PAGES)
    book_path = harness.add_file(pdf, "Books/Story of the World V.2.pdf")
    store = harness.ctx.store
    with store.transaction() as tx:
        lucas = tx.insert("children", {"name": "Lucas"})
        history = tx.insert("subjects", {"child_id": lucas["id"], "name": "History"})
        book = tx.insert("documents", {"file_path": book_path, "original_filename": "Story of the World V.2.pdf",
                                       "size_bytes": len(pdf), "page_count": 3,
                                       "sha256": hashlib.sha256(pdf).hexdigest(), "source": "drive"})
        rabbi = tx.insert("topics", {"subject_id": history["id"], "title": "The Clever Rabbi of Cordova",
                                     "page_start": 1, "page_end": 2, "chapter_order": 53, "document_id": book["id"],
                                     "source_key": "C20-T02", "start_at": "The Clever Rabbi of Cordova",
                                     "stop_before": "Genghis Khan, Emperor of All Men", "completed": True})
        genghis = tx.insert("topics", {"subject_id": history["id"], "title": "Genghis Khan, Emperor of All Men",
                                       "page_start": 2, "page_end": 3, "chapter_order": 54, "document_id": book["id"],
                                       "source_key": "C21-T01", "start_at": "Genghis Khan, Emperor of All Men",
                                       "stop_before": "The Mongol Conquest of China"})
        conquest = tx.insert("topics", {"subject_id": history["id"], "title": "The Mongol Conquest of China",
                                        "page_start": 3, "page_end": 3, "chapter_order": 55, "document_id": book["id"],
                                        "source_key": "C21-T02", "start_at": "The Mongol Conquest of China"})
        tx.insert("chapters", {"id": f"{history['id']}:21", "subject_id": history["id"], "chapter": 21,
                               "title": "The Mongols Devastate the East", "test_pdf_start": 82, "test_pdf_end": 84,
                               "test_print_start": 79, "test_print_end": 81, "key_pdf_page": 173})
        for number, topic in ((1, genghis), (2, genghis), (4, conquest)):
            tx.insert("question_maps", {"id": f"{history['id']}:21:{number}", "subject_id": history["id"],
                                        "chapter": 21, "question": number, "topic_id": topic["id"],
                                        "anchor": "felt tents", "evidence": "They lived in felt tents."})
        tx.insert("teacher_keys", {"id": f"{history['id']}:21:1", "subject_id": history["id"], "chapter": 21,
                                   "question_start": 1, "question_end": 1, "answer": "SECRET-KEY-ANSWER",
                                   "key_pdf_page": 173})
        # Imported unfinished discussion (see migration/history_import.py).
        tx.insert("tutor_sessions", {"id": "2026-09-24-genghis", "child_id": lucas["id"], "subject_id": history["id"],
                                     "topic_id": genghis["id"], "date": date(2026, 9, 24), "status": "unfinished",
                                     "phase": "discussion", "session_type": "Reading and discussion"})
        tx.insert("checkpoints", {"id": "2026-09-24-genghis-cp", "session_id": "2026-09-24-genghis",
                                  "child_id": lucas["id"], "topic_id": genghis["id"], "phase": "discussion",
                                  "status": "open", "next_prompt": "What did the man who spoke up do next?",
                                  "observations": [{"prompt": "What did he do with the tribes?",
                                                    "first_response": "he made all of them join together"}]})
    return {"lucas": lucas, "history": history, "genghis": genghis, "conquest": conquest, "rabbi": rabbi,
            "book": book}


def test_start_resumes_unfinished_genghis_discussion(harness):
    s = seed_history(harness)
    context = harness.call("GET", "/api/tutor/context", role="tutor",
                           params={"child_id": s["lucas"]["id"], "subject_id": s["history"]["id"]}).json()
    assert context["topic"]["source_key"] == "C21-T01"
    assert context["resume"]["next_prompt"] == "What did the man who spoke up do next?"
    started = harness.call("POST", "/api/tutor/sessions/start", role="tutor", key="start-1",
                           json={"child_id": s["lucas"]["id"], "subject_id": s["history"]["id"]}).json()
    assert started["resumed"] is True and started["session_id"] == "2026-09-24-genghis"
    assert started["next_prompt"] == "What did the man who spoke up do next?"
    assert started["reader_path"].startswith(f"/lesson?learner={s['lucas']['id']}&topic={s['genghis']['id']}")
    advance = harness.call("POST", "/api/tutor/sessions/start", role="tutor", key="start-2",
                           json={"child_id": s["lucas"]["id"], "subject_id": s["history"]["id"],
                                 "topic_id": s["conquest"]["id"]})
    assert advance.status_code == 409  # resume before advancing
    genghis = harness.ctx.store.get("topics", s["genghis"]["id"])
    assert genghis["completed"] is False and genghis["understanding"] is None


def _session(harness, s):
    started = harness.call("POST", "/api/tutor/sessions/start", role="tutor", key="start",
                           json={"child_id": s["lucas"]["id"], "subject_id": s["history"]["id"]}).json()
    return started["session_id"], started["revision"]


def test_handwritten_answer_keeps_first_attempt_hints_and_revision(harness):
    s = seed_history(harness)
    session_id, revision = _session(harness, s)
    r = harness.call("POST", f"/api/tutor/sessions/{session_id}/attempts", role="tutor", key="att-1", json={
        "expected_revision": revision,
        "attempts": [{"question_ref": "Q1 / book 79", "first_answer": "the yaka", "first_result": "Partly correct",
                      "help_given": "Look again at the second paragraph.", "revised_answer": "the Yakka tribe",
                      "after_help_result": "With help", "reading_certainty": "Clear"}]})
    assert r.status_code == 200, r.text
    attempt = harness.ctx.store.get("attempts", r.json()["attempts"][0])
    assert attempt["first_answer"] == "the yaka" and attempt["revised_answer"] == "the Yakka tribe"
    assert attempt["help_given"] and attempt["independence"] == "with_help"
    cheat = harness.call("POST", f"/api/tutor/sessions/{session_id}/attempts", role="tutor", key="att-2", json={
        "expected_revision": r.json()["revision"],
        "attempts": [{"question_ref": "Q2", "first_answer": "b", "first_result": "Correct",
                      "help_given": "Pointed to the answer", "independence": "independent"}]})
    assert cheat.status_code == 400 and "assisted" in cheat.json()["detail"]
    overwrite = harness.call("POST", f"/api/tutor/sessions/{session_id}/attempts", role="tutor", key="att-3", json={
        "expected_revision": r.json()["revision"],
        "attempts": [{"id": attempt["id"], "question_ref": "Q1", "first_answer": "Yakka", "first_result": "Correct"}]})
    assert overwrite.status_code == 400 and "immutable" in overwrite.json()["detail"]
    assert harness.ctx.store.get("attempts", attempt["id"])["first_answer"] == "the yaka"


def test_repeated_saves_do_not_duplicate_and_stale_revision_conflicts(harness):
    s = seed_history(harness)
    session_id, revision = _session(harness, s)
    body = {"expected_revision": revision, "phase": "discussion",
            "next_prompt": "What did the man who spoke up do next?",
            "observations": [{"prompt": "What did he do with the tribes?",
                              "first_response": "he made all of them join together"},
                             {"prompt": "What did the man who spoke up do next?",
                              "first_response": "he knocked the mongol off his horse"}]}
    first = harness.call("POST", f"/api/tutor/sessions/{session_id}/checkpoint", role="tutor", key="cp-1", json=body)
    second = harness.call("POST", f"/api/tutor/sessions/{session_id}/checkpoint", role="tutor", key="cp-1", json=body)
    assert first.status_code == 200 and second.json() == first.json()
    assert second.headers["x-idempotent-replay"] == "true"
    checkpoint = harness.ctx.store.get("checkpoints", "2026-09-24-genghis-cp")
    assert len(checkpoint["observations"]) == 2
    stale = harness.call("POST", f"/api/tutor/sessions/{session_id}/checkpoint", role="tutor", key="cp-2", json=body)
    assert stale.status_code == 409  # based on an old session revision
    rewrite = dict(body, expected_revision=first.json()["revision"],
                   observations=[{"prompt": "What did he do with the tribes?", "first_response": "rewritten"}])
    assert harness.call("POST", f"/api/tutor/sessions/{session_id}/checkpoint", role="tutor", key="cp-3",
                        json=rewrite).status_code == 400


def test_learner_views_exclude_teacher_keys(harness):
    s = seed_history(harness)
    session_id, _ = _session(harness, s)
    reader = harness.call("GET", "/api/tutor/reader", role="learner",
                          params={"learner": s["lucas"]["id"], "topic": s["genghis"]["id"], "session": session_id})
    assert reader.status_code == 200
    assert "SECRET-KEY-ANSWER" not in reader.text and "felt tents." not in str(reader.json().get("grading"))
    for path in ("/api/tutor/context", f"/api/tutor/sessions/{session_id}", "/api/tutor/learners"):
        assert harness.call("GET", path, role="learner", params={
            "child_id": s["lucas"]["id"], "subject_id": s["history"]["id"], "phase": "grading",
            "questions": "1"}).status_code == 403
    grading = harness.call("GET", "/api/tutor/context", role="tutor", params={
        "child_id": s["lucas"]["id"], "subject_id": s["history"]["id"], "phase": "grading", "questions": "1"}).json()
    assert grading["grading"]["items"][0]["key_answer"] == "SECRET-KEY-ANSWER"
    whole_key = harness.call("GET", "/api/tutor/context", role="tutor", params={
        "child_id": s["lucas"]["id"], "subject_id": s["history"]["id"], "phase": "grading"})
    assert whole_key.status_code == 400


def test_passage_respects_partial_page_boundaries(harness):
    s = seed_history(harness)
    package = passages.load(harness.ctx, harness.ctx.store.get("topics", s["genghis"]["id"]))
    assert package["passage"].startswith("Genghis Khan, Emperor of All Men")
    assert "He was allowed to stay" not in package["passage"]
    assert "Kublai" not in package["passage"] and "One man spoke up." in package["passage"]
    assert package["status"] == "needs_review"
    assert package["pdf_pages"] == {"start": 2, "end": 3}


class FakeTTS:
    """Google TTS stand-in: one fake MP3 per request and a timepoint for every sentence mark."""
    def synthesize(self, ssml, voice, rate):
        import base64
        import re
        marks = re.findall(r'<mark name="(s\d+)"/>', ssml)
        return {"audioContent": base64.b64encode(b"ID3fake").decode(),
                "timepoints": [{"markName": m, "timeSeconds": i * 2.5} for i, m in enumerate(marks)]}


def test_narration_guards_monthly_characters(harness, tmp_path, monkeypatch):
    s = seed_history(harness)
    topic = harness.ctx.store.get("topics", s["genghis"]["id"])
    draft = passages.load(harness.ctx, topic)
    review = harness.call("POST", f"/api/tutor/passages/{topic['id']}/review", role="tutor", json={
        "reviewed_pdf_pages": [2, 3], "notes": "Checked both pages", "passage_sha256": draft["passage_sha256"]})
    assert review.status_code == 200, review.text
    verified = passages.load(harness.ctx, topic)
    assert verified["status"] == "verified"

    ledger_root = tmp_path / "HomeTutor"
    monkeypatch.setattr("config.home_tutor_dir", lambda: ledger_root)
    ledger = audio_mod.UsageLedger(ledger_root, "gen-lang-client-0088393168")
    ledger.reserve(audio_mod.month_key(), "earlier-month-usage", audio_mod.MONTHLY_LIMIT - 10)
    with pytest.raises(audio_mod.LedgerError):
        with harness.ctx.store.transaction() as tx:
            audio_mod.generate(harness.ctx, tx, topic, verified, voice="en-US-Neural2-J", rate=0.9, engine=FakeTTS())
    approval = {"approved_by_parent": True, "extra_characters": 1000, "device": "test parent"}
    with harness.ctx.store.transaction() as tx:
        result = audio_mod.generate(harness.ctx, tx, topic, verified, voice="en-US-Neural2-J", rate=0.9,
                                    engine=FakeTTS(), overage_approval=approval)
    assert result["reused"] is False
    tracks = harness.call("GET", "/api/tutor/reader", role="learner",
                          params={"learner": s["lucas"]["id"], "topic": topic["id"]}).json()["audio"]
    assert tracks[0]["synchronized"] is True and tracks[0]["voice"] == "en-US-Neural2-J"
    manifest = harness.call("GET", f"/api/tutor/audio/{tracks[0]['track_id']}/manifest", role="learner").json()
    assert manifest["tracks"][0]["sentenceStarts"][:2] == [0.0, 2.5]


def test_any_device_builds_a_lessons_voice_that_the_tutor_reuses(harness, tmp_path, monkeypatch):
    s = seed_history(harness)
    topic = harness.ctx.store.get("topics", s["genghis"]["id"])
    monkeypatch.setattr("config.home_tutor_dir", lambda: tmp_path / "HomeTutor")
    monkeypatch.setattr(audio_mod, "GoogleTTS", lambda project: FakeTTS())
    body = {"learner": s["lucas"]["id"], "topic": topic["id"]}
    estimate = harness.call("POST", "/api/tutor/reader/narration", role="learner", json=body)
    assert estimate.status_code == 200, estimate.text
    assert estimate.json()["dry_run"] is True and estimate.json()["characters"] > 0
    assert harness.ctx.store.find("audio_tracks", topic_id=topic["id"]) == []
    built = harness.call("POST", "/api/tutor/reader/narration", role="learner", json={**body, "dry_run": False})
    assert built.status_code == 200, built.text
    assert built.json()["reused"] is False
    reader = harness.call("GET", "/api/tutor/reader", role="learner", params=body).json()
    assert reader["passage"]["status"] == "needs_review"  # built from the unreviewed book text
    assert [t["synchronized"] for t in reader["audio"]] == [True]
    tutor = harness.call("POST", "/api/tutor/audio/generate", role="tutor",
                         json={"topic_id": topic["id"], "dry_run": False})
    assert tutor.json()["reused"] is True and tutor.json()["track_id"] == reader["audio"][0]["track_id"]
    other = harness.call("POST", "/api/tutor/reader/narration", role="learner",
                         json={"learner": s["lucas"]["id"] + 99, "topic": topic["id"]})
    assert other.status_code == 400


def test_portuguese_lessons_are_read_in_portuguese(harness):
    s = seed_history(harness)
    topic = harness.ctx.store.get("topics", s["genghis"]["id"])
    with harness.ctx.store.transaction() as tx:
        tx.update("subjects", topic["subject_id"], {"name": "Português"})
        tx.insert("preferences", {"id": f"{s['lucas']['id']}:narrator", "child_id": s["lucas"]["id"],
                                  "key": "narrator", "value": {"voice": "en-US-Neural2-J", "rate": 0.9}})
    body = {"learner": s["lucas"]["id"], "topic": topic["id"]}
    reader = harness.call("GET", "/api/tutor/reader", role="learner", params=body).json()
    assert reader["language"] == "pt-BR"
    estimate = harness.call("POST", "/api/tutor/reader/narration", role="learner", json=body).json()
    assert estimate["voice"] == "pt-BR-Neural2-A" and estimate["rate"] == 0.9  # the English preference is skipped


def test_reader_explains_a_missing_book_file(harness):
    s = seed_history(harness)
    topic = harness.ctx.store.get("topics", s["genghis"]["id"])
    with harness.ctx.store.transaction() as tx:
        tx.update("documents", topic["document_id"], {"file_path": None})
    reader = harness.call("GET", "/api/tutor/reader", role="learner",
                          params={"learner": s["lucas"]["id"], "topic": topic["id"]})
    assert reader.status_code == 200
    assert reader.json()["passage"]["sentences"] == []
    assert "missing" in reader.json()["passage"]["issues"][0]


def test_reader_and_audio_never_complete_the_lesson_and_finish_needs_next_topic(harness):
    s = seed_history(harness)
    session_id, revision = _session(harness, s)
    harness.call("GET", "/api/tutor/reader", role="learner",
                 params={"learner": s["lucas"]["id"], "topic": s["genghis"]["id"], "session": session_id})
    assert harness.ctx.store.get("topics", s["genghis"]["id"])["completed"] is False
    no_next = harness.call("POST", f"/api/tutor/sessions/{session_id}/finish", role="tutor", key="f-0", json={
        "expected_revision": revision, "next_topic_id": s["genghis"]["id"], "learner_explained": "Retold it"})
    assert no_next.status_code == 400
    done = harness.call("POST", f"/api/tutor/sessions/{session_id}/finish", role="tutor", key="f-1", json={
        "expected_revision": revision, "next_topic_id": s["conquest"]["id"], "complete_topic": True,
        "learner_explained": "Explained that the tribes united and the eighteenth man fought back.",
        "understanding": "Independent"})
    assert done.status_code == 200, done.text
    state = harness.call("GET", f"/api/tutor/reader/{session_id}/state", role="learner").json()
    assert state["reader_state"] == "closed"
    assert harness.call("GET", "/api/health").status_code == 200  # the home server keeps running
    context = harness.call("GET", "/api/tutor/context", role="tutor",
                           params={"child_id": s["lucas"]["id"], "subject_id": s["history"]["id"]}).json()
    assert context["topic"]["source_key"] == "C21-T02" and context["resume"] is None
