import base64
import io
import json
import wave
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
import pytest
from pydantic import BaseModel

from services.ai_budget import BudgetError, BudgetLedger, local_month
from services.ai_provider import AIService, strict_schema, InvalidStructuredResponseError, StructuredResponseError
from tutoring.expressive_audio import generate, chunks, rates
from tutoring import passages
from tests.test_tutoring import seed_history


def test_atomic_tracking_uncertain_restart_and_month(tmp_path):
    moment = [datetime(2026, 11, 1, 2, tzinfo=timezone.utc)]
    path = tmp_path / 'usage.sqlite3'
    ledger = BudgetLedger(path, lambda: moment[0])
    assert local_month(moment[0]) == '2026-10'
    def reserve(i):
        try:
            ledger.reserve(str(i), 'teaching', 100_000, {'teaching': 1}, provider='openai', model='gpt-6-luna', operation='test')
            return True
        except BudgetError:
            return False
    assert reserve(0) and reserve(1)
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(reserve, range(2, 30))) == 28
    ledger.mark('0', 'uncertain')
    restarted = BudgetLedger(path, lambda: moment[0])
    assert restarted.summary({'teaching': 1})['categories']['teaching']['used_usd'] == 3
    assert restarted.summary({'teaching': 1})['categories']['teaching']['limit_usd'] is None
    with pytest.raises(BudgetError): reserve_duplicate(restarted)
    restarted.settle('1', 10_000)
    assert restarted.summary({'teaching': 1})['categories']['teaching']['used_usd'] == 2.91
    moment[0] = datetime(2026, 11, 1, 3, tzinfo=timezone.utc)
    assert restarted.summary({'teaching': 1})['categories']['teaching']['used_usd'] == 0
    with pytest.raises(BudgetError): reserve_duplicate(restarted)
    restarted.recover_interrupted()
    restarted.reconcile('0', 0)
    reserve_duplicate(restarted)  # explicit, verified unbilled request can be retried


def reserve_duplicate(ledger):
    ledger.reserve('0', 'teaching', 1, {'teaching': 1}, provider='openai', model='gpt-6-luna', operation='retry')


def test_legacy_pilot_and_job_caps_do_not_limit_tracked_costs(tmp_path):
    ledger = BudgetLedger(tmp_path / 'usage.sqlite3')
    limits = {'teaching': 3, 'books': 2, '_pilot_text': .25, '_pilot_voice': .1}
    ledger.reserve('a', 'teaching', 200_000, limits, provider='openai', model='gpt-6-luna', operation='test')
    ledger.reserve('b', 'books', 60_000, limits, provider='openai', model='gpt-6-luna', operation='test')
    ledger.configure_scope('job', 1, category='teaching')
    ledger.reserve('c', 'teaching', 500_000, limits, provider='openai', model='gpt-6-luna', operation='test', scope_id='job')
    ledger.configure_scope('job', 1, category='teaching')
    assert ledger.scope_summary('job')['used_usd'] == .5
    assert ledger.scope_summary('job')['maximum_usd'] is None
    assert ledger.summary(limits)['tracking_only'] is True


