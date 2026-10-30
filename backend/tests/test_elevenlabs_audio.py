import base64
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from services.ai_budget import BudgetError
from tests.test_tutoring import seed_history
from tutoring import audio, elevenlabs_audio as eleven, passages


def setup(harness, respond):
    seeded = seed_history(harness)
    harness.ctx.ai.save_key('elevenlabs', 'synthetic-elevenlabs-never-real')
    harness.config.update(tts={'provider': 'elevenlabs', 'elevenlabs_enabled': True},
        ai={'provider': 'openai', 'monthly_generation_enabled': True})
    harness.ctx.ai.http = httpx.Client(transport=httpx.MockTransport(respond))
    sentences = [{'text': 'Read the first sentence.', 'paragraphIndex': 0},
                 {'text': 'What changed?', 'paragraphIndex': 1, 'pause_after': 'question'},
                 {'text': 'Read the next part.', 'paragraphIndex': 2}]
    package = {'sentences': sentences, 'activities': [{'start_sentence': 1}],
               'passage_sha256': passages.passage_sha256('synthetic ElevenLabs lesson')}
    return seeded['genghis'], package


def response_for(text, *, malformed=False):
    starts = [i * .02 for i in range(len(text))]
    result = {'audio_base64': base64.b64encode(b'\0\0' * int((len(text) * .02 + .2) * 24000)).decode(),
              'alignment': {'characters': list(text), 'character_start_times_seconds': starts,
                            'character_end_times_seconds': [v + .01 for v in starts]}}
    if malformed:
        result['alignment']['characters'][-1] = 'X'
    return httpx.Response(200, json=result, headers={'request-id': 'synthetic-provider-request'})


def test_one_request_for_several_paragraphs_preserves_pause_clips_and_reuses(harness):
    sent = []
    def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        assert request.url.params['output_format'] == 'pcm_24000'
        return response_for(body['text'])
    topic, package = setup(harness, respond)
    sessions = harness.ctx.store.all('tutor_sessions')
    result = eleven.generate(harness.ctx, topic, package, maximum_usd=.2)
    assert len(sent) == 1
    assert sent[0]['model_id'] == 'eleven_flash_v2_5'
    assert sent[0]['language_code'] == 'en'
    assert sent[0]['text'] == ' '.join(s['text'] for s in package['sentences'])
    assert result['job_status'] == 'ready'
    row = harness.ctx.store.get('audio_tracks', result['track_id'])
    manifest = json.loads(harness.ctx.file_bytes(row['manifest_path']))
    assert manifest['provider'] == 'elevenlabs'
    assert manifest['timing'] == 'provider-alignment'
    assert [t['startSentence'] for t in manifest['tracks']] == [0, 1, 2]
    assert audio.validate_manifest(manifest, package['passage_sha256'], 3)[0]
    for track in manifest['tracks']:
        assert harness.ctx.file_bytes(track['path'], track['sha256'])
    eleven.generate(harness.ctx, topic, package)
    assert len(sent) == 1
    assert not harness.ctx.store.all('attempts')
    assert harness.ctx.store.all('tutor_sessions') == sessions
    usage = harness.ctx.ai.ledger.requests()[0]
    assert usage['provider'] == 'elevenlabs' and usage['status'] == 'completed'


def test_two_clients_generate_one_purchase(harness):
    calls = []
    def respond(request):
        calls.append(True)
        return response_for(json.loads(request.content)['text'])
    topic, package = setup(harness, respond)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: eleven.generate(harness.ctx, topic, package), range(2)))
    assert len(calls) == 1 and results[0]['track_id'] == results[1]['track_id']


def test_bad_timing_keeps_raw_paid_reply_and_never_buys_again(harness):
    calls = []
    def respond(request):
        calls.append(True)
        return response_for(json.loads(request.content)['text'], malformed=True)
    topic, package = setup(harness, respond)
    for _ in range(2):
        with pytest.raises(ValueError, match='complete original script'):
            eleven.generate(harness.ctx, topic, package)
    assert len(calls) == 1
    job = harness.ctx.ai.ledger.jobs()[0]
    assert job['status'] == 'paused'
    assert harness.ctx.ai.ledger.result(job['request_ids'][0])
    assert not harness.ctx.store.all('audio_tracks')


