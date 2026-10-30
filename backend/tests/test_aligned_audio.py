import json
from datetime import datetime, timedelta, timezone

import pytest

from services.ai_budget import BudgetError, BudgetLedger
from tests.test_ai_costs import enable_voice, audio_response
from tests.test_tutoring import seed_history
from tutoring import aligned_audio, narration_alignment, guide, narration
from tutoring import audio


def prepared(h, monkeypatch):
    seed = seed_history(h)
    topic = h.ctx.store.get('topics', seed['genghis']['id'])
    sentences = [{'text': 'Notice the map.', 'pause_after': 'first'}, {'text': 'What changed?', 'pause_after': 'second'}]
    passage = {'passage_sha256': guide.guide_sha(sentences), 'sentences': sentences,
               'activities': [{'start_sentence': 0}, {'start_sentence': 1}]}
    monkeypatch.setattr(narration_alignment, 'available', lambda *args: True)
    monkeypatch.setattr(narration_alignment, 'validate_script', lambda *args: None)
    def aligned(ctx, data, rows, language):
        assert not ctx.store._lock._is_owned()
        return {'sentenceStarts': [i*.5 for i in range(len(rows))], 'sentenceEnds': [.4, .9],
                'duration': 1., 'alignment': {'version': narration_alignment.VERSION}}
    monkeypatch.setattr(narration_alignment, 'align', aligned)
    return topic, passage


def test_one_purchase_produces_multiple_safe_activity_clips_and_cached_replay(harness, monkeypatch):
    h = harness
    topic, passage = prepared(h, monkeypatch)
    calls = []
    enable_voice(h, lambda request: calls.append(json.loads(request.content)) or audio_response())
    h.config.update(tts={**h.config.get('tts'), 'aligned_blocks': True})
    preview = narration.generate(h.ctx, topic, passage, dry_run=True)
    assert preview['parts'] == 1 and not calls
    made = narration.generate(h.ctx, topic, passage)
    assert len(calls) == 1 and made['job_status'] == 'ready'
    row = h.ctx.store.get('audio_tracks', made['track_id'])
    manifest = json.loads(h.ctx.file_bytes(row['manifest_path']))
    assert manifest['generation_blocks'] == 1 and len(manifest['tracks']) == 2
    assert [t['sentenceStarts'] for t in manifest['tracks']] == [[0.], [0.]]
    assert [t['duration'] for t in manifest['tracks']] == [.5, .5]
    assert narration.generate(h.ctx, topic, passage)['reused']
    assert len(calls) == 1 and not h.ctx.store.all('attempts')
    assert h.call('GET', f"/api/tutor/audio/{made['track_id']}/manifest").json()['timing'] == 'local-alignment'


@pytest.mark.parametrize('aligned',[False,True])
def test_free_estimate_stays_responsive_during_another_voice_purchase(harness,monkeypatch,aligned):
    import threading
    from tutoring import expressive_audio
    h=harness;topic,passage=prepared(h,monkeypatch)
    calls=[];enable_voice(h,lambda request:calls.append(request) or audio_response())
    h.config.update(tts={**h.config.get('tts'),'aligned_blocks':aligned})
    held=threading.Event();release=threading.Event();finished=threading.Event();result=[]
    def purchase():
        with expressive_audio._lock:
            held.set();release.wait(8)
    def preview():
        try:result.append(narration.generate(h.ctx,topic,passage,dry_run=True))
        except Exception as error:result.append(error)
        finally:finished.set()
    owner=threading.Thread(target=purchase);owner.start();assert held.wait(2)
    estimator=threading.Thread(target=preview);estimator.start()
    try:
        assert finished.wait(3),'A free preview waited for unrelated audio generation'
        assert isinstance(result[0],dict) and result[0]['dry_run']
        assert not calls and not h.ctx.ai.ledger.requests()
    finally:
        release.set();owner.join(3);estimator.join(3)


