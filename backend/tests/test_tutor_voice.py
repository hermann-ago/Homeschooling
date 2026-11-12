"""The reply a child hears is worded by their tutor, within rules the code keeps."""
from tutoring import tutor_voice
from tests.test_activity_engine import engine_lesson, event, invoke
from tutoring import interactive


def test_a_line_may_not_state_a_key_answer_the_child_has_not_given():
    assert tutor_voice.reveals("Close! The difference is 182,562.", ["182562"], "182,561")
    assert not tutor_voice.reveals("Look at the ones column again: what is 10 take away 8?", ["182562"], "182,561")
    # Repeating what the child wrote is not a reveal, and single letters cannot be judged.
    assert not tutor_voice.reveals("You wrote 2,371, and that is exactly right.", ["2371"], "2,371")
    assert not tutor_voice.reveals("Read choice a again.", ["a"], "b")
    assert tutor_voice.reveals("It was Mehmed the Conqueror.", ["Mehmed the Conqueror"], "Osman")


def voiced(harness, monkeypatch, said, grade, checked_by_app=True):
    """One answered question; the app checks it against a key itself unless told otherwise."""
    from tutoring import source_key
    harness.ctx.config.update(ai={**harness.ctx.config.get("ai", {}), "tutor_voice": True})
    if checked_by_app:
        monkeypatch.setattr(source_key, "for_message", lambda *args: {"pinned": True})
        monkeypatch.setattr(interactive, "checked_binary_assessment", lambda *args: dict(grade))
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state)
    prompts = []
    monkeypatch.setattr(harness.ctx.ai, "generate", lambda prompt, **kw: prompts.append(prompt) or {"text": said})
    monkeypatch.setattr(interactive, "gemini_turn", lambda *args, **kw: grade)
    state = event(engine, state, "submit_response", {"response_id": "answer", "text": "He united the tribes."})
    state = event(engine, state, "assess", {"response_id": "answer"})
    return state, prompts


def test_the_tutor_words_the_reply_and_the_graders_note_stays_private(harness, monkeypatch):
    state, prompts = voiced(harness, monkeypatch, "Yes! You noticed that he brought the tribes together.",
        {"feedback": "Correct. Matches the passage.", "result": "Correct", "ready_to_continue": True})
    assert state["active_activity"]["messages"][-1]["text"] == "Yes! You noticed that he brought the tribes together."
    assert "He united the tribes." in prompts[0] and "Correct. Matches the passage." in prompts[0]
    saved = next(m for m in harness.ctx.store.all("lesson_dialogue") if m["role"] == "student")["assessment"]
    assert saved["grader_note"] == "Correct. Matches the passage." and saved["result"] == "Correct"


def test_an_unusable_line_falls_back_to_the_graders_words(harness, monkeypatch):
    state, _ = voiced(harness, monkeypatch, "", {"feedback": "Look again at the groups.", "result": "Not yet", "ready_to_continue": False})
    assert state["active_activity"]["messages"][-1]["text"].startswith("Look again at the groups.")


def test_without_the_setting_replies_are_unchanged(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state)
    monkeypatch.setattr(harness.ctx.ai, "generate", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no extra call")))
    monkeypatch.setattr(interactive, "gemini_turn", lambda *args, **kw: {"feedback": "Yes.", "result": "Correct", "ready_to_continue": True})
    state = event(engine, state, "submit_response", {"response_id": "answer", "text": "He united the tribes."})
    state = event(engine, state, "assess", {"response_id": "answer"})
    assert state["active_activity"]["messages"][-1]["text"] == "Yes."


def test_a_reply_the_ai_grader_wrote_for_this_child_is_left_as_it_is(harness, monkeypatch):
    state, prompts = voiced(harness, monkeypatch, "A second voice.", {"feedback": "Yes, he joined the tribes together.",
        "result": "Correct", "ready_to_continue": True}, checked_by_app=False)
    assert state["active_activity"]["messages"][-1]["text"] == "Yes, he joined the tribes together." and not prompts
