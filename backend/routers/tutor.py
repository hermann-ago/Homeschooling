"""Tutoring API for family devices and the tutor bridge. The reader routes are
learner-safe and never include answer keys or grading evidence."""
from __future__ import annotations

import json
import copy
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator

from app_context import request_operation as write
from dependencies import context, current_device, require_family, require_host, store
from security.devices import Device
from tutoring import audio as audio_mod
from tutoring import guide as guide_mod
from tutoring import passages
from tutoring.preparation_limits import DEFAULT_SCRIPT_CAP_USD, DEFAULT_AUDIO_CAP_USD
from utils import get_or_404

router = APIRouter()


def service():
    return context().tutor


class FamilySkillSave(BaseModel):
    content: str = Field(min_length=1, max_length=30000)
    profiles: dict[str, dict] = Field(default_factory=dict, max_length=100)
    expected_version: int = Field(ge=0)


@router.get('/teaching-style', dependencies=[Depends(require_family)])
def family_teaching_style():
    from tutoring.family_skill import inventory
    return inventory(store())


@router.put('/teaching-style', dependencies=[Depends(require_family)])
def save_family_teaching_style(payload: FamilySkillSave):
    from tutoring.family_skill import save
    try:
        with write('family_skill.save', 'Updated shared tutoring instructions and confirmed ages') as tx:
            return save(tx, payload.content, payload.profiles, payload.expected_version)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _activity_session(session_id):
    playback = store().get("lesson_playback", session_id)
    if playback and playback.get("activity_contract_version"):
        from tutoring.activity_engine import service as activity_service
        return activity_service(context())
    return None


def _compat_activity_command(engine, session_id, revision, command, payload=None, operation=None):
    import request_context
    state = engine.state(session_id)
    active = state["active_activity"]
    if not active:
        raise HTTPException(409, "There is no active activity to change")
    identity = operation or (request_context.current().key if request_context.current() else str(uuid.uuid4()))
    return engine.command(session_id, revision, identity, active["id"], active["interaction"]["id"], command, payload or {})


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
    if _activity_session(session_id):
        raise HTTPException(409, "Use this lesson's confirmed response and parent-review controls to record observed work")
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


@router.get("/sessions/{session_id}/exercises")
def available_exercises(session_id: str):
    session = get_or_404(store(), "tutor_sessions", session_id, "Session")
    return context().books.eligible(store().get("topics", session["topic_id"]), include_optional=True)


class ExerciseAssignRequest(BaseModel):
    expected_revision: int
    exercise_ids: list[str] = Field(min_length=1, max_length=100)


@router.post("/sessions/{session_id}/exercises")
def assign_exercises(session_id: str, payload: ExerciseAssignRequest):
    session = get_or_404(store(), "tutor_sessions", session_id, "Session")
    eligible = {e["id"]: e for e in context().books.eligible(store().get("topics", session["topic_id"]), include_optional=True)}
    if any(i not in eligible for i in payload.exercise_ids):
        raise HTTPException(400, "Choose eligible exercises for this lesson")
    with write("tutor.exercise_assign") as tx:
        service().guard(tx, session_id, payload.expected_revision)
        items = [context().books.assign_item(tx, session, i, eligible[i]["version_id"]) for i in dict.fromkeys(payload.exercise_ids)]
    return _session_result({"assignment_item_ids": [i["id"] for i in items]}, session_id)


@router.get("/sessions/{session_id}/exercise-grading")
def exercise_grading(session_id: str, item_ids: str):
    session = get_or_404(store(), "tutor_sessions", session_id, "Session")
    items = []
    for item_id in item_ids.split(","):
        item = get_or_404(store(), "assignment_items", item_id, "Assignment item")
        exercise = store().get("exercises", item["exercise_id"])
        book = store().get("subject_books", exercise["book_id"])
        if item["child_id"] != session["child_id"] or book["subject_id"] != session["subject_id"]:
            raise HTTPException(400, "This work belongs to another learner or subject")
        items.append({"item_id": item["id"], "exercise_id": item["exercise_id"], **item["snapshot"]})
    return {"teacher_only": True, "items": items}


@router.post("/sessions/{session_id}/assignments")
def assign(session_id: str, payload: AssignRequest):
    with write("tutor.assign", f"Assigned questions for {session_id}") as tx:
        result = service().assign(tx, session_id, payload.expected_revision, payload.questions, payload.note)
    return _session_result(result, session_id)


@router.post("/sessions/{session_id}/evidence")
async def evidence(session_id: str, expected_revision: int = Form(...), note: str | None = Form(None),
                   action_id: str | None = Form(None),
                   file: UploadFile = File(...)):
    data = await file.read(25 * 1024 * 1024 + 1)
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Photos are limited to 25 MiB")
    from starlette.concurrency import run_in_threadpool

    def save():
        with write("tutor.evidence", f"Learner work for {session_id}") as tx:
            return service().evidence(tx, session_id, expected_revision, file.filename or "work.jpg", data,
                                      file.content_type or "application/octet-stream", note, action_id)
    result = await run_in_threadpool(save)
    return _session_result(result, session_id)


class FinishRequest(BaseModel):
    expected_revision: int
    next_topic_id: int | None = None
    end_of_subject: bool = False
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
    if _activity_session(session_id):
        raise HTTPException(409, "Finish the shared activity lesson from its closing card")
    with write("tutor.finish", f"Finished {session_id}") as tx:
        result = service().finish(tx, session_id, payload.expected_revision, payload.model_dump())
    service().close_reader(session_id)
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
    if payload.approve_overage_characters and not device.is_family:
        raise HTTPException(status_code=403, detail="Only a parent can approve paid narration overage")
    topic = get_or_404(store(), "topics", payload.topic_id, "Topic")
    voice, rate = _narrator(topic, payload.voice, payload.speaking_rate)
    approval = ({"approved_by_parent": True, "extra_characters": payload.approve_overage_characters,
                 "device": device.name} if payload.approve_overage_characters else None)
    return _generate(topic, voice, rate, payload.dry_run, approval)


def _narrator(topic: dict, voice: str | None = None, rate: float | None = None, *, provider=None) -> tuple[str, float]:
    """The requested voice, else the learner's confirmed narrator preference, else the host default,
    keeping only voices in the subject's language."""
    subject = store().get("subjects", topic["subject_id"])
    language = audio_mod.language_of(store(), subject)
    tts = context().config.get("tts", {})
    selected_provider=provider or tts.get('provider','google-gemini')
    if selected_provider == 'inworld':
        from tutoring.inworld_voices import narrator, selected
        return voice or selected(store(), topic['id']) or narrator(context(), language, subject['child_id']), rate or tts.get('rate') or audio_mod.DEFAULT_RATE
    if selected_provider == 'elevenlabs':
        from tutoring.elevenlabs_audio import narrator
        from tutoring.voice_choices import selected
        return voice or selected(store(), topic['id']) or narrator(context(), language, subject['child_id']), rate or tts.get('rate') or audio_mod.DEFAULT_RATE
    if selected_provider == "kokoro-local":
        from tutoring.local_audio import narrator, VOICES
        if voice and voice not in VOICES[language]:
            raise HTTPException(status_code=400, detail="Choose a local voice in the lesson language")
        return voice or narrator(context(), language), rate or tts.get("rate") or audio_mod.DEFAULT_RATE
    if selected_provider == "google-gemini":
        if voice and voice != "Achird":
            raise HTTPException(status_code=400, detail="The approved expressive voice is Achird")
        return "Achird", rate or tts.get("rate") or audio_mod.DEFAULT_RATE
    preferred = next((p["value"] for p in store().find("preferences", child_id=subject["child_id"])
                      if p["key"] == "narrator"), None) or {}
    same_language = [v for v in (preferred.get("voice"), tts.get("voice")) if v and v.startswith(language)]
    return (voice or next(iter(same_language), audio_mod.DEFAULT_VOICES[language]),
            rate or preferred.get("rate") or tts.get("rate") or audio_mod.DEFAULT_RATE)