def test_refused_block_stays_text_only_other_blocks_finish_and_retry_never_resends(harness,monkeypatch):
    import httpx
    h=harness;topic,passage=prepared(h,monkeypatch)
    monkeypatch.setattr(aligned_audio,'MAX_CHARACTERS',20)
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(400,json={'error':{'message':'Blocked by safety controls'}}) if len(calls)==1 else audio_response()
    enable_voice(h,respond)
    result=aligned_audio.generate(h.ctx,topic,passage)
    assert result['job_status']=='ready_with_fallback' and result['fallback_parts']==1 and len(calls)==2
    row=h.ctx.store.get('audio_tracks',result['track_id'])
    manifest=json.loads(h.ctx.file_bytes(row['manifest_path']))
    assert manifest['version']==4 and manifest['tracks'][0]['fallback']
    assert manifest['tracks'][0]['sentenceCount']==1 and not manifest['tracks'][0].get('path')
    assert manifest['tracks'][1]['sentenceStarts']==[0]
    assert audio.validate_manifest(manifest,passage['passage_sha256'],2)[0]
    assert aligned_audio.generate(h.ctx,topic,passage)['reused'] and len(calls)==2
    bad=json.loads(json.dumps(manifest));bad['tracks'][0]['duration']=1
    assert not audio.validate_manifest(bad,passage['passage_sha256'],2)[0]


@pytest.mark.parametrize('declined_again',[False,True])
def test_explicit_missing_retry_keeps_identical_request_and_reuses_working_blocks(harness,monkeypatch,declined_again):
    import httpx
    h=harness;topic,passage=prepared(h,monkeypatch)
    monkeypatch.setattr(aligned_audio,'MAX_CHARACTERS',20)
    calls=[]
    def respond(request):
        calls.append(json.loads(request.content))
        if len(calls)==1 or len(calls)==3 and declined_again:
            return httpx.Response(400,json={'error':{'message':'Blocked by safety controls'}})
        return audio_response()
    enable_voice(h,respond)
    original=aligned_audio.generate(h.ctx,topic,passage)
    old_ids=h.ctx.ai.ledger.jobs()[-1]['request_ids']
    working=h.ctx.ai.ledger.part(old_ids[1])
    preview=aligned_audio.generate(h.ctx,topic,passage,retry_missing=True,dry_run=True,maximum_usd=.75)
    assert preview['estimated_cost_usd']>0 and len(calls)==2
    result=aligned_audio.generate(h.ctx,topic,passage,retry_missing=True,maximum_usd=.75)
    assert len(calls)==3 and calls[0]==calls[2]  # No filter-avoidance rewriting or rebatching.
    assert h.ctx.ai.ledger.part(old_ids[1])==working
    assert h.ctx.ai.ledger.part(old_ids[0])['fallback']  # Original refusal remains inspectable.
    assert result['track_id']==original['track_id']
    assert result['job_status']==('ready_with_fallback' if declined_again else 'ready')
    aligned_audio.generate(h.ctx,topic,passage,retry_missing=True)
    assert len(calls)==3  # Repeated/manual/ambiguous retries cannot buy another attempt.
    assert not h.ctx.store.all('activity_responses')


def test_uncertain_missing_retry_cannot_hide_behind_an_old_partial_manifest(harness,monkeypatch):
    import httpx
    h=harness;topic,passage=prepared(h,monkeypatch)
    monkeypatch.setattr(aligned_audio,'MAX_CHARACTERS',20)
    calls=[]
    def respond(request):
        calls.append(request)
        if len(calls)==1:return httpx.Response(400,json={'error':{'message':'Blocked by safety controls'}})
        if len(calls)==3:raise httpx.ReadTimeout('Synthetic ambiguous outcome')
        return audio_response()
    enable_voice(h,respond)
    aligned_audio.generate(h.ctx,topic,passage)
    with pytest.raises(ValueError,match='connection timeout.*outcome is unknown'):
        aligned_audio.generate(h.ctx,topic,passage,retry_missing=True)
    with pytest.raises(BudgetError,match='already sent'):
        aligned_audio.generate(h.ctx,topic,passage)
    assert len(calls)==3


