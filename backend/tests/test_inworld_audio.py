import base64
import io
import json
import wave
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from tests.test_tutoring import seed_history
from tests.test_elevenlabs_audio import response_for
from tutoring import audio, inworld_audio, inworld_voices, passages
from services.ai_budget import BudgetError


def voices():
    return [{'voiceId': name, 'displayName': name, 'description': 'Clear tutoring voice.',
        'languageCode': language, 'langCode': language.replace('-', '_').upper(), 'gender': gender, 'source': 'SYSTEM'}
        for (language, gender), names in inworld_voices.CURATED.items() for name in names]


def setup(h, respond):
    s = seed_history(h)
    h.ctx.ai.save_key('inworld', 'synthetic-inworld-key-never-real')
    h.config.update(tts={'provider': 'inworld', 'inworld_enabled': True})
    def route(request):
        assert request.headers['authorization'] == 'Basic synthetic-inworld-key-never-real'
        if request.url.path == '/voices/v1/voices':
            return httpx.Response(200, json={'voices': voices(), 'totalSize': 18})
        return respond(request)
    h.ctx.ai.http = httpx.Client(transport=httpx.MockTransport(route))
    sentences = [{'text': 'Read the first sentence.', 'paragraphIndex': 0},
        {'text': 'Did it change?', 'paragraphIndex': 1, 'pause_after': 'question'},
        {'text': 'Read the next part.', 'paragraphIndex': 2}]
    package = {'sentences': sentences, 'activities': [{'start_sentence': i, 'end_sentence': i} for i in range(3)],
        'passage_sha256': passages.passage_sha256('Synthetic Inworld lesson')}
    return s, package


def speech(text, malformed=False):
    old = response_for(text, malformed=malformed).json()
    result = io.BytesIO()
    with wave.open(result, 'wb') as wav:
        wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        wav.writeframes(base64.b64decode(old['audio_base64']))
    return httpx.Response(200, json={'audioContent': base64.b64encode(result.getvalue()).decode(),
        'timestampInfo': {'characterAlignment': {
            'characters': old['alignment']['characters'],
            'characterStartTimeSeconds': old['alignment']['character_start_times_seconds'],
            'characterEndTimeSeconds': old['alignment']['character_end_times_seconds']}},
        'usage': {'processedCharactersCount': len(text), 'modelId': inworld_audio.MODEL}})


def test_flash_narration_reuses_unchanged_activities_preserves_clips_and_tracks_cost(harness):
    calls = []
    def respond(request):
        body = json.loads(request.content)
        calls.append(body)
        assert body['modelId'] == 'inworld-tts-2-flash'
        assert body['timestampType'] == 'CHARACTER'
        assert body['audioConfig']['sampleRateHertz'] == 24000
        return speech(body['text'])
    s, package = setup(harness, respond)
    before = harness.ctx.store.all('tutor_sessions')
    estimate = inworld_audio.generate(harness.ctx, s['genghis'], package, dry_run=True, maximum_usd=.000001)
    assert estimate['allowed'] and not calls and estimate['tracking_only']
    made = inworld_audio.generate(harness.ctx, s['genghis'], package)
    assert made['job_status'] == 'ready' and len(calls) == 3
    row = harness.ctx.store.get('audio_tracks', made['track_id'])
    manifest = json.loads(harness.ctx.file_bytes(row['manifest_path']))
    assert manifest['model'] == 'inworld-tts-2-flash'
    assert audio.validate_manifest(manifest, package['passage_sha256'], 3)[0]
    assert len(manifest['tracks']) == 3
    revised = {**package, 'sentences': [*package['sentences']], 'passage_sha256': passages.passage_sha256('Changed one question')}
    revised['sentences'][1] = {**revised['sentences'][1], 'text': 'Was it different? Yes or no.'}
    assert inworld_audio.generate(harness.ctx, s['genghis'], revised, dry_run=True)['completed_parts'] == 2
    inworld_audio.generate(harness.ctx, s['genghis'], revised)
    assert len(calls) == 4 and calls[-1]['text'] == revised['sentences'][1]['text']
    assert inworld_audio.generate(harness.ctx, s['genghis'], revised, dry_run=True)['estimated_cost_usd'] == 0
    assert harness.ctx.store.all('tutor_sessions') == before and not harness.ctx.store.all('attempts')


def test_unknown_purchase_is_never_repeated_after_restart(harness):
    calls = []
    def lost(request):
        calls.append(True)
        raise httpx.ReadTimeout('Synthetic lost reply')
    s, package = setup(harness, lost)
    with pytest.raises(ValueError, match='will not be repeated'):
        inworld_audio.generate(harness.ctx, s['genghis'], package)
    harness.restart()
    harness.ctx.ai.http = httpx.Client(transport=httpx.MockTransport(lost))
    with pytest.raises(BudgetError, match='already sent'):
        inworld_audio.generate(harness.ctx, s['genghis'], package)
    assert len(calls) == 1


