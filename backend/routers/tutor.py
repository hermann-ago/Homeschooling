"""Tutoring API for family devices and the tutor bridge. The reader routes are
learner-safe and never include answer keys or grading evidence."""
from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app_context import request_operation as write
from dependencies import context, current_device, require_family, store
from security.devices import Device
from tutoring import audio as audio_mod
from tutoring import guide as guide_mod
from tutoring import passages
from utils import get_or_404

router = APIRouter()


def service():
    return context().tutor


def _session_result(result: dict, session_id: str) -> dict:
    session = store().get("tutor_sessions", session_id)
    return {**result, "revision": session["revision"] if session else None}


@router.get("/learners")
def learners():
    return service().learners()


@router.get("/context")
def tutor_context(child_id: int, subject_id: int, phase: Literal["start", "reading", "grading", "closeout"] = "start",
                  questions: str | None = Query(None, description="Comma-separated question numbers for grading")):
    numbers = [int(q) for q in questions.split(",") if q.strip()] if questions else None
    return service().context(child_id, subject_id, phase, numbers)


class StartRequest(BaseModel):
    child_id: int
    subject_id: int
    topic_id: int | None = None


@router.post("/sessions/start")
def start_session(payload: StartRequest):
    with write("tutor.start", "Started or resumed a lesson") as tx:
        result = service().start(tx, payload.child_id, payload.subject_id, payload.topic_id)
    service().open_reader(result["session_id"])
    return _session_result(result, result["session_id"])


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    session = get_or_404(store(), "tutor_sessions", session_id, "Session")
    return {**service()._session_view(session), "checkpoint": service().open_checkpoint(session_id),
            "reader_path": service().reader_path(session), "reader_state": service().reader_state(session_id)}


class Observation(BaseModel):
    prompt: str
    first_response: str
    help: str | None = None
    revision: str | None = None
    explanation_supplied: str | None = None
    note: str | None = None


class CheckpointRequest(BaseModel):
    expected_revision: int
    phase: str = Field(..., max_length=40)
    next_prompt: str = Field(..., max_length=1000)
    observations: list[Observation] = Field(default_factory=list, max_length=200)
    basis: str | None = None
    minutes: int | None = Field(None, ge=0, le=600)


@router.post("/sessions/{session_id}/checkpoint")
def checkpoint(session_id: str, payload: CheckpointRequest):
    with write("tutor.checkpoint", f"Checkpoint for {session_id}") as tx:
        result = service().checkpoint(tx, session_id, payload.expected_revision, payload.phase, payload.next_prompt,
                                      [o.model_dump(exclude_none=True) for o in payload.observations],
                                      payload.basis, payload.minutes)
    return _session_result(result, session_id)


class AttemptsRequest(BaseModel):
    expected_revision: int
    attempts: list[dict[str, Any]] = Field(..., min_length=1, max_length=60)


@router.post("/sessions/{session_id}/attempts")
def attempts(session_id: str, payload: AttemptsRequest):
    with write("tutor.attempts", f"{len(payload.attempts)} answers for {session_id}") as tx:
        result = service().attempts(tx, session_id, payload.expected_revision, payload.attempts)
    return _session_result(result, session_id)


class ReviewsRequest(BaseModel):
    expected_revision: int
    reviews: list[dict[str, Any]] = Field(..., min_length=1, max_length=30)


@router.post("/sessions/{session_id}/reviews")
def reviews(session_id: str, payload: ReviewsRequest):
    with write("tutor.reviews", f"Reviews for {session_id}") as tx:
        result = service().reviews(tx, session_id, payload.expected_revision, payload.reviews)
    return _session_result(result, session_id)


@router.get("/sessions/{session_id}/assignments")
def available_assignments(session_id: str):
    session = get_or_404(store(), "tutor_sessions", session_id, "Session")
    return service().assignments(store().get("topics", session["topic_id"]))


class AssignRequest(BaseModel):
    expected_revision: int
    questions: list[int] = Field(..., min_length=1, max_length=60)
    note: str | None = None


@router.post("/sessions/{session_id}/assignments")
def assign(session_id: str, payload: AssignRequest):
    with write("tutor.assign", f"Assigned questions for {session_id}") as tx:
        result = service().assign(tx, session_id, payload.expected_revision, payload.questions, payload.note)
    return _session_result(result, session_id)


@router.post("/sessions/{session_id}/evidence")
async def evidence(session_id: str, expected_revision: int = Form(...), note: str | None = Form(None),
                   file: UploadFile = File(...)):
    data = await file.read(25 * 1024 * 1024 + 1)
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Photos are limited to 25 MiB")
    from starlette.concurrency import run_in_threadpool

    def save():
        with write("tutor.evidence", f"Learner work for {session_id}") as tx:
            return service().evidence(tx, session_id, expected_revision, file.filename or "work.jpg", data,
                                      file.content_type or "application/octet-stream", note)
    result = await run_in_threadpool(save)
    return _session_result(result, session_id)