def test_generation_tracks_costs_without_pilot_or_monthly_permission(harness, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-openai-never-real')
    harness.config.update(ai={'provider': 'openai', 'limits': {'teaching': 0}, 'monthly_generation_enabled': False})
    ai = harness.ctx.ai
    def respond(request):
        if request.url.path.endswith('/input_tokens'):
            return httpx.Response(200, json={'input_tokens': 100})
        return httpx.Response(200, json={'status': 'completed', 'usage': {'input_tokens': 100, 'output_tokens': 50},
            'output': [{'content': [{'type': 'output_text', 'text': 'Saved guide.'}]}]})
    ai.http = httpx.Client(transport=httpx.MockTransport(respond))
    assert ai.generate('New guided lesson', max_output=8192) == 'Saved guide.'
    saved = harness.call('PUT', '/api/ai/settings', json={'teaching_usd': 0}).json()
    assert saved['spending_policy'] == 'tracking_only'
    assert saved['usage']['categories']['teaching']['used_usd'] > 0
    assert saved['usage']['categories']['teaching']['limit_usd'] is None
    harness.restart()
    harness.ctx.ai.ledger.reserve('after-restart', 'teaching', 1_000_000, harness.ctx.ai.limits,
        provider='openai', model='gpt-6-luna', operation='guide')
    assert harness.ctx.ai.ledger.summary({})['categories']['teaching']['used_usd'] > 1


class SmallResponse(BaseModel):
    answer: str
    note: str | None = None


@pytest.mark.parametrize('replacement_valid', [True, False, None])
def test_invalid_complete_reply_has_one_explicit_durable_replacement(harness, monkeypatch, replacement_valid):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-openai-key-never-real')
    generations = []
    invalid = '{"answer":"one","note":null} trailing {"answer":"conflicting","note":null}'
    def respond(request):
        if request.url.path.endswith('/input_tokens'):
            return httpx.Response(200, json={'input_tokens': 100})
        generations.append(json.loads(request.content))
        if len(generations) > 1 and replacement_valid is None:
            raise httpx.ReadTimeout('unknown replacement outcome')
        text = '{"answer":"replacement","note":null}' if len(generations) > 1 and replacement_valid else invalid
        return httpx.Response(200, json={'status': 'completed', 'usage': {'input_tokens': 100, 'output_tokens': 50},
            'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': text}]}]})
    ai = harness.ctx.ai = AIService(harness.ctx, httpx.Client(transport=httpx.MockTransport(respond)))
    with pytest.raises(InvalidStructuredResponseError):
        ai.generate('Assess observed work', schema=SmallResponse)
    with pytest.raises(InvalidStructuredResponseError):
        ai.generate('Assess observed work', schema=SmallResponse)
    assert len(generations) == 1  # a normal retry never repurchases invalid output
    for _ in range(2):
        if replacement_valid:
            assert ai.generate('Assess observed work', schema=SmallResponse, replace_invalid=True)['answer'] == 'replacement'
        elif replacement_valid is False:
            with pytest.raises(InvalidStructuredResponseError):
                ai.generate('Assess observed work', schema=SmallResponse, replace_invalid=True)
        else:
            with pytest.raises(ValueError):
                ai.generate('Assess observed work', schema=SmallResponse, replace_invalid=True)
        ai = AIService(harness.ctx, httpx.Client(transport=httpx.MockTransport(respond)))
    assert len(generations) == 2
    if replacement_valid is None:
        assert ai.ledger.summary(ai.limits)['categories']['teaching']['uncertain_usd'] > 0
    assert 'FORMAT RECOVERY' in generations[1]['input'][0]['content'][0]['text']
    with pytest.raises(StructuredResponseError, match='complete saved invalid reply'):
        ai.generate('Unknown outcome', schema=SmallResponse, replace_invalid=True)
    assert len(generations) == 2


def test_openai_vision_schema_usage_and_no_fallback(harness, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-openai-key-never-real')
    calls = []
    def respond(request):
        calls.append(json.loads(request.content))
        if request.url.path.endswith('/input_tokens'):
            return httpx.Response(200, json={'input_tokens': 100})
        return httpx.Response(200, json={'status': 'completed', 'usage': {'input_tokens': 100, 'output_tokens': 50},
            'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': '{"answer":"saved","note":null}'}]}]})
    harness.ctx.ai = AIService(harness.ctx, httpx.Client(transport=httpx.MockTransport(respond)))
    result = harness.ctx.ai.generate('Read this answer', images=[(b'fake', 'image/png')], schema=SmallResponse)
    assert result['answer'] == 'saved'
    assert calls[-1]['model'] == 'gpt-6-luna' and calls[-1]['reasoning']['effort'] == 'low'
    assert calls[-1]['input'][0]['content'][1]['type'] == 'input_image'
    assert calls[-1]['text']['format']['schema']['required'] == ['answer', 'note']
    assert harness.ctx.ai.ledger.summary(harness.ctx.ai.limits)['categories']['teaching']['used_usd'] == .000035
    # Background book units recover completed results before a main-DB checkpoint.
    harness.ctx.ai.generate('checkpointed page', schema=SmallResponse, category='books')
    before = len(calls)
    harness.ctx.ai.generate('checkpointed page', schema=SmallResponse, category='books')
    assert len(calls) == before
    harness.ctx.ai.generate('Read original book pages', schema=SmallResponse, category='books', pdf=b'%PDF test')
    assert calls[-1]['reasoning']['effort'] == 'low'
    assert calls[-1]['input'][0]['content'][1]['type'] == 'input_file'
    def failed(request):
        if request.url.path.endswith('/input_tokens'): return httpx.Response(200, json={'input_tokens': 100})
        raise httpx.ReadTimeout('lost response')
    harness.ctx.ai.http = httpx.Client(transport=httpx.MockTransport(failed))
    with pytest.raises(ValueError, match='reserv'):
        harness.ctx.ai.generate('uncertain')
    assert harness.ctx.ai.ledger.summary(harness.ctx.ai.limits)['categories']['teaching']['uncertain_usd'] > 0


