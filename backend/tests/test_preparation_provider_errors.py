import httpx
import pytest

from services.ai_provider import AIService, RateLimitError


@pytest.mark.parametrize('code,expected', [
    ('insufficient_quota', 'provider_quota'),
    ('billing_hard_limit_reached', 'provider_quota'),
    ('credit_balance_exhausted', 'provider_quota'),
    ('rate_limit_exceeded', 'provider_rate_limit'),
    ('unrecognized', 'provider_429'),
])
def test_preparation_distinguishes_quota_and_rate_limits_without_leaking_upstream_text(harness, code, expected):
    calls=[]
    def respond(request):
        calls.append(True)
        return httpx.Response(429, headers={'retry-after': '12'}, json={
            'error': {'code': code, 'message': 'PRIVATE SOURCE AND SECRET must not reach the UI'}})
    ai=AIService(harness.ctx,httpx.Client(transport=httpx.MockTransport(respond)))
    with pytest.raises(RateLimitError) as caught:
        ai._post('https://api.openai.com/v1/responses/input_tokens',{}, {})
    assert caught.value.code==expected and caught.value.retry_after==12
    assert 'PRIVATE' not in str(caught.value) and len(calls)==1
    assert not ai.ledger.requests()


@pytest.mark.parametrize('code,kind,expected', [
    (None, 'insufficient_quota', 'provider_quota'),
    ('new_billing_code', 'insufficient_quota', 'provider_quota'),
    (None, 'rate_limit_exceeded', 'provider_rate_limit'),
    ('new_code', 'unknown_type', 'provider_429'),
])
def test_provider_error_type_is_a_safe_fallback(harness, code, kind, expected):
    transport=httpx.MockTransport(lambda request:httpx.Response(429,json={
        'error':{'code':code,'type':kind,'message':'PRIVATE source, account and key'}}))
    ai=AIService(harness.ctx,httpx.Client(transport=transport))
    with pytest.raises(RateLimitError) as caught:
        ai._post('https://api.openai.com/v1/responses',{}, {})
    assert caught.value.code==expected
    assert 'PRIVATE' not in str(caught.value)
