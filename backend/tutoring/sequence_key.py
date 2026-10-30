"""Private ordering keys, matched to every printed statement in its printed order.

No inferred solutions or item-number-only matches. OCR whitespace and punctuation
can differ, but words, negations, qualifiers and the edition must all agree.
"""
import re
import unicodedata

from storage.store import sha256_text


def literal(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text).casefold() if c.isalnum())


def numbered(text):
    return [(int(m[1]), literal(m[2])) for m in re.finditer(r'^\s*\(\s*(\d+)\s*\)\s*([^\r\n]+)', text or '', re.M)]


def resolve(db, action):
    from .source_key import original_refs, normalized
    content = action.get('activity_content') or {}
    if (action.get('origin') != 'required_book' or content.get('answer_format', 'text') != 'text'
            or content.get('require_reasoning') or content.get('evidence_requirement', 'answer') != 'answer'):
        return None
    session = db.get('tutor_sessions', action['session_id'])
    playback = db.get('lesson_playback', action['session_id'])
    if not session or not playback:
        return None
    prepared = (playback.get('context_snapshot') or {}).get('prepared_guide') or {}
    mid = (((prepared.get('subject_sources') or {}).get('selection') or {}).get('map_id')
           or (prepared.get('learning_memory') or {}).get('map_id'))
    row = db.get('subject_maps', mid) if mid else None
    if not row or not any(b['collection_id'] == row['collection_id'] for b in db.find('subject_collections', subject_id=session['subject_id'])):
        return None
    data = row['data']

    def checked(book):
        doc = db.get('documents', book['document_id'])
        review = db.get('book_source_reviews', (data.get('source_review_ids') or {}).get(book['id']))
        if (not doc or not review or doc['sha256'] != book['sha256'] or review['sha256'] != book['sha256']
                or review['content_sha256'] != (data.get('source_companion_hashes') or {}).get(str(book['document_id']))):
            return None
        return review

    candidates = []
    for ref in original_refs(action):
        lines = [s.strip() for s in ref['quote'].splitlines() if s.strip()]
        if len(lines) < 3 or not re.search(r'\b(enumere|numere|number)\b.*\b(ordem|order)\b', lines[0], re.I):
            continue
        items = [literal(re.sub(r'^\(\s*\)\s*', '', s)) for s in lines[1:]]
        if not 2 <= len(items) <= 40 or len(set(items)) != len(items) or any(not s for s in items):
            continue
        if not any(t.get('document_id') == ref['document_id'] and t.get('page') == ref['page']
                   and normalized(t.get('instruction')) == normalized(ref['quote'])
                   for t in (prepared.get('source_requirements') or {}).get('tasks', [])):
            continue
        if any(n.get('assessment_note') and n.get('first_page', 0) <= ref['page'] <= n.get('last_page', 0)
               for n in prepared.get('source_assessment_notes') or []):
            continue
        source = next((b for b in data.get('books', []) if b['document_id'] == ref['document_id']), None)
        review = checked(source) if source else None
        if not review or not any(p.get('document_id') == ref['document_id'] and p.get('page') == ref['page']
                and p.get('document_sha256') == source['sha256'] for p in (prepared.get('visual_source') or {}).get('pages', [])):
            continue
        page = next((p for p in review['data'].get('pages', []) if p['page'] == ref['page']
                     and p.get('status') == 'checked' and not p.get('issues')), None)
        printed = [literal(m[1]) for m in re.finditer(r'^\s*\(\s*\)\s*([^\r\n]+)', (page or {}).get('text', ''), re.M)]
        if items != printed:
            continue
        for answer in data.get('private_answers', []):
            if answer.get('target_id') != source['id'] or answer.get('issue'):
                continue
            pairs = numbered(answer.get('answer'))
            if [s for _, s in pairs] != items or sorted(n for n, _ in pairs) != list(range(1, len(items) + 1)):
                continue
            key = next((b for b in data['books'] if b['id'] == answer.get('source_id')), None)
            if not key or key.get('role') != 'answer_key' or source['id'] not in [key.get('answer_for_id'), *(key.get('answer_for_ids') or [])]:
                continue
            key_review = checked(key)
            verified = []
            for p in (key_review or {}).get('data', {}).get('pages', []):
                if p['page'] not in answer.get('pages', []) or p.get('status') != 'checked' or p.get('issues'):
                    continue
                marked = numbered(p.get('text'))
                if any(marked[i:i+len(pairs)] == pairs for i in range(len(marked)-len(pairs)+1)):
                    verified.append(p['page'])
            if verified:
                candidates.append({'status': 'matched', 'answer_link_status': 'reviewed', 'answer_format': 'ordering',
                    'answer': [n for n, _ in pairs], 'section': 'Ordering', 'prompt': action['prompt'],
                    'language': (key_review['data'].get('source') or {}).get('language'), 'map_id': row['id'],
                    'source_sha256': source['sha256'], 'answer_source': {'document_id': key['document_id'],
                        'sha256': key['sha256'], 'pages': verified, 'source_review_id': key_review['id']}})
    if not candidates or len({tuple(c['answer']) for c in candidates}) != 1:
        return None
    return {**candidates[0], 'version_id': 'literal-ordering-key-' + sha256_text(candidates[0])}
