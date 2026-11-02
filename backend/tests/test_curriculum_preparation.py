import json
import pytest
from tests.test_interactive import prepare
from tests.test_tutoring import seed_history
from tutoring import curriculum_preparation as prep, family_skill


def params(s):return {'learner':s['lucas']['id'],'subject':s['history']['id'],'topic_ids':[s['genghis']['id']]}
def body(s,**extra):return {'learner':s['lucas']['id'],'topic':s['genghis']['id'],'operation_id':'synthetic-prepare-01','target':'both',**extra}


def test_script_credit_failure_survives_writer_and_job_without_starting_audio(harness,monkeypatch):
    from services.ai_provider import RateLimitError
    h=harness;s=seed_history(h)
    monkeypatch.setattr(prep,'launch',lambda *a:None)
    calls=[];voices=[]
    def rejected(*args,**kwargs):
        calls.append(True)
        raise RateLimitError(provider_code='credit_balance_exhausted',provider_type='insufficient_quota')
    monkeypatch.setattr(h.ctx.ai,'generate',rejected)
    monkeypatch.setattr(prep.narration,'generate',lambda *a,**k:voices.append(True))
    job=h.call('POST','/api/tutor/preparation',json=body(s)).json()
    prep.run(h.ctx,job['id'])
    saved=h.ctx.store.get('lesson_preparation_jobs',job['id'])
    assert saved['status']=='paused' and saved['phase']=='script',saved
    assert saved['error_code']=='provider_quota',saved
    assert 'waiting will not fix' in saved['error']
    assert calls==[True] and not voices
    assert not h.ctx.store.all('guides') and not h.ctx.store.all('attempts')


@pytest.mark.parametrize('code,retried',[('provider_rate_limit',True),('provider_quota',False),('provider_429',False)])
def test_review_retries_only_a_known_temporary_rejection_once(harness,monkeypatch,code,retried):
    from tutoring import script_review
    h=harness;s,g=prepare(h,monkeypatch)
    row=h.ctx.store.get('guides',g['guide_id'])
    script_review.save(h.ctx,row,script_review.inputs(h.ctx,row),{'findings':[],
        'error':'Provider rejected the review.','error_code':code,'retry_after':12},'ai')
    reviews=[];delays=[];voices=[]
    monkeypatch.setattr(h.ctx.ai,'generate',lambda *a,**k:reviews.append(True) or {'findings':[]})
    monkeypatch.setattr(prep.time,'sleep',lambda seconds:delays.append(seconds))
    monkeypatch.setattr(prep,'launch',lambda *a:None)
    monkeypatch.setattr(prep.narration,'generate',lambda *a,**k:voices.append(True) or {'job_status':'ready','track_id':'saved-voice'})
    h.config.update(tts={'provider':'inworld','inworld_enabled':True})
    job=h.call('POST','/api/tutor/preparation',json=body(s,target='audio')).json()
    prep.run(h.ctx,job['id'])
    saved=h.ctx.store.get('lesson_preparation_jobs',job['id'])
    assert saved['status']==('completed' if retried else 'paused'),saved
    assert reviews==([True] if retried else []) and delays==([12] if retried else [])
    assert voices==([True] if retried else [])


def test_curriculum_uses_configured_inworld_with_child_narrator(harness, monkeypatch):
    h = harness
    s, _ = prepare(h, monkeypatch)
    h.ctx.ai.save_key('inworld', 'synthetic-inworld-key-never-real')
    h.config.update(tts={'provider': 'inworld', 'inworld_enabled': True,
        'inworld_learner_voices': [{'child_id': s['lucas']['id'], 'english_voice': 'Dennis'}]})
    monkeypatch.setattr(prep, 'launch', lambda *a: None)
    calls = []
    def generate(ctx, topic, guide, **options):
        calls.append(options)
        return {'allowed': True, 'estimated_cost_usd': .01, 'job_status': 'ready', 'track_id': 'flash-pilot'}
    monkeypatch.setattr(prep.narration, 'generate', generate)
    payload = body(s, target='audio')
    estimate = h.call('POST', '/api/tutor/preparation/estimate', json={k: v for k, v in payload.items() if k != 'operation_id'})
    assert estimate.status_code == 200 and estimate.json()['allowed'], estimate.text
    assert calls[-1]['voice'] == 'Dennis'
    job = h.call('POST', '/api/tutor/preparation', json=payload).json()
    prep.run(h.ctx, job['id'])
    assert h.ctx.store.get('lesson_preparation_jobs', job['id'])['status'] == 'completed'
    assert calls[-1]['voice'] == 'Dennis'
    assert not h.ctx.store.all('attempts')


