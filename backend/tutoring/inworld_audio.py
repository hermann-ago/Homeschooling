"""Inworld narration (Flash, or TTS-2 for Portuguese): stable activity blocks, durable purchases, exact timings."""
import base64
import hashlib
import io
import json
import math
import threading
import wave

from services.ai_budget import BudgetError, micros
from storage import layout
from .inworld_voices import MODEL, USD_PER_MILLION as PRICES, model_for, narrator

PROVIDER = 'inworld'
VERSION = 'inworld-flash-timed-v1'
USD_PER_MILLION = PRICES[MODEL]  # On-Demand list rate for Flash; paid plans may discount actual billing.
_lock = threading.RLock()


def characters(text):
    return len(text.encode('utf-16-le')) // 2


def blocks(sentences):
    result, current, first = [], [], 0
    for index, sentence in enumerate(sentences):
        text = sentence['text']
        if not text.strip() or characters(text) > 2000:
            raise ValueError('Split empty or oversized narration sentences before generating Inworld audio.')
        if current and characters(' '.join([*current, text])) > 2000:
            result.append((first, len(current), ' '.join(current)))
            current, first = [], index
        current.append(text)
    if current:
        result.append((first, len(current), ' '.join(current)))
    return result


def identity(text, voice, language, rate):
    return 'voice:inworld:' + hashlib.sha256(json.dumps(
        [VERSION, model_for(language), voice, language, rate, text], ensure_ascii=False).encode()).hexdigest()


def recording(ctx, result, sentences, language):
    data = base64.b64decode(result['audioContent'], validate=True)
    with wave.open(io.BytesIO(data)) as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 24000):
            raise ValueError('Inworld returned an unsupported WAV format; the paid reply is saved.')
        pcm = wav.readframes(wav.getnframes())
    timing = (result.get('timestampInfo') or {}).get('characterAlignment') or {}
    chars, starts, ends = (timing.get(k, []) for k in
        ('characters', 'characterStartTimeSeconds', 'characterEndTimeSeconds'))
    # Flash may include empty timing markers between synthesis chunks as well
    # as at the WAV tail. They carry no script character. Remove those entries
    # together, retaining the provider's original times for every real character.
    # Never repair mismatched arrays or interpolate timestamps.
    if len(chars) == len(starts) == len(ends):
        kept = [(c, start, end) for c, start, end in zip(chars, starts, ends) if c != '']
        chars = [c for c, _, _ in kept]
        starts = [start for _, start, _ in kept]
        ends = [end for _, _, end in kept]
    canonical = {'audio_base64': base64.b64encode(pcm).decode(), 'alignment': {
        'characters': chars,
        'character_start_times_seconds': starts,
        'character_end_times_seconds': ends}}
    from .elevenlabs_audio import timed_recording
    try:
        return (*timed_recording(canonical, sentences), 'provider-alignment')
    except ValueError:
        # Some normalized words have different character layouts. Verify locally
        # against the ORIGINAL script; never estimate times or repurchase audio.
        from . import narration_alignment
        measured = narration_alignment.align(ctx, data, sentences, language)
        return data, measured['duration'], measured['sentenceStarts'], 'local-alignment'


def generate(ctx, topic, passage, *, voice=None, rate=.9, language='en-US', dry_run=False,
             purpose='lesson', maximum_usd=None):
    from .elevenlabs_reuse import sections as activity_sections
    subject = ctx.store.get('subjects', topic['subject_id'])
    voice = voice or narrator(ctx, language, subject['child_id'])
    if language not in ('en-US', 'pt-BR') or not math.isfinite(rate) or not .5 <= rate <= 1.5:
        raise ValueError('Choose English or Brazilian Portuguese and a voice speed between 0.5 and 1.5.')
    sections = activity_sections(passage, blocks)
    if not sections:
        raise ValueError('This lesson has no text to narrate.')
    ids = [identity(text, voice, language, rate) for _, _, text in sections]
    key = hashlib.sha256(json.dumps([VERSION, passage['passage_sha256'], purpose, ids]).encode()).hexdigest()
    if dry_run:
        return _generate(ctx, topic, passage, sections, ids, key, voice, rate, language, True, purpose)
    with _lock:
        return _generate(ctx, topic, passage, sections, ids, key, voice, rate, language, False, purpose)


