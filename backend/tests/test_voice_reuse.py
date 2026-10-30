"""Changing one passage does not repurchase identical audio or retry uncertain charges."""
import hashlib
import json

import httpx
import pytest

from tests.test_ai_costs import seed_history, enable_voice, audio_response
from tutoring import guide, passages
from tutoring.expressive_audio import generate, part_key, chunks, PROVIDER, MODEL, STYLE
from services.ai_budget import BudgetError


def package(intro):
    rows = [{**s, 'kind': 'teacher', 'paragraphIndex': 0} for s in passages.split_sentences(intro)] + [
            {'text': 'The book passage stays the same.', 'kind': 'book', 'paragraphIndex': 1}]
    return {'passage_sha256': guide.guide_sha(rows), 'sentences': rows}


def manifest(h, track_id):
    return json.loads(h.ctx.file_bytes(h.ctx.store.get('audio_tracks', track_id)['manifest_path']))


def test_changed_intro_reuses_exact_book_audio_and_remaps_passage_ranges(harness):
    h = harness; s = seed_history(h); topic = h.ctx.store.get('topics', s['genghis']['id']); sent = []
    def respond(request):
        sent.append(json.loads(request.content)['input'][0]['content'][0]['text'])
        return audio_response()
    enable_voice(h, respond)
    first = generate(h.ctx, topic, package('Welcome, Lucas.'))
    old = manifest(h, first['track_id'])
    h.restart(); enable_voice(h, respond)
    changed = package('Welcome back. Let us revisit one idea.')
    estimate = generate(h.ctx, topic, changed, dry_run=True)
    assert estimate['completed_parts'] == 1 and len(sent) == 2
    made = generate(h.ctx, topic, changed)
    new = manifest(h, made['track_id'])
    assert len(sent) == 3 and new['tracks'][1]['path'] == old['tracks'][1]['path']
    assert new['tracks'][1]['startSentence'] == 2 and old['tracks'][1]['startSentence'] == 1
    assert new['cost_usd'] < old['cost_usd'] and new['part_cache'] == 'exact-text-v1'
    assert generate(h.ctx, topic, changed)['reused'] and len(sent) == 3
    # A changed layout with all exact text already recorded needs no key or enabled billing.
    h.config.update(tts={'enabled': False})
    shifted = {**changed, 'passage_sha256': 'another-layout'}
    assert generate(h.ctx, topic, shifted, dry_run=True)['allowed']
    made = generate(h.ctx, topic, shifted)
    assert h.call('GET', f"/api/tutor/audio/{made['track_id']}/manifest").json()['cost_usd'] == 0
    assert len(sent) == 3


def test_identical_parts_within_one_job_are_generated_once(harness):
    h = harness; s = seed_history(h); topic = h.ctx.store.get('topics', s['genghis']['id']); sent = []
    def respond(request):
        sent.append(request); return audio_response()
    enable_voice(h, respond)
    rows = [{'text': 'Repeat this thought.', 'paragraphIndex': i} for i in range(2)]
    made = generate(h.ctx, topic, {'passage_sha256': 'repeated', 'sentences': rows})
    manifest = h.call('GET', f"/api/tutor/audio/{made['track_id']}/manifest").json()
    assert len(sent) == 1 and len(manifest['tracks']) == 2
    assert [t['startSentence'] for t in manifest['tracks']] == [0, 1]
    assert h.ctx.ai.ledger.jobs()[0]['completed_parts'] == 2


def test_definite_rate_limit_waits_and_reuses_the_same_reservation_identity(harness, monkeypatch):
    from tutoring import expressive_audio
    seeded = seed_history(harness)
    calls, waits = [], []
    def respond(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={'retry-after': '2'}, json={'error': 'synthetic rate limit'})
        return audio_response()
    enable_voice(harness, respond)
    monkeypatch.setattr(expressive_audio.time, 'sleep', waits.append)
    made = generate(harness.ctx, seeded['genghis'], package('Welcome.'))
    assert made['job_status'] == 'ready'
    assert waits == [2]
    requests = harness.ctx.ai.ledger.requests()
    assert len(calls) == 3 and len(requests) == 2
    assert all(r['status'] == 'completed' for r in requests)


def test_rate_limit_retries_are_bounded_and_unknown_outcomes_are_not_retried(harness, monkeypatch):
    from tutoring import expressive_audio
    seeded = seed_history(harness)
    calls, waits = [], []
    def limited(request):
        calls.append(request)
        return httpx.Response(429, json={'error': 'synthetic quota limit'})
    enable_voice(harness, limited)
    monkeypatch.setattr(expressive_audio.time, 'sleep', waits.append)
    with pytest.raises(ValueError, match='429'):
        generate(harness.ctx, seeded['genghis'], package('Welcome.'))
    assert len(calls) == 3 and waits == [60, 60]
    assert harness.ctx.ai.ledger.requests()[0]['status'] == 'rejected'
    assert harness.ctx.ai.ledger.summary(harness.ctx.ai.limits)['categories']['voice']['used_usd'] == 0
    def unknown(request):
        calls.append(request)
        raise httpx.ReadTimeout('Unknown outcome')
    enable_voice(harness, unknown)
    with pytest.raises(ValueError, match='outcome is unknown'):
        generate(harness.ctx, seeded['genghis'], package('Welcome.'))
    assert len(calls) == 4 and waits == [60, 60]