def test_failed_alignment_retains_raw_audio_and_retry_after_restart_is_free(harness, monkeypatch):
    h = harness
    topic, passage = prepared(h, monkeypatch)
    good = narration_alignment.align
    monkeypatch.setattr(narration_alignment, 'align', lambda *args: (_ for _ in ()).throw(narration_alignment.AlignmentError('uncertain boundary')))
    calls = []
    enable_voice(h, lambda request: calls.append(request) or audio_response())
    with pytest.raises(narration_alignment.AlignmentError): aligned_audio.generate(h.ctx, topic, passage)
    assert not h.ctx.store.all('audio_tracks') and len(calls) == 1
    assert h.ctx.ai.ledger.jobs()[-1]['status'] == 'alignment_review'
    assert h.ctx.ai.ledger.part(h.ctx.ai.ledger.jobs()[-1]['request_ids'][0])['timing'] == 'alignment_pending'
    h.restart()
    enable_voice(h, lambda request: calls.append(request) or audio_response())
    monkeypatch.setattr(narration_alignment, 'align', good)
    made = aligned_audio.generate(h.ctx, topic, passage)
    assert made['job_status'] == 'ready' and len(calls) == 1


def test_explicit_repair_buys_only_one_replacement_and_retains_original_purchase(harness, monkeypatch):
    h = harness
    topic, passage = prepared(h, monkeypatch)
    good = narration_alignment.align
    calls = []
    enable_voice(h, lambda request: calls.append(json.loads(request.content)) or audio_response())
    with pytest.raises(ValueError, match='Only the saved block'):
        aligned_audio.generate(h.ctx,topic,passage,repair_block=0)
    assert not calls
    monkeypatch.setattr(narration_alignment,'align',lambda *args: (_ for _ in ()).throw(narration_alignment.AlignmentError('missing example')))
    with pytest.raises(narration_alignment.AlignmentError):
        aligned_audio.generate(h.ctx,topic,passage)
    original = h.ctx.ai.ledger.jobs()[-1]['request_ids'][0]
    with pytest.raises(ValueError, match='Only the saved block'):
        aligned_audio.generate(h.ctx,topic,passage,repair_block=1)
    preview = aligned_audio.generate(h.ctx,topic,passage,repair_block=0,dry_run=True)
    assert preview['estimated_cost_usd'] > 0 and len(calls) == 1
    # A normal retry still reuses the original audio; repair needs explicit intent.
    with pytest.raises(narration_alignment.AlignmentError):
        aligned_audio.generate(h.ctx,topic,passage)
    assert len(calls) == 1
    monkeypatch.setattr(narration_alignment,'align',good)
    made = aligned_audio.generate(h.ctx,topic,passage,repair_block=0)
    assert made['job_status'] == 'ready' and len(calls) == 2
    assert aligned_audio.REPAIR_STYLE in calls[1]['input'][0]['content'][0]['annotations'][0]['style']
    assert calls[0]['input'][0]['content'][0]['annotations'][0]['style'].count(aligned_audio.REPAIR_STYLE)==1
    job = h.ctx.ai.ledger.jobs()[-1]
    assert original != job['request_ids'][0]
    assert h.ctx.ai.ledger.part(original) and h.ctx.ai.ledger.part(job['request_ids'][0])
    assert aligned_audio.generate(h.ctx,topic,passage)['reused']
    assert len(calls) == 2


def test_older_partial_recording_keeps_its_purchase_identity_and_reuses_saved_bytes(harness,monkeypatch):
    from tests.test_ai_costs import wav_data
    from storage import layout
    h=harness;topic,passage=prepared(h,monkeypatch)
    text=' '.join(s['text'] for s in passage['sentences'])
    old=aligned_audio.identity(text,'Achird','en-US',.9,verbatim=False)
    with h.ctx.store.transaction() as tx:
        path,sha=tx.add_blob(wav_data(),layout.for_topic(h.ctx.store,topic['id'],layout.AUDIO),'old-block.wav','audio/wav')
    h.ctx.ai.ledger.save_part(old,{'path':path,'sha256':sha,'duration':1.,'timing':'alignment_pending',
        'script_sha256':'saved-synthetic-script'})
    calls=[]
    enable_voice(h,lambda request:calls.append(request) or audio_response())
    result=aligned_audio.generate(h.ctx,topic,passage)
    assert result['job_status']=='ready' and not calls
    assert h.ctx.ai.ledger.jobs()[-1]['request_ids']==[old]
    assert h.ctx.ai.ledger.part(old)['path']==path