def _generate(ctx, topic, passage, sections, ids, key, voice, rate, language, dry_run, purpose):
    ledger = ctx.ai.ledger
    model = model_for(language)
    price = PRICES[model]
    saved = [ledger.part(rid) for rid in ids]
    missing = [i for i, part in enumerate(saved) if not part]
    costs = [micros(characters(text) * price / 1_000_000) for _, _, text in sections]
    purchases = {ids[i]: i for i in missing if ledger.result(ids[i]) is None}
    uncertain = any(ledger.request_state(rid) not in (None, 'rejected') for rid in purchases)
    allowed = not uncertain and (not purchases or bool(ctx.ai.key(PROVIDER) and ctx.config.get('tts', {}).get('inworld_enabled')))
    estimate = {'track_id': key, 'provider': PROVIDER, 'model': model, 'voice': voice, 'rate': rate, 'language': language,
        'parts': len(sections), 'completed_parts': len(sections) - len(missing),
        'characters': sum(characters(t) for _, _, t in sections),
        'estimated_cost_usd': sum(costs[i] for i in purchases.values()) / 1_000_000,
        'cost_basis': 'on_demand_list_rate', 'tracking_only': True, 'remaining_usd': None,
        'allowed': allowed, 'reused': not missing, 'fallback_parts': 0,
        'job_status': 'ready' if not missing else 'waiting', 'alignment': 'provider'}
    if dry_run:
        return {**estimate, 'dry_run': True, 'reason': 'An earlier Inworld request is still pending or uncertain; it will not be purchased again.' if uncertain else None if allowed else 'Connect and enable Inworld in Settings.'}
    if uncertain:
        raise BudgetError('This Inworld request was already sent. Its uncertain outcome will not be purchased again.')
    if not allowed:
        raise BudgetError('Connect and enable Inworld in Settings. No speech request sent.')
    if purchases:
        from .inworld_voices import catalog
        if not any(v['id'] == voice and v['language'] == language for v in catalog(ctx)):
            raise ValueError('Choose an available Inworld narrator in the lesson language.')
    previous = next((j for j in ledger.jobs() if j['id'] == key), {})
    job = {**previous, 'provider': PROVIDER, 'model': model, 'voice': voice, 'topic_id': topic['id'],
        'purpose': purpose, 'passage_sha256': passage['passage_sha256'], 'parts': len(sections),
        'completed_parts': len(sections) - len(missing), 'request_ids': ids, 'status': 'running',
        'error': None, 'timing': 'provider-alignment', 'cost_basis': 'on_demand_list_rate'}
    ledger.save_job(key, job)
    try:
        for i, ((first, count, text), rid) in enumerate(zip(sections, ids)):
            saved[i] = saved[i] or ledger.part(rid)
            if saved[i]:
                ctx.file_bytes(saved[i]['path'], saved[i]['sha256'])
                continue
            cached = ledger.result(rid)
            if cached is None:
                if ledger.request_state(rid) not in (None, 'rejected'):
                    raise BudgetError('This Inworld request was already sent. Its uncertain outcome will not be purchased again.')
                ledger.reserve(rid, 'voice', costs[i], ctx.ai.limits, provider=PROVIDER, model=model, operation='narration')
                body = {'text': text, 'voiceId': voice, 'modelId': model, 'language': language,
                    'audioConfig': {'audioEncoding': 'LINEAR16', 'sampleRateHertz': 24000, 'speakingRate': rate},
                    'timestampType': 'CHARACTER', 'applyTextNormalization': 'OFF'}
                try:
                    response = ctx.ai.http.post('https://api.inworld.ai/tts/v1/voice',
                        headers={'Authorization': f'Basic {ctx.ai.key(PROVIDER)}'}, json=body)
                except Exception as exc:
                    ledger.mark(rid, 'uncertain')
                    raise ValueError('Inworld connection failed. The sent request is saved and will not be repeated automatically.') from exc
                if not response.is_success:
                    ledger.mark(rid, 'rejected' if response.status_code in (400, 401, 402, 403, 404, 422, 429) else 'uncertain')
                    raise ValueError(f'Inworld returned {response.status_code}. Check account credits and the key; saved recordings are kept.')
                try:
                    result = response.json()
                except ValueError as exc:
                    ledger.mark(rid, 'uncertain')
                    raise ValueError('Inworld returned an unreadable response. Its uncertain purchase is kept.') from exc
                ledger.save_result(rid, json.dumps(result))
                processed = (result.get('usage') or {}).get('processedCharactersCount', characters(text))
                if not isinstance(processed, int) or isinstance(processed, bool) or processed < 0:
                    processed = characters(text)
                ledger.settle(rid, micros(processed * price / 1_000_000), {
                    'characters': processed, 'request_id': response.headers.get('x-request-id') or response.headers.get('request-id'),
                    'cost_basis': 'on_demand_list_rate', 'usd_per_million_characters': price})
            else:
                result = json.loads(cached)
            data, duration, offsets, timing = recording(ctx, result, passage['sentences'][first:first + count], language)
            with ctx.store.transaction(kind='tutor.inworld_audio_part') as tx:
                path, sha = tx.add_blob(data, layout.for_topic(ctx.store, topic['id'], layout.AUDIO), f'inworld-{rid[-24:]}.wav', 'audio/wav')
            saved[i] = {'path': path, 'sha256': sha, 'mime': 'audio/wav', 'duration': duration,
                'sentenceStarts': offsets, 'timing': timing}
            ledger.save_part(rid, saved[i])
            job['completed_parts'] = sum(bool(p) for p in saved)
            ledger.save_job(key, job)
        from .aligned_audio import _publish
        if any(p.get('timing') == 'local-alignment' for p in saved):
            job['timing'] = 'checked-alignment'
        _publish(ctx, topic, passage, sections, saved, key, voice, rate, language, job)
    except Exception as exc:
        job.update(status='paused', error=str(exc), cost_usd=ledger.voice_cost(key))
        ledger.save_job(key, job)
        raise
    return {**estimate, 'job_status': 'ready', 'completed_parts': len(sections), 'cost_usd': ledger.voice_cost(key)}
