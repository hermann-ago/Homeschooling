"""Durable preparation from curriculum; delegates to the existing guide/voice services."""
from datetime import datetime, timezone
from contextlib import nullcontext
import hashlib
import json
import threading
import time

from fastapi import BackgroundTasks
from dependencies import select_context
from . import passages, narration, automatic_voice

ACTIVE = ('queued','running')


def _enabled(ctx,provider=None):
    tts = ctx.config.get('tts', {})
    if (provider or tts.get('provider')) == 'inworld':
        return bool(tts.get('inworld_enabled') and ctx.ai.key('inworld'))
    return bool(tts.get('elevenlabs_enabled') and ctx.ai.key('elevenlabs')) if (provider or tts.get('provider')) == 'elevenlabs' else bool(tts.get('enabled'))


def topic_for(ctx, learner, topic_id):
    topic=ctx.store.get('topics',topic_id)
    subject=ctx.store.get('subjects',topic['subject_id']) if topic else None
    if not subject or subject['child_id']!=learner:
        raise ValueError('This lesson is not assigned to that learner')
    return topic


def saved_guide(ctx, topic):
    if not ctx.store.find('guides',topic_id=topic['id']):return None
    return ctx.tutor.guide(topic,passages.load(ctx,topic))


def public_job(job):
    return {k:job.get(k) for k in ('id','target','status','phase','guide_id','error','error_code','recovery',
            'teaching_provider','audio_provider','maximum_guide_usd','maximum_audio_usd','retry_uncertain')}


def snapshot(ctx, topic, jobs=None, voice_jobs=None):
    guide=None; error=None
    try:guide=saved_guide(ctx,topic)
    except (ValueError,OSError) as exc:error=str(exc)
    rows=jobs if jobs is not None else ctx.store.find('lesson_preparation_jobs',topic_id=topic['id'])
    latest=max(rows,key=lambda j:(j['created_at'],j['id']),default=None)
    audio={'status':'missing'}
    if guide:
        tracks=ctx.tutor.audio_tracks(topic,guide,only=guide['passage_sha256'])
        advanced=[t for t in tracks if t['provider'] in ('google-gemini','elevenlabs','inworld') and t['synchronized'] and t['status']=='ready'
                  and (t['provider'] != 'elevenlabs' or t.get('preferred'))]
        advanced.sort(key=lambda t: (not t.get('preferred'), t['provider'] != ctx.config.get('tts', {}).get('provider', 'google-gemini')))
        full=next((t for t in advanced if not t.get('fallback_parts') and t.get('job_status')!='ready_with_fallback'),None)
        chosen=(latest or {}).get('audio_provider')
        job=automatic_voice.status(ctx,guide['guide_id'],all_jobs=voice_jobs,**({'provider':chosen} if chosen and chosen!='configured' else {}))
        if full:audio={'status':'ready','voice':full['voice'],'provider':full['provider']}
        elif job and job.get('provider') in ('google-gemini','elevenlabs','inworld'):audio={**job,'status':job['status']}
        elif advanced:audio={'status':'partial','voice':advanced[0]['voice'],'provider':advanced[0]['provider']}
    return {'topic_id':topic['id'],'guide_id':guide['guide_id'] if guide else None,
        'review':guide.get('script_review') if guide else None,
        'origin':guide.get('origin') if guide else None,'revision_of':guide.get('revision_of') if guide else None,
        'script_status':'ready' if guide and guide['current'] else 'outdated' if guide else 'missing',
        'audio':audio,'job':public_job(latest) if latest else None,'error':error,
        'can_prepare':bool(topic.get('document_id'))}


def estimate(ctx, learner, topic_id, target, maximum_guide_usd, maximum_audio_usd,replace_invalid=False,repair_audio=False,teaching_provider='configured',rewrite=False,audio_provider='configured'):
    from routers.tutor import reader_guide, ReaderGuideRequest, _narrator
    topic=topic_for(ctx,learner,topic_id)
    guide=saved_guide(ctx,topic)
    text=None; voice=None
    provider=ctx.config.get('tts',{}).get('provider','google-gemini') if audio_provider=='configured' else audio_provider
    voice_options={} if audio_provider=='configured' else {'provider':audio_provider}
    with select_context(ctx),ctx.ai.using_provider(teaching_provider):
        if target in ('guide','both'):
            if teaching_provider!='configured' and (rewrite or not (guide and guide['current'])) and not ctx.ai.key(teaching_provider):
                raise ValueError(f'Add the {teaching_provider.title()} teaching API key in Settings before using it for this script.')
            text=reader_guide(ReaderGuideRequest(learner=learner,topic=topic_id,dry_run=True,
                prepare_voice=False,rewrite=rewrite,replace_invalid=replace_invalid,maximum_usd=maximum_guide_usd),BackgroundTasks())
        if target in ('audio','both'):
            if provider not in ('google-gemini','elevenlabs','inworld'):
                raise ValueError('Choose Inworld, ElevenLabs or Google in Settings to prepare advanced audio.')
            if guide and guide['current'] and not (rewrite and target=='both'):
                speaker,rate=_narrator(topic,**voice_options)
                voice=narration.generate(ctx,topic,guide,voice=speaker,rate=rate,dry_run=True,
                    language=guide['language'],maximum_usd=maximum_audio_usd,**voice_options,**_repair_options(ctx,guide,repair_audio))
            elif target=='audio':raise ValueError('Prepare an up-to-date tutor script before its audio.')
            else:voice={'allowed':bool(_enabled(ctx,provider)),
                'estimated_cost_usd':None,'maximum_usd':maximum_audio_usd,
                'reason':'The audio estimate becomes available after the script is saved.' if _enabled(ctx,provider)
                    else 'Narration is not connected or is paused in Settings.'}
    return {'script':text,'audio':voice,'allowed':all(x.get('allowed',False) for x in (text,voice) if x is not None)}


