import io
import json
import wave
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.test_tutoring import seed_history
from tests.test_voice_reuse import package, manifest
from tutoring import local_audio


def setup(harness, monkeypatch):
    s = seed_history(harness)
    harness.config.update(tts={"provider": "kokoro-local", "enabled": False, "rate": .9})
    monkeypatch.setattr(local_audio, "available", lambda ctx: True)
    data = io.BytesIO()
    with wave.open(data, "wb") as w:
        w.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        w.writeframes(b'\x00\x00' * 24000)
    calls = []
    def render(ctx, text, voice, language, rate):
        calls.append((text, voice, language, rate))
        return data.getvalue()
    monkeypatch.setattr(local_audio, "render", render)
    # Any paid-provider access is a failure, even with an empty monthly allowance.
    def forbidden(*args, **kwargs):
        raise AssertionError("Local narration must not contact a paid provider")
    monkeypatch.setattr(harness.ctx.ai, "_post", forbidden)
    monkeypatch.setattr(harness.ctx.ai.ledger, "reserve", forbidden)
    return harness.ctx.store.get('topics', s['genghis']['id']), calls, render


def test_concurrent_devices_generate_each_part_once_without_budget_or_key(harness, monkeypatch):
    topic, calls, _ = setup(harness, monkeypatch)
    before = harness.ctx.ai.ledger.requests()
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: local_audio.generate(harness.ctx, topic, package('Hello.')), range(3)))
    assert len(calls) == 2 and len({r['track_id'] for r in results}) == 1
    assert harness.ctx.ai.ledger.requests() == before
    assert all(r['cost_usd'] == 0 for r in results)
    saved = manifest(harness, results[0]['track_id'])
    assert saved['timing'] == 'passage' and not any(p.get('fallback') for p in saved['tracks'])
    # Replay requires neither the runtime nor the model files.
    monkeypatch.setattr(local_audio, 'available', lambda ctx: False)
    assert local_audio.generate(harness.ctx, topic, package('Hello.'), dry_run=True)['reused']


def test_interruption_restart_and_changed_intro_reuse_completed_parts(harness, monkeypatch):
    topic, calls, render = setup(harness, monkeypatch)
    def fail_second(*args):
        if calls: raise RuntimeError('CPU interrupted')
        return render(*args)
    monkeypatch.setattr(local_audio, 'render', fail_second)
    with pytest.raises(ValueError, match='Completed passages are saved'):
        local_audio.generate(harness.ctx, topic, package('Hello.'))
    assert harness.ctx.ai.ledger.jobs()[0]['completed_parts'] == 1
    assert harness.ctx.ai.ledger.jobs()[0]['status'] == 'paused'
    harness.restart()
    monkeypatch.setattr(local_audio, 'render', render)
    made = local_audio.generate(harness.ctx, topic, package('Hello.'))
    assert len(calls) == 2 and made['completed_parts'] == 2
    changed = local_audio.generate(harness.ctx, topic, package('Hello again. Another thought.'))
    assert len(calls) == 3
    old, new = manifest(harness, made['track_id']), manifest(harness, changed['track_id'])
    assert old['tracks'][1]['path'] == new['tracks'][1]['path']
    assert new['tracks'][1]['startSentence'] == 2 and not harness.ctx.ai.ledger.requests()


def test_language_and_exact_identity_and_provider_settings(harness, monkeypatch):
    topic, calls, _ = setup(harness, monkeypatch)
    value = package('Leia com calma.')
    local_audio.generate(harness.ctx, topic, value, language='pt-BR')
    assert all(c[1:3] == ('pf_dora', 'pt-BR') for c in calls)
    with pytest.raises(ValueError, match='lesson language'):
        local_audio.generate(harness.ctx, topic, value, voice='am_michael', language='pt-BR')
    assert local_audio.part_key('Hello.', 'am_michael', 'en-US', .9) != local_audio.part_key('Hello.', 'af_heart', 'en-US', .9)
    assert local_audio.part_key('Hello.', 'am_michael', 'en-US', .9) != local_audio.part_key('Hello.', 'am_michael', 'en-US', 1)
    # An older client saving allowances must not switch the selected provider back.
    status = harness.call('PUT', '/api/ai/settings', json={'google_voice_enabled': True}).json()
    assert status['voice']['provider'] == 'kokoro-local' and status['voice']['google_enabled']
    assert harness.call('PUT', '/api/ai/settings', json={'voice_provider': 'google-gemini', 'google_voice_enabled': True}).json()['voice']['provider'] == 'google-gemini'


def test_routes_select_local_voice_and_saved_track_is_preferred(harness, monkeypatch):
    topic, calls, _ = setup(harness, monkeypatch)
    response = harness.call('POST', '/api/tutor/reader/narration', json={'learner': 1, 'topic': topic['id'], 'dry_run': False})
    assert response.status_code == 200 and response.json()['provider'] == 'kokoro-local'
    assert all(c[1] == 'am_michael' for c in calls)
    reader = harness.call('GET', f"/api/tutor/reader?learner=1&topic={topic['id']}").json()
    assert reader['audio'][0]['preferred'] and reader['audio'][0]['fallback_parts'] == 0
    harness.config.update(tts={"provider": "kokoro-local", "local_voice_en": "af_heart", "rate": .9})
    reader = harness.call('GET', f"/api/tutor/reader?learner=1&topic={topic['id']}").json()
    assert not reader['audio'][0]['preferred']  # Selecting Heart must not reuse Michael as that voice.
    estimate = harness.call('POST', '/api/tutor/reader/narration', json={'learner': 1, 'topic': topic['id']}).json()
    assert estimate['voice'] == 'af_heart' and not estimate['reused']


def test_missing_model_estimate_does_not_download_or_start_job(harness, monkeypatch):
    topic, calls, _ = setup(harness, monkeypatch)
    monkeypatch.setattr(local_audio, 'available', lambda ctx: False)
    estimate = local_audio.generate(harness.ctx, topic, package('Hello.'), dry_run=True)
    assert not estimate['allowed'] and not calls and not harness.ctx.ai.ledger.jobs()
    with pytest.raises(ValueError, match='Install the local voice'):
        local_audio.generate(harness.ctx, topic, package('Hello.'))


def test_test_mode_uses_host_model_without_publishing_rehearsal_learning(harness):
    from services.test_mode import TestModes
    modes = TestModes(harness.ctx)
    ctx = modes.get(modes.create())
    assert local_audio.folder(ctx) == local_audio.folder(harness.ctx)
    assert ctx.config.dir != harness.ctx.config.dir
    assert not local_audio.available(ctx)


def test_corrupt_model_is_rejected_before_inference(harness, monkeypatch):
    monkeypatch.setattr(local_audio, 'available', lambda ctx: True)
    target = local_audio.folder(harness.ctx)
    target.mkdir(parents=True)
    for name in local_audio.ASSETS:
        (target / name).write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='integrity check'):
        local_audio._engine(harness.ctx)
