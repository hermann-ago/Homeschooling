"""Read-only native voice discovery and cached, unbilled Flash previews."""
import base64
import hashlib
import json
import threading
import time
from urllib.parse import quote

MODEL = 'inworld-tts-2-flash'
# Flash's Brazilian Portuguese was not usable for the family; Portuguese uses
# Inworld's top model (better pronunciation and intonation). The language comes
# from the lesson's topic. List prices per million characters (On-Demand).
MODELS_BY_LANGUAGE = {'pt-BR': 'inworld-tts-2'}
USD_PER_MILLION = {'inworld-tts-2-flash': 15, 'inworld-tts-2': 25}


def model_for(language):
    return MODELS_BY_LANGUAGE.get(language, MODEL)
CURATED = {
    ('en-US', 'male'): ['Brian', 'Dennis', 'Oliver', 'Alex', 'Timothy'],
    ('en-US', 'female'): ['Ashley', 'Hazel', 'Lauren', 'Nadia', 'Zoe'],
    ('pt-BR', 'male'): ['Davi', 'Heitor', 'Murilo'],
    ('pt-BR', 'female'): ['Bruna', 'Larissa', 'Maitê', 'Renata', 'Vanessa'],
}
_cache, _lock = {}, threading.RLock()


def catalog(ctx):
    key = ctx.ai.key('inworld')
    if not key:
        raise ValueError('Save an Inworld key in Settings to browse voices.')
    identity = (id(ctx), hashlib.sha256(key.encode()).hexdigest())
    with _lock:
        previous = _cache.get(identity)
        if previous and previous[0] > time.monotonic():
            return previous[1]
        rows, token, seen = [], None, set()
        for _ in range(10):
            params = {'pageSize': 2000, 'filter': 'source="SYSTEM"'}
            if token:
                params['pageToken'] = token
            try:
                response = ctx.ai.http.get('https://api.inworld.ai/voices/v1/voices',
                    headers={'Authorization': f'Basic {key}'}, params=params)
            except Exception:
                raise ValueError('Could not reach the Inworld voice catalog. Try again later.') from None
            if not response.is_success:
                raise ValueError(f'Inworld voice listing returned {response.status_code}. Check the key and Voices Read permission.')
            try:
                data = response.json()
                if not isinstance(data, dict) or not isinstance(data.get('voices'), list):
                    raise ValueError('Invalid catalog')
            except ValueError:
                raise ValueError('Inworld returned an unreadable voice catalog.') from None
            for raw in data.get('voices', []):
                voice = raw.get('voiceId')
                language = (raw.get('languageCode') or raw.get('langCode', '').replace('_', '-'))
                language = {'en-us': 'en-US', 'pt-br': 'pt-BR'}.get(language.lower(), language)
                if voice in seen or language not in ('en-US', 'pt-BR') or raw.get('source') != 'SYSTEM':
                    continue
                seen.add(voice)
                rows.append({'id': voice, 'name': raw.get('displayName') or voice,
                    'language': language, 'gender': raw.get('gender'),
                    'description': (raw.get('description') or '')[:500],
                    'labels': {'language': 'US English' if language == 'en-US' else 'Brazilian Portuguese', 'gender': raw.get('gender', '')},
                    'featured': voice in CURATED.get((language, raw.get('gender')), []),
                    'preview_url': '/api/ai/inworld/voices/' + quote(voice, safe='') + '/preview'})
            token = data.get('nextPageToken')
            if not token:
                break
        _cache[identity] = (time.monotonic() + 300, rows)
        return rows


def packet(ctx):
    voices = catalog(ctx)
    groups = []
    for (language, gender), ids in CURATED.items():
        selected = [v for name in ids for v in voices if v['id'] == name and v['language'] == language and v['gender'] == gender]
        groups.append({'language': language, 'gender': gender, 'voices': selected})
    return {'provider': 'inworld', 'model': MODEL, 'voices': [v for g in groups for v in g['voices']], 'available_count': len(voices), 'groups': groups,
        'popularity_ranked': False,
        'selection_note': 'Curated for tutoring. Inworld does not supply popularity rankings. All three native Brazilian male voices are included.',
        'preview_billed': False}


def preview(ctx, voice):
    if not any(v['id'] == voice for v in catalog(ctx)):
        raise ValueError('Choose an available Inworld voice.')
    key = ctx.ai.key('inworld')
    model = model_for(next(v['language'] for v in catalog(ctx) if v['id'] == voice))
    digest = hashlib.sha256(json.dumps([model, voice, hashlib.sha256(key.encode()).hexdigest()]).encode()).hexdigest()
    path = ctx.config.dir / 'cache' / 'inworld-previews' / (digest + '.mp3')
    with _lock:
        if path.exists():
            return path.read_bytes()
        try:
            response = ctx.ai.http.get('https://api.inworld.ai/tts/v1/voice:preview',
                headers={'Authorization': f'Basic {key}'}, params={'voice_id': voice, 'model_id': model})
        except Exception:
            raise ValueError('Could not reach the Inworld preview service. Try again later.') from None
        if not response.is_success:
            raise ValueError(f'Inworld preview returned {response.status_code}. Try again later; no lesson was generated.')
        try:
            data = base64.b64decode(response.json()['audioContent'], validate=True)
            if not 100 < len(data) <= 5_000_000:
                raise ValueError('Invalid preview size')
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError('Inworld returned an unreadable preview.') from exc
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(data)
        temporary.replace(path)
        return data


def selected(db, topic_id):
    row = db.get('topic_narrators', str(topic_id)) or {}
    # Provider-specific prefix preserves the existing table and old selections.
    value = row.get('voice', '')
    return value.removeprefix('inworld:') if value.startswith('inworld:') else None


def narrator(ctx, language, child_id=None):
    settings = ctx.config.get('tts', {})
    field = 'portuguese_voice' if language == 'pt-BR' else 'english_voice'
    learner = next((r.get(field) for r in settings.get('inworld_learner_voices', []) if r['child_id'] == child_id), None)
    return learner or settings.get('inworld_voice_pt' if language == 'pt-BR' else 'inworld_voice_en') or ('Bruna' if language == 'pt-BR' else 'Brian')


def learner_choices(ctx):
    active = {s['child_id'] for s in ctx.store.all('subjects') if s.get('purpose') != 'library_paused'}
    overrides = {r['child_id']: r for r in ctx.config.get('tts', {}).get('inworld_learner_voices', [])}
    return [{'child_id': c['id'], 'name': c['name'], 'english_voice': overrides.get(c['id'], {}).get('english_voice'),
        'portuguese_voice': overrides.get(c['id'], {}).get('portuguese_voice')} for c in ctx.store.all('children') if c['id'] in active]