def _generate(topic: dict, voice: str, rate: float, dry_run: bool, approval: dict | None = None) -> dict:
    package = passages.load(context(), topic)
    try:
        if context().config.get("tts", {}).get("provider", "google-gemini") in ("google-gemini", "kokoro-local", "elevenlabs", "inworld"):
            from tutoring.narration import generate
            subject = store().get("subjects", topic["subject_id"])
            return generate(context(), topic, package, voice=voice, rate=rate, dry_run=dry_run,
                            language=audio_mod.language_of(store(), subject))
        if dry_run:
            return audio_mod.generate(context(), store_tx_readonly(), topic, package, voice=voice, rate=rate,
                                      dry_run=True)
        with write("tutor.audio", f"Narration for {topic['title']}") as tx:
            result = audio_mod.generate(context(), tx, topic, package, voice=voice, rate=rate,
                                        overage_approval=approval)
        from tutoring.library_materials import remember_audio
        remember_audio(context(), topic, result['track_id'])
        return result
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


@router.post('/reader/narration/import', dependencies=[Depends(require_family), Depends(require_host)])
def import_narration(learner: int = Form(...), topic: int = Form(...), guide_id: str = Form(...),
                     passage_sha256: str = Form(...), session: str | None = Form(None),
                     voice: Literal['Clive', 'Maitê', 'Heitor'] = Form(...), speaking_rate: float = Form(.9),
                     parts: str = Form(...), recordings: list[UploadFile] = File(...)):
    """Host import of saved Inworld WAVs; verify against the pinned guide before publishing."""
    selected = _learners_topic(learner, topic)
    if session:
        owned = store().get('tutor_sessions', session)
        playback = store().get('lesson_playback', session)
        if not owned or owned['child_id'] != learner or owned['topic_id'] != topic or not playback or playback['guide_id'] != guide_id:
            raise HTTPException(400, 'This session does not match the saved guide')
    package = passages.load(context(), selected)
    # Before a child starts, prepare only the current checked guide. A supplied
    # session instead keeps its exact pinned version and ownership checks.
    guide = service().guide(selected, package, guide_id if session else None)
    if not guide or guide['guide_id'] != guide_id or not guide['current'] or guide['passage_sha256'] != passage_sha256:
        raise HTTPException(409, 'The saved lesson script changed; refresh before importing audio')
    if not 1 <= len(recordings) <= 16 or len(parts) > 20000:
        raise HTTPException(400, 'Invalid imported audio block count')
    data = []
    for recording in recordings:
        content = recording.file.read(22_000_001)
        if len(content) > 22_000_000:
            raise HTTPException(400, 'An imported audio file is too large')
        data.append(content)
    try:
        from tutoring.imported_audio import install
        from tutoring.script_review import require_audio
        require_audio(context(), guide)
        subject = store().get('subjects', selected['subject_id'])
        descriptions = json.loads(parts)
        if not isinstance(descriptions, list):
            raise ValueError('Audio block metadata must be a list')
        return install(context(), selected, guide, descriptions, data, voice=voice,
                       language=audio_mod.language_of(store(), subject), rate=speaking_rate)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc


class ReaderNarrationRequest(BaseModel):
    learner: int
    topic: int
    dry_run: bool = True
    guide: bool = False
    session: str | None = None
    maximum_usd: float | None = Field(default=DEFAULT_AUDIO_CAP_USD, gt=0, le=2)
    repair_block: int | None = Field(default=None, ge=0, strict=True)
    retry_missing:bool=False
    provider:Literal['configured','google-gemini']='configured'


def _learners_topic(learner: int, topic_id: int) -> dict:
    topic = get_or_404(store(), "topics", topic_id, "Topic")
    if store().get("subjects", topic["subject_id"])["child_id"] != learner:
        raise HTTPException(status_code=400, detail="This lesson is not assigned to that learner")
    return topic


