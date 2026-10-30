"""One app-owned editorial correction, with all usage tracked in its original job."""
import pytest

from services.ai_provider import _generation_scope
from tests.test_interactive import prepare
from tutoring import guide, script_review


@pytest.mark.parametrize('second_blocked', [False, True])
def test_one_repair_receives_saved_finding_and_reuses_original_scope(harness, monkeypatch, second_blocked):
    h = harness
    seed, old = prepare(h, monkeypatch)
    prompts, scopes, reviews = [], [], []
    def planner(text, models, **kwargs):
        prompts.append(text); scopes.append(_generation_scope.get())
        return {'mode': 'expand', 'segments': [
            {'type': 'intro', 'text': 'Let us read together.'},
            {'type': 'read', 'from': 0, 'to': 99},
            {'type': 'action', 'text': 'What changed?', 'action_kind': 'answer'},
            {'type': 'recap', 'text': 'We have reached our stopping place.'}]}, 'synthetic'
    def review(prompt, **kwargs):
        assert issubclass(kwargs['schema'], script_review.Review)
        reviews.append(_generation_scope.get())
        return {'findings': [{'category': 'task', 'severity': 'blocking',
            'activity_ids': [], 'detail': 'An assigned explanatory footnote was omitted.',
            'suggestion': 'Read its exact words from the original page.'}]
            if len(reviews) == 1 or second_blocked else []}
    monkeypatch.setattr(guide, 'write_plan', planner)
    monkeypatch.setattr(h.ctx.ai, 'generate', review)
    result = h.call('POST', '/api/tutor/reader/guide', json={
        'learner': seed['lucas']['id'], 'topic': seed['genghis']['id'],
        'rewrite': True, 'prepare_voice': False, 'maximum_usd': .1})
    assert result.status_code == 200, result.text
    assert len(prompts) == len(reviews) == 2  # never an unbounded paid loop
    assert 'An assigned explanatory footnote was omitted.' in prompts[1]
    assert len(set(scopes + reviews)) == 1
    assert h.ctx.ai.ledger.scope_summary(scopes[0])['maximum_usd'] is None
    assert result.json()['script_review']['status'] == ('needs_changes' if second_blocked else 'approved')
    assert len(h.ctx.store.find('guides', topic_id=seed['genghis']['id'])) == 3
    assert h.ctx.store.get('guides', old['guide_id'])
    assert not h.ctx.store.all('activity_responses') and not h.ctx.store.all('attempts')


@pytest.mark.parametrize('category', ['source_conflict', 'factual', 'answer_leak', 'failed'])
def test_disputes_privacy_and_failed_reviews_do_not_trigger_paid_repair(harness, monkeypatch, category):
    h = harness
    seed, _ = prepare(h, monkeypatch)
    plans, reviews = [], []
    original = guide.write_plan
    def planner(*args, **kwargs):
        plans.append(1)
        return original(*args, **kwargs)
    def review(*args, **kwargs):
        reviews.append(1)
        if category == 'failed':
            raise ValueError('Synthetic uncertain provider outcome')
        return {'findings': [{'category': category, 'severity': 'blocking', 'activity_ids': [],
            'detail': 'A source or private answer needs inspection.', 'suggestion': 'Keep the saved script for review.'}]}
    monkeypatch.setattr(guide, 'write_plan', planner)
    monkeypatch.setattr(h.ctx.ai, 'generate', review)
    response = h.call('POST', '/api/tutor/reader/guide', json={
        'learner': seed['lucas']['id'], 'topic': seed['genghis']['id'],
        'rewrite': True, 'prepare_voice': False})
    assert response.status_code == 200, response.text
    assert len(plans) == len(reviews) == 1
    assert response.json()['script_review']['status'] != 'approved'


def test_repair_tracks_all_usage_without_enforcing_the_legacy_job_cap(harness, monkeypatch):
    h = harness
    seed, _ = prepare(h, monkeypatch)
    original = guide.write_plan
    calls = []
    def charge():
        calls.append(_generation_scope.get())
        identity = 'synthetic-editorial-charge-' + str(len(calls))
        h.ctx.ai.ledger.reserve(identity, 'teaching', 30000, h.ctx.ai.limits,
            provider='openai', model='synthetic', operation='test', scope_id=calls[-1])
        h.ctx.ai.ledger.settle(identity, 30000, {})
    def planner(*args, **kwargs):
        charge()
        return original(*args, **kwargs)
    def review(*args, **kwargs):
        charge()
        return {'findings': [{'category': 'waiting', 'severity': 'blocking', 'activity_ids': [],
            'detail': 'A task needs a waiting control.', 'suggestion': 'Use one action.'}]}
    monkeypatch.setattr(guide, 'write_plan', planner)
    monkeypatch.setattr(h.ctx.ai, 'generate', review)
    response = h.call('POST', '/api/tutor/reader/guide', json={
        'learner': seed['lucas']['id'], 'topic': seed['genghis']['id'],
        'rewrite': True, 'prepare_voice': False, 'maximum_usd': .1})
    assert response.status_code == 200, response.text
    assert response.json()['script_review']['status'] == 'needs_changes'
    assert len(calls) == 4 and len(set(calls)) == 1
    assert h.ctx.ai.ledger.scope_summary(calls[0])['used_usd'] == .12
    assert len(h.ctx.ai.ledger.requests()) == 4
    assert not h.ctx.store.all('attempts')
