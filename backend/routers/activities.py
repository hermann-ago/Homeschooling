"""Shared semantic teaching tools; learner events stay on family devices."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from dependencies import context, current_device, require_family
from security.devices import Device
from tutoring.activities import ActivityResult, definitions
from tutoring.activity_engine import service

router = APIRouter()
Operation = str


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Invocation(StrictRequest):
    operation_id: str = Field(min_length=8, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")
    expected_revision: int = Field(ge=0)
    kind: str
    content: dict
    parent_activity_id: str | None = Field(None, max_length=300)
    origin: Literal["required_book", "adaptive", "supplemental", "review"] = "adaptive"

    @model_validator(mode="before")
    @classmethod
    def kind_alias(cls, value):
        if isinstance(value, dict) and "activity_type" in value and "kind" not in value:
            return {"kind": value["activity_type"], **{k: v for k, v in value.items() if k != "activity_type"}}
        return value


class ActivityEvent(StrictRequest):
    operation_id: str = Field(min_length=8, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")
    expected_revision: int = Field(ge=0)
    activity_id: str = Field(min_length=1, max_length=300)
    interaction_id: str | None = Field(None, max_length=500)
    type: Literal["submit_response", "confirm_response", "assess", "request_hint", "physical_complete",
        "continue", "skip", "take_break", "resume", "acknowledge_return", "reveal", "advance_stage", "parent_review",
        "save_cursor", "save_draft", "checkpoint", "reading_done", "request_followup", "finish",
        "retry_transcription", "request_parent_review", "revisit_activity", "recheck_key", "go_back", "restart_lesson", "acknowledge_source_issue", "focus_unfinished",
        "open_page_work", "submit_page_work", "confirm_page_work", "retry_page_work", "close_page_work", "submit_exercise_answers",
        "parent_check", "try_first", "show_teaching", "video_watched", "done_in_book", "submit_book_check", "retry_book_check"]
    payload: dict = Field(default_factory=dict)


def activity_access(session_id: str, device: Device = Depends(current_device)):
    ctx = context()
    session = ctx.store.get("tutor_sessions", session_id)
    if not session:
        raise HTTPException(404, "Lesson not found")
    playback = ctx.store.get("lesson_playback", session_id)
    if not device.is_family and not (playback and playback.get("tutor_activity_access")):
        raise HTTPException(403, "A family device must allow tutor activity tools for this lesson")
    return device


@router.get("/activity-definitions")
def activity_definitions():
    result = definitions()
    return {"contract_version": 1, "definitions": result, "activities": result}


@router.get("/sessions/{session_id}/activity-state")
def activity_state(session_id: str, after: int = Query(0, ge=0), device: Device = Depends(activity_access)):
    state = service(context()).state(session_id)
    if after:
        state["events"] = [event for event in state["events"] if event["sequence"] > after]
    return state


def saved_result(state, session_id, operation_id):
    """The returned handle refers to committed events, not an invented child reply."""
    import request_context
    receipt_id = f"activity:{session_id}:{operation_id}"
    event = next((event for event in state["events"] if event["operation_id"] == operation_id), None)
    activity = next((activity for activity in state["activities"] if event and activity["id"] == event["activity_id"]), None)
    interaction = context().store.get("activity_interactions", event["interaction_id"]) if event and event["interaction_id"] else None
    status = (interaction or {}).get("status") or "completed"
    waiting = status if status.startswith("awaiting_") or status in ("parent_review", "assessment_pending", "assessment_failed") else None
    handle = ActivityResult(activity_id=(event or {}).get("activity_id"), interaction_id=(event or {}).get("interaction_id"),
        status=status, revision=state["revision"], event_cursor=state["event_cursor"], receipt_id=receipt_id, waiting_for=waiting)
    request = request_context.current()
    if request and context().store.get("operation_receipts", receipt_id) and receipt_id not in request.operation_ids:
        request.operation_ids.append(receipt_id)
    return {**state, "activity_result": handle.model_dump(), "receipt_id": receipt_id,
            "pending": bool(activity and activity["status"] == "pending")}


@router.post("/sessions/{session_id}/activities")
def invoke_activity(session_id: str, payload: Invocation, device: Device = Depends(activity_access)):
    try:
        state = service(context()).invoke(session_id, payload.expected_revision, payload.operation_id,
            payload.kind, payload.content, payload.parent_activity_id, payload.origin)
        return saved_result(state, session_id, payload.operation_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/sessions/{session_id}/activity-events", dependencies=[Depends(require_family)])
def activity_event(session_id: str, payload: ActivityEvent):
    state = service(context()).command(session_id, payload.expected_revision, payload.operation_id,
        payload.activity_id, payload.interaction_id, payload.type, payload.payload)
    return saved_result(state, session_id, payload.operation_id)


@router.get("/sessions/{session_id}/activity-events")
def activity_events(session_id: str, after: int = Query(0, ge=0), device: Device = Depends(activity_access)):
    state = service(context()).state(session_id)
    return {"session_id": session_id, "revision": state["revision"], "cursor": state["event_cursor"],
            "events": [event for event in state["events"] if event["sequence"] > after]}


class AccessRequest(StrictRequest):
    enabled: bool


class RepeatRequest(StrictRequest):
    operation_id: str = Field(min_length=8, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")
    from_beginning: bool = False
    unfinished_only: bool = False


class ReplaceScriptRequest(StrictRequest):
    operation_id: str = Field(min_length=8, max_length=120, pattern=r'^[A-Za-z0-9_.:-]+$')
    expected_revision: int = Field(ge=0)
    guide_id: str = Field(min_length=1, max_length=300)


@router.post('/sessions/{session_id}/replace-script', dependencies=[Depends(require_family)])
def replace_script(session_id: str, payload: ReplaceScriptRequest):
    return service(context()).replace_script(session_id, payload.guide_id, payload.expected_revision, payload.operation_id)


@router.post("/sessions/{session_id}/repeat", dependencies=[Depends(require_family)])
def repeat_lesson(session_id: str, payload: RepeatRequest, background_tasks: BackgroundTasks):
    state = service(context()).repeat(session_id, payload.operation_id, from_beginning=payload.from_beginning, unfinished_only=payload.unfinished_only)
    from routers.tutor import _narrator
    from tutoring.automatic_voice import schedule
    from tutoring import guide as guide_mod
    ctx = context()
    playback = ctx.store.get("lesson_playback", state["session_id"])
    topic = ctx.store.get("topics", ctx.store.get("tutor_sessions", state["session_id"])["topic_id"])
    guide = guide_mod.package(ctx, ctx.store.get("guides", playback["guide_id"]), True)
    voice, rate = _narrator(topic)
    schedule(ctx, topic, guide, voice, rate, background_tasks)
    return state


@router.post("/sessions/{session_id}/activity-access", dependencies=[Depends(require_family)])
def set_activity_access(session_id: str, payload: AccessRequest):
    engine = service(context())
    engine.bootstrap(session_id)
    with engine.lock(session_id):
        with context().store.transaction(kind="activity.access") as tx:
            tx.update("lesson_playback", session_id, {"tutor_activity_access": payload.enabled})
    return {"session_id": session_id, "enabled": payload.enabled}