def test_curriculum_can_choose_google_for_audio_without_changing_family_default(harness,monkeypatch):
    h=harness;s,g=prepare(h,monkeypatch)
    h.config.update(tts={**h.config.get('tts',{}),'provider':'elevenlabs','enabled':True})
    monkeypatch.setattr(prep,'launch',lambda *a:None)
    calls=[]
    def generate(ctx,topic,guide,**options):
        calls.append(options)
        return {'allowed':True,'estimated_cost_usd':.02,'remaining_usd':1,'job_status':'ready','track_id':'google-pilot'}
    monkeypatch.setattr(prep.narration,'generate',generate)
    payload=body(s,target='audio',audio_provider='google-gemini')
    estimate=h.call('POST','/api/tutor/preparation/estimate',json={k:v for k,v in payload.items() if k!='operation_id'})
    assert estimate.status_code==200 and estimate.json()['allowed'],estimate.text
    assert calls[-1]['provider']=='google-gemini' and calls[-1]['voice']=='Achird'
    job=h.call('POST','/api/tutor/preparation',json=payload).json()
    assert job['audio_provider']=='google-gemini'
    prep.run(h.ctx,job['id'])
    assert h.ctx.store.get('lesson_preparation_jobs',job['id'])['status']=='completed'
    assert calls[-1]['provider']=='google-gemini' and h.config.get('tts')['provider']=='elevenlabs'


def test_status_is_free_scoped_and_distinguishes_script_from_advanced_audio(harness,monkeypatch):
    h=harness;s=seed_history(h)
    result=h.call('GET','/api/tutor/preparation',params=params(s))
    assert result.status_code==200,result.text
    assert result.json()['lessons'][0]['script_status']=='missing'
    assert not h.ctx.ai.ledger.requests()
    assert h.call('GET','/api/tutor/preparation',params={**params(s),'learner':999}).status_code==404
    assert h.call('GET','/api/tutor/preparation',params={**params(s),'topic_ids':[999]}).status_code==400
    assert h.call('GET','/api/tutor/preparation',role='tutor',params=params(s)).status_code==403
    lesson={'learner':s['lucas']['id'],'topic':s['genghis']['id']}
    single=h.call('GET','/api/tutor/preparation/lesson',params=lesson)
    assert single.status_code==200 and single.json()['title']==s['genghis']['title']
    assert single.json()['script_status']=='missing' and not h.ctx.ai.ledger.requests()
    assert h.call('GET','/api/tutor/preparation/lesson',params={**lesson,'learner':999}).status_code==404
    assert h.call('GET','/api/tutor/preparation/lesson',role='tutor',params=lesson).status_code==403


def test_current_saved_script_and_its_actual_google_recording_are_reported(harness,monkeypatch):
    h=harness;s,g=prepare(h,monkeypatch)
    def tracks(topic,package,**options):
        assert options['only']==g['passage_sha256']
        return [{'provider':'google-gemini','synchronized':True,'status':'ready','voice':'Achird','job_status':'ready','fallback_parts':0}]
    monkeypatch.setattr(h.ctx.tutor,'audio_tracks',tracks)
    row=h.call('GET','/api/tutor/preparation',params=params(s)).json()['lessons'][0]
    assert row['script_status']=='ready' and row['audio']['status']=='ready'
    assert 'sentences' not in json.dumps(row) and 'context_snapshot' not in json.dumps(row)
    with h.ctx.store.transaction() as tx:
        family_skill.save(tx,family_skill.current(tx)['content']+'\nAllow time to think.',{},0)
    row=h.call('GET','/api/tutor/preparation',params=params(s)).json()['lessons'][0]
    assert row['script_status']=='outdated' and row['audio']['status']=='ready'
    monkeypatch.setattr(h.ctx.tutor,'audio_tracks',lambda *args,**kw:[{'provider':'kokoro-local','synchronized':True,'status':'ready','voice':'Home'}])
    assert h.call('GET','/api/tutor/preparation',params=params(s)).json()['lessons'][0]['audio']['status']=='missing'


