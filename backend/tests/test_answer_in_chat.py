"""An answer typed in the chat box during a book exercise is that exercise's answer."""
from tutoring.activity_engine import answer_in_chat

BOOK = {"activity_kind": "request_book_work", "status": "pending", "id": "s:activity-4"}
WAITING = {"status": "awaiting_work"}
BOXES = {"blanks": [{"id": "blank-1", "label": "4,018 − 1,647 ="}, {"id": "blank-2", "label": "400,000 − 217,438 ="}]}


def test_a_plain_message_answers_the_exercise_and_fills_its_boxes_in_order():
    typed = answer_in_chat(BOXES, BOOK, WAITING, {"prompt": "the answers are 2,371 and 182,562"}, "op")
    assert typed["blanks"] == {"blank-1": "2,371", "blank-2": "182,562"} and typed["assess_after_save"]
    by_line = answer_in_chat(BOXES, BOOK, WAITING, {"prompt": "2 371\n182 562"}, "op")
    assert by_line["blanks"] == {"blank-1": "2 371", "blank-2": "182 562"}
    # Without boxes the whole message is the answer, read in context by the grader.
    assert answer_in_chat({}, BOOK, WAITING, {"prompt": "362427 3719018 550396 2253797"}, "op")["text"].startswith("362427")


def test_questions_and_unclear_messages_stay_questions():
    assert answer_in_chat(BOXES, BOOK, WAITING, {"prompt": "Why do I borrow from the thousands?"}, "op") is None
    assert answer_in_chat(BOXES, BOOK, WAITING, {"prompt": "I think it is 2,371"}, "op") is None  # one number, two boxes
    assert answer_in_chat({}, {**BOOK, "activity_kind": "explain_or_observe"}, WAITING, {"prompt": "ok"}, "op") is None
    assert answer_in_chat({}, {**BOOK, "status": "answered"}, WAITING, {"prompt": "2371"}, "op") is None


def test_the_answer_is_checked_like_a_typed_one(harness, monkeypatch):
    from tests.test_activity_engine import engine_lesson, event, invoke
    from tutoring import interactive
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state, kind="request_book_work", content={"prompt": "Who joined the tribes?"})
    row = next(a for a in harness.ctx.store.find("lesson_actions", session_id=state["session_id"]) if a["action_id"] == state["active_activity"]["id"])
    with harness.ctx.store.transaction() as tx:
        tx.update("lesson_actions", row["id"], {"origin": "required_book"})
    graded = []
    monkeypatch.setattr(interactive, "gemini_turn", lambda prompt, *a, **k: graded.append(prompt) or
                        {"feedback": "Yes.", "result": "Correct", "ready_to_continue": True})
    state = event(engine, engine.state(state["session_id"]), "request_followup", {"prompt": "Genghis Khan united them"})
    responses = harness.ctx.store.find("activity_responses", session_id=state["session_id"])
    assert len(responses) == 1 and responses[0]["confirmed_text"] == "Genghis Khan united them" and graded
    assert not [a for a in harness.ctx.store.find("lesson_actions", session_id=state["session_id"]) if a["kind"] == "question"]
