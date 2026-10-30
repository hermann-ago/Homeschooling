"""Private, literal answer-key lookup for source-bound main-book activities.

Only checked annotations of complete statements qualify. Binary and ordering
exercises use distinct literal matchers. Never solve a question, match by item
number alone, or put private keys in activity content.
"""
import re
import unicodedata

from storage.store import sha256_text


def normalized(text):
    text = re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text or '')).strip().casefold()
    return re.sub(r'\s+([.,;:!?])', r'\1', text)


def original_refs(action):
    refs = [*(action.get('source_refs') or []), *((action.get('activity_content') or {}).get('source_refs') or [])]
    unique = {}
    for ref in refs:
        if ref.get('quote'):
            unique[(ref.get('document_id'), ref.get('page'), ref['quote'])] = {
                k: ref.get(k) for k in ('document_id', 'page', 'quote')}
    return list(unique.values())


def _annotated_lines(text, statement):
    # A complete, explicitly marked line, not a substring of a longer claim.
    return [match[1].casefold() for match in re.finditer(
        r'^\s*\(\s*(V|F|T|true|false|verdadeiro|falso)\s*\)\s*([^\r\n]+)', text or '', re.I | re.M)
        if normalized(match[2]) == statement]


def resolve(db, action):
    from .sequence_key import resolve as sequence_key
    return sequence_key(db, action) or _resolve_binary(db, action)


def _resolve_binary(db, action):
    content = action.get('activity_content') or {}
    if (action.get('origin') != 'required_book' or content.get('answer_format') != 'true_false'
            or content.get('require_reasoning') or content.get('evidence_requirement', 'answer') != 'answer'):
        return None
    session = db.get('tutor_sessions', action['session_id'])
    playback = db.get('lesson_playback', action['session_id'])
    if not session or not playback:
        return None
    prepared = (playback.get('context_snapshot') or {}).get('prepared_guide') or {}
    # Pin the same source map used by preparation, rather than a newer map.
    map_id = ((prepared.get('subject_sources') or {}).get('selection') or {}).get('map_id')
    map_id = map_id or (prepared.get('learning_memory') or {}).get('map_id')
    row = db.get('subject_maps', map_id) if map_id else None
    if not row or not any(b['collection_id'] == row['collection_id'] for b in db.find(
            'subject_collections', subject_id=session['subject_id'])):
        return None
    data = row['data']
    requirements = (prepared.get('source_requirements') or {}).get('tasks') or []
    prompt = normalized(action.get('prompt'))
    refs = [ref for ref in original_refs(action) if any(
        t.get('document_id') == ref['document_id'] and t.get('page') == ref['page']
        and normalized(t.get('instruction')) == normalized(ref['quote'])
        and prompt.endswith(normalized(ref['quote'].split('\n')[-1])) for t in requirements)]
    candidates = []
    for ref in refs:
        statement = normalized(ref['quote'].split('\n')[-1])
        if any(note.get('assessment_note') and note.get('first_page', 0) <= ref['page'] <= note.get('last_page', 0)
                for note in prepared.get('source_assessment_notes') or []):
            continue
        source = next((b for b in data.get('books', []) if b['document_id'] == ref['document_id']), None)
        pinned_pages = (prepared.get('visual_source') or {}).get('pages') or []
        if not source or not any(p.get('document_id') == source['document_id'] and p.get('page') == ref['page']
                and p.get('document_sha256') == source['sha256'] for p in pinned_pages):
            continue
        source_doc = db.get('documents', source['document_id'])
        source_review = db.get('book_source_reviews', (data.get('source_review_ids') or {}).get(source['id']))
        if (not source_doc or source_doc['sha256'] != source['sha256'] or not source_review
                or source_review['sha256'] != source['sha256']
                or source_review['content_sha256'] != (data.get('source_companion_hashes') or {}).get(str(source['document_id']))
                or not any(p['page'] == ref['page'] and p.get('status') == 'checked' and not p.get('issues')
                    and any(normalized(re.sub(r'^\s*\(\s*\)\s*', '', line)) == statement
                        for line in (p.get('text') or '').splitlines())
                    for p in source_review['data'].get('pages', []))):
            continue
        for answer in data.get('private_answers', []):
            if answer.get('target_id') != source['id'] or answer.get('issue'):
                continue
            marks = _annotated_lines(answer.get('answer'), statement)
            if not marks:
                continue
            key = next((b for b in data['books'] if b['id'] == answer.get('source_id')), None)
            if not key or key.get('role') != 'answer_key' or source['id'] not in [
                    *(key.get('answer_for_ids') or []), key.get('answer_for_id')]:
                continue
            review = db.get('book_source_reviews', (data.get('source_review_ids') or {}).get(key['id']))
            doc = db.get('documents', key['document_id'])
            if (not review or not doc or review['sha256'] != key['sha256'] or doc['sha256'] != key['sha256']
                    or review['content_sha256'] != (data.get('source_companion_hashes') or {}).get(str(key['document_id']))):
                continue
            verified = [(p['page'], mark) for p in review['data'].get('pages', [])
                if p['page'] in answer.get('pages', []) and p.get('status') == 'checked' and not p.get('issues')
                for mark in _annotated_lines(p.get('text'), statement)]
            if not verified or set(marks) != {mark for _, mark in verified}:
                continue
            for mark in marks:
                candidates.append({'status': 'matched', 'answer_link_status': 'reviewed',
                    'section': 'Verdadeiro ou falso', 'prompt': action['prompt'],
                    'answer': {'v': 'true', 't': 'true', 'f': 'false'}.get(mark, mark),
                    'language': (review['data'].get('source') or {}).get('language'),
                    'source_sha256': source['sha256'], 'map_id': row['id'],
                    'answer_source': {'document_id': key['document_id'], 'sha256': key['sha256'],
                        'pages': sorted({p for p, _ in verified}), 'source_review_id': review['id']}})
    if not candidates or len({c['answer'] for c in candidates}) != 1:
        return None
    snapshot = candidates[0]
    return {**snapshot, 'version_id': 'literal-key-' + sha256_text(snapshot)}


def for_message(db, action, message):
    captures = db.find('activity_responses', session_id=action['session_id'], message_id=message['id'])
    jobs = db.find('activity_jobs', session_id=action['session_id'], response_id=captures[0]['id']) if captures else []
    job = next((j for j in jobs if j['kind'] == 'assessment'), None)
    frozen = (job.get('input_snapshot') or {}).get('assessment_request') if job else None
    return frozen.get('source_key') if frozen is not None else resolve(db, action)