def test_uncertain_part_is_not_retried_by_a_new_guide_or_restart(harness):
    h = harness; s = seed_history(h); topic = h.ctx.store.get('topics', s['genghis']['id']); sent = []
    def respond(request):
        sent.append(request); raise httpx.ReadTimeout('Lost paid response')
    enable_voice(h, respond)
    with pytest.raises(ValueError): generate(h.ctx, topic, package('Welcome.'))
    h.restart(); enable_voice(h, respond)
    shifted = {**package('Welcome.'), 'passage_sha256': 'changed-guide-identity'}
    with pytest.raises(BudgetError, match='already sent'): generate(h.ctx, topic, shifted)
    assert len(sent) == 1 and h.ctx.ai.ledger.summary(h.ctx.ai.limits)['categories']['voice']['uncertain_usd'] > 0


def test_legacy_uncertain_identity_is_preserved_after_guide_change(harness):
    h = harness; s = seed_history(h); topic = h.ctx.store.get('topics', s['genghis']['id'])
    original = package('Welcome.')
    source = passages.load(h.ctx, topic)
    built = {'mode': 'expand', 'sentences': original['sentences'], 'segments': [], 'actions': []}
    with h.ctx.store.transaction() as tx:
        guide.save(tx, topic, source, built, model='old voice', language='en-US')
    old_key = hashlib.sha256(json.dumps([original['passage_sha256'], 'lesson', PROVIDER, MODEL, 'Achird', 'en-US', .9, STYLE,
        [(first, count) for first, count, _ in chunks(original['sentences'])], 3]).encode()).hexdigest()
    rid = f'voice:{old_key}:0'
    h.ctx.ai.ledger.reserve(rid, 'voice', 1000, h.ctx.ai.limits, provider=PROVIDER, model=MODEL, operation='narration')
    h.ctx.ai.ledger.mark(rid, 'uncertain')
    sent = []
    enable_voice(h, lambda request: sent.append(request) or audio_response())
    changed = {**original, 'passage_sha256': 'new-layout'}
    with pytest.raises(BudgetError, match='already sent'): generate(h.ctx, topic, changed)
    assert not sent and h.ctx.ai.ledger.request_state(rid) == 'uncertain'
    assert part_key('Welcome.', 'Achird', 'en-US', .9) != part_key('Welcome.', 'Achird', 'pt-BR', .9)


def test_legacy_voice_limit_is_tracking_only_and_restart_reuses_recordings(harness):
    h = harness; s = seed_history(h); topic = h.ctx.store.get('topics', s['genghis']['id']); sent = []
    enable_voice(h, lambda request: sent.append(request) or audio_response())
    value = package('Welcome to the lesson.')
    preview = generate(h.ctx, topic, value, maximum_usd=.001, dry_run=True)
    assert preview['allowed'] and preview['job_limit_usd'] is None and not h.ctx.ai.ledger.jobs()
    result = generate(h.ctx, topic, value, maximum_usd=.001)
    assert result['job_status'] == 'ready' and len(sent) == 2
    h.restart(); enable_voice(h, lambda request: sent.append(request) or audio_response())
    preview = generate(h.ctx, topic, value, maximum_usd=.10, dry_run=True)
    assert preview['allowed'] and preview['estimated_cost_usd'] == 0
    assert generate(h.ctx, topic, value)['reused']
    assert len(sent) == 2


def test_known_content_refusal_uses_device_part_without_retrying_or_altering_text(harness):
    from tutoring.audio import validate_manifest
    h = harness; s = seed_history(h); topic = h.ctx.store.get('topics', s['genghis']['id']); sent = []
    def respond(request):
        value = json.loads(request.content)['input'][0]['content'][0]['text']; sent.append(value)
        return httpx.Response(400, json={'error': {'message': 'Input blocked by content policy'}}) if value.startswith('The book') else audio_response()
    enable_voice(h, respond); value = package('Welcome to History.')
    made = generate(h.ctx, topic, value, maximum_usd=.10)
    saved = manifest(h, made['track_id'])
    assert made['job_status'] == 'ready_with_fallback' and made['fallback_parts'] == 1
    assert made['completed_parts'] == made['parts'] == 2
    assert saved['tracks'][1]['fallback'] and saved['tracks'][1]['timing'] == 'device'
    assert validate_manifest(saved, value['passage_sha256'], len(value['sentences']))[0]
    assert sent == ['Welcome to History.', 'The book passage stays the same.']
    h.restart(); enable_voice(h, respond)
    replay = generate(h.ctx, topic, value)
    assert replay['reused'] and replay['completed_parts'] == 2 and len(sent) == 2
    assert h.call('GET', f"/api/tutor/audio/{made['track_id']}/parts/1").status_code == 404


def test_voice_reservation_bounds_follow_the_actual_passage_output_limit():
    from tutoring.expressive_audio import body, maximum_cost, rates
    from services.ai_budget import token_cost
    short = body('A short recall question.', 'Achird', 'en-US', .9)
    long = body('A longer narration. ' * 70, 'Achird', 'en-US', .9)
    assert short['generation_config']['max_output_tokens'] == 1500
    assert long['generation_config']['max_output_tokens'] == 6000
    for value in (short, long):
        input_bound = len(json.dumps(value, ensure_ascii=False).encode()) + 256
        assert maximum_cost(value) == token_cost(input_bound, value['generation_config']['max_output_tokens'], *rates())
    assert maximum_cost(short) < maximum_cost(long)