def test_lost_response_keeps_reservation_without_blind_retry(harness):
    calls = []
    def respond(request):
        calls.append(True)
        raise httpx.ReadTimeout('Synthetic lost reply')
    topic, package = setup(harness, respond)
    with pytest.raises(ValueError, match='remains reserved'):
        eleven.generate(harness.ctx, topic, package)
    with pytest.raises(BudgetError, match='uncertain outcome'):
        eleven.generate(harness.ctx, topic, package)
    assert len(calls) == 1
    assert harness.ctx.ai.ledger.requests()[0]['status'] == 'uncertain'


def test_estimate_tracks_cost_without_a_cap_and_disabled_provider_sends_nothing(harness):
    topic, package = setup(harness, lambda request: pytest.fail('No network expected'))
    estimate = eleven.generate(harness.ctx, topic, package, dry_run=True, maximum_usd=.000001)
    assert estimate['allowed'] and estimate['remaining_usd'] is None
    assert not harness.ctx.ai.ledger.requests()
    harness.config.update(tts={'provider': 'elevenlabs', 'elevenlabs_enabled': False})
    with pytest.raises(BudgetError, match='No request sent'):
        eleven.generate(harness.ctx, topic, package)


def test_saved_response_recovers_rounding_at_an_exhausted_cap_without_repurchase(harness, monkeypatch):
    calls = []
    def respond(request):
        calls.append(True)
        return response_for(json.loads(request.content)['text'])
    topic, package = setup(harness, respond)
    original = eleven.timed_recording
    monkeypatch.setattr(eleven, 'timed_recording', lambda *args: (_ for _ in ()).throw(ValueError('Synthetic timing failure')))
    maximum = eleven.generate(harness.ctx, topic, package, dry_run=True)['estimated_cost_usd']
    with pytest.raises(ValueError, match='Synthetic timing'):
        eleven.generate(harness.ctx, topic, package, maximum_usd=maximum)
    harness.config.update(tts={'provider': 'elevenlabs', 'elevenlabs_enabled': False})
    monkeypatch.setattr(eleven, 'timed_recording', original)
    estimate = eleven.generate(harness.ctx, topic, package, dry_run=True)
    assert estimate['allowed'] and estimate['estimated_cost_usd'] == 0
    assert eleven.generate(harness.ctx, topic, package)['job_status'] == 'ready'
    assert len(calls) == 1


def test_provider_tail_rounding_is_tolerated_but_truncation_is_rejected():
    sentences = [{'text': 'A sentence.'}]
    result = response_for(sentences[0]['text']).json()
    pcm_duration = len(base64.b64decode(result['audio_base64'])) / 48000
    result['alignment']['character_end_times_seconds'][-1] = pcm_duration + .0015
    assert eleven.timed_recording(result, sentences)[1] == pcm_duration
    result['alignment']['character_end_times_seconds'][-1] = pcm_duration + .5
    with pytest.raises(ValueError, match='invalid PCM'):
        eleven.timed_recording(result, sentences)


def test_key_storage_and_read_only_connection_check_are_host_only(harness):
    calls = []
    def respond(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={'email': 'do-not-expose@example.invalid'})
    harness.ctx.ai.http = httpx.Client(transport=httpx.MockTransport(respond))
    key = 'synthetic-elevenlabs-never-real'
    saved = harness.call('PUT', '/api/ai/key', json={'provider': 'elevenlabs', 'key': key})
    assert saved.status_code == 200 and key not in saved.text
    assert key not in harness.config.path.read_text() if harness.config.path.exists() else True
    check = harness.call('GET', '/api/ai/elevenlabs/check')
    assert check.json() == {'configured': True, 'verified': True, 'speech_requested': False}
    assert 'email' not in check.text and key not in check.text
    assert calls == [('GET', '/v1/user')]
    assert harness.call('GET', '/api/ai/elevenlabs/check', role='tutor').status_code == 403
    assert not harness.ctx.ai.ledger.requests()


