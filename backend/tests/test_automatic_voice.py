from fastapi import BackgroundTasks
import threading
import time
from tests.test_interactive import prepare, start
from tutoring import automatic_voice, narration
from tutoring.expressive_audio import chunks


def test_google_recording_can_be_selected_without_changing_family_default(harness,monkeypatch):
    from tutoring import aligned_audio
    seeded,guide=prepare(harness,monkeypatch)
    harness.config.update(tts={**harness.config.get('tts',{}),'provider':'elevenlabs','enabled':True,'aligned_blocks':True})
    before=dict(harness.config.get('tts'))
    calls=[]
    def google(ctx,topic,passage,**options):
        calls.append(options)
        assert ctx.config.get('tts')['provider']=='elevenlabs'
        return {'provider':'google-gemini','voice':options['voice'],'allowed':True,'track_id':'synthetic-google'}
    monkeypatch.setattr(aligned_audio,'generate',google)
    body={'learner':seeded['lucas']['id'],'topic':seeded['genghis']['id'],'guide':True,'provider':'google-gemini'}
    for dry_run in (True,False):
        response=harness.call('POST','/api/tutor/reader/narration',json={**body,'dry_run':dry_run})
        assert response.status_code==200,response.text
        assert response.json()['provider']=='google-gemini' and calls[-1]['voice']=='Achird'
    assert harness.config.get('tts')==before
    assert not harness.ctx.store.all('attempts')


def wait_voice(ctx, guide_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = automatic_voice.status(ctx, guide_id)
        if status and status['status'] not in ('queued', 'running', 'aligning'):
            return status
        time.sleep(.01)
    raise AssertionError('Synthetic voice job did not finish')


def test_manual_recording_progress_is_visible_without_an_automatic_wrapper(harness,monkeypatch):
    _,guide=prepare(harness,monkeypatch)
    harness.config.update(tts={'provider':'google-gemini'})
    harness.ctx.ai.ledger.save_job('manual-synthetic',{'provider':'google-gemini','status':'aligning',
        'passage_sha256':guide['passage_sha256'],'parts':2,'completed_parts':0})
    current=automatic_voice.status(harness.ctx,guide['guide_id'])
    assert current['status']=='aligning' and current['parts']==2
    assert current['track_id']=='manual-synthetic'


def test_guide_creation_automatically_prepares_once_and_start_reuses(harness, monkeypatch):
    calls = []
    monkeypatch.setattr(narration, 'generate', lambda ctx, topic, guide, **kwargs: calls.append((guide['guide_id'], kwargs)) or {'track_id': 'saved', 'job_status': 'ready'})
    harness.config.update(tts={'enabled': True, 'provider': 'google-gemini', 'voice': 'Achird', 'rate': 0.9})
    seeded, guide = prepare(harness, monkeypatch)
    wait_voice(harness.ctx, guide['guide_id'])
    assert len(calls) == 1
    assert not harness.ctx.store.all('attempts')
    started = start(harness, seeded, guide)
    assert len(calls) == 1
    assert started['session_id']
    assert automatic_voice.status(harness.ctx, guide['guide_id'])['status'] == 'ready'


def test_paused_voice_preserves_lesson_and_is_not_automatically_repurchased(harness, monkeypatch):
    calls = []
    def fail(*args, **kwargs):
        calls.append(True)
        raise ValueError('Unknown provider outcome; reservation retained')
    monkeypatch.setattr(narration, 'generate', fail)
    harness.config.update(tts={'enabled': True, 'provider': 'google-gemini'})
    seeded, guide = prepare(harness, monkeypatch)
    wait_voice(harness.ctx, guide['guide_id'])
    assert len(calls) == 1
    start(harness, seeded, guide)
    assert len(calls) == 1
    assert automatic_voice.status(harness.ctx, guide['guide_id'])['status'] == 'paused'
    assert not harness.ctx.store.all('attempts')
    harness.restart()
    start(harness, seeded, guide)
    assert len(calls) == 1


def test_queued_work_is_durable_and_duplicate_schedule_is_one_task(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch)
    harness.config.update(tts={'enabled': True, 'provider': 'google-gemini'})
    tasks = BackgroundTasks()
    topic = seeded['genghis']
    automatic_voice.schedule(harness.ctx, topic, guide, 'Achird', 0.9, tasks)
    automatic_voice.schedule(harness.ctx, topic, guide, 'Achird', 0.9, tasks)
    assert len(tasks.tasks) == 1
    assert automatic_voice.status(harness.ctx, guide['guide_id'])['status'] == 'queued'
    monkeypatch.setattr(narration, 'generate', lambda *args, **kwargs: {'track_id': 'saved', 'job_status': 'ready'})
    tasks.tasks[0].func()
    wait_voice(harness.ctx, guide['guide_id'])
    assert automatic_voice.status(harness.ctx, guide['guide_id'])['track_id'] == 'saved'


def test_slow_voice_does_not_hold_creation_or_start_response(harness, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def slow_voice(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return {'track_id': 'saved', 'job_status': 'ready'}
    monkeypatch.setattr(narration, 'generate', slow_voice)
    harness.config.update(tts={'enabled': True, 'provider': 'google-gemini'})
    try:
        seeded, guide = prepare(harness, monkeypatch)
        assert entered.wait(2)
        assert automatic_voice.status(harness.ctx, guide['guide_id'])['status'] == 'running'
        assert start(harness, seeded, guide)['session_id']
        assert not release.is_set()
    finally:
        release.set()
    wait_voice(harness.ctx, guide['guide_id'])


def test_recordings_stop_at_all_planned_activity_boundaries():
    sentences = [{'text': 'Welcome.'}, {'text': 'Notice the map.'}, {'text': 'What changed?'}]
    assert len(chunks(sentences)) == 1
    assert chunks(sentences, {0, 1, 2}) == [(0, 1, 'Welcome.'), (1, 1, 'Notice the map.'), (2, 1, 'What changed?')]


def test_status_reports_saved_audio_even_when_synchronization_failed(harness,monkeypatch):
    seeded,guide=prepare(harness,monkeypatch)
    ctx=harness.ctx;ctx.config.update(tts={'provider':'google-gemini'})
    ctx.ai.ledger.save_job('automatic-status',{'automatic_guide_id':guide['guide_id'],'provider':'google-gemini','status':'paused'})
    ctx.ai.ledger.save_part('saved-block',{'path':'already-saved.wav','timing':'alignment_pending'})
    ctx.ai.ledger.save_job('recording-status',{'passage_sha256':guide['passage_sha256'],'provider':'google-gemini',
        'status':'alignment_review','parts':3,'completed_parts':0,'strategy':'aligned-blocks',
        'request_ids':['saved-block','not-sent-2','not-sent-3'],'error':'Synthetic timing uncertainty'})
    result=automatic_voice.status(ctx,guide['guide_id'])
    assert result['status']=='alignment_review'
    assert result['recorded_parts']==1 and result['completed_parts']==0 and result['parts']==3
    assert result['alignment']=='local'
