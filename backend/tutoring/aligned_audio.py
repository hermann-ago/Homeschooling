"""Generate larger Gemini blocks, retain raw purchases, align locally, publish safe clips."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import wave

from services.ai_budget import BudgetError, token_cost
from services.ai_provider import ContentRejectedError
from . import audio, expressive_audio as expressive, narration_alignment as alignment
from storage import layout

VERSION = 'aligned-blocks-v1'
MAX_CHARACTERS = 2400
MAX_WORDS = 420
MAX_OUTPUT = 12000
REPAIR_STYLE = (' Read the supplied text verbatim, from beginning to end. Speak every repeated '
                'instruction, every example, and every choice label each time it appears. '
                'Do not summarize, skip, answer, correct, or add words.')


def blocks(sentences):
    """Group across paragraph/activity boundaries; never cut a sentence in half."""
    result, current, first = [], [], 0
    for index, sentence in enumerate(sentences):
        text = sentence['text']
        if len(text) > MAX_CHARACTERS or len(text.encode()) > 6000 or len(text.split()) > MAX_WORDS:
            raise ValueError('A narrator sentence is too long for a checked audio block.')
        joined = ' '.join(current + [text])
        if current and (len(joined) > MAX_CHARACTERS or len(joined.encode()) > 6000 or len(joined.split()) > MAX_WORDS):
            result.append((first, len(current), ' '.join(current)))
            current, first = [], index
        current.append(text)
    if current:
        result.append((first, len(current), ' '.join(current)))
    return result


def identity(text, voice, language, rate, *, verbatim=True):
    return 'voice:block:' + hashlib.sha256(json.dumps(
        [VERSION, expressive.PROVIDER, expressive.MODEL, expressive.STYLE+(REPAIR_STYLE if verbatim else ''), voice, language, rate, text],
        ensure_ascii=False).encode()).hexdigest()


def sentence_layout(sentences):
    return hashlib.sha256(json.dumps([s['text'] for s in sentences], ensure_ascii=False).encode()).hexdigest()


def has_alignment(part, sentences):
    return bool(part and part.get('sentenceStarts') and len(part['sentenceStarts']) == len(sentences)
        and part.get('sentence_layout') == sentence_layout(sentences)
        and (part.get('alignment') or {}).get('version') == alignment.VERSION)


def payload(text, voice, language, rate, *, verbatim=True):
    result = expressive.body(text, voice, language, rate)
    if verbatim:result['input'][0]['content'][0]['annotations'][0]['style'] += REPAIR_STYLE
    result['generation_config']['max_output_tokens'] = MAX_OUTPUT
    return result


def clip(data, start, end):
    with wave.open(io.BytesIO(data)) as source:
        rate = source.getframerate()
        lo, hi = round(start * rate), round(end * rate)
        if not 0 <= lo < hi <= source.getnframes():
            raise alignment.AlignmentError('An activity cut lies outside the saved recording.')
        source.setpos(lo)
        frames = source.readframes(hi - lo)
        output = io.BytesIO()
        with wave.open(output, 'wb') as target:
            target.setparams((source.getnchannels(), source.getsampwidth(), rate, 0, 'NONE', 'not compressed'))
            target.writeframes(frames)
    return output.getvalue()


def _publish(ctx, topic, passage, sections, saved, key, voice, rate, language, job):
    provider, model = job.get('provider', expressive.PROVIDER), job.get('model', expressive.MODEL)
    timing = job.get('timing', 'local-alignment')
    tracks = []
    folder = layout.for_topic(ctx.store, topic['id'], layout.AUDIO)
    boundaries = {a['start_sentence'] for a in passage.get('activities', []) if a.get('start_sentence') is not None}
    boundaries.update(i + 1 for i, s in enumerate(passage['sentences']) if s.get('pause_after'))
    for (first, count, _), block in zip(sections, saved):
        cuts = sorted({first, first + count} | {i for i in boundaries if first < i < first + count})
        if block.get('fallback'):
            tracks.extend({'fallback':True,'reason':block['reason'],'startSentence':lo,
                'sentenceCount':hi-lo,'duration':0,'timing':'device'} for lo,hi in zip(cuts,cuts[1:]))
            continue
        data = ctx.file_bytes(block['path'], block['sha256'])
        times = block['sentenceStarts']
        for lo, hi in zip(cuts, cuts[1:]):
            start = times[lo-first]
            end = times[hi-first] if hi < first+count else block['duration']
            content = clip(data, start, end)
            with ctx.store.transaction(kind='tutor.aligned_audio_clip') as tx:
                path, sha = tx.add_blob(content, folder,
                    f"aligned-{hashlib.sha256(content).hexdigest()[:24]}.wav", 'audio/wav')
            tracks.append({'path': path, 'sha256': sha, 'mime': 'audio/wav', 'startSentence': lo,
                'sentenceCount': hi-lo, 'sentenceStarts': [round(t-start, 6) for t in times[lo-first:hi-first]],
                'duration': round(end-start, 6), 'timing': timing})
    fallback_parts=sum(bool(t.get('fallback')) for t in tracks)
    ready_status='ready_with_fallback' if fallback_parts else 'ready'
    cost = None if job.get('cost_basis') == 'external_recording' else ctx.ai.ledger.voice_cost(key)
    manifest = {'version': 4, 'cacheKey': key, 'provider': provider, 'model': model,
        'voice': voice, 'language': language, 'speakingRate': rate, 'passageHash': passage['passage_sha256'],
        'sentenceCount': len(passage['sentences']), 'timing': timing, 'tracks': tracks,
        'generation_blocks': len(sections), 'job_status': ready_status,'fallback_parts':fallback_parts,
        'cost_usd': cost}
    valid, reason = audio.validate_manifest(manifest, passage['passage_sha256'], len(passage['sentences']))
    if not valid:
        raise alignment.AlignmentError(reason)
    with ctx.store.transaction(kind='tutor.aligned_audio_manifest') as tx:
        path, _ = tx.add_blob(json.dumps(manifest).encode(), folder, f'narration-{key[:24]}-manifest.json', 'application/json')
        values = {'topic_id': topic['id'], 'passage_sha256': passage['passage_sha256'], 'provider': provider,
            'voice': voice, 'speaking_rate': rate, 'manifest_path': path, 'status': 'ready',
            'characters': sum(len(s['text']) for s in passage['sentences']), 'sentence_count': len(passage['sentences']),
            'timing': timing, 'note': 'feedback:audio' if job['purpose'] == 'feedback' else None}
        if tx.get('audio_tracks', key):
            tx.update('audio_tracks', key, values)
        else:
            tx.insert('audio_tracks', {'id': key, **values})
    job.update(status=ready_status, completed_parts=len(sections),fallback_parts=fallback_parts, cost_usd=manifest['cost_usd'])
    ctx.ai.ledger.save_job(key, job)


def generate(ctx, topic, passage, *, voice='Achird', rate=.9, language='en-US', dry_run=False,
             purpose='lesson', maximum_usd=None, repair_block=None, retry_missing=False):
    if dry_run:
        return _generate(ctx, topic, passage, voice, rate, language, True, purpose, maximum_usd, repair_block,retry_missing)
    # Share the provider purchase lock with the legacy path. Activity transitions
    # and database transactions do not wait on this worker lock.
    with expressive._lock:
        return _generate(ctx, topic, passage, voice, rate, language, dry_run, purpose, maximum_usd, repair_block,retry_missing)


def _generate(ctx, topic, passage, voice, rate, language, dry_run, purpose, maximum_usd, repair_block,retry_missing=False):
    sentences = passage['sentences']
    if not sentences:
        raise ValueError('This lesson has no text to narrate')
    jobs={j['id']:j for j in ctx.ai.ledger.jobs()}
    def reusable(manifest,track_id):
        job=jobs.get(track_id,{})
        return (manifest.get('job_status','ready') in ('ready','ready_with_fallback')
            and not (retry_missing and manifest.get('fallback_parts'))
            and not (job.get('retry_requests') and job.get('status') not in ('ready','ready_with_fallback')))
    # Keep complete, verified recordings playable without buying replacements.
    for row in ctx.store.find('audio_tracks', passage_sha256=passage['passage_sha256']):
        if (row['provider'] != expressive.PROVIDER or row['voice'] != voice or row['speaking_rate'] != rate
                or row['status'] != 'ready'):
            continue
        manifest = json.loads(ctx.file_bytes(row['manifest_path']))
        valid, _ = audio.validate_manifest(manifest, passage['passage_sha256'], len(sentences))
        if valid and manifest.get('language') == language and reusable(manifest,row['id']):
            for track in manifest['tracks']:
                if not track.get('fallback'):ctx.file_bytes(track['path'], track['sha256'])
            count = manifest.get('generation_blocks', len(manifest['tracks']))
            return {'track_id': row['id'], 'reused': True, 'allowed': True, 'estimated_cost_usd': 0,
                    'parts': count, 'completed_parts': count, 'job_status': manifest.get('job_status','ready'),
                    'fallback_parts':manifest.get('fallback_parts',0),
                    'provider': expressive.PROVIDER, 'model': expressive.MODEL}
    for sentence in sentences:
        alignment.normalize(sentence['text'], language)  # check unsupported forms before purchasing
    sections = blocks(sentences)
    ledger = ctx.ai.ledger
    # Preserve every identity declared by an older partial job, including blocks
    # not yet sent. New lessons receive the stricter read-verbatim direction.
    declared={rid for job in ledger.jobs() if job.get('passage_sha256')==passage['passage_sha256']
              for rid in job.get('request_ids',[])}
    legacy=[identity(text,voice,language,rate,verbatim=False) for _,_,text in sections]
    use_legacy=[rid in declared or bool(ledger.part(rid)) or ledger.request_state(rid) is not None for rid in legacy]
    ids = [legacy[i] if use_legacy[i] else identity(text, voice, language, rate) for i,(_,_,text) in enumerate(sections)]
    key = hashlib.sha256(json.dumps([VERSION, passage['passage_sha256'], purpose, ids,
                                    alignment.VERSION, [a.get('start_sentence') for a in passage.get('activities', [])]]).encode()).hexdigest()
    existing = ctx.store.get('audio_tracks', key)
    if existing and existing['status'] == 'ready':
        manifest = json.loads(ctx.file_bytes(existing['manifest_path']))
        valid, _ = audio.validate_manifest(manifest, passage['passage_sha256'], len(sentences))
        if valid and reusable(manifest,key):
            for track in manifest['tracks']:
                if not track.get('fallback'):ctx.file_bytes(track['path'], track['sha256'])
            return {'track_id': key, 'reused': True, 'allowed': True, 'estimated_cost_usd': 0,
                    'parts': len(sections), 'completed_parts': len(sections), 'job_status': manifest.get('job_status','ready'),
                    'fallback_parts':manifest.get('fallback_parts',0),
                    'provider': expressive.PROVIDER, 'model': expressive.MODEL}
    previous = next((j for j in ledger.jobs() if j['id'] == key), {})
    retries=dict(previous.get('retry_requests') or {})
    for index,rid in retries.items():ids[int(index)]=rid
    repairs = dict(previous.get('repair_requests') or {})
    if repair_block is not None and str(repair_block) not in repairs:
        if (not isinstance(repair_block,int) or isinstance(repair_block,bool)
                or not 0 <= repair_block < len(sections)
                or previous.get('status') != 'alignment_review'
                or repair_block != previous.get('completed_parts')
                or not ledger.part(ids[repair_block])):
            raise ValueError('Only the saved block stopped for alignment review can be re-recorded.')
        repairs[str(repair_block)] = 'voice:block:repair:' + hashlib.sha256(
            (ids[repair_block]+REPAIR_STYLE).encode()).hexdigest()
    scope_id = previous.get('generation_scope_id')
    scope = ledger.scope_summary(scope_id) if scope_id else None
    if maximum_usd is not None and not scope_id:
        scope_id = 'narration-' + key
        scope = {'maximum_usd': maximum_usd, 'remaining_usd': maximum_usd}
    requests = [payload(text, voice, language, rate,verbatim=not use_legacy[i]) for i,(_,_,text) in enumerate(sections)]
    for index,rid in repairs.items():
        index = int(index)
        ids[index] = rid
        requests[index]['input'][0]['content'][0]['annotations'][0]['style'] += REPAIR_STYLE
    if retry_missing:
        for i,rid in enumerate(ids):
            part=ledger.part(rid)
            if str(i) in retries or not part or not part.get('fallback'):continue
            if ledger.request_state(rid)!='rejected':
                raise BudgetError('Only a definite declined block can be explicitly retried; uncertain requests stay reserved.')
            # One explicit reconsideration, same model/text/style/boundaries.
            # Keep the refusal and working audio intact; never split, reword,
            # switch providers, or automatically cycle through more attempts.
            retries[str(i)]='voice:block:explicit-retry:'+hashlib.sha256(
                json.dumps([rid,requests[i],'missing-audio-retry-v1'],sort_keys=True).encode()).hexdigest()
            ids[i]=retries[str(i)]
    saved = [ledger.part(rid) for rid in ids]
    # Recover a definite refusal from older aligned jobs that stopped instead of
    # saving a text-only placeholder. A quota/transport/unknown result is never
    # treated as a content refusal and never skipped by this adapter.
    first_missing=next((i for i,p in enumerate(saved) if not p),None)
    if (first_missing is not None and str(previous.get('error') or '').startswith('Google declined this passage under its ')
            and ledger.request_state(ids[first_missing])=='rejected'):
        saved[first_missing]={'fallback':True,'reason':previous['error'],'duration':0,'timing':'device'}
    missing = [i for i, part in enumerate(saved) if not part]
    if any(ledger.request_state(ids[i]) not in (None,'rejected') for i in missing):
        raise BudgetError('This audio block was already sent. Its saved outcome needs review; it will not be purchased again.')
    checked = [has_alignment(part, sentences[first:first+count]) for (first, count, _), part in zip(sections, saved)]
    needs_alignment = [i for i, part in enumerate(saved) if part and not part.get('fallback') and not checked[i]]
    budget = ledger.summary(ctx.ai.limits)['categories']['voice']
    remaining = None
    ready = alignment.available(ctx, language)
    estimated = sum(expressive.maximum_cost(requests[i]) for i in missing) / 1_000_000
    enabled = ctx.config.get('tts', {}).get('enabled', False)
    quota_error = None
    if missing:
        try:
            ledger.claim_voice_slot(ids[missing[0]], expressive.PROVIDER, expressive.MODEL, dry_run=True)
        except BudgetError as exc:
            quota_error = str(exc)
    estimate = {'track_id': key, 'reused': False, 'provider': expressive.PROVIDER, 'model': expressive.MODEL,
        'voice': voice, 'rate': rate, 'language': language, 'parts': len(sections),
        'completed_parts': sum(checked),
        'characters': sum(len(s['text']) for s in sentences), 'estimated_cost_usd': estimated,
        'remaining_usd': remaining, 'monthly_limit_usd': budget['limit_usd'],
        'job_limit_usd': None, 'tracking_only': True,
        'allowed': not quota_error and ready and (not missing or enabled),
        'job_status': 'alignment_review' if needs_alignment else 'partial' if any(saved) else 'waiting',
        'alignment': 'local', 'reason': quota_error or (None if ready else 'Install the local narrator alignment models first.')}
    if dry_run:
        return {**estimate, 'dry_run': True}
    if not ready:
        raise alignment.AlignmentError(estimate['reason'])
    alignment.validate_script(ctx, sentences, language)
    if missing and not enabled:
        raise BudgetError('Google voice generation is paused. Saved recordings remain available.')
    if missing and not ctx.ai.key('google'):
        raise ValueError('The Google API key is missing on the home server')
    # Rebatching must not bypass an unresolved earlier purchase of this script.
    _, legacy_attempts = expressive.older_recordings(ctx, voice, language, rate)
    for _, _, text in expressive.chunks(sentences, {a['start_sentence'] for a in passage.get('activities', [])}):
        rid = expressive.part_key(text, voice, language, rate)
        prior = legacy_attempts.get(rid, rid)
        if ledger.request_state(prior) in ('reserved', 'uncertain', 'completed') and not ledger.part(prior):
            raise BudgetError('An earlier recording outcome needs review before this text can be purchased in a larger block.')
    if scope_id and not previous.get('generation_scope_id'):
        ledger.configure_scope(scope_id, round(maximum_usd * 1_000_000), category='voice')
    job = {'topic_id': topic['id'], 'purpose': purpose, 'provider': expressive.PROVIDER, 'model': expressive.MODEL,
        'passage_sha256': passage['passage_sha256'], 'voice': voice, 'rate': rate, 'status': 'running',
        'parts': len(sections), 'completed_parts': estimate['completed_parts'], 'request_ids': ids,
        'generation_scope_id': scope_id, 'strategy': VERSION, 'error': None,
        'repair_requests':repairs,'retry_requests':retries,
        'blocks': [{'first': first, 'count': count, 'request_id': rid} for (first, count, _), rid in zip(sections, ids)]}
    ledger.save_job(key, job)
    folder = layout.for_topic(ctx.store, topic['id'], layout.AUDIO)
    try:
        for i, ((first, count, _), rid, request) in enumerate(zip(sections, ids, requests)):
            part = saved[i]
            if part and part.get('fallback'):
                if ledger.part(rid) is None:ledger.save_part(rid,part)
                continue
            if part is None:
                state = ledger.request_state(rid)
                if state not in (None, 'rejected'):
                    raise BudgetError('This audio block was already sent. Its saved outcome needs review; it will not be purchased again.')
                # Wait before marking a purchase sent: restarting while queued
                # must not turn a request that never left the server uncertain.
                _provider_slot(ledger, rid)
                ledger.reserve(rid, 'voice', expressive.maximum_cost(request), ctx.ai.limits,
                    provider=expressive.PROVIDER, model=expressive.MODEL, operation='narration', scope_id=scope_id)
                try:
                    result = ctx.ai._post('https://generativelanguage.googleapis.com/v1beta/interactions',
                        {'x-goog-api-key': ctx.ai.key('google')}, request, rid)
                except ContentRejectedError as exc:
                    part={'fallback':True,'reason':str(exc),'duration':0,'timing':'device'}
                    ledger.save_part(rid,part);saved[i]=part
                    continue
                usage = result.get('usage') or {}
                inp, out = usage.get('total_input_tokens'), usage.get('total_output_tokens')
                if isinstance(inp, int) and isinstance(out, int) and min(inp, out) >= 0:
                    ledger.settle(rid, token_cost(inp, out, *expressive.rates()), usage)
                else:
                    ledger.mark(rid, 'uncertain')
                output = result.get('output_audio') or next((c for step in result.get('steps', [])
                    if step.get('type') == 'model_output' for c in step.get('content', []) if c.get('type') == 'audio'), None)
                if result.get('status') != 'completed' or not output or output.get('mime_type', 'audio/wav') != 'audio/wav':
                    raise alignment.AlignmentError('The paid voice reply was incomplete; no new recording will be purchased automatically.')
                data = base64.b64decode(output['data'], validate=True)
                _, duration = alignment._wav(data)
                with ctx.store.transaction(kind='tutor.narrator_raw_block') as tx:
                    path, sha = tx.add_blob(data, folder, f"block-{hashlib.sha256(rid.encode()).hexdigest()[:24]}.wav", 'audio/wav')
                part = {'path': path, 'sha256': sha, 'duration': duration, 'timing': 'alignment_pending',
                        'script_sha256': hashlib.sha256(sections[i][2].encode()).hexdigest()}
                ledger.save_part(rid, part)  # raw audio survives failed alignment and restart
                saved[i] = part
            if not has_alignment(part, sentences[first:first+count]):
                job.update(status='aligning', error=None)
                ledger.save_job(key, job)
                cuts = {a['start_sentence'] for a in passage.get('activities', []) if a.get('start_sentence') is not None}
                cuts.update(k+1 for k,s in enumerate(sentences) if s.get('pause_after'))
                local_sentences = [{**s, '_alignment_boundary_before':first+k in cuts}
                                   for k,s in enumerate(sentences[first:first+count])]
                timing = alignment.align(ctx, ctx.file_bytes(part['path'], part['sha256']), local_sentences, language)
                part = {**part, **timing, 'timing': 'local-alignment',
                        'sentence_layout': sentence_layout(sentences[first:first+count])}
                ledger.replace_part(rid, part)
                saved[i] = part
            job.update(completed_parts=sum(has_alignment(p, sentences[lo:lo+n])
                       for (lo, n, _), p in zip(sections, saved)), status='running')
            ledger.save_job(key, job)
        _publish(ctx, topic, passage, sections, saved, key, voice, rate, language, job)
    except Exception as exc:
        job.update(status='alignment_review' if isinstance(exc, alignment.AlignmentError) else 'paused',
                   error=str(exc), cost_usd=ledger.voice_cost(key))
        ledger.save_job(key, job)
        raise
    return {**estimate, 'completed_parts': len(sections), 'job_status': job['status'],
            'fallback_parts':job.get('fallback_parts',0),'allowed': True,
            'cost_usd': ledger.voice_cost(key)}


def _provider_slot(ledger, request_id):
    """Persist actual attempts and wait outside transactions; daily refusal stops."""
    import time
    while True:
        delay = ledger.claim_voice_slot(request_id, expressive.PROVIDER, expressive.MODEL)
        if delay <= 0:
            return
        time.sleep(min(delay, 30))
