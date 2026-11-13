"""An honest look back at a finished lesson, kept for the next one's "Last time"."""
from tutoring import interactive, tutor_voice
from tests.test_activity_engine import engine_lesson, event, invoke


def finished_lesson(harness, monkeypatch, voice_on=True):
    if voice_on:
        harness.ctx.config.update(ai={**harness.ctx.config.get("ai", {}), "tutor_voice": True})
    monkeypatch.setattr(tutor_voice, "remember_in_background", lambda ctx, session_id: None)  # run it by hand below
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state)
    grades = iter([{"feedback": "Not yet.", "result": "Not yet", "ready_to_continue": False},
                   {"feedback": "Yes.", "result": "Correct", "ready_to_continue": True}])
    monkeypatch.setattr(interactive, "gemini_turn", lambda *args, **kwargs: next(grades))
    monkeypatch.setattr(harness.ctx.ai, "generate", lambda *args, **kwargs: {"text": "A spoken line."})
    for response_id, text in (("first", "They stayed apart."), ("second", "He united the tribes.")):
        state = event(engine, state, "submit_response", {"response_id": response_id, "text": text})
        state = event(engine, state, "assess", {"response_id": response_id})
    for _ in range(20):
        active = state["active_activity"]
        if active["kind"] == "close_lesson":
            break
        if active["kind"] == "read_source" and active["status"] == "pending":
            state = event(engine, state, "reading_done")
        elif active["status"] == "pending" and active["kind"] not in ("introduce", "explain_or_observe", "read_source"):
            state = event(engine, state, "skip")
        else:
            state = event(engine, state, "continue")
    return engine, event(engine, state, "finish")


def test_the_note_is_written_from_how_the_lesson_went_and_shown_next_time(harness, monkeypatch):
    engine, state = finished_lesson(harness, monkeypatch)
    record = tutor_voice.lesson_record(harness.ctx.store, state["session_id"])
    assert any("Not yet, then Correct" in line for line in record)
    seen = []
    monkeypatch.setattr(harness.ctx.ai, "generate", lambda prompt, **kwargs: seen.append(prompt) or
                        {"text": "You brought the tribes together in the end. Next time we will look again at what joined them."})
    note = tutor_voice.remember_closing(harness.ctx, state["session_id"])
    assert note["text"].startswith("You brought the tribes together") and "Not yet, then Correct" in seen[0]
    store = harness.ctx.store
    session = store.get("tutor_sessions", state["session_id"])
    assert session["completion_summary"]["closing_note"]["text"] == note["text"]
    # The next lesson in the subject opens with it under "Last time".
    done = store.get("topics", session["topic_id"])
    with store.transaction() as tx:
        tx.update("topics", done["id"], {"completed": True, "is_core": True, "chapter_order": 1})
        upcoming = tx.insert("topics", {"subject_id": done["subject_id"], "title": "Lesson B", "page_start": 3, "page_end": 3,
                                        "chapter_order": 2, "is_core": True})
    assert harness.ctx.tutor.warm_up(store.get("topics", upcoming["id"]))["last"]["summary"] == note["text"]
    assert tutor_voice.last_note(store, session["child_id"], session["subject_id"])["text"] == note["text"]


def test_without_the_tutor_voice_no_note_is_written(harness, monkeypatch):
    started = []
    monkeypatch.setattr("threading.Thread.start", lambda self: started.append(self))
    harness.ctx.config.update(ai={**harness.ctx.config.get("ai", {}), "tutor_voice": False})
    tutor_voice.remember_in_background(harness.ctx, "any-session")
    assert not started


def test_a_finished_lesson_page_links_to_its_thread(harness, monkeypatch):
    engine, state = finished_lesson(harness, monkeypatch)
    session = harness.ctx.store.get("tutor_sessions", state["session_id"])
    page = harness.ctx.tutor.reader(session["child_id"], session["topic_id"], None)
    assert page["finished_lesson"]["session_id"] == state["session_id"]
    assert page["finished_lesson"]["path"].endswith("session=" + state["session_id"])
    assert harness.ctx.tutor.reader(session["child_id"], session["topic_id"], state["session_id"])["finished_lesson"] is None
