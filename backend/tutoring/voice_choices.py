"""Read-only account voice discovery and provider-supplied preview samples."""
import time
import threading
import hashlib

_cache = {}
_lock = threading.Lock()


def catalog(ctx):
    key = ctx.ai.key('elevenlabs')
    if not key:
        raise ValueError('Save an ElevenLabs key in Settings to browse narrators.')
    with _lock:
        cache_key = (id(ctx), hashlib.sha256(key.encode()).hexdigest())
        old = _cache.get(cache_key)
        if old and old[0] > time.monotonic():
            return old[1]
        result = []; token = None
        for _ in range(10):
            params = {'page_size': 100}
            if token:
                params['next_page_token'] = token
            reply = ctx.ai.http.get('https://api.elevenlabs.io/v2/voices', headers={'xi-api-key': key}, params=params)
            if not reply.is_success:
                raise ValueError('Could not list ElevenLabs voices. Check the key’s Read Voices permission in Settings.')
            body = reply.json()
            for row in body.get('voices', []):
                labels = row.get('labels') or {}
                preview = row.get('preview_url') or ''
                result.append({'id': row['voice_id'], 'name': row.get('name') or 'Narrator',
                    'description': (row.get('description') or '')[:500], 'labels': labels,
                    'preview_url': preview if preview.startswith('https://') else None})
            token = body.get('next_page_token')
            if not body.get('has_more') or not token:
                break
        _cache[cache_key] = (time.monotonic()+300, result)
        return result


def selected(db, topic_id):
    value = (db.get('topic_narrators', str(topic_id)) or {}).get('voice')
    return value if value and not value.startswith('inworld:') else None


def name(ctx, voice):
    saved = next((r.get('voice_name') for r in ctx.store.find('topic_narrators', voice=voice) if r.get('voice_name')), None)
    if saved:
        return saved
    for (context_id, _), (_, voices) in list(_cache.items()):
        if context_id == id(ctx):
            match = next((v['name'] for v in voices if v['id'] == voice), None)
            if match:
                return match
    return {'JBFqnCBsd6RMkjVDRZzb': 'George', 'hpp4J3VqNfWAUOO0d1Us':'Bella',
            'nuwpqeXdykQWOB3gY2BP':'Adam', 'nczLZ6GvJGozyc3FlLte':'Juliana',
            '3ULAAai0IVN00DTWA6vF':'Henrique'}.get(voice, voice)