@router.post("/reader/narration")
def reader_narration(payload: ReaderNarrationRequest):
    """Estimate (default) or build the lesson's read-along voice from any home device.

    With ``guide`` it voices the lesson's guided walk-through instead of the book text. It stays
    tracks usage locally; provider subscription credits control availability.
    """
    topic = _learners_topic(payload.learner, payload.topic)
    selected_provider=None if payload.provider=='configured' else payload.provider
    provider=selected_provider or context().config.get('tts',{}).get('provider','google-gemini')
    if selected_provider and not payload.guide:
        raise HTTPException(400,'A per-request provider is supported for guided lesson recordings.')
    repair_options = {}
    if payload.retry_missing:
        settings=context().config.get('tts',{})
        if not payload.guide or provider!='google-gemini' or not settings.get('aligned_blocks'):
            raise HTTPException(400,'Retry missing recordings requires a guided Google recording with local synchronization.')
        repair_options['retry_missing']=True
    if payload.repair_block is not None:
        settings = context().config.get('tts', {})
        if not payload.guide or provider != 'google-gemini' or not settings.get('aligned_blocks'):
            raise HTTPException(status_code=400, detail='Re-recording a failed block requires a guided Google recording with local synchronization.')
        repair_options['repair_block'] = payload.repair_block
    voice, rate = _narrator(topic,provider=selected_provider)
    if not payload.guide:
        return _generate(topic, voice, rate, payload.dry_run)
    package = passages.load(context(), topic)
    pinned = None
    if payload.session:
        owned = store().get("tutor_sessions", payload.session)
        if not owned or owned["topic_id"] != topic["id"] or owned["child_id"] != payload.learner:
            raise HTTPException(status_code=400, detail="This session does not match the lesson")
        pinned = store().get("lesson_playback", payload.session)
    guide = service().guide(topic, package, pinned["guide_id"] if pinned else None)
    if not guide or not guide["current"]:
        raise HTTPException(status_code=400, detail="Write the guided lesson first")
    try:
        if provider in ("google-gemini", "kokoro-local", "elevenlabs", "inworld"):
            from tutoring.narration import generate
            subject = store().get("subjects", topic["subject_id"])
            return generate(context(), topic, guide, voice=voice, rate=rate, dry_run=payload.dry_run,
                            language=audio_mod.language_of(store(), subject), maximum_usd=payload.maximum_usd,
                            **({'provider':selected_provider} if selected_provider else {}), **repair_options)
        if payload.dry_run:
            return audio_mod.generate(context(), store_tx_readonly(), topic, guide, voice=voice, rate=rate, dry_run=True)
        with write("tutor.guide_audio", f"Guided lesson voice for {topic['title']}") as tx:
            result = audio_mod.generate(context(), tx, topic, guide, voice=voice, rate=rate)
        from tutoring.library_materials import remember_audio
        remember_audio(context(), topic, result['track_id'])
        return result
    except (ValueError, audio_mod.LedgerError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class ReaderGuideRequest(BaseModel):
    learner: int
    topic: int
    rewrite: bool = False
    replace_invalid: bool = False
    prepare_voice: bool = True
    dry_run: bool = False
    maximum_usd: float = Field(default=DEFAULT_SCRIPT_CAP_USD, gt=0, le=5)
    teaching_provider: Literal['configured','openai','google']='configured'
    export_inputs: bool = False

    @model_validator(mode='after')
    def export_is_read_only(self):
        if self.export_inputs and not self.dry_run:
            raise ValueError('Export lesson inputs with dry_run enabled.')
        return self


@router.post("/reader/guide", dependencies=[Depends(require_family)])
def reader_guide(payload: ReaderGuideRequest, background_tasks: BackgroundTasks):
    with context().ai.using_provider(payload.teaching_provider), context().ai.preparing_lesson():
        return _reader_guide(payload,background_tasks)


from tutoring.page_script import Script as OriginalPageScript


class ReviewedGuideRequest(BaseModel):
    learner:int
    topic:int
    source_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    expected_skill_version:int=Field(ge=0)
    plan:guide_mod.GuidePlan | None = None
    script:OriginalPageScript | None = None
    # A revision of a script the app wrote (or of an earlier revision): it is
    # marked Revised and keeps the original's identity.
    revises_guide_id:str | None = Field(default=None, min_length=1, max_length=300)

    @model_validator(mode='after')
    def one_script_format(self):
        if (self.plan is None) == (self.script is None):
            raise ValueError('Supply exactly one reviewed plan or structured script.')
        return self


class ScriptReviewRequest(BaseModel):
    maximum_usd:float=Field(default=0.30,gt=0,le=1)
    expected_input_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')


@router.get('/guides/{guide_id}/script',dependencies=[Depends(require_family)])
def saved_script(guide_id:str):
    """The structured script a saved guide was compiled from, to revise it (teacher view)."""
    row=get_or_404(store(),'guides',guide_id,'Guide')
    frozen=(row.get('context_snapshot') or {}).get('teaching_script') or {}
    if not frozen.get('script'):
        raise HTTPException(404,'This guide has no structured script to revise.')
    return {'guide_id':row['id'],'topic_id':row['topic_id'],'model':row['model'],'origin':guide_mod.origin(row),
            'version':frozen.get('version'),'script':frozen['script']}


@router.get('/guides/{guide_id}/review',dependencies=[Depends(require_family)])
def script_review_details(guide_id:str):
    from tutoring import script_review
    row=get_or_404(store(),'guides',guide_id,'Guide')
    from tutoring.page_script import answer_key, approvals
    return {'review':script_review.latest(context(),guide_id),
        'status':script_review.status(context(),row),
        'input_sha256':script_review.identity(script_review.inputs(context(),row)),
        # Family-only route: the teacher's key answers recorded by the writer.
        'answer_key':answer_key(row.get('context_snapshot'),approvals(context(),guide_id))}


class AnswerApproval(BaseModel):
    answers:list[str]=Field(min_length=1,max_length=30)


def _approvable(guide_id:str,work_index:int):
    from tutoring.page_script import answer_key
    row=get_or_404(store(),'guides',guide_id,'Guide')
    entries=answer_key(row.get('context_snapshot'))
    if not 0<=work_index<len(entries) or not entries[work_index]['blanks'] or entries[work_index]['answer']:
        raise HTTPException(400,'Only answer boxes without a book key can be approved here')
    return entries[work_index]


@router.put('/guides/{guide_id}/answers/{work_index}',dependencies=[Depends(require_family)])
def approve_answers(guide_id:str,work_index:int,payload:AnswerApproval):
    """A grown-up confirms the expected answer for each box, so it is checked instantly."""
    entry=_approvable(guide_id,work_index)
    answers=[a.strip() for a in payload.answers]
    if len(answers)!=len(entry['blanks']) or any(not a or len(a)>200 for a in answers):
        raise HTTPException(400,'Give one short answer for each box')
    record_id=f'{guide_id}:{work_index}'
    with write('tutor.answer_approval',f'Approved answers for exercise {work_index+1}') as tx:
        values={'guide_id':guide_id,'work_index':work_index,'answers':answers,'approved_at':datetime.now(timezone.utc)}
        if tx.get('answer_approvals',record_id):tx.update('answer_approvals',record_id,values)
        else:tx.insert('answer_approvals',{'id':record_id,**values})
    return {'index':work_index,'approved_answers':answers}


@router.delete('/guides/{guide_id}/answers/{work_index}',status_code=204,dependencies=[Depends(require_family)])
def withdraw_answers(guide_id:str,work_index:int):
    _approvable(guide_id,work_index)
    with write('tutor.answer_approval_withdrawn','Withdrew approved answers') as tx:
        if tx.get('answer_approvals',f'{guide_id}:{work_index}'):tx.delete('answer_approvals',f'{guide_id}:{work_index}')


class SourceSpacingRequest(BaseModel):
    expected_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    replacements:list[tuple[str,str]]=Field(min_length=1,max_length=20)


class GuideLayoutRequest(BaseModel):
    expected_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')


class TeacherWordingRequest(BaseModel):
    expected_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    replacements: list[tuple[str, str]] = Field(min_length=1, max_length=20)


@router.post('/guides/{guide_id}/teacher-wording', dependencies=[Depends(require_family)])
def correct_teacher_wording(guide_id: str, payload: TeacherWordingRequest):
    from tutoring.teaching_text import correct
    row = get_or_404(store(), 'guides', guide_id, 'Guide')
    try:
        return correct(context(), row, payload.expected_sha256, payload.replacements)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post('/guides/{guide_id}/reading-layout',dependencies=[Depends(require_family)])
def update_reading_layout(guide_id:str,payload:GuideLayoutRequest):
    from tutoring.lesson_quality import reflow
    row=get_or_404(store(),'guides',guide_id,'Guide')
    try:return reflow(context(),row,payload.expected_sha256)
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc


@router.post('/guides/{guide_id}/source-spacing',dependencies=[Depends(require_family)])
def correct_source_spacing(guide_id:str,payload:SourceSpacingRequest):
    from tutoring.source_spacing import correct
    row=get_or_404(store(),'guides',guide_id,'Guide')
    try:return correct(context(),row,payload.expected_sha256,payload.replacements)
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc


@router.post('/guides/{guide_id}/review',dependencies=[Depends(require_family)])
def retry_script_review(guide_id:str,payload:ScriptReviewRequest):
    from tutoring import script_review
    from services.ai_budget import micros
    row=get_or_404(store(),'guides',guide_id,'Guide')
    digest=script_review.identity(script_review.inputs(context(),row))
    if digest!=payload.expected_input_sha256:raise HTTPException(409,'The review inputs changed. Reopen the saved review.')
    scope='script-review-'+guide_id+'-'+digest[:16]
    context().ai.ledger.configure_scope(scope,micros(payload.maximum_usd),category='teaching')
    prior=script_review.latest(context(),guide_id)
    provider=((prior or {}).get('data') or {}).get('provider') or 'configured'
    with context().ai.using_provider(provider),context().ai.scoped(scope):
        script_review.run(context(),row,retry=True)
    return script_review_details(guide_id)


@router.post('/reader/guide/import',dependencies=[Depends(require_family)])
def import_reviewed_guide(payload:ReviewedGuideRequest,background_tasks:BackgroundTasks):
    """Codex/family-reviewed scripts use the same source and coverage checks as AI."""
    from tutoring import skills
    topic=_learners_topic(payload.learner,payload.topic)
    package=passages.load(context(),topic)
    subject=store().get('subjects',topic['subject_id'])
    if package['passage_sha256']!=payload.source_sha256 or skills.packet(store(),subject)['version']!=payload.expected_skill_version:
        raise HTTPException(409,'The source or teaching instructions changed. Review the current version before importing the script.')
    if context().is_test:
        raise HTTPException(400,'Import a reviewed script in the family workspace; test sessions can use its prepared copy.')
    revision_of=None
    if payload.revises_guide_id:
        original=store().get('guides',payload.revises_guide_id)
        if not original or original['topic_id']!=topic['id']:
            raise HTTPException(400,'The script being revised does not belong to this lesson.')
        earlier=(original.get('context_snapshot') or {}).get('revision_of') or {}
        revision_of={'guide_id':original['id'],'original_guide_id':earlier.get('original_guide_id') or original['id'],
            'original_model':earlier.get('original_model') or original['model'],
            'revised_at':datetime.now(timezone.utc).isoformat()}
    return _reader_guide(ReaderGuideRequest(learner=payload.learner,topic=payload.topic,rewrite=True,prepare_voice=False),
        background_tasks,reviewed_plan=(payload.script or payload.plan).model_dump(by_alias=True,exclude_none=True),
        revision_of=revision_of)


def _reader_guide(payload: ReaderGuideRequest, background_tasks: BackgroundTasks, *, reviewed_plan=None,
                  _editorial_repairs=1, _spending_scope=None, revision_of=None):
    from tutoring.library_materials import preparation_lock
    topic = _learners_topic(payload.learner, payload.topic)
    with preparation_lock(context(), topic):
        return _prepare_reader_guide(payload, background_tasks, reviewed_plan=reviewed_plan,
            _editorial_repairs=_editorial_repairs, _spending_scope=_spending_scope, revision_of=revision_of)


def _prepare_reader_guide(payload: ReaderGuideRequest, background_tasks: BackgroundTasks, *, reviewed_plan=None,
                          _editorial_repairs=1, _spending_scope=None, revision_of=None):
    """Write the lesson's guided walk-through with the AI (or return the current one).

    The book text is always read in full and in order; the AI adds an introduction, short
    explanations and a recap, or tidies a lesson that is already a teacher's script.
    """
    if context().is_test:
        from services.test_mode import compatible_topic, sync_materials
        from dependencies import select_context
        test = context()
        if compatible_topic(test, payload.topic):
            # Prepare from actual observed learning, never from pretend mistakes or mastery.
            with select_context(test.live):
                result = reader_guide(payload, background_tasks)
            sync_materials(test)
            if not payload.dry_run:
                # The recording finishes after text preparation. Copy only its
                # reusable materials after that job, never learner evidence.
                background_tasks.add_task(sync_materials, test)
            return result
    topic = _learners_topic(payload.learner, payload.topic)
    package = passages.load(context(), topic)
    existing = service().guide(topic, package)
    if existing and existing["current"] and not payload.rewrite and not payload.export_inputs:
        if not payload.dry_run and payload.prepare_voice:
            from tutoring.automatic_voice import schedule
            voice, rate = _narrator(topic)
            schedule(context(), topic, existing, voice, rate, background_tasks)
        return {"reused": True, "estimated_cost_usd": 0, "allowed": True, "guide_id": existing["guide_id"]} if payload.dry_run else existing
    subject = store().get("subjects", topic["subject_id"])
    child = store().get("children", payload.learner)
    language = audio_mod.language_of(store(), subject)
    configured = context().config.get("ai", {}).get("guide_model")
    models = (configured, *guide_mod.DEFAULT_MODELS) if configured else guide_mod.DEFAULT_MODELS
    from tutoring import skills
    skills.ensure(context())
    skill = skills.packet(store(), subject)
    packet = service().context(payload.learner, subject["id"])
    learner_context = json.loads(json.dumps({k: packet[k] for k in (
        "preferences", "resume", "recent_sessions", "due_reviews", "pending_assignments", "pending_actions")}, default=str))
    learner_context["workbook_fingerprint"] = context().books.fingerprint(subject["id"])
    exercises = []  # Linked ORIGINAL pages, never a pre-extracted exercise catalog.
    learner_context["workbook_exercises"] = exercises
    from tutoring.lesson_context import preparation
    learner_context.update(preparation(context(), payload.learner, topic, package))
    from tutoring import library_materials
    shared_book = library_materials.book_for(store(), subject['id'])
    if shared_book:
        learner_context = library_materials.neutral_context(context(), learner_context)
        child = {'name': 'the reader'}
    from tutoring import page_script as teaching_script
    learner_context['preparation_policy']=teaching_script.VERSION
    from tutoring.navigation import checked_selections, selections
    learner_context['selected_source_pages'] = checked_selections(store(), topic, selections(context(), topic))
    # Exercise pages shared with other lessons: this lesson teaches only its own items.
    from tutoring import exercise_assignment
    shared_exercises = exercise_assignment.group(store(), topic)
    assignment = exercise_assignment.saved(store(), shared_exercises)
    if shared_exercises and not assignment and not payload.dry_run and not payload.export_inputs and reviewed_plan is None:
        from services.ai_budget import micros
        scope = 'exercise-assignment-' + shared_exercises['id'].rsplit(':', 1)[-1]
        context().ai.ledger.configure_scope(scope, micros(exercise_assignment.MAXIMUM_USD), category='teaching')
        try:
            with context().ai.scoped(scope):
                assignment = exercise_assignment.assign(context(), shared_exercises)
        except ValueError as exc:
            raise HTTPException(502, {'code': 'exercise_assignment_failed', 'message': str(exc)}) from exc
    if assignment:
        learner_context['exercise_assignment'] = exercise_assignment.for_topic(assignment, topic['id'])
    elif shared_exercises and (payload.export_inputs or reviewed_plan is not None):
        raise HTTPException(409, {'code': 'exercise_assignment_needed',
            'message': 'These exercise pages are shared with other lessons. Assign their items first '
                       '(lesson_workflow.py assign, or Prepare lesson in the app).'})
    if payload.rewrite and existing:
        from tutoring.script_review import revision_context
        feedback=revision_context(context(),store().get('guides',existing['guide_id']))
        if feedback:
            learner_context['review_feedback'] = ({k: v for k, v in feedback.items() if k in
                ('findings', 'earlier_corrections', 'previous_activities', 'note')} if shared_book else feedback)
    from tutoring import visual_source
    try:
        visual_pdf, visual_context = visual_source.prepare(context(), topic, package, skill['content'])
        assigned_pdf = visual_pdf
        assigned_context = visual_context
        from tutoring.navigation import attach
        visual_pdf, visual_context, review_sources = attach(context(), topic, visual_pdf, visual_context)
    except guide_mod.GuideError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not package['sentences'] and not visual_context:
        raise HTTPException(status_code=400, detail='This lesson has no text or original page images available to guide')
    if visual_context:
        learner_context['visual_source'] = visual_context
        visual_source.prefer_original_pages(learner_context)
    # The writer reads the private bundle when it holds answer-key pages, so it
    # can record each exercise's key answer; the child's pages stay key-free.
    key_pages = [p for p in review_sources[1]['pages'] if p['role'] == 'answer_key'] if review_sources else []
    writer_pdf = review_sources[0] if key_pages else visual_pdf
    if key_pages:
        learner_context['answer_key_pages'] = [{k: p.get(k) for k in ('document_id', 'page', 'book_name')} for p in key_pages]
    text = teaching_script.prompt(package, subject=subject["name"], learner=child.get("nickname") or child["name"],
                            grade=subject.get("grade") or child.get("grade_year"), language=language,
                            skill=skill["content"], learner_context=learner_context)
    shared_key = library_materials.key(context(), topic, package, language, skill, learner_context) if shared_book else None
    if payload.export_inputs:
        import base64
        return {'topic': topic, 'subject': subject, 'package': package, 'skill': skill,
            'context': learner_context, 'language': language, 'prompt': text,
            'schema': teaching_script.schema(package, learner_context, language).model_json_schema(),
            'source_pdf_base64': base64.b64encode(writer_pdf).decode() if writer_pdf else None,
            'paid_generation': False}
    shared_material = (library_materials.load(context(), shared_key)
                       if shared_key and not payload.rewrite and library_materials.reuse_enabled(context()) else None)
    if shared_material and reviewed_plan is None:
        if payload.dry_run:
            return {'reused': True, 'reused_book_material': True, 'estimated_cost_usd': 0,
                    'allowed': True, 'shared_material_id': shared_material['id']}
        with write('library.guide.reuse', 'Bound saved book teaching to a new reader without generating it again') as tx:
            row = library_materials.bind_guide(context(), tx, shared_material, topic, package, skill, learner_context)
        library_materials.bind_review(context(), row, shared_material)
        result = service().guide(topic, package)
        if payload.prepare_voice:
            from tutoring.automatic_voice import schedule
            voice, rate = _narrator(topic)
            schedule(context(), topic, result, voice, rate, background_tasks)
        return {**result, 'reused_book_material': True, 'shared_material_id': shared_material['id']}
    source_inventory_needed = False
    source_inventory_cached = False
    from services.ai_budget import token_cost, micros
    from services.ai_provider import strict_schema, PREPARATION_REASONING
    from decimal import Decimal
    provider, selected_model = context().ai.selection()
    plan_schema=teaching_script.schema(package,learner_context,language)
    input_bound = len(text.encode()) + len(json.dumps(strict_schema(plan_schema)).encode()) + 4096
    if visual_context:
        input_bound += (len(visual_context['pages']) + len(key_pages)) * 4096
    pricing = context().ai.rates(provider, selected_model)
    ceiling = token_cost(input_bound, guide_mod.MAX_PLAN_OUTPUT, pricing[0] * Decimal("1.25") if provider == "openai" else pricing[0], pricing[1]) / 1_000_000
    if source_inventory_needed and not source_inventory_cached:ceiling*=2
    from tutoring import script_review
    review_ceiling=token_cost(input_bound+guide_mod.MAX_PLAN_OUTPUT*8,script_review.MAX_OUTPUT,*pricing)/1_000_000
    if review_sources:
        review_ceiling+=token_cost(max(0,len(review_sources[1]['pages'])-len(visual_context['pages']))*4096,
                                  0,*pricing)/1_000_000
    remaining = context().ai.ledger.summary(context().ai.limits)["categories"]["teaching"]["remaining_usd"]
    if payload.dry_run:
        cached_script = context().ai.has_valid_cached_reply(text,schema=plan_schema,
            instructions=guide_mod.FORMAT_INSTRUCTIONS,max_output=guide_mod.MAX_PLAN_OUTPUT,pdf=writer_pdf)
        if source_inventory_needed:cached_script=False
        if cached_script:ceiling=0
        ceiling+=review_ceiling
        # A first lesson on shared exercise pages also pays for their assignment (capped).
        assignment_ceiling=exercise_assignment.MAXIMUM_USD if shared_exercises and not assignment else 0
        ceiling+=assignment_ceiling
        failure=context().ai.cached_failure(text,schema=plan_schema,
            instructions=guide_mod.FORMAT_INSTRUCTIONS,max_output=guide_mod.MAX_PLAN_OUTPUT,pdf=writer_pdf)
        return {"reused": False, "estimated_cost_usd": ceiling, "remaining_usd": remaining,
            "cached_script_available":cached_script,
            "cached_invalid_reply":context().ai.has_invalid_cached_reply(text,schema=plan_schema,
                instructions=guide_mod.FORMAT_INSTRUCTIONS,max_output=guide_mod.MAX_PLAN_OUTPUT,pdf=writer_pdf),
            "cached_failure":failure,
            "maximum_usd": None, "tracking_only": True, "allowed": not failure or failure['replaceable'],
            "source_context": {"current_concepts": [c["title"] for c in learner_context["subject_sources"]["current_concepts"]],
                "earlier_topics": [c["topic_id"] for c in learner_context["subject_sources"]["earlier_concepts"]],
                "connections": len(learner_context["subject_sources"]["connections"]),
                "observations": len((learner_context.get("learning_memory") or {}).get("observations", [])),
                "warmup": learner_context.get("adaptive_warmup")},
            "provider": provider, "model": selected_model,
            "reasoning_effort": PREPARATION_REASONING if provider=='openai' else None,
            "preparation_format":teaching_script.VERSION,
            'source_mode': 'visual_pages' if visual_context else 'text',
            'visual_page_count': len(visual_context['pages']) if visual_context else 0,
            'source_inventory_required':source_inventory_needed,
            'source_inventory_cached':source_inventory_cached,
            "review_estimated_cost_usd":review_ceiling,
            "exercise_assignment_estimated_cost_usd":assignment_ceiling,
            "note": "Estimated generation cost includes review and one possible editorial repair. Costs are tracked; provider billing controls spending. Audio follows an approved review."}
    scope_id = _spending_scope or "guided-lesson-" + passages.passage_sha256(text)
    if reviewed_plan is None:
        context().ai.ledger.configure_scope(scope_id, micros(payload.maximum_usd), category="teaching")
    try:
        if reviewed_plan is not None:
            plan,model=reviewed_plan,'codex-reviewed'
        else:
            with context().ai.scoped(scope_id):
                plan, model = guide_mod.write_plan(text, models, **({'pdf': writer_pdf} if writer_pdf is not None else {}),
                    **({'schema':plan_schema} if plan_schema is not guide_mod.GuidePlan else {}),
                    **({'replace_invalid':True} if payload.replace_invalid else {}))
        # The paid writer returns teaching words, not engine commands. Local
        # compilation preserves those words and binds checked source identities.
        # Reviewed imports and older integrations retain their canonical adapter.
        authored='turns' in plan
        if authored:
            learner_context['teaching_script']={'version':teaching_script.VERSION,'script':copy.deepcopy(plan)}
            try:
                plan=teaching_script.compile_script(plan,package,learner_context,language)
            except guide_mod.GuideError:
                raise
            except ValueError as exc:
                raise guide_mod.GuideError(str(exc)) from exc
        from tutoring import lesson_quality
        plan=lesson_quality.resolve_readings(plan,learner_context['source_requirements'])
        allowed = {c["id"] for c in learner_context["subject_sources"]["current_concepts"] + learner_context["subject_sources"]["earlier_concepts"]}
        if not authored:
            plan = guide_mod.sanitize_planner_activities(plan, allowed)
        guide_mod.validate_source_references(context(), subject["id"], plan)
        from tutoring import book_questions
        if not authored and not book_questions.read_along(learner_context) and not any(isinstance(s, dict) and (s.get("type") == "action" or
                (s.get("type") == "activity" and guide_mod.requires_response(s.get("activity_kind"), s.get("content") or {})))
                for s in plan.get("segments", [])):
            prompt = ("O que você aprendeu? Conte uma ideia com suas palavras." if language == "pt-BR"
                      else "What did you learn? Explain one idea in your own words.")
            plan["segments"].append({"type": "action", "text": prompt, "action_kind": "answer"})
        # Real workbook work is server-selected. Generic AI checks remain typed questions.
        for segment in plan["segments"]:
            if segment.get("type") == "action" and segment.get("action_kind") == "handwritten":
                segment["action_kind"] = "answer"
            for key in ("exercise_id", "version_id", "exercise"):
                segment.pop(key, None)
            segment["concept_ids"] = [cid for cid in (segment.get("concept_ids") or []) if cid in allowed][:2]
        plan = lesson_quality.coherent_readings(plan)
        built = guide_mod.build(package["sentences"], plan, faithful=authored,
            instruction_only=authored)
        built['source_coverage']=lesson_quality.validate(built,learner_context['source_requirements'])
        from tutoring import book_questions
        if book_questions.enabled(learner_context):
            try: book_questions.validate_activities(guide_mod.guide_activities(built), learner_context)
            except ValueError as exc: raise guide_mod.GuideError(str(exc)) from exc
    except guide_mod.GuideError as exc:
        if exc.invalid_response:
            raise HTTPException(status_code=502,detail={"code":"invalid_guide_response","reason":exc.reason,
                "recovery":"replace_script","message":str(exc)}) from exc
        if exc.reason:
            raise HTTPException(status_code=502,detail={"code":exc.reason,"message":str(exc)}) from exc
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    with write("tutor.guide", f"Guided lesson for {topic['title']}") as tx:
        from tutoring.source_annotations import packet as annotation_packet
        learner_context['source_assessment_notes']=annotation_packet(store(),topic,assessment=True)
        learner_context['script_review_policy']=script_review.VERSION
        shared_folder = library_materials.folder(shared_book) if shared_book else None
        if shared_book:
            shared_key = library_materials.key(context(), topic, package, language, skill, learner_context)
            learner_context['library_material_key'] = shared_key
            learner_context['workbook_fingerprint'] = context().books.fingerprint(subject['id'])
        learner_context['lesson_sources']=visual_source.freeze(tx,topic,visual_pdf,visual_context,review_sources,folder=shared_folder)
        if revision_of:
            learner_context['revision_of'] = revision_of
        row = guide_mod.save(tx, topic, package, built, model=model, language=language, skill=skill, learner_context=learner_context,folder=shared_folder)
    if reviewed_plan is not None:
        script_review.run(context(),row,human=True)
    else:
        running=[j for j in store().find('lesson_preparation_jobs',topic_id=topic['id']) if j['status']=='running']
        if running:
            with write('lesson.preparation.reviewing','Reviewing the saved script before audio') as tx:
                for job in running:tx.update('lesson_preparation_jobs',job['id'],{'phase':'review','guide_id':row['id']})
        # The second call uses the same total script allowance and existing AI cache.
        with context().ai.scoped(scope_id):
            script_review.run(context(),row)
    saved_guide = service().guide(topic, package)
    if reviewed_plan is None and _editorial_repairs and script_review.repairable(context(), row):
        # Reuse the same total allowance; never grant a second cap to a repair.
        # Source disputes, refusals, failed/uncertain requests and a failed second
        # review remain paused with their original artifacts and reservations.
        running = [j for j in store().find('lesson_preparation_jobs',topic_id=topic['id']) if j['status']=='running']
        if running:
            with write('lesson.preparation.repairing','Applying the saved editorial findings once') as tx:
                for job in running:tx.update('lesson_preparation_jobs',job['id'],{'phase':'script','guide_id':row['id']})
        return _reader_guide(payload.model_copy(update={'rewrite':True,'replace_invalid':False}),background_tasks,
                             _editorial_repairs=0,_spending_scope=scope_id)
    from tutoring.automatic_voice import schedule
    if shared_book and library_materials.reuse_enabled(context()):
        library_materials.publish_guide(context(), shared_book, shared_key, row, built)
    voice, rate = _narrator(topic)
    if payload.prepare_voice:
        schedule(context(), topic, saved_guide, voice, rate, background_tasks)
    return saved_guide


class InteractiveStartRequest(BaseModel):
    learner: int
    topic: int
    guide_id: str
    slot_id: int | None = None
    maximum_usd: float | None = Field(default=None, gt=0, le=1)
    activity_contract_version: Literal[1] | None = None


@router.post("/interactive/start", dependencies=[Depends(require_family)])
def interactive_start(payload: InteractiveStartRequest, background_tasks: BackgroundTasks):
    interactive = service().interactive
    topic_row = store().get("topics", payload.topic)
    open_session = service().open_session(payload.learner, topic_row["subject_id"], payload.topic) if topic_row else None
    open_playback = store().get("lesson_playback", open_session["id"]) if open_session else None
    if open_playback and open_playback["guide_id"] != payload.guide_id:
        # Never swap versions silently: an unfinished session keeps its own script.
        raise HTTPException(409, {"code": "earlier_version_open", "session_id": open_session["id"],
            "message": "This lesson was started with an earlier version. Continue it, or start the updated lesson."})
    with interactive.lock:
        with write("tutor.interactive_start", "Started or resumed guided teaching") as tx:
            session_id = interactive.start(tx, payload.learner, payload.topic, payload.guide_id, payload.slot_id)
            playback = tx.get("lesson_playback", session_id)
            if payload.maximum_usd is not None and not playback.get("generation_scope_id"):
                scope_id = "tutor-session-" + session_id
                context().ai.ledger.configure_scope(scope_id, round(payload.maximum_usd * 1_000_000), category="teaching")
                tx.update("lesson_playback", session_id, {"generation_scope_id": scope_id})
        service().open_reader(session_id)
    from tutoring.automatic_voice import schedule
    topic = store().get("topics", payload.topic)
    pinned_guide = guide_mod.package(context(), store().get("guides", playback["guide_id"]), True)
    voice, rate = _narrator(topic)
    schedule(context(), topic, pinned_guide, voice, rate, background_tasks)
    if payload.activity_contract_version == 1:
        from tutoring.activity_engine import service as activity_service
        return activity_service(context()).state(session_id)
    return interactive.state(session_id)


@router.get("/sessions/{session_id}/conversation", dependencies=[Depends(require_family)])
def conversation(session_id: str):
    engine = _activity_session(session_id)
    if engine:
        return engine.state(session_id)["legacy"]
    return service().interactive.state(session_id)


@router.get("/sessions/{session_id}/activity-source/{document_id}/{page}", dependencies=[Depends(require_family)])
def activity_source_page(session_id: str, document_id: int, page: int):
    """Return one checked learner source page without teacher metadata or annotations."""
    import io
    from pypdf import PdfReader, PdfWriter
    from tutoring.activity_engine import service as activity_engine
    engine = activity_engine(context())
    session = engine._session(session_id)
    engine._validate_sources(session, {"document_id": document_id, "page": page})
    document = get_or_404(store(), "documents", document_id, "Document")
    reader = PdfReader(io.BytesIO(context().file_bytes(document["file_path"], document["sha256"])))
    if not 1 <= page <= len(reader.pages):
        raise HTTPException(400, "This page is outside the assigned source")
    writer = PdfWriter()
    writer.add_page(reader.pages[page - 1])
    writer.add_metadata({"/Title": f"Book illustration · page {page}"})
    output = io.BytesIO()
    writer.write(output)
    return Response(output.getvalue(), media_type="application/pdf", headers={"Cache-Control": "private, no-store"})


class FeedbackAudioRequest(BaseModel):
    message_id: str = Field(min_length=1, max_length=150)
    dry_run: bool = True
    track_id:str | None=Field(default=None,min_length=1,max_length=100)
    maximum_usd:float=Field(default=.05,gt=0,le=.25)
    provider:Literal['configured','google-gemini']='configured'
    autoplay: bool = False


class ActionAudioRequest(BaseModel):
    action_id: str = Field(min_length=1, max_length=300)
    dry_run: bool = True


@router.post("/sessions/{session_id}/action-audio", dependencies=[Depends(require_family)])
def action_audio(session_id: str, payload: ActionAudioRequest):
    session = get_or_404(store(), "tutor_sessions", session_id, "Lesson")
    action = store().get("lesson_actions", f"{session_id}:{payload.action_id}")
    if not action or action["child_id"] != session["child_id"]:
        raise HTTPException(400, "Choose a saved task from this lesson")
    topic = _learners_topic(session["child_id"], action["topic_id"])
    subject = store().get("subjects", session["subject_id"])
    text = action["prompt"]
    package = {"passage_sha256": passages.passage_sha256(text), "sentences": passages.split_sentences(text)}
    from tutoring.narration import generate
    voice, rate = _narrator(topic)
    try:
        return generate(context(), topic, package, voice=voice, rate=rate, dry_run=payload.dry_run,
            language=audio_mod.language_of(store(), subject), purpose="feedback")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/sessions/{session_id}/feedback-audio", dependencies=[Depends(require_family)])
def feedback_audio(session_id: str, payload: FeedbackAudioRequest):
    result = speak_reply(session_id, payload.message_id, dry_run=payload.dry_run, track_id=payload.track_id,
                         provider=payload.provider, maximum_usd=payload.maximum_usd)
    if payload.autoplay and not payload.dry_run:
        # The next replies in this lesson are voiced as soon as they are written.
        from tutoring import reply_voice
        reply_voice.remember(session_id, track_id=payload.track_id, provider=payload.provider, maximum_usd=payload.maximum_usd)
    return result


def speak_reply(session_id, message_id, *, dry_run=True, track_id=None, provider='configured', maximum_usd=.05):
    """The voice of one saved tutor reply, in the lesson's narrator; a recording is never bought twice."""
    payload = FeedbackAudioRequest(message_id=message_id, dry_run=dry_run, track_id=track_id, provider=provider, maximum_usd=maximum_usd)
    session = get_or_404(store(), "tutor_sessions", session_id, "Lesson")
    message = get_or_404(store(), "lesson_dialogue", payload.message_id, "Feedback")
    if message["session_id"] != session_id or message["role"] != "teacher" or not message["text"]:
        raise HTTPException(400, "Choose a saved teacher reply from this lesson")
    topic = _learners_topic(session["child_id"], session["topic_id"])
    subject = store().get("subjects", topic["subject_id"])
    text = message["text"]
    package = {"passage_sha256": passages.passage_sha256(text), "sentences": passages.split_sentences(text)}
    from tutoring.narration import generate
    provider=None if payload.provider=='configured' else payload.provider
    if payload.track_id:
        from tutoring.library_materials import audio_track
        track=audio_track(store(),payload.track_id,topic)
        playback=store().get('lesson_playback',session_id)
        saved=store().get('guides',playback['guide_id']) if playback else None
        if not track or not saved or track['passage_sha256']!=saved['guide_sha256'] or track['status']!='ready':
            raise HTTPException(400,'Choose a saved narrator from this lesson')
        provider=track['provider']
        if payload.provider!='configured' and payload.provider!=provider:
            raise HTTPException(400,'The requested provider does not match this lesson narrator')
        if provider not in ('google-gemini','elevenlabs','kokoro-local','inworld'):
            raise HTTPException(400,'Live replies are text-only for this imported narrator; the saved lesson audio remains available.')
        voice,rate=track['voice'],track['speaking_rate']
    else:voice, rate = _narrator(topic,provider=provider)
    try:
        result = generate(context(), topic, package, voice=voice, rate=rate, dry_run=payload.dry_run,
                          language=audio_mod.language_of(store(), subject), purpose="feedback",maximum_usd=payload.maximum_usd,
                          **({'provider':provider} if provider else {}))
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class PlaybackRequest(BaseModel):
    expected_revision: int
    sentence_index: int = Field(..., ge=0)
    action_id: str | None = None
    reading_finished: bool = False
    ask_question: bool = False


@router.post("/sessions/{session_id}/playback", dependencies=[Depends(require_family)])
def playback(session_id: str, payload: PlaybackRequest):
    engine = _activity_session(session_id)
    if engine:
        if payload.ask_question or payload.action_id:
            raise HTTPException(409, "Use the current activity's help and response controls")
        state = _compat_activity_command(engine, session_id, payload.expected_revision,
            "reading_done" if payload.reading_finished else "save_cursor", {"sentence_index": payload.sentence_index})
        return state["legacy"]
    interactive = service().interactive
    with interactive.lock:
        with write("tutor.playback", "Saved guided lesson position") as tx:
            interactive.playback(tx, session_id, payload.expected_revision, payload.sentence_index,
                                 payload.action_id, payload.reading_finished, payload.ask_question)
        return interactive.state(session_id)


class TurnRequest(BaseModel):
    expected_revision: int
    action_id: str = Field(..., max_length=300)
    message_id: str = Field(..., pattern=r"^[A-Za-z0-9-]{1,100}$")
    text: str = Field("", max_length=4000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=5)
    retry: bool = False


@router.post("/sessions/{session_id}/answer", dependencies=[Depends(require_family)])
def answer(session_id: str, payload: TurnRequest):
    engine = _activity_session(session_id)
    if engine:
        current = engine.state(session_id)
        active = current["active_activity"]
        if not active or active["id"] != payload.action_id:
            raise HTTPException(409, "Answer the current saved activity")
        if payload.evidence_ids:
            raise HTTPException(409, "Confirm the photo transcription in the current activity before assessment")
        response_id = "compat-" + payload.message_id[:90]
        response = store().get("activity_responses", response_id)
        if response is None:
            current = _compat_activity_command(engine, session_id, payload.expected_revision, "submit_response",
                {"response_id": response_id, "method": "typed", "text": payload.text}, "compat-submit-" + payload.message_id)
        assessed = _compat_activity_command(engine, session_id, current["revision"], "assess",
            {"response_id": response_id}, "compat-assess-" + payload.message_id)
        return assessed["legacy"]
    return service().interactive.answer(session_id, payload.expected_revision, payload.action_id,
        payload.message_id, payload.text, payload.evidence_ids, payload.retry)


class ControlRequest(BaseModel):
    expected_revision: int


def _control(session_id, payload, command):
    engine = _activity_session(session_id)
    if engine:
        return _compat_activity_command(engine, session_id, payload.expected_revision, command)["legacy"]
    interactive = service().interactive
    with interactive.lock:
        with write(f"tutor.{command}", f"Student chose {command}") as tx:
            interactive.control(tx, session_id, payload.expected_revision, command)
        return interactive.state(session_id)


@router.post("/sessions/{session_id}/skip", dependencies=[Depends(require_family)])
def skip_action(session_id: str, payload: ControlRequest):
    return _control(session_id, payload, "skip")


@router.post("/sessions/{session_id}/continue", dependencies=[Depends(require_family)])
def continue_lesson(session_id: str, payload: ControlRequest):
    return _control(session_id, payload, "continue")


@router.post("/sessions/{session_id}/interactive-finish", dependencies=[Depends(require_family)])
def interactive_finish(session_id: str, payload: ControlRequest):
    engine = _activity_session(session_id)
    if engine:
        return _compat_activity_command(engine, session_id, payload.expected_revision, "finish")["legacy"]
    interactive = service().interactive
    with interactive.lock:
        with write("tutor.interactive_finish", "Saved lesson outcome and scheduled completion") as tx:
            interactive.finish(tx, session_id, payload.expected_revision)
        service().close_reader(session_id)
        return interactive.state(session_id)


@router.get("/records/{child_id}", dependencies=[Depends(require_family)])
def lesson_records(child_id: int):
    return service().interactive.records(child_id)


class AmendmentRequest(BaseModel):
    expected_revision: int
    first_answer: str = Field(..., max_length=4000)
    source_note: str = Field(..., min_length=1, max_length=1000)


@router.post("/attempts/{attempt_id}/amend", dependencies=[Depends(require_family)])
def amend_attempt(attempt_id: str, payload: AmendmentRequest):
    original = get_or_404(store(), "attempts", attempt_id, "Attempt")
    with write("tutor.amend", "Corrected answer transcription, preserving the original") as tx:
        if original["revision"] != payload.expected_revision or any(a["amends_attempt_id"] == attempt_id for a in tx.find("attempts", child_id=original["child_id"])):
            raise HTTPException(status_code=409, detail="This attempt changed; reload before correcting it")
        if not payload.first_answer.strip() or not payload.source_note.strip():
            raise HTTPException(400, "Enter the clarified wording and reason for the correction")
        row = tx.insert("attempts", {**{k: original[k] for k in ("session_id", "child_id", "topic_id", "chapter",
            "question_ref", "question_text", "first_result", "help_given", "revised_answer", "after_help_result",
            "independence", "reading_certainty", "recheck_date", "evidence_paths", "tutor_created", "exercise_id", "assignment_item_id")}, "id": f"amend-{uuid.uuid4().hex}",
            "first_answer": payload.first_answer, "source_note": payload.source_note, "amends_attempt_id": attempt_id})
        topic = tx.get("topics", original["topic_id"])
        context().learning_memory.refresh(tx, original["child_id"], topic["subject_id"])
    return store().get("attempts", row["id"])


@router.get("/reader/{session_id}/state")
def reader_state(session_id: str):
    return {"session_id": session_id, "reader_state": service().reader_state(session_id)}


def _manifest(track_id: str) -> dict:
    from tutoring.library_materials import audio_track
    row = audio_track(store(), track_id)
    if not row:
        raise HTTPException(404, 'Audio track not found')
    if not row["manifest_path"]:
        raise HTTPException(status_code=404, detail="This track has no audio files")
    return json.loads(context().file_bytes(row["manifest_path"], None))


@router.get("/audio/{track_id}/manifest")
def audio_manifest(track_id: str):
    manifest = _manifest(track_id)
    return {"track_id": track_id, "passageHash": manifest.get("passageHash"),
            "sentenceCount": manifest.get("sentenceCount"), "voice": manifest.get("voice"),
            "provider": manifest.get("provider"), "model": manifest.get("model"), "timing": manifest.get("timing"),
            "cost_usd": manifest.get("cost_usd"), "job_status": manifest.get("job_status", "ready"),
            "fallback_parts": manifest.get("fallback_parts", 0),
            "generation_blocks": manifest.get('generation_blocks'),
            "tracks": [{"index": i, "startSentence": t.get("startSentence"), "sentenceStarts": t.get("sentenceStarts"),
                        "sentenceCount": t.get("sentenceCount"), "duration": t.get("duration"), "timing": t.get("timing"),
                        "fallback": t.get("fallback", False), "reason": t.get("reason")}
                       for i, t in enumerate(manifest.get("tracks", []))]}


@router.get("/audio/{track_id}/parts/{index}")
def audio_part(track_id: str, index: int):
    tracks = _manifest(track_id).get("tracks", [])
    if 0 <= index < len(tracks) and tracks[index].get("fallback"):
        raise HTTPException(404, "This passage uses device speech")
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
    return {"month": month, "characters": ledger.used(month), "monthly_limit": None, "tracking_only": True}
