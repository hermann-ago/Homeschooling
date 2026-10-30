"""Preparation previews are free and bounded generation shares the family ledger."""
import json

import httpx

from tests.test_tutoring import seed_history
from tests.test_ai_costs import enable_voice, audio_response
from tutoring import passages


def test_guide_preview_sends_no_request_and_generation_respects_job_cap(harness, monkeypatch):
    h = harness; s = seed_history(h); sent = []
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key-never-real')
    h.config.update(ai={'provider': 'openai', 'monthly_generation_enabled': True})
    def respond(request):
        assert not h.ctx.store._lock._is_owned()
        sent.append(request.url.path)
        if request.url.path.endswith('/input_tokens'):
            return httpx.Response(200, json={'input_tokens': 100})
        plan = {'welcome':'Let us read.','turns':[
            {'type':'read','first':0,'last':len(passages.load(h.ctx,s['genghis'])['sentences'])-1},
            {'type':'ask','prompt':'Explain one idea.'}],'closing':'We reached our stopping place.'}
        if json.loads(request.content).get('instructions')=='Return only the structured editorial review.':plan={'findings':[]}
        return httpx.Response(200, json={'status': 'completed', 'usage': {'input_tokens': 100, 'output_tokens': 100},
            'output': [{'content': [{'type': 'output_text', 'text': json.dumps(plan)}]}]})
    h.ctx.ai.http = httpx.Client(transport=httpx.MockTransport(respond))
    payload = {'learner': s['lucas']['id'], 'topic': s['genghis']['id'], 'maximum_usd': .000001}
    before = h.ctx.store.all('attempts')
    preview = h.call('POST', '/api/tutor/reader/guide', json={**payload, 'dry_run': True})
    assert preview.status_code == 200 and not preview.json()['allowed'] and not sent and not h.ctx.store.all('guides')
    stopped = h.call('POST', '/api/tutor/reader/guide', json=payload)
    assert stopped.status_code == 502 and all(p.endswith('/input_tokens') for p in sent)
    assert not h.ctx.store.all('guides') and not h.ctx.ai.ledger.requests()
    payload['maximum_usd'] = .30
    ready = h.call('POST', '/api/tutor/reader/guide', json=payload)
    assert ready.status_code == 200, ready.text
    count = len(sent)
    replay = h.call('POST', '/api/tutor/reader/guide', json={**payload, 'dry_run': True}).json()
    assert replay['reused'] and replay['estimated_cost_usd'] == 0 and len(sent) == count
    assert ready.json()['script_review']['status']=='approved'
    assert h.ctx.store.all('attempts') == before and len(h.ctx.ai.ledger.requests()) == 2
    with h.ctx.ai.ledger.connect() as db:
        assert db.execute('SELECT COUNT(DISTINCT scope_id) FROM request_scopes').fetchone()[0] == 1
    assert h.call('POST', '/api/tutor/reader/guide', role='tutor', json={**payload, 'dry_run': True}).status_code == 403


def test_saved_warmup_audio_retrieves_server_prompt_and_cached_replay_is_free(harness):
    h = harness; s = seed_history(h); session_id = '2026-09-24-genghis'; sent = []
    with h.ctx.store.transaction() as tx:
        tx.insert('lesson_actions', {'id': session_id + ':warmup', 'session_id': session_id, 'child_id': s['lucas']['id'],
            'subject_id': s['history']['id'], 'topic_id': s['genghis']['id'], 'action_id': 'warmup', 'kind': 'answer',
            'status': 'pending', 'prompt': 'Recall the tribes from our earlier lesson.'})
    enable_voice(h, lambda request: sent.append(json.loads(request.content)) or audio_response())
    url = f'/api/tutor/sessions/{session_id}/action-audio'
    assert h.call('POST', url, json={'action_id': 'invented', 'dry_run': False}).status_code == 400
    ready = h.call('POST', url, json={'action_id': 'warmup', 'text': 'Do not speak this client text.', 'dry_run': False})
    assert ready.status_code == 200, ready.text
    assert sent[0]['input'][0]['content'][0]['text'] == 'Recall the tribes from our earlier lesson.'
    h.config.update(tts={'enabled': False})
    assert h.call('POST', url, json={'action_id': 'warmup', 'dry_run': False}).json()['reused'] and len(sent) == 1
    assert h.call('POST', url, role='tutor', json={'action_id': 'warmup'}).status_code == 403


def test_interactive_pilot_cap_retains_saved_answer_without_a_paid_request(harness, monkeypatch):
    from tests.test_interactive import prepare, pause, change
    h = harness; s, guide = prepare(h, monkeypatch); sent = []
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key-never-real')
    h.config.update(ai={'provider': 'openai', 'monthly_generation_enabled': True})
    def respond(request):
        sent.append(request.url.path)
        assert request.url.path.endswith('/input_tokens')
        return httpx.Response(200, json={'input_tokens': 100})
    h.ctx.ai.http = httpx.Client(transport=httpx.MockTransport(respond))
    payload = {'learner': s['lucas']['id'], 'topic': s['genghis']['id'], 'guide_id': guide['guide_id'], 'maximum_usd': .000001}
    state = h.call('POST', '/api/tutor/interactive/start', json=payload).json()
    state = pause(h, state, guide)
    result = change(h, state, 'answer', action_id='action-1', message_id='capped-answer', text='He united the tribes.')
    assert result['error'] and h.ctx.store.get('lesson_dialogue', 'capped-answer')['text'] == 'He united the tribes.'
    assert not h.ctx.store.all('attempts') and not h.ctx.ai.ledger.requests()
    scope = result['playback']['generation_scope_id']
    h.restart()
    resumed = h.call('POST', '/api/tutor/interactive/start', json={**payload, 'maximum_usd': .15}).json()
    assert resumed['playback']['generation_scope_id'] == scope
    assert h.ctx.ai.ledger.scope_summary(scope)['maximum_usd'] == .000001
    assert all(path.endswith('/input_tokens') for path in sent)