class FinishRequest(BaseModel):
    expected_revision: int
    next_topic_id: int
    learner_explained: str
    difficulty: str | None = None
    help_that_worked: str | None = None
    next_action: str | None = None
    parent_observation: str | None = None
    understanding: str | None = None
    next_step: str | None = None
    complete_topic: bool = False
    minutes: int | None = Field(None, ge=0, le=600)
    session_type: str | None = None
    reading_mode: str | None = None
    chapter_updates: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/sessions/{session_id}/finish")
def finish(session_id: str, payload: FinishRequest):
    with write("tutor.finish", f"Finished {session_id}") as tx:
        result = service().finish(tx, session_id, payload.expected_revision, payload.model_dump())
    return _session_result(result, session_id)


@router.post("/sessions/{session_id}/reader/close")
def close_reader(session_id: str):
    """Close the lesson's reader session. The home server keeps running for the household."""
    get_or_404(store(), "tutor_sessions", session_id, "Session")
    service().close_reader(session_id)
    return {"session_id": session_id, "reader_state": "closed"}


class PreferenceRequest(BaseModel):
    child_id: int
    key: str = Field(..., max_length=80)
    value: Any
    confirmed_by: str = Field(..., max_length=80)


@router.post("/preferences")
def preference(payload: PreferenceRequest):
    with write("tutor.preference", f"Preference {payload.key}") as tx:
        return service().preference(tx, payload.child_id, payload.key, payload.value, payload.confirmed_by)


class PassageReview(BaseModel):
    reviewed_pdf_pages: list[int]
    notes: str = Field(..., min_length=5)
    passage: str | None = None
    passage_sha256: str | None = None
    images: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/passages/{topic_id}/review")
def review_passage(topic_id: int, payload: PassageReview):
    """Record a tutor/parent review after inspecting every assigned page."""
    topic = get_or_404(store(), "topics", topic_id, "Topic")
    draft = passages.load(context(), topic)
    if payload.passage is None:
        if payload.passage_sha256 != draft["passage_sha256"]:
            raise HTTPException(status_code=400, detail="Supply corrected passage text, or the exact passage_sha256 "
                                                        "of the unchanged draft")
        text = draft["passage"]
    else:
        text = payload.passage.strip()
    document = store().get("documents", topic["document_id"])
    with write("tutor.passage_review", f"Reviewed passage for {topic['title']}") as tx:
        try:
            row = passages.record_review(tx, topic, document, text, payload.reviewed_pdf_pages, payload.notes,
                                         payload.images)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"passage_id": row["id"], "status": row["status"], "passage_sha256": row["passage_sha256"]}


class AudioRequest(BaseModel):
    topic_id: int
    voice: str | None = None
    speaking_rate: float | None = Field(None, ge=0.5, le=1.5)
    dry_run: bool = True
    approve_overage_characters: int | None = Field(None, ge=1, le=100_000)


@router.post("/audio/generate")
def generate_audio(payload: AudioRequest, device: Device = Depends(current_device)):
    """Estimate (default) or generate one narrator. Paid overage needs a family device's approval; the tutor cannot approve it."""
    if payload.approve_overage_characters and not device.is_parent:
        raise HTTPException(status_code=403, detail="Only a parent can approve paid narration overage")
    topic = get_or_404(store(), "topics", payload.topic_id, "Topic")
    voice, rate = _narrator(topic, payload.voice, payload.speaking_rate)
    approval = ({"approved_by_parent": True, "extra_characters": payload.approve_overage_characters,
                 "device": device.name} if payload.approve_overage_characters else None)
    return _generate(topic, voice, rate, payload.dry_run, approval)


def _narrator(topic: dict, voice: str | None = None, rate: float | None = None) -> tuple[str, float]:
    """The requested voice, else the learner's confirmed narrator preference, else the host default,
    keeping only voices in the subject's language."""
    subject = store().get("subjects", topic["subject_id"])
    language = audio_mod.language_for(subject["name"])
    tts = context().config.get("tts", {})
    preferred = next((p["value"] for p in store().find("preferences", child_id=subject["child_id"])
                      if p["key"] == "narrator"), None) or {}
    same_language = [v for v in (preferred.get("voice"), tts.get("voice")) if v and v.startswith(language)]
    return (voice or next(iter(same_language), audio_mod.DEFAULT_VOICES[language]),
            rate or preferred.get("rate") or tts.get("rate") or audio_mod.DEFAULT_RATE)