def test_low_legacy_cap_allows_generation_but_unknown_purchase_is_not_repeated(harness, monkeypatch):
    import httpx
    h = harness
    topic, passage = prepared(h, monkeypatch)
    calls = []
    enable_voice(h, lambda request: calls.append(request) or audio_response())
    assert aligned_audio.generate(h.ctx, topic, passage, maximum_usd=.000001)['job_status'] == 'ready'
    assert len(calls) == 1
    calls.clear()
    # New job identity in a separate synthetic context, without the frozen low cap.
    changed = {**passage, 'passage_sha256': 'another-scope', 'sentences': [{'text': 'A different invented recording.'}]}
    def lost(request):
        calls.append(request)
        raise httpx.ReadTimeout('unknown result')
    enable_voice(h, lost)
    with pytest.raises(ValueError): aligned_audio.generate(h.ctx, topic, changed)
    with pytest.raises(BudgetError): aligned_audio.generate(h.ctx, topic, changed)
    assert len(calls) == 1


def test_voice_pacing_is_durable_without_a_local_daily_ceiling(tmp_path):
    now = [datetime(2026,10,19,18,tzinfo=timezone.utc)]
    ledger = BudgetLedger(tmp_path/'usage.sqlite3', lambda: now[0])
    for i in range(9): assert ledger.claim_voice_slot(str(i), 'google-gemini', 'model') == 0
    assert ledger.claim_voice_slot('wait', 'google-gemini', 'model') > 0
    for i in range(9,100):
        now[0] += timedelta(seconds=62)
        assert ledger.claim_voice_slot(str(i), 'google-gemini', 'model') == 0
    restarted = BudgetLedger(ledger.path, lambda: now[0])
    assert restarted.claim_voice_slot('beyond-old-ceiling', 'google-gemini', 'model') == 0
    now[0] = datetime(2026,10,20,7,tzinfo=timezone.utc)
    assert restarted.claim_voice_slot('next-day', 'google-gemini', 'model') == 0


def test_layout_changes_realign_saved_purchase_without_rebuying(harness, monkeypatch):
    h = harness
    topic, passage = prepared(h, monkeypatch)
    calls = []
    enable_voice(h, lambda request: calls.append(request) or audio_response())
    aligned_audio.generate(h.ctx, topic, passage)
    # Same narration text, a different semantic sentence boundary.
    changed = {**passage, 'passage_sha256': 'changed-layout',
               'sentences': [{'text': 'Notice the'}, {'text': 'map. What changed?'}]}
    made = aligned_audio.generate(h.ctx, topic, changed)
    assert made['job_status'] == 'ready' and len(calls) == 1
    part = h.ctx.ai.ledger.part(h.ctx.ai.ledger.jobs()[-1]['request_ids'][0])
    assert part['sentence_layout'] == aligned_audio.sentence_layout(changed['sentences'])


def test_unsupported_script_and_exhausted_quota_do_not_purchase(harness, monkeypatch):
    h = harness
    topic, passage = prepared(h, monkeypatch)
    calls = []
    enable_voice(h, lambda request: calls.append(request) or audio_response())
    with pytest.raises(narration_alignment.AlignmentError):
        aligned_audio.generate(h.ctx, topic, {**passage, 'sentences': [{'text': '2 + 2 = 4'}]})
    monkeypatch.setattr(h.ctx.ai.ledger, 'claim_voice_slot', lambda *args, **kwargs: (_ for _ in ()).throw(BudgetError('daily quota')))
    preview = aligned_audio.generate(h.ctx, topic, passage, dry_run=True)
    assert not preview['allowed'] and preview['reason'] == 'daily quota'
    with pytest.raises(BudgetError, match='daily'):
        aligned_audio.generate(h.ctx, topic, passage)
    assert not calls
    assert not h.ctx.ai.ledger.requests()


@pytest.mark.parametrize('starts,duration,count', [([0,0], 1,2), ([0,float('nan')],1,2),
    ([0,1],1,2), ([.2],1,1), ([0],float('inf'),1), ([0],1,2)])
def test_invalid_local_timings_are_not_published(starts, duration, count):
    manifest = {'version': 4, 'passageHash': 'script', 'sentenceCount': count,
        'tracks': [{'startSentence': 0, 'sentenceCount': count, 'sentenceStarts': starts, 'duration': duration}]}
    assert not audio.validate_manifest(manifest, 'script', count)[0]