def test_complete_preferred_inworld_import_is_ready_despite_old_provider_failure(harness, monkeypatch):
    h = harness
    s, g = prepare(h, monkeypatch)
    monkeypatch.setattr(h.ctx.tutor, 'audio_tracks', lambda *a, **kw: [
        {'provider':'google-gemini','synchronized':True,'status':'ready','voice':'Achird','preferred':False},
        {'provider':'inworld','synchronized':True,'status':'ready','voice':'Clive','preferred':True}])
    monkeypatch.setattr(prep.automatic_voice, 'status', lambda *a, **kw: {'status':'paused','provider':'elevenlabs'})
    row = h.call('GET','/api/tutor/preparation',params=params(s)).json()['lessons'][0]
    assert row['audio'] == {'status':'ready','voice':'Clive','provider':'inworld'}


def test_jobs_dedupe_preserve_progress_and_use_canonical_preparation(harness,monkeypatch):
    h=harness;s,g=prepare(h,monkeypatch)
    h.config.update(tts={'enabled':True,'provider':'google-gemini'})
    launches=[];voices=[]
    monkeypatch.setattr(prep,'launch',lambda ctx,jid:launches.append(jid))
    def voice(ctx,topic,guide,**options):
        assert not ctx.store._lock._is_owned()
        voices.append(options)
        return {'allowed':True,'reused':False,'estimated_cost_usd':.02,'remaining_usd':1,'track_id':'synthetic-audio','job_status':'ready'}
    monkeypatch.setattr(prep.narration,'generate',voice)
    before={table:h.ctx.store.all(table) for table in ('attempts','tutor_sessions','topics','activity_responses')}
    estimate=h.call('POST','/api/tutor/preparation/estimate',json={k:v for k,v in body(s).items() if k!='operation_id'})
    assert estimate.status_code==200,estimate.text
    assert estimate.json()['allowed'] and voices[-1]['dry_run']
    made=h.call('POST','/api/tutor/preparation',json=body(s))
    assert made.status_code==200,made.text
    assert made.json()['status']=='queued' and launches==['synthetic-prepare-01']
    assert h.call('POST','/api/tutor/preparation',json=body(s)).json()['id']==made.json()['id']
    assert h.call('POST','/api/tutor/preparation',json=body(s,operation_id='synthetic-prepare-02')).json()['id']==made.json()['id']
    assert len(launches)==1
    assert h.call('POST','/api/tutor/preparation',json=body(s,target='audio')).status_code==400
    prep.run(h.ctx,made.json()['id'])
    assert h.ctx.store.get('lesson_preparation_jobs',made.json()['id'])['status']=='completed'
    assert voices[-1].get('dry_run') is None
    assert voices[-1]['maximum_usd']==.75
    assert {table:h.ctx.store.all(table) for table in before}==before
    prep.run(h.ctx,made.json()['id'])
    assert len(voices)==2  # estimate and one execution; no second purchase
    assert h.call('POST','/api/tutor/preparation',role='tutor',json=body(s)).status_code==403


def test_interrupted_jobs_pause_on_restart_and_failed_audio_keeps_the_guide(harness,monkeypatch):
    h=harness;s,g=prepare(h,monkeypatch)
    h.config.update(tts={'enabled':True,'provider':'google-gemini'})
    monkeypatch.setattr(prep,'launch',lambda *args:None)
    h.call('POST','/api/tutor/preparation',json=body(s))
    h.restart()
    monkeypatch.setattr(h.ctx.ai,'generate',lambda *a,**kw:{'findings':[]})
    job=h.ctx.store.get('lesson_preparation_jobs','synthetic-prepare-01')
    assert job['status']=='paused' and 'restart' in job['error']
    monkeypatch.setattr(prep.narration,'generate',lambda *args,**kw:(_ for _ in ()).throw(ValueError('Synthetic voice quota pause')))
    response=h.call('POST','/api/tutor/preparation',json=body(s,operation_id='synthetic-retry-01',target='both'))
    prep.run(h.ctx,response.json()['id'])
    job=h.ctx.store.get('lesson_preparation_jobs',response.json()['id'])
    assert job['status']=='paused' and job['phase']=='audio' and 'quota' in job['error'],h.ctx.store.all('lesson_script_reviews')
    assert h.ctx.store.get('guides',job['guide_id']) and h.ctx.store.get('guides',g['guide_id']) and not h.ctx.store.all('attempts')


def test_test_mode_job_creation_does_not_write_live_job_records(harness,monkeypatch):
    from tests.test_test_mode import enter,call
    h=harness;s=seed_history(h)
    monkeypatch.setattr(prep,'launch',lambda *args:None)
    token=enter(h)
    response=call(h,'POST','/api/tutor/preparation',token,json=body(s))
    assert response.status_code==200,response.text
    assert not h.ctx.store.all('lesson_preparation_jobs')