def test_edit_reuses_exact_paid_speech_and_buys_only_the_changed_activity(harness):
    calls = []
    def respond(request):
        text = json.loads(request.content)['text']
        calls.append(text)
        return response_for(text)
    topic, package = setup(harness, respond)
    original = eleven.generate(harness.ctx, topic, package)
    assert len(calls) == 1  # Legacy batch includes three activity clips.
    revised = {**package, 'sentences': [*package['sentences']],
        'activities': [{'start_sentence': i, 'end_sentence': i} for i in range(3)],
        'passage_sha256': passages.passage_sha256('Revised selection question')}
    revised['sentences'][1] = {**revised['sentences'][1], 'text': 'Did it change? Yes or no.'}
    estimate = eleven.generate(harness.ctx, topic, revised, dry_run=True)
    assert estimate['completed_parts'] == 2 and estimate['parts'] == 3
    assert estimate['estimated_cost_usd'] == pytest.approx(len(revised['sentences'][1]['text']) * .04 / 1000)
    assert len(calls) == 1 and len(harness.ctx.ai.ledger.jobs()) == 1
    made = eleven.generate(harness.ctx, topic, revised)
    assert made['job_status'] == 'ready' and calls[1:] == [revised['sentences'][1]['text']]
    manifest = json.loads(harness.ctx.file_bytes(harness.ctx.store.get('audio_tracks', made['track_id'])['manifest_path']))
    assert audio.validate_manifest(manifest, revised['passage_sha256'], 3)[0]
    assert all(harness.ctx.file_bytes(t['path'], t['sha256']) for t in manifest['tracks'])
    assert original['track_id'] != made['track_id']
    eleven.generate(harness.ctx, topic, revised)
    assert len(calls) == 2


def test_saved_speech_cannot_be_reused_as_another_voice_or_speed(harness):
    topic, package = setup(harness, lambda request: response_for(json.loads(request.content)['text']))
    eleven.generate(harness.ctx, topic, package)
    revised = {**package, 'passage_sha256': passages.passage_sha256('New package'),
               'activities': [{'start_sentence': i, 'end_sentence': i} for i in range(3)]}
    for changes in ({'voice': 'another_voice_123'}, {'rate': 1.0}, {'purpose': 'feedback'}, {'language': 'pt-BR'}):
        estimate = eleven.generate(harness.ctx, topic, revised, dry_run=True, **changes)
        assert estimate['completed_parts'] == 0 and estimate['estimated_cost_usd'] > 0


def test_subscription_credit_rejection_preserves_saved_audio_and_explains_plan_can_be_active(harness):
    topic, package = setup(harness, lambda request: httpx.Response(401, json={'detail': {'status': 'quota_exceeded'}}))
    with pytest.raises(ValueError, match='plan may still be active'):
        eleven.generate(harness.ctx, topic, package)
    assert harness.ctx.ai.ledger.jobs()[0]['provider_error_code'] == 'quota_exceeded'


def test_learner_narrators_use_language_and_keep_family_fallback(harness):
    seeded = seed_history(harness)
    child = harness.ctx.store.get('subjects', seeded['genghis']['subject_id'])['child_id']
    payload = {'elevenlabs_learner_voices': [{'child_id': child,
        'english_voice': 'synthetic_male_en', 'portuguese_voice': 'synthetic_male_pt'}]}
    saved = harness.call('PUT', '/api/ai/settings', json=payload)
    assert saved.status_code == 200
    assert eleven.narrator(harness.ctx, 'en-US', child) == 'synthetic_male_en'
    assert eleven.narrator(harness.ctx, 'pt-BR', child) == 'synthetic_male_pt'
    assert eleven.narrator(harness.ctx, 'en-US', child + 999) == eleven.VOICES['en-US'][0]
    assert harness.call('PUT', '/api/ai/settings', json={}).status_code == 200
    assert eleven.narrator(harness.ctx, 'en-US', child) == 'synthetic_male_en'
    assert harness.call('PUT', '/api/ai/settings', json={'elevenlabs_learner_voices': payload['elevenlabs_learner_voices'] * 2}).status_code == 400
    assert harness.call('PUT', '/api/ai/settings', json={'elevenlabs_learner_voices': [{**payload['elevenlabs_learner_voices'][0], 'child_id': child + 999}]}).status_code == 400
