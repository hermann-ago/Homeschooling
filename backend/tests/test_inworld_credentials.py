"""Inworld setup uses the existing host-only encrypted secret store."""
import json

from fastapi.testclient import TestClient
import httpx


def test_inworld_key_is_host_only_durable_and_never_exposed_or_used(harness, monkeypatch):
    h = harness
    monkeypatch.delenv('INWORLD_API_KEY', raising=False)
    secret = 'c3ludGhldGljLWlud29ybGQta2V5'
    def no_requests(*args, **kwargs):
        raise AssertionError('Saving credentials must not contact any provider')
    monkeypatch.setattr(h.ctx.ai.http, 'request', no_requests)
    before = h.config.get('tts', {}).copy()
    assert not h.call('GET', '/api/ai/status').json()['keys']['inworld']
    remote = TestClient(h.app, client=('192.168.1.9', 1234))
    assert remote.put('/api/ai/key', json={'provider': 'inworld', 'key': secret}).status_code == 403
    response = h.call('PUT', '/api/ai/key', json={'provider': 'inworld', 'key': secret})
    assert response.status_code == 200 and secret not in response.text
    assert h.ctx.ai.key('inworld') == secret and h.config.get('tts', {}) == before
    assert secret not in h.config.path.read_text() if h.config.path.exists() else True
    assert not h.ctx.ai.ledger.requests()
    h.restart()
    status = h.call('GET', '/api/ai/status').json()
    assert status['keys']['inworld'] and secret not in json.dumps(status)
    assert h.ctx.ai.key('inworld') == secret
    assert not h.ctx.ai.ledger.requests()


def test_inworld_environment_credential_is_supported_without_exposing_it(harness, monkeypatch):
    monkeypatch.setenv('INWORLD_API_KEY', 'synthetic-inworld-key-never-real')
    assert harness.ctx.ai.key('inworld') == 'synthetic-inworld-key-never-real'
    assert harness.call('GET', '/api/ai/status').json()['keys']['inworld']


def test_connection_check_reads_voices_without_synthesizing_or_exposing_key(harness):
    h = harness
    secret = 'synthetic-inworld-key-never-real'
    h.ctx.ai.save_key('inworld', secret)
    calls = []
    def respond(request):
        calls.append((request.method, request.url.path))
        assert request.headers['authorization'] == f'Basic {secret}'
        return httpx.Response(200, json={'voices': [{'voiceId': 'fixture', 'displayName': 'Private voice name'}]})
    h.ctx.ai.http = httpx.Client(transport=httpx.MockTransport(respond))
    checked = h.call('GET', '/api/ai/inworld/check')
    assert checked.status_code == 200 and checked.json() == {'configured': True, 'verified': True, 'speech_requested': False}
    assert secret not in checked.text and 'Private voice name' not in checked.text
    assert calls == [('GET', '/voices/v1/voices')] and not h.ctx.ai.ledger.requests()
    assert h.call('GET', '/api/ai/inworld/check', role='tutor').status_code == 403
    remote = TestClient(h.app, client=('192.168.1.9', 1234))
    assert remote.get('/api/ai/inworld/check').status_code == 403