def test_background_preparation_keeps_explicit_provider_without_changing_default(harness,monkeypatch):
    from routers import tutor
    h=harness;s,g=prepare(h,monkeypatch)
    monkeypatch.setattr(prep,'launch',lambda *args:None)
    original=h.ctx.ai.selection()
    seen=[]
    def guide(*args):
        assert args[0].rewrite
        seen.append(h.ctx.ai.selection()[0])
        return g
    monkeypatch.setattr(tutor,'reader_guide',guide)
    response=h.call('POST','/api/tutor/preparation',json=body(s,target='guide',teaching_provider='google',rewrite=True))
    assert response.status_code==200,response.text
    assert h.ctx.store.get('lesson_preparation_jobs',response.json()['id'])['teaching_provider']=='google'
    prep.run(h.ctx,response.json()['id'])
    assert seen==['google'] and h.ctx.ai.selection()==original
    assert h.ctx.store.get('lesson_preparation_jobs',response.json()['id'])['status']=='completed'


def test_authorized_uncertain_retry_is_durable_and_leaves_old_reservation(harness, monkeypatch):
    import httpx
    from routers import tutor
    from tests.test_ai_costs import SmallResponse
    h=harness;s,g=prepare(h,monkeypatch)
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-never-real')
    # Restore the real generation method hidden by the ordinary guide fixture.
    from services.ai_provider import AIService
    monkeypatch.setattr(h.ctx.ai,'generate',AIService.generate.__get__(h.ctx.ai))
    calls=[]
    def respond(request):
        if request.url.path.endswith('/input_tokens'):return httpx.Response(200,json={'input_tokens':100})
        calls.append(request)
        if len(calls)==1:raise httpx.ReadTimeout('Synthetic unknown outcome')
        return httpx.Response(200,json={'status':'completed','usage':{'input_tokens':100,'output_tokens':20},
            'output':[{'content':[{'type':'output_text','text':'{"answer":"saved"}'}]}]})
    h.ctx.ai.http=httpx.Client(transport=httpx.MockTransport(respond))
    def guide(*args):
        with h.ctx.ai.preparing_lesson():h.ctx.ai.generate('Exact synthetic source',schema=SmallResponse,max_output=100)
        return g
    monkeypatch.setattr(tutor,'reader_guide',guide)
    monkeypatch.setattr(prep,'launch',lambda *args:None)
    # The exact input cannot be repurchased by a new ordinary preparation job.
    for op in ('unknown-attempt-1','ordinary-retry-2'):
        h.call('POST','/api/tutor/preparation',json=body(s,target='guide',operation_id=op))
        prep.run(h.ctx,op)
        assert h.ctx.store.get('lesson_preparation_jobs',op)['status']=='paused'
    assert len(calls)==1
    earlier=h.ctx.ai.ledger.requests()[0]
    made=h.call('POST','/api/tutor/preparation',json=body(s,target='guide',operation_id='authorized-retry-3',retry_uncertain=True))
    assert made.status_code==200,made.text
    assert made.json()['retry_uncertain'] is True
    # Duplicate API delivery and execution reuse this authorized attempt.
    assert h.call('POST','/api/tutor/preparation',json=body(s,target='guide',operation_id='authorized-retry-3',retry_uncertain=True)).json()==made.json()
    prep.run(h.ctx,'authorized-retry-3');prep.run(h.ctx,'authorized-retry-3')
    assert h.ctx.store.get('lesson_preparation_jobs','authorized-retry-3')['status']=='completed'
    assert len(calls)==2
    assert next(r for r in h.ctx.ai.ledger.requests() if r['id']==earlier['id'])==earlier
    assert earlier['status']=='uncertain'


def test_preexisting_job_fingerprint_does_not_change_when_retry_flag_is_absent(harness, monkeypatch):
    import hashlib
    from routers.preparation import StartRequest
    h=harness;s=seed_history(h)
    monkeypatch.setattr(prep,'launch',lambda *args:None)
    request=StartRequest(**body(s,target='guide'))
    legacy=request.model_dump(exclude={'retry_uncertain','audio_provider'})
    digest=hashlib.sha256(json.dumps(legacy,sort_keys=True).encode()).hexdigest()
    made=h.call('POST','/api/tutor/preparation',json=body(s,target='guide'))
    row=h.ctx.store.get('lesson_preparation_jobs',made.json()['id'])
    assert row['request_sha256']==digest
    assert h.call('POST','/api/tutor/preparation',json=body(s,target='guide')).json()['id']==row['id']