def test_two_clients_purchase_each_part_once(harness):
    calls = []
    s, package = setup(harness, lambda request: calls.append(True) or speech(json.loads(request.content)['text']))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: inworld_audio.generate(harness.ctx, s['genghis'], package), range(2)))
    assert len(calls) == 3 and results[0]['track_id'] == results[1]['track_id']


def test_bad_timing_keeps_paid_reply_without_a_repurchase(harness):
    calls = []
    s, package = setup(harness, lambda request: calls.append(True) or speech(json.loads(request.content)['text'], malformed=True))
    for _ in range(2):
        with pytest.raises(ValueError):
            inworld_audio.generate(harness.ctx, s['genghis'], package)
    assert len(calls) == 1 and harness.ctx.ai.ledger.result(harness.ctx.ai.ledger.jobs()[0]['request_ids'][0])


def test_native_shortlist_and_free_previews_are_cached_without_synthesis(harness):
    calls = []
    def respond(request):
        calls.append((request.method, request.url.path))
        assert request.url.params['model_id'] == 'inworld-tts-2-flash'
        return httpx.Response(200, json={'audioContent': base64.b64encode(b'ID3' + b'\0' * 150).decode()})
    setup(harness, respond)
    listed = harness.call('GET', '/api/ai/inworld/voices')
    assert listed.status_code == 200, listed.text
    packet = listed.json()
    assert [(g['language'], g['gender'], len(g['voices'])) for g in packet['groups']] == [
        ('en-US', 'male', 5), ('en-US', 'female', 5), ('pt-BR', 'male', 3), ('pt-BR', 'female', 5)]
    assert not packet['popularity_ranked'] and not packet['preview_billed']
    for _ in range(2):
        reply = harness.call('GET', '/api/ai/inworld/voices/Brian/preview')
        assert reply.status_code == 200 and reply.headers['content-type'] == 'audio/mpeg'
    assert calls == [('GET', '/tts/v1/voice:preview')] and not harness.ctx.ai.ledger.requests()


def test_voice_preferences_are_language_checked_and_flash_is_not_upgraded(harness):
    s, _ = setup(harness, lambda request: pytest.fail('Do not synthesize while selecting voices'))
    body = {'voice_provider': 'inworld', 'inworld_enabled': True, 'inworld_voice_en': 'Brian', 'inworld_voice_pt': 'Bruna',
        'inworld_model': 'inworld-tts-2', 'inworld_learner_voices': [{'child_id': s['lucas']['id'], 'english_voice': 'Dennis', 'portuguese_voice': 'Maitê'}]}
    saved = harness.call('PUT', '/api/ai/settings', json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()['voice']['model'] == 'inworld-tts-2-flash'
    assert inworld_voices.narrator(harness.ctx, 'en-US', s['lucas']['id']) == 'Dennis'
    assert harness.call('PUT', '/api/ai/settings', json={**body, 'inworld_voice_en': 'Bruna'}).status_code == 400
    selected = harness.call('PUT', f"/api/topics/{s['genghis']['id']}/narrator", json={'voice': 'Alex'})
    assert selected.status_code == 200, selected.text
    assert harness.call('GET', f"/api/topics/{s['genghis']['id']}/narrator").json()['voice'] == 'Alex'
    assert not harness.ctx.ai.ledger.requests()


def test_utf16_provider_limit_is_checked_before_purchase():
    with pytest.raises(ValueError, match='oversized'):
        inworld_audio.blocks([{'text': '😀' * 1001}])


def test_flash_terminal_timing_marker_needs_no_local_alignment(harness, monkeypatch):
    from tutoring import narration_alignment
    monkeypatch.setattr(narration_alignment, 'align', lambda *a: pytest.fail('Valid provider timings need no local model'))
    reply = speech('Read the first sentence.').json()
    timing = reply['timestampInfo']['characterAlignment']
    timing['characters'].append('')
    timing['characterStartTimeSeconds'].append(timing['characterEndTimeSeconds'][-1])
    timing['characterEndTimeSeconds'].append(timing['characterEndTimeSeconds'][-1])
    _, duration, offsets, source = inworld_audio.recording(harness.ctx, reply, [{'text': 'Read the first sentence.'}], 'en-US')
    assert duration > 0 and offsets == [0] and source == 'provider-alignment'


def test_child_can_inherit_changed_family_narrator_without_purchasing(harness):
    s, _ = setup(harness, lambda request: pytest.fail('Preferences never synthesize'))
    child = s['lucas']['id']
    body = {'voice_provider': 'inworld', 'inworld_enabled': True, 'inworld_voice_en': 'Oliver',
        'inworld_learner_voices': [{'child_id': child, 'english_voice': None, 'portuguese_voice': None}]}
    saved = harness.call('PUT', '/api/ai/settings', json=body)
    assert saved.status_code == 200, saved.text
    choice = next(r for r in saved.json()['voice']['inworld_learner_voices'] if r['child_id'] == child)
    assert choice['english_voice'] is None
    assert inworld_voices.narrator(harness.ctx, 'en-US', child) == 'Oliver'
    assert not harness.ctx.ai.ledger.requests()
