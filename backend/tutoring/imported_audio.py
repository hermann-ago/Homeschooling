"""Attach externally generated narration to an exact saved script.

No provider calls, credentials or learner transitions. Acoustic verification runs
outside database transactions; publication uses the normal lesson audio clips.
"""
import hashlib
import json
import math
import threading

from pydantic import BaseModel, ConfigDict, Field
from . import audio, narration_alignment
from storage import layout

PREFERRED = 'preferred-guide-recording'
VOICE_LANGUAGES = {'Clive':'en-US', 'Maitê':'pt-BR', 'Heitor':'pt-BR'}
_lock = threading.Lock()
_imports = {}


class Part(BaseModel):
    model_config = ConfigDict(extra='forbid')
    start_sentence: int = Field(ge=0, strict=True)
    sentence_count: int = Field(ge=1, le=500, strict=True)
    script_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


def install(ctx, topic, guide, descriptions, recordings, *, voice, language, rate=.9):
    if voice not in VOICE_LANGUAGES or language not in {'en-US', 'pt-BR'}:
        raise ValueError('Choose a supported imported Inworld narrator and language')
    if VOICE_LANGUAGES[voice] != language or not math.isfinite(rate) or not .5 <= rate <= 1.5:
        raise ValueError('The narrator, language or recording speed is invalid')
    if not 1 <= len(descriptions) == len(recordings) <= 16:
        raise ValueError('Supply between one and sixteen matching audio blocks')
    if sum(map(len, recordings)) > 60_000_000:
        raise ValueError('Imported recordings exceed the size limit')
    sections, signatures, covered = [], [], 0
    for raw, data in zip(descriptions, recordings):
        part = Part.model_validate(raw)
        first, count = part.start_sentence, part.sentence_count
        if first != covered or first + count > len(guide['sentences']):
            raise ValueError('Imported audio must cover every sentence once, in order')
        text = ' '.join(s['text'] for s in guide['sentences'][first:first+count])
        if hashlib.sha256(text.encode()).hexdigest() != part.script_sha256:
            raise ValueError('The recording text does not match the saved lesson script')
        if not 0 < len(data) <= 22_000_000:
            raise ValueError('An audio block exceeds the size limit')
        narration_alignment._wav(data)  # Validate format/duration before saving anything.
        sections.append((first, count, text))
        signatures.append(hashlib.sha256(data).hexdigest())
        covered += count
    if covered != len(guide['sentences']):
        raise ValueError('Imported audio is missing the end of the lesson')
    key = hashlib.sha256(json.dumps(['imported-inworld-v1', guide['passage_sha256'],
        voice, language, rate, signatures, [(a,b) for a,b,_ in sections]]).encode()).hexdigest()
    with _lock:
        guard = _imports.setdefault(key, threading.Lock())
    with guard:
        existing = ctx.store.get('audio_tracks', key)
        if existing:
            manifest = json.loads(ctx.file_bytes(existing['manifest_path']))
            valid, reason = audio.validate_manifest(manifest, guide['passage_sha256'], covered)
            if not valid:
                raise ValueError(reason)
            for track in manifest['tracks']:
                ctx.file_bytes(track['path'], track['sha256'])
            _prefer(ctx, topic, guide, key)
            return {'track_id': key, 'job_status': 'ready', 'reused': True,
                    'sentences': covered, 'clips': len(manifest['tracks'])}
        ledger = ctx.ai.ledger
        ids = [f'imported:{key}:{i}' for i in range(len(sections))]
        job = {'provider':'inworld', 'model':'inworld-tts-2', 'voice':voice,
               'topic_id':topic['id'], 'purpose':'lesson', 'passage_sha256':guide['passage_sha256'],
               'automatic_guide_id':guide['guide_id'], 'request_ids':ids,
               'parts':len(sections), 'completed_parts':0, 'status':'aligning',
               'timing':'local-alignment', 'cost_basis':'external_recording', 'error':None}
        ledger.save_job(key, job)
        saved = []
        try:
            for index, ((first,count,_), data, identity) in enumerate(zip(sections, recordings, ids)):
                part = ledger.part(identity)
                if part:
                    ctx.file_bytes(part['path'], part['sha256'])
                else:
                    with ctx.store.transaction(kind='tutor.imported_audio_raw') as tx:
                        path, sha = tx.add_blob(data, layout.for_topic(ctx.store, topic['id'], layout.AUDIO),
                            f'inworld-import-{signatures[index][:24]}.wav', 'audio/wav')
                    cuts={a['start_sentence'] for a in guide.get('activities',[])}
                    cuts.update(k+1 for k,s in enumerate(guide['sentences']) if s.get('pause_after'))
                    rows=[{**s,'_alignment_boundary_before':first+k in cuts}
                          for k,s in enumerate(guide['sentences'][first:first+count])]
                    alignment = narration_alignment.align(ctx, data, rows, language)
                    part = {'path':path, 'sha256':sha, 'mime':'audio/wav',
                            'duration':alignment['duration'], 'sentenceStarts':alignment['sentenceStarts'],
                            'timing':'local-alignment', 'alignment':alignment['alignment']}
                    ledger.save_part(identity, part)
                saved.append(part)
                job['completed_parts'] = len(saved)
                ledger.save_job(key, job)
            from .aligned_audio import _publish
            _publish(ctx, topic, guide, sections, saved, key, voice, rate, language, job)
            _prefer(ctx, topic, guide, key)
        except Exception as exc:
            job.update(status='paused', error=str(exc))
            ledger.save_job(key, job)
            raise
        manifest = json.loads(ctx.file_bytes(ctx.store.get('audio_tracks',key)['manifest_path']))
        return {'track_id':key, 'job_status':'ready', 'reused':False,
                'sentences':covered, 'clips':len(manifest['tracks'])}


def _prefer(ctx, topic, guide, key):
    with ctx.store.transaction(kind='tutor.preferred_guide_recording') as tx:
        for track in tx.find('audio_tracks', topic_id=topic['id']):
            if track['passage_sha256'] == guide['passage_sha256']:
                if track['id'] == key and track.get('note') != PREFERRED:
                    tx.update('audio_tracks', key, {'note':PREFERRED})
                elif track['id'] != key and track.get('note') == PREFERRED:
                    tx.update('audio_tracks', track['id'], {'note':None})
