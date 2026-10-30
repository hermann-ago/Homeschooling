from typing import Literal
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from dependencies import context, require_family
from tutoring import curriculum_preparation as service
from tutoring.preparation_limits import DEFAULT_SCRIPT_CAP_USD, DEFAULT_AUDIO_CAP_USD

router=APIRouter(dependencies=[Depends(require_family)])


@router.get('/lesson')
def lesson_status(learner: int, topic: int):
    try:
        row = service.topic_for(context(), learner, topic)
        return {**service.snapshot(context(), row), 'title': row['title']}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


class PreparationRequest(BaseModel):
    learner:int
    topic:int
    target:Literal['guide','audio','both']='both'
    maximum_guide_usd:float=Field(default=DEFAULT_SCRIPT_CAP_USD,gt=0,le=5)
    maximum_audio_usd:float=Field(default=DEFAULT_AUDIO_CAP_USD,gt=0,le=2)
    replace_invalid:bool=False
    repair_audio:bool=False
    teaching_provider:Literal['configured','openai','google']='configured'
    audio_provider:Literal['configured','google-gemini']='configured'
    rewrite:bool=False


class StartRequest(PreparationRequest):
    operation_id:str=Field(min_length=8,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    retry_uncertain:bool=Field(default=False, description='Explicitly authorize a new paid attempt; preserve any earlier unknown charge.')


@router.get('')
def statuses(learner:int, subject:int, topic_ids:list[int]=Query(max_length=200)):
    ctx=context(); owner=ctx.store.get('subjects',subject)
    if not owner or owner['child_id']!=learner:raise HTTPException(404,'Subject not found for this learner')
    topics=[]
    for tid in dict.fromkeys(topic_ids):
        topic=ctx.store.get('topics',tid)
        if not topic or topic['subject_id']!=subject:raise HTTPException(400,'A lesson does not belong to this subject')
        topics.append(topic)
    jobs=ctx.store.find('lesson_preparation_jobs',subject_id=subject)
    voice_jobs=ctx.ai.ledger.jobs()
    return {'lessons':[service.snapshot(ctx,t,[j for j in jobs if j['topic_id']==t['id']],voice_jobs) for t in topics]}


@router.post('/estimate')
def estimate(body:PreparationRequest):
    try:return service.estimate(context(),**body.model_dump(exclude={'topic'}),topic_id=body.topic)
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc


@router.post('')
def start(body:StartRequest,tasks:BackgroundTasks):
    try:
        job,created=service.enqueue(context(),body)
        if created:tasks.add_task(service.launch,context(),job['id'])
        return service.public_job(job)
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc
