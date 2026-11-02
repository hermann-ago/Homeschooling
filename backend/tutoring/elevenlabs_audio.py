"""Exact-script narration with provider timings and the existing lesson manifest.

New scripts use stable activity blocks, up to 8,000 characters. Exact saved
speech and timestamps survive script corrections without another purchase.
Unknown purchases are never resent. USD values are list-price equivalents for
the local allowance, not claims about subscription credits or a provider bill.
"""
import base64
import hashlib
import io
import json
import math
import re
import threading
import wave

from services.ai_budget import BudgetError, micros
from storage import layout
from . import audio

PROVIDER = 'elevenlabs'
MODEL = 'eleven_flash_v2_5'
VERSION = 'elevenlabs-timed-v1'
PRICE_PER_1000 = .04  # Published starting-rate equivalent, not subscription billing.
MAX_CHARACTERS = 8000
VOICES = {'en-US': ('hpp4J3VqNfWAUOO0d1Us', 'Bella'),
          'pt-BR': ('hpp4J3VqNfWAUOO0d1Us', 'Bella')}
_lock = threading.Lock()
_locks = {}


def narrator(ctx, language, child_id=None):
    if language not in VOICES:
        raise ValueError('ElevenLabs narration supports English and Brazilian Portuguese')
    settings = ctx.config.get('tts', {})
    field = 'portuguese_voice' if language == 'pt-BR' else 'english_voice'
    selected = next((row[field] for row in settings.get('elevenlabs_learner_voices', [])
        if row['child_id'] == child_id), None) if child_id is not None else None
    return selected or settings.get('elevenlabs_voice_pt' if language == 'pt-BR' else 'elevenlabs_voice_en') or VOICES[language][0]


def blocks(sentences):
    result, current, first = [], [], 0
    for index, sentence in enumerate(sentences):
        text = sentence['text']
        if not text.strip() or len(text) > MAX_CHARACTERS:
            raise ValueError('Split empty or oversized narration sentences before generating audio')
        if current and len(' '.join([*current, text])) > MAX_CHARACTERS:
            result.append((first, len(current), ' '.join(current)))
            current, first = [], index
        current.append(text)
    if current:
        result.append((first, len(current), ' '.join(current)))
    return result


def identity(text, voice, language, rate):
    return 'voice:elevenlabs:' + hashlib.sha256(json.dumps(
        [VERSION, MODEL, voice, language, rate, text], ensure_ascii=False).encode()).hexdigest()


def timed_recording(result, sentences):
    """Validate the ORIGINAL-text alignment, then map exact sentence offsets."""
    text = ' '.join(s['text'] for s in sentences)
    timing = result.get('alignment') or {}
    starts, ends, chars = (timing.get(k) or [] for k in
        ('character_start_times_seconds', 'character_end_times_seconds', 'characters'))
    if (any(not isinstance(c,str) or not c for c in chars) or ''.join(chars) != text
            or len(starts) != len(chars) or len(ends) != len(chars)):
        raise ValueError('ElevenLabs timing does not match the complete original script. Saved response is kept.')
    if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in [*starts, *ends])
            or any(a > b for a, b in zip(starts, ends))
            or any(b < a for a, b in zip(starts, starts[1:]))
            or any(b < a for a, b in zip(ends, ends[1:]))):
        raise ValueError('ElevenLabs returned invalid timing; no replacement was purchased')
    pcm = base64.b64decode(result['audio_base64'], validate=True)
    duration = len(pcm) / 48000
    # Provider timestamps are rounded independently of PCM sample counts. A
    # sub-frame tail discrepancy must not discard an otherwise valid recording.
    if not pcm or len(pcm) % 2 or not 0 < duration <= 1200 or max(ends) > duration + .02:
        raise ValueError('ElevenLabs returned an invalid PCM recording')
    # Providers may group adjacent original characters, especially in URLs.
    # Use only measured fragment boundaries; never invent character timings.
    boundaries, position = {}, 0
    for index, fragment in enumerate(chars):
        boundaries[position] = starts[index]
        position += len(fragment)
    offsets, position = [], 0
    for sentence in sentences:
        if position not in boundaries:
            raise ValueError('A provider timing fragment crosses a sentence boundary; its timing needs review')
        offsets.append(boundaries[position])
        position += len(sentence['text']) + 1
    offsets[0] = 0  # Keep the actual leading silence with the first sentence.
    if any(b <= a for a, b in zip(offsets, offsets[1:])) or offsets[-1] >= duration:
        raise ValueError('ElevenLabs sentence boundaries could not be verified')
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        wav.writeframes(pcm)
    return output.getvalue(), duration, offsets


