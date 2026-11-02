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


