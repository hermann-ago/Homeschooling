"""Invented exercises and mocked provider replies; never use family evidence."""
import json

import httpx
import pytest
from pydantic import ValidationError

from tutoring import interactive
from tutoring.activity_engine import service
from tests.test_activity_engine import event
from tests.test_workbooks import workbook_guide


def item(item_id):
    return {"item_id": item_id, "feedback": "Synthetic feedback.", "result": "Correct", "ready_to_continue": True}


def test_scoped_validation_keeps_the_original_workbook_output_budget(harness, monkeypatch):
    calls = []
    monkeypatch.setattr(harness.ctx.ai, "generate", lambda *a, **k: calls.append(k))
    interactive.gemini_workbook("Synthetic context", [], (), expected_item_ids=["a"])
    assert calls[0]["max_output"] == 8192
    assert calls[0]["schema"].model_json_schema() == interactive.WorkbookAssessment.model_json_schema()


@pytest.mark.parametrize("ids", [["wrong"], [], ["a", "a"], ["a", "b"]])
def test_workbook_identity_validation_keeps_original_cache_contract(ids):
    schema = interactive.workbook_assessment_schema(["a"])
    assert schema.__name__ == interactive.WorkbookAssessment.__name__
    assert schema.model_json_schema() == interactive.WorkbookAssessment.model_json_schema()
    with pytest.raises(ValidationError):
        schema.model_validate({"feedback": "Synthetic feedback.", "items": [item(i) for i in ids]})
    assert schema.model_validate({"feedback": "Synthetic feedback.", "items": [item("a")]}).items[0].item_id == "a"
    # A separately scoped schema cannot relax the first request's ownership.
    other = interactive.workbook_assessment_schema(["b"])
    assert other.model_validate({"feedback": "Synthetic feedback.", "items": [item("b")]}).items[0].item_id == "b"
    with pytest.raises(ValidationError):
        schema.model_validate({"feedback": "Synthetic feedback.", "items": [item("b")]})


def test_bad_exercise_identity_reuses_reply_until_explicit_replacement(harness, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-never-real")
    _, _, legacy = workbook_guide(harness, monkeypatch)
    engine = service(harness.ctx)
    state = event(engine, engine.state(legacy["session_id"]), "physical_complete")
    calls = []

    def respond(request):
        if request.url.path.endswith("/input_tokens"):
            return httpx.Response(200, json={"input_tokens": 100})
        prompt = json.loads(request.content)["input"][0]["content"][0]["text"]
        tasks = json.JSONDecoder().raw_decode(prompt.rsplit("Item context is teacher-only:\n", 1)[1])[0]
        calls.append(prompt)
        reply = {"feedback": "Synthetic feedback.", "items": [item("mistyped-id" if len(calls) == 1 else tasks[0]["item_id"])]}
        return httpx.Response(200, json={"status": "completed", "usage": {"input_tokens": 100, "output_tokens": 50},
            "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(reply)}]}]})

    harness.ctx.ai.http = httpx.Client(transport=httpx.MockTransport(respond))
    state = event(engine, state, "submit_response", {"response_id": "invented-workbook-response", "text": "Letter B", "assess_after_save": True})
    response = state["active_activity"]["responses"][0]
    assert response["status"] == "assessment_failed" and response["feedback_failure"] == "invalid_reply"
    assert response["confirmed_text"] == "Letter B"
    assert not harness.ctx.store.find("attempts", session_id=state["session_id"])
    state = event(engine, state, "assess", {"response_id": response["id"]})
    assert len(calls) == 1
    harness.restart()
    harness.ctx.ai.http = httpx.Client(transport=httpx.MockTransport(respond))
    engine = service(harness.ctx)
    state = engine.state(state["session_id"])
    state = event(engine, state, "assess", {"response_id": response["id"]})
    assert len(calls) == 1 and state["active_activity"]["responses"][0]["feedback_failure"] == "invalid_reply"
    before = state
    payload = {"response_id": response["id"], "replace_invalid_reply": True}
    state = event(engine, state, "assess", payload, operation="replace-bad-workbook-id")
    assert len(calls) == 2 and calls[1].startswith(calls[0])
    assert state["active_activity"]["responses"][0]["status"] == "assessed"
    assert state["active_activity"]["responses"][0]["feedback_replacement_used"]
    assert len(harness.ctx.store.find("attempts", session_id=state["session_id"])) == 1
    event(engine, before, "assess", payload, operation="replace-bad-workbook-id")
    assert len(calls) == 2 and len(harness.ctx.store.find("attempts", session_id=state["session_id"])) == 1