def generate(ctx, topic, passage, *, voice=None, rate=.9, language='en-US', dry_run=False,
             purpose='lesson', maximum_usd=None):
    subject = ctx.store.get('subjects', topic['subject_id'])
    voice = voice or narrator(ctx, language, (subject or {}).get('child_id'))
    if not re.fullmatch(r'[A-Za-z0-9_-]{10,100}', voice) or not .7 <= rate <= 1.2:
        raise ValueError('Choose a valid ElevenLabs voice and a rate between 0.7 and 1.2')
    from .elevenlabs_reuse import sections as activity_sections
    prior = next((j for j in reversed(ctx.ai.ledger.jobs()) if j.get('passage_sha256') == passage['passage_sha256']
                  and j.get('voice') == voice and j.get('model') == MODEL and j.get('purpose') == purpose), None)
    # Preserve old partial request identities, including sent/uncertain purchases.
    if prior and not prior.get('section_ranges'):
        sections = blocks(passage['sentences'])
    elif prior:
        sections = [(first, count, ' '.join(s['text'] for s in passage['sentences'][first:first + count]))
                    for first, count in prior['section_ranges']]
    else:
        sections = activity_sections(passage, blocks)
    if not sections:
        raise ValueError('This lesson has no text to narrate')
    ids = [identity(text, voice, language, rate) for _, _, text in sections]
    key = hashlib.sha256(json.dumps([VERSION, passage['passage_sha256'], purpose, ids]).encode()).hexdigest()
    with _lock:
        work_lock = _locks.setdefault(key, threading.Lock())
    with work_lock:
        return _generate(ctx, topic, passage, sections, ids, key, voice, rate, language, dry_run, purpose, maximum_usd)