def enqueue(ctx, payload):
    topic=topic_for(ctx,payload.learner,payload.topic)
    # Preserve identities of jobs queued before the optional retry flag existed.
    exclude={'retry_uncertain'} if not payload.retry_uncertain else set()
    if payload.audio_provider=='configured':exclude.add('audio_provider')
    body=payload.model_dump(exclude=exclude)
    fingerprint=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
    with ctx.store.transaction(kind='lesson.preparation.queue') as tx:
        prior=tx.get('lesson_preparation_jobs',payload.operation_id)
        if prior:
            if prior['request_sha256']!=fingerprint:raise ValueError('This preparation identity belongs to a different request.')
            return prior,False
        active=next((j for j in tx.find('lesson_preparation_jobs',topic_id=topic['id']) if j['status'] in ACTIVE),None)
        if active:return active,False
        row=tx.insert('lesson_preparation_jobs',{'id':payload.operation_id,'child_id':payload.learner,
            'subject_id':topic['subject_id'],'topic_id':topic['id'],'target':payload.target,'status':'queued',
            'phase':'script' if payload.target!='audio' else 'audio','created_at':datetime.now(timezone.utc),
            'request_sha256':fingerprint,'maximum_guide_usd':payload.maximum_guide_usd,
            'maximum_audio_usd':payload.maximum_audio_usd,'replace_invalid':payload.replace_invalid,'repair_audio':payload.repair_audio,
            'teaching_provider':payload.teaching_provider,'audio_provider':payload.audio_provider,'rewrite':payload.rewrite,
            'retry_uncertain':payload.retry_uncertain})
    return row,True


def recover(ctx):
    rows=[j for j in ctx.store.all('lesson_preparation_jobs') if j['status'] in ACTIVE]
    if rows:
        with ctx.store.transaction(kind='lesson.preparation.recover') as tx:
            for row in rows:tx.update('lesson_preparation_jobs',row['id'],{'status':'paused',
                'error':'Preparation was interrupted by a server restart. Retry explicitly; saved materials are kept.'})


