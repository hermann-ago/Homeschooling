"""Finishing a lesson from its closing step."""
import pytest

from tutoring import interactive, tutor_voice
from tutoring.service import TutorError
from tests.test_activity_engine import engine_lesson, event, invoke


def at_closing_step(harness, monkeypatch):
    monkeypatch.setattr(tutor_voice, "remember_in_background", lambda ctx, session_id: None)
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state)
    grades = iter([{"feedback": "Yes.", "result": "Correct", "ready_to_continue": True}] * 4)
    monkeypatch.setattr(interactive, "gemini_turn", lambda *args, **kwargs: next(grades))
    monkeypatch.setattr(harness.ctx.ai, "generate", lambda *args, **kwargs: {"text": "A spoken line."})
    for _ in range(30):
        active = state["active_activity"]
        if active["kind"] == "close_lesson":
            return engine, state
        if active["kind"] == "read_source" and active["status"] == "pending":
            state = event(engine, state, "reading_done")
        elif active["status"] == "pending" and active["kind"] not in ("introduce", "explain_or_observe", "read_source"):
            state = event(engine, state, "skip")
        else:
            state = event(engine, state, "continue")
    raise AssertionError("the lesson never reached its closing step")


def test_a_lesson_started_on_a_slot_that_a_replan_replaced_still_finishes(harness, monkeypatch):
    engine, state = at_closing_step(harness, monkeypatch)
    store = harness.ctx.store
    session = store.get("tutor_sessions", state["session_id"])
    with store.transaction() as tx:
        slot = tx.insert("scheduled_slots", {"child_id": session["child_id"], "subject_id": session["subject_id"],
                                             "topic_id": session["topic_id"], "date": "2026-11-17",
                                             "time_start": "08:00", "time_end": "09:00"})
        tx.update("lesson_playback", session["id"], {"slot_id": slot["id"]})
    with store.transaction() as tx:  # "Re-plan from today" replaces the calendar's slots
        tx.delete("scheduled_slots", slot["id"])
    finished = event(engine, state, "finish")
    assert finished["status"] == "completed"
    assert store.get("tutor_sessions", session["id"])["completion_summary"]["lesson_status"] == "completed"


def test_a_finish_that_fails_keeps_the_closing_step_and_its_finish_button(harness, monkeypatch):
    engine, state = at_closing_step(harness, monkeypatch)
    calls = []

    def failing(self, tx, session_id, revision):
        calls.append(session_id)
        raise TutorError("Something went wrong while saving")
    owner = type(harness.ctx.tutor.interactive)
    original = owner.finish
    monkeypatch.setattr(owner, "finish", failing)
    with pytest.raises(TutorError):
        event(engine, state, "finish")
    reopened = engine.state(state["session_id"])
    assert reopened["status"] != "completed" and calls
    assert reopened["active_activity"]["kind"] == "close_lesson" and reopened["active_activity"]["status"] == "pending"
    monkeypatch.setattr(owner, "finish", original)
    assert event(engine, reopened, "finish")["status"] == "completed"


def test_recovering_a_failed_finish_with_the_same_operation_finishes(harness, monkeypatch):
    engine, state = at_closing_step(harness, monkeypatch)
    owner = type(harness.ctx.tutor.interactive)
    original = owner.finish
    monkeypatch.setattr(owner, "finish", lambda self, tx, session_id, revision: (_ for _ in ()).throw(RuntimeError("disk busy")))
    with pytest.raises(RuntimeError):
        event(engine, state, "finish", operation="finish-once")
    monkeypatch.setattr(owner, "finish", original)
    assert event(engine, state, "finish", operation="finish-once")["status"] == "completed"  # "Recover saved action"