def wav_data():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000)
        wav.writeframes(b'\0\0' * 24000)
    return buffer.getvalue()


def enable_voice(harness, respond):
    harness.ctx.ai.save_key('google', 'test-google-key-never-real')
    harness.config.update(tts={'provider': 'google-gemini', 'voice': 'Achird', 'rate': .9, 'enabled': True})
    harness.ctx.ai.http = httpx.Client(transport=httpx.MockTransport(respond))


def audio_response():
    return httpx.Response(200, json={'status': 'completed', 'usage': {'total_input_tokens': 100, 'total_output_tokens': 25},
        'output_audio': {'mime_type': 'audio/wav', 'data': base64.b64encode(wav_data()).decode()}})


def test_voice_passages_reuse_pause_resume_and_price_date(harness):
    seeded = seed_history(harness)
    topic = harness.ctx.store.get('topics', seeded['genghis']['id'])
    sentences = [{'text': 'Read this first.', 'paragraphIndex': 0},
                 {'text': 'Now answer.', 'paragraphIndex': 0, 'pause_after': 'a'},
                 {'text': 'The next passage.', 'paragraphIndex': 1}]
    package = {'passage_sha256': passages.passage_sha256('test'), 'sentences': sentences}
    sent = []
    def respond(request):
        sent.append(json.loads(request.content))
        return audio_response() if len(sent) != 2 else httpx.Response(403, json={'error': 'billing'})
    enable_voice(harness, respond)
    with pytest.raises(ValueError, match='403'):
        generate(harness.ctx, topic, package)
    assert len(sent) == 2
    assert harness.ctx.ai.ledger.jobs()[0]['status'] == 'paused'
    assert harness.ctx.ai.ledger.jobs()[0]['completed_parts'] == 1
    assert sent[0]['input'][0]['content'][0]['text'] == 'Read this first. Now answer.'
    assert 'annotations' in sent[0]['input'][0]['content'][0]
    harness.restart()
    enable_voice(harness, respond)
    made = generate(harness.ctx, topic, package)
    assert len(sent) == 3  # first completed part was not regenerated after restart
    manifest = harness.call('GET', f"/api/tutor/audio/{made['track_id']}/manifest").json()
    assert manifest['timing'] == 'passage'
    assert manifest['job_status'] == 'ready' and manifest['cost_usd'] > 0
    assert [(p['startSentence'], p['sentenceCount']) for p in manifest['tracks']] == [(0, 2), (2, 1)]
    assert all(p['sentenceStarts'] is None for p in manifest['tracks'])
    before = harness.ctx.ai.ledger.summary(harness.ctx.ai.limits)
    harness.config.update(tts={'provider': 'google-gemini', 'enabled': False})
    assert generate(harness.ctx, topic, package)['reused'] is True
    assert harness.ctx.ai.ledger.summary(harness.ctx.ai.limits) == before
    assert len(sent) == 3
    assert rates(datetime(2026, 12, 31, tzinfo=timezone.utc)) == (.5, 6)
    assert rates(datetime(2027, 1, 1, tzinfo=timezone.utc)) == (1, 12)


def test_uncertain_voice_never_retried_automatically(harness):
    seeded = seed_history(harness)
    topic = harness.ctx.store.get('topics', seeded['genghis']['id'])
    package = {'passage_sha256': 'uncertain', 'sentences': [{'text': 'Read me.'}]}
    sent = []
    def respond(request):
        sent.append(request)
        raise httpx.ReadTimeout('unknown outcome')
    enable_voice(harness, respond)
    with pytest.raises(ValueError): generate(harness.ctx, topic, package)
    with pytest.raises(BudgetError, match='already sent'): generate(harness.ctx, topic, package)
    assert len(sent) == 1