def run(ctx, job_id):
    from routers.tutor import reader_guide, ReaderGuideRequest, _narrator
    with ctx.store.transaction(kind='lesson.preparation.claim') as tx:
        job=tx.get('lesson_preparation_jobs',job_id)
        if not job or job['status']!='queued':return
        job=tx.update('lesson_preparation_jobs',job_id,{'status':'running'})
    # Compatible rehearsal material is generated from real observed learning,
    # exactly as the ordinary preparation route does, without learner actions.
    selected=ctx
    if ctx.is_test:
        from services.test_mode import compatible_topic
        if compatible_topic(ctx,job['topic_id']):selected=ctx.live
    try:
        with select_context(selected),selected.ai.using_provider(job.get('teaching_provider')):
            topic=topic_for(selected,job['child_id'],job['topic_id'])
            if job['target'] in ('guide','both'):
                # An explicit new attempt has its own durable provider identity.
                # Normal retries still use the exact-input cache and cannot
                # repurchase an uncertain request. Earlier reservations remain.
                retry = selected.ai.identified('authorized-retry:'+job['id']) if job.get('retry_uncertain') else nullcontext()
                with retry:
                    guide=reader_guide(ReaderGuideRequest(learner=job['child_id'],topic=topic['id'],prepare_voice=False,
                        rewrite=bool(job.get('rewrite')),replace_invalid=bool(job.get('replace_invalid')),maximum_usd=job['maximum_guide_usd']),BackgroundTasks())
            else:guide=saved_guide(selected,topic)
            if not guide or not guide['current']:raise ValueError('Prepare an up-to-date tutor script first.')
            with ctx.store.transaction(kind='lesson.preparation.script') as tx:
                tx.update('lesson_preparation_jobs',job_id,{'guide_id':guide['guide_id'],'phase':'review'})
            from . import script_review
            from .script_review import require_audio
            report=script_review.latest(selected,guide['guide_id'])
            detail=(report or {}).get('data') or {}
            if report and report['status']=='failed' and detail.get('error_code')=='provider_rate_limit':
                # A known rejected request has no unknown purchase to repeat.
                # Defer this one review once; never retry quota/billing errors,
                # timeouts, refusals or uncertain outcomes automatically.
                delay=max(1,min(float(detail.get('retry_after') or 60),120))
                with ctx.store.transaction(kind='lesson.preparation.review_wait') as tx:
                    tx.update('lesson_preparation_jobs',job_id,{'error':f'The provider is busy. Waiting {int(delay)} seconds before one review retry; the script is saved.'})
                time.sleep(delay)
                script_review.run(selected,selected.store.get('guides',guide['guide_id']),retry=True)
            require_audio(selected,guide)
            with ctx.store.transaction(kind='lesson.preparation.reviewed') as tx:
                tx.update('lesson_preparation_jobs',job_id,{'phase':'audio' if job['target']!='guide' else 'script','error':None})
            if job['target'] in ('audio','both'):
                chosen=job.get('audio_provider')
                voice_options={'provider':chosen} if chosen and chosen!='configured' else {}
                if voice_options.get('provider',selected.config.get('tts',{}).get('provider','google-gemini')) not in ('google-gemini','elevenlabs','inworld'):
                    raise ValueError('Choose Inworld, ElevenLabs or Google in Settings to prepare advanced audio.')
                speaker,rate=_narrator(topic,**voice_options)
                result=narration.generate(selected,topic,guide,voice=speaker,rate=rate,language=guide['language'],
                    maximum_usd=job['maximum_audio_usd'],**voice_options,**_repair_options(selected,guide,job.get('repair_audio')))
                if result.get('job_status') not in ('ready','ready_with_fallback',None):raise ValueError('The script is saved, but some audio still needs attention.')
            if selected is not ctx:
                from services.test_mode import sync_materials
                sync_materials(ctx)
        with ctx.store.transaction(kind='lesson.preparation.complete') as tx:
            tx.update('lesson_preparation_jobs',job_id,{'status':'completed','error':None})
    except Exception as exc:
        detail=getattr(exc,'detail',None) or str(exc)
        code=None;recovery=None
        if isinstance(detail,dict):
            code=detail.get('reason') or detail.get('code');recovery=detail.get('recovery')
            detail=detail.get('message') or str(detail)
        if job.get('target') in ('audio','both') and 'guide' in locals() and guide:
            chosen=job.get('audio_provider')
            voice_status=automatic_voice.status(selected,guide['guide_id'],**({'provider':chosen} if chosen and chosen!='configured' else {}))
            if voice_status and voice_status.get('status')=='alignment_review':
                code='audio_alignment_review';recovery='repair_audio'
        with ctx.store.transaction(kind='lesson.preparation.pause') as tx:
            tx.update('lesson_preparation_jobs',job_id,{'status':'paused','error':str(detail)[:1000],
                'error_code':code,'recovery':recovery})


def _repair_options(ctx,guide,requested):
    if not requested:return {}
    from . import aligned_audio
    jobs=[j for j in ctx.ai.ledger.jobs() if j.get('passage_sha256')==guide['passage_sha256'] and j.get('strategy')==aligned_audio.VERSION]
    job=jobs[-1] if jobs else None
    if not job or job.get('status')!='alignment_review':
        raise ValueError('There is no saved audio block awaiting synchronization review.')
    return {'repair_block':job['completed_parts']}


def launch(ctx, job_id):
    try:threading.Thread(target=run,args=(ctx,job_id),name='curriculum-prepare-'+job_id,daemon=True).start()
    except Exception as exc:
        with ctx.store.transaction(kind='lesson.preparation.launch_failed') as tx:
            tx.update('lesson_preparation_jobs',job_id,{'status':'paused','error':str(exc)[:1000]})


def prepare_next(ctx, child_id, subject_id, finished_topic_id):
    """When a lesson is finished, prepare the subject's next lesson (script, review,
    then voice) in the background, as Prepare lesson does. A lesson already
    prepared costs nothing; an active job for it is not duplicated. Turn off with
    config preparation.auto_next = false. Rehearsals (test mode) never spend."""
    if ctx.is_test or not (ctx.config.get('preparation') or {}).get('auto_next', True):
        return None
    ordered = ctx.tutor._topics(subject_id)
    position = next((i for i, t in enumerate(ordered) if t['id'] == finished_topic_id), None)
    if position is None:
        return None
    upcoming = next((t for t in ordered[position + 1:] if not t.get('completed')), None)
    if not upcoming:
        return None
    from routers.preparation import StartRequest
    import uuid
    job, created = enqueue(ctx, StartRequest(learner=child_id, topic=upcoming['id'], target='both',
                                             operation_id='auto-next-' + uuid.uuid4().hex))
    if created:
        launch(ctx, job['id'])
    return job
