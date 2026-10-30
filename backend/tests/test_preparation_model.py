import json

import httpx

from services.ai_provider import DEFAULT_MODEL, PREPARATION_MODEL, PREPARATION_READ_TIMEOUT


def test_preparation_has_its_own_model_reasoning_cache_and_price(harness, monkeypatch):
    ai = harness.ctx.ai
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-openai-never-real')
    bodies = []
    def respond(request):
        if request.url.path.endswith('/input_tokens'):
            return httpx.Response(200, json={'input_tokens': 100})
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={'status': 'completed', 'usage': {'input_tokens': 100, 'output_tokens': 50},
            'output': [{'content': [{'type': 'output_text', 'text': 'A complete synthetic lesson.'}]}]})
    ai.http = httpx.Client(transport=httpx.MockTransport(respond))
    ordinary = ai.cache_id('same task', max_output=100)
    with ai.preparing_lesson():
        assert ai.selection() == ('openai', PREPARATION_MODEL)
        assert ai.cache_id('same task', max_output=100) != ordinary
        assert ai.generate('same task', max_output=100) == 'A complete synthetic lesson.'
        ai.generate('same task', max_output=100)
    assert ai.selection() == ('openai', DEFAULT_MODEL)
    assert len(bodies) == 1
    assert bodies[0]['model'] == PREPARATION_MODEL
    assert bodies[0]['reasoning']['effort'] == 'high'
    assert ai.ledger.requests()[0]['charged_usd'] == .0007


def test_long_preparation_wait_does_not_change_live_tutoring_timeout(harness, monkeypatch):
    ai=harness.ctx.ai
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-key-never-real')
    timeouts=[]
    def respond(request):
        if request.url.path.endswith('/input_tokens'):
            return httpx.Response(200,json={'input_tokens':100})
        timeouts.append(request.extensions['timeout'])
        return httpx.Response(200,json={'status':'completed','usage':{'input_tokens':100,'output_tokens':20},
            'output':[{'content':[{'type':'output_text','text':'Synthetic reply.'}]}]})
    ai.http=httpx.Client(transport=httpx.MockTransport(respond),timeout=180)
    with ai.preparing_lesson():ai.generate('Prepare a synthetic visual lesson',max_output=100)
    ai.generate('Respond to a synthetic learner',max_output=100)
    assert timeouts[0]['read']==PREPARATION_READ_TIMEOUT
    assert timeouts[0]['connect']==30
    assert timeouts[1]['read']==180