def _generate(ctx, topic, passage, sections, ids, key, voice, rate, language, dry_run, purpose, maximum_usd):
    ledger = ctx.ai.ledger
    saved = [ledger.part(rid) for rid in ids]
    missing = [i for i, part in enumerate(saved) if not part]
    from .elevenlabs_reuse import recordings
    wanted = {i: sections[i] for i in missing if ledger.result(ids[i]) is None}
    reusable = recordings(ctx, topic, passage, wanted, voice, rate, language, purpose,
                          identity, MODEL, timed_recording) if wanted else {}
    for i in reusable:
        missing.remove(i)
    costs = [micros(len(text) * PRICE_PER_1000 / 1000) for _, _, text in sections]
    unique_missing = {ids[i]: i for i in missing if ledger.result(ids[i]) is None}
    budget = ledger.summary(ctx.ai.limits)['categories']['voice']
    previous = next((j for j in ledger.jobs() if j['id'] == key), {})
    scope_id = previous.get('generation_scope_id') or ('narration-' + key if maximum_usd is not None else None)
    scope = ledger.scope_summary(scope_id) if previous.get('generation_scope_id') else None
    remaining = None
    enabled = ctx.config.get('tts', {}).get('elevenlabs_enabled', False)
    configured = bool(ctx.ai.key(PROVIDER))
    estimate = {'track_id': key, 'provider': PROVIDER, 'model': MODEL, 'voice': voice, 'rate': rate, 'language': language,
        'characters': sum(len(t) for _, _, t in sections), 'parts': len(sections), 'completed_parts': len(saved) - len(missing),
        'estimated_cost_usd': sum(costs[i] for i in unique_missing.values()) / 1_000_000, 'remaining_usd': remaining,
        'cost_basis': 'list_price_equivalent', 'reused': not missing, 'fallback_parts': 0,
        'tracking_only': True, 'allowed': not unique_missing or bool(enabled and configured),
        'job_status': 'ready' if not missing else 'waiting', 'alignment': 'provider'}
    if dry_run:
        return {**estimate, 'dry_run': True, 'reason': None if not unique_missing or enabled and configured else
            'Connect ElevenLabs and enable its narration in Settings. Existing recordings remain available.'}
    for i, part in reusable.items():
        metadata = {k: v for k, v in part.items() if k != 'data'}
        with ctx.store.transaction(kind='tutor.elevenlabs_reuse') as tx:
            path, sha = tx.add_blob(part['data'], layout.for_topic(ctx.store, topic['id'], layout.AUDIO),
                                    f'elevenlabs-{ids[i][-24:]}.wav', 'audio/wav')
        saved[i] = {**metadata, 'path': path, 'sha256': sha}
        ledger.save_part(ids[i], saved[i])
    if missing and not estimate['allowed']:
        raise BudgetError('ElevenLabs is not connected or enabled. No request sent.')
    if scope_id and not previous.get('generation_scope_id'):
        ledger.configure_scope(scope_id, micros(maximum_usd), category='voice')
    job = {**previous, 'provider': PROVIDER, 'model': MODEL, 'voice': voice, 'topic_id': topic['id'], 'purpose': purpose,
        'passage_sha256': passage['passage_sha256'], 'parts': len(sections), 'completed_parts': len(saved) - len(missing),
        'request_ids': ids, 'status': 'running', 'error': None, 'generation_scope_id': scope_id,
        'section_ranges': [[first, count] for first, count, _ in sections],
        'timing': 'provider-alignment', 'cost_basis': 'list_price_equivalent'}
    ledger.save_job(key, job)
    try:
        for i, ((first, count, text), rid) in enumerate(zip(sections, ids)):
            saved[i] = saved[i] or ledger.part(rid)
            if saved[i]:
                ctx.file_bytes(saved[i]['path'], saved[i]['sha256'])
                continue
            # Keep the raw successful response in the existing local ledger before
            # processing it. Timing/storage repair can then use it without repurchase.
            cached = ledger.result(rid)
            if cached is None:
                if ledger.request_state(rid) not in (None, 'rejected'):
                    raise BudgetError('This ElevenLabs request was already sent. Its uncertain outcome will not be purchased again.')
                ledger.reserve(rid, 'voice', costs[i], ctx.ai.limits, provider=PROVIDER, model=MODEL,
                               operation='narration', scope_id=scope_id)
                body = {'text': text, 'model_id': MODEL, 'language_code': language.split('-')[0],
                    'voice_settings': {'stability': .5, 'similarity_boost': .75, 'speed': rate},
                    'previous_text': sections[i-1][2][-500:] if i else None,
                    'next_text': sections[i+1][2][:500] if i+1 < len(sections) else None}
                try:
                    response = ctx.ai.http.post(f'https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps?output_format=pcm_24000',
                        headers={'xi-api-key': ctx.ai.key(PROVIDER)}, json=body)
                except Exception as exc:
                    ledger.mark(rid, 'uncertain')
                    raise ValueError('ElevenLabs connection failed; the sent request remains reserved and will not be repeated.') from exc
                if response.status_code >= 400:
                    ledger.mark(rid, 'rejected' if response.status_code in (400, 401, 402, 403, 404, 422, 429) else 'uncertain')
                    try:
                        code = response.json().get('detail', {}).get('status')
                    except (ValueError, AttributeError):
                        code = None
                    # Store only an allowlisted diagnostic code; upstream error
                    # messages can echo submitted text or credentials.
                    known = {'paid_plan_required', 'payment_required', 'quota_exceeded', 'voice_not_found',
                             'missing_permissions', 'invalid_api_key', 'insufficient_credits'}
                    job['provider_error_code'] = code if code in known else None
                    job['provider_request_id'] = response.headers.get('request-id')
                    if code in ('quota_exceeded', 'insufficient_credits'):
                        raise ValueError('ElevenLabs has insufficient subscription credits for this recording. '
                            'Your plan may still be active. Saved audio is kept; no automatic replacement was requested.')
                    if response.status_code == 402:
                        raise ValueError('ElevenLabs needs account credits or a paid plan for this voice. '
                            'Free accounts cannot use Voice Library voices through the API. Choose an available built-in voice '
                            'or update the ElevenLabs plan; the script is saved and this request was not charged.')
                    raise ValueError(f'ElevenLabs returned {response.status_code}. Check the key, voice availability and account credits in Settings.')
                try:
                    result = response.json()
                except ValueError as exc:
                    ledger.mark(rid, 'uncertain')
                    raise ValueError('ElevenLabs returned an unreadable response; its reservation is kept.') from exc
                ledger.save_result(rid, json.dumps(result))
                ledger.settle(rid, costs[i], {'characters': len(text), 'request_id': response.headers.get('request-id'),
                    'cost_basis': 'list_price_equivalent', 'usd_per_1000_characters': PRICE_PER_1000})
            else:
                result = json.loads(cached)
            data, duration, offsets = timed_recording(result, passage['sentences'][first:first+count])
            with ctx.store.transaction(kind='tutor.elevenlabs_audio_part') as tx:
                path, sha = tx.add_blob(data, layout.for_topic(ctx.store, topic['id'], layout.AUDIO), f'elevenlabs-{rid[-24:]}.wav', 'audio/wav')
            saved[i] = {'path': path, 'sha256': sha, 'mime': 'audio/wav', 'duration': duration,
                        'sentenceStarts': offsets, 'timing': 'provider-alignment'}
            ledger.save_part(rid, saved[i])
            job['completed_parts'] = sum(bool(p) for p in saved)
            ledger.save_job(key, job)
        from .aligned_audio import _publish
        _publish(ctx, topic, passage, sections, saved, key, voice, rate, language, job)
    except Exception as exc:
        job.update(status='paused', error=str(exc), cost_usd=ledger.voice_cost(key))
        ledger.save_job(key, job)
        raise
    return {**estimate, 'allowed': True, 'job_status': 'ready', 'completed_parts': len(sections), 'cost_usd': ledger.voice_cost(key)}