def test_settings_keys_and_allowances_are_host_only(harness):
    from fastapi.testclient import TestClient
    secret = 'test-openai-secret-never-real'
    response = harness.call('PUT', '/api/ai/key', json={'provider': 'openai', 'key': secret})
    assert response.status_code == 200 and secret not in response.text
    assert secret not in harness.config.path.read_text()
    status = harness.call('GET', '/api/ai/status').json()
    assert status['keys']['openai'] is True
    assert secret not in json.dumps(status)
    assert status['usage']['categories']['books']['limit_usd'] is None
    assert status['voice']['enabled'] is False
    remote = TestClient(harness.app, client=('192.168.1.9', 1234))
    assert remote.put('/api/ai/key', json={'provider': 'openai', 'key': secret}).status_code == 403
    assert remote.put('/api/ai/settings', json={}).status_code == 403
    assert harness.call('GET', '/api/ai/status', role='tutor').status_code == 403


def test_zero_legacy_limit_sends_one_generation_and_tracks_usage(harness, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-openai-never-real')
    harness.config.update(ai={'limits': {'teaching': 0}, 'provider': 'openai'})
    called = []
    def respond(request):
        called.append(request.url.path)
        if request.url.path.endswith('/input_tokens'):
            return httpx.Response(200, json={'input_tokens': 10})
        return httpx.Response(200, json={'status': 'completed', 'usage': {'input_tokens': 10, 'output_tokens': 10},
            'output': [{'content': [{'type': 'output_text', 'text': 'Hello.'}]}]})
    harness.ctx.ai.http = httpx.Client(transport=httpx.MockTransport(respond))
    assert harness.ctx.ai.generate('hello') == 'Hello.'
    assert harness.ctx.ai.generate('hello') == 'Hello.'
    assert called == ['/v1/responses/input_tokens', '/v1/responses']
    assert harness.ctx.ai.ledger.summary({})['categories']['teaching']['used_usd'] > 0


def test_balance_checks_persist_without_reconciling_usage_or_changing_limits(harness):
    from fastapi.testclient import TestClient
    before = harness.call('GET', '/api/ai/status').json()
    payload = {'balance': 7.81, 'currency': 'USD', 'auto_reload': False, 'note': 'Checked billing page'}
    saved = harness.call('PUT', '/api/ai/balances/openai', json=payload)
    assert saved.status_code == 200 and saved.json()['checked_at']
    remote = TestClient(harness.app, client=('192.168.1.9', 1234))
    assert remote.put('/api/ai/balances/google', json=payload).status_code == 403
    assert harness.call('PUT', '/api/ai/balances/google', json=payload).status_code == 400
    harness.restart()
    after = harness.call('GET', '/api/ai/status').json()
    assert after['provider_balances']['openai']['balance'] == 7.81
    assert after['usage'] == before['usage'] and after['voice'] == before['voice']


def test_saved_feedback_reads_server_reply_and_replays_without_generation(harness):
    seeded = seed_history(harness)
    session = '2026-09-24-genghis'
    with harness.ctx.store.transaction() as tx:
        tx.insert('lesson_dialogue', {'id': 'feedback-one', 'session_id': session,
                  'role': 'teacher', 'status': 'complete', 'text': 'Well done, Lucas.'})
        tx.insert('lesson_dialogue', {'id': 'student-one', 'session_id': session,
                  'role': 'student', 'status': 'complete', 'text': 'Student answer.'})
    calls = []
    def respond(request):
        calls.append(json.loads(request.content))
        response = audio_response().json()
        output = response.pop('output_audio')
        response['steps'] = [{'type': 'model_output', 'content': [{'type': 'audio', **output}]}]
        return httpx.Response(200, json=response)
    enable_voice(harness, respond)
    url = f'/api/tutor/sessions/{session}/feedback-audio'
    assert harness.call('POST', url, json={'message_id': 'student-one', 'dry_run': False}).status_code == 400
    made = harness.call('POST', url, json={'message_id': 'feedback-one', 'dry_run': False, 'text': 'Never speak this client text.'})
    assert made.status_code == 200, made.text
    assert calls[0]['input'][0]['content'][0]['text'] == 'Well done, Lucas.'
    harness.config.update(tts={'enabled': False})
    replay = harness.call('POST', url, json={'message_id': 'feedback-one', 'dry_run': False})
    assert replay.json()['reused'] and len(calls) == 1
    track = made.json()['track_id']
    topic = harness.ctx.store.get('topics', seeded['genghis']['id'])
    assert track not in [t['track_id'] for t in harness.ctx.tutor.audio_tracks(topic, passages.load(harness.ctx, topic))]