def _generate(topic: dict, voice: str, rate: float, dry_run: bool, approval: dict | None = None) -> dict:
    package = passages.load(context(), topic)
    try:
        if dry_run:
            return audio_mod.generate(context(), store_tx_readonly(), topic, package, voice=voice, rate=rate,
                                      dry_run=True)
        with write("tutor.audio", f"Narration for {topic['title']}") as tx:
            return audio_mod.generate(context(), tx, topic, package, voice=voice, rate=rate,
                                      overage_approval=approval)
    except (ValueError, audio_mod.LedgerError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def store_tx_readonly():
    class ReadOnly:
        def get(self, table, record_id):
            return store().get(table, record_id)
    return ReadOnly()


# ── Learner-safe reader ─────────────────────────────────────────────────────

@router.get("/reader")
def reader(learner: int, topic: int, session: str | None = None):
    return service().reader(learner, topic, session)


class ReaderNarrationRequest(BaseModel):
    learner: int
    topic: int
    dry_run: bool = True
    guide: bool = False


def _learners_topic(learner: int, topic_id: int) -> dict:
    topic = get_or_404(store(), "topics", topic_id, "Topic")
    if store().get("subjects", topic["subject_id"])["child_id"] != learner:
        raise HTTPException(status_code=400, detail="This lesson is not assigned to that learner")
    return topic


@router.post("/reader/narration")
def reader_narration(payload: ReaderNarrationRequest):
    """Estimate (default) or build the lesson's read-along voice from any home device.

    With ``guide`` it voices the lesson's guided walk-through instead of the book text. It stays
    within the monthly guard; only a parent can approve paid overage (see /audio/generate).
    """
    topic = _learners_topic(payload.learner, payload.topic)
    voice, rate = _narrator(topic)
    if not payload.guide:
        return _generate(topic, voice, rate, payload.dry_run)
    package = passages.load(context(), topic)
    guide = service().guide(topic, package)
    if not guide or not guide["current"]:
        raise HTTPException(status_code=400, detail="Write the guided lesson first")
    try:
        if payload.dry_run:
            return audio_mod.generate(context(), store_tx_readonly(), topic, guide, voice=voice, rate=rate, dry_run=True)
        with write("tutor.guide_audio", f"Guided lesson voice for {topic['title']}") as tx:
            return audio_mod.generate(context(), tx, topic, guide, voice=voice, rate=rate)
    except (ValueError, audio_mod.LedgerError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class ReaderGuideRequest(BaseModel):
    learner: int
    topic: int
    rewrite: bool = False


@router.post("/reader/guide", dependencies=[Depends(require_family)])
def reader_guide(payload: ReaderGuideRequest):
    """Write the lesson's guided walk-through with the AI (or return the current one).

    The book text is always read in full and in order; the AI adds an introduction, short
    explanations and a recap, or tidies a lesson that is already a teacher's script.
    """
    topic = _learners_topic(payload.learner, payload.topic)
    package = passages.load(context(), topic)
    existing = service().guide(topic, package)
    if existing and existing["current"] and not payload.rewrite:
        return existing
    if not package["sentences"]:
        raise HTTPException(status_code=400, detail="This lesson has no text from the book to guide")
    subject = store().get("subjects", topic["subject_id"])
    child = store().get("children", payload.learner)
    language = audio_mod.language_for(subject["name"])
    configured = context().config.get("ai", {}).get("guide_model")
    models = (configured, *guide_mod.DEFAULT_MODELS) if configured else guide_mod.DEFAULT_MODELS
    text = guide_mod.prompt(package, subject=subject["name"], learner=child.get("nickname") or child["name"],
                            grade=child.get("grade_year"), language=language)
    try:
        plan, model = guide_mod.write_plan(text, models)  # outside the transaction: it can take a while
        built = guide_mod.build(package["sentences"], plan)
    except guide_mod.GuideError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    with write("tutor.guide", f"Guided lesson for {topic['title']}") as tx:
        row = guide_mod.save(tx, topic, package, built, model=model, language=language)
    return guide_mod.package(context(), row, True)


@router.get("/reader/{session_id}/state")
def reader_state(session_id: str):
    return {"session_id": session_id, "reader_state": service().reader_state(session_id)}


def _manifest(track_id: str) -> dict:
    row = get_or_404(store(), "audio_tracks", track_id, "Audio track")
    if not row["manifest_path"]:
        raise HTTPException(status_code=404, detail="This track has no audio files")
    return json.loads(context().file_bytes(row["manifest_path"], None))


@router.get("/audio/{track_id}/manifest")
def audio_manifest(track_id: str):
    manifest = _manifest(track_id)
    return {"track_id": track_id, "passageHash": manifest.get("passageHash"),
            "sentenceCount": manifest.get("sentenceCount"), "voice": manifest.get("voice"),
            "tracks": [{"index": i, "startSentence": t.get("startSentence"), "sentenceStarts": t.get("sentenceStarts")}
                       for i, t in enumerate(manifest.get("tracks", []))]}


@router.get("/audio/{track_id}/parts/{index}")
def audio_part(track_id: str, index: int):
    tracks = _manifest(track_id).get("tracks", [])
    if not 0 <= index < len(tracks):
        raise HTTPException(status_code=404, detail="No such audio part")
    data = context().file_bytes(tracks[index]["path"], tracks[index].get("sha256"))
    return Response(content=data, media_type=tracks[index].get("mime", "audio/mpeg"),
                    headers={"Cache-Control": "private, max-age=86400"})


@router.get("/usage", dependencies=[Depends(require_family)])
def narration_usage():
    from config import home_tutor_dir
    ledger = audio_mod.UsageLedger(home_tutor_dir(), context().config.get("tts", {}).get("project"))
    month = audio_mod.month_key()
    return {"month": month, "characters": ledger.used(month), "monthly_limit": audio_mod.MONTHLY_LIMIT}
