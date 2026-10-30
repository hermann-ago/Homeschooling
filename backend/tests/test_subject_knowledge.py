"""Sibling reuse is free, source-bound and independent of learner evidence."""
import copy
import hashlib
import json

from tests.test_map_review import mapped, read, edit
from tutoring.subject_knowledge import FORMAT


def target(h):
    with h.ctx.store.transaction() as tx:
        child = tx.insert('children', {'name': 'Sibling'})
        subject = tx.insert('subjects', {'child_id': child['id'], 'name': 'History', 'grade': '4th'})
    return subject


def test_archive_and_sibling_reuse_preserve_sources_reviews_and_child_records(mapped):
    h, mid, sent, base, _ = mapped
    origin = int(base.split('/')[3])
    concept = read(h, mid)['concepts'][0]
    edit(h, mid, concept, status='approved', changes={})
    before = {t: copy.deepcopy(h.ctx.store.all(t)) for t in ('attempts', 'reviews', 'guides', 'audio_tracks', 'topics', 'exercise_versions')}
    count = len(sent)
    saved = h.call('POST', f'/api/subjects/{origin}/knowledge-file')
    assert saved.status_code == 200, saved.text
    assert '/Subject Knowledge/subject-knowledge-v1-' in saved.json()['path']
    envelope = json.loads(h.ctx.files.read(saved.json()['path'], saved.json()['sha256']))
    body = envelope['contents']
    assert body['format'] == FORMAT and body['format_version'] == 1
    assert hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest() == envelope['content_sha256']
    assert body['reuse_rules']['child_records_included'] is False
    assert body['teacher_only']['raw_scan_units'] and body['teacher_only']['answer_key_entries']
    assert 'private_answers' not in body['knowledge']
    assert not any(k in body for k in ('attempts', 'children', 'guides', 'learning_snapshots'))
    sibling = target(h)
    reused = h.call('POST', f"/api/subjects/{sibling['id']}/reuse-knowledge", json={
        'source_subject_id': origin, 'expected_revision': 0, 'expected_version_id': None})
    assert reused.status_code == 200, reused.text
    assert reused.json()['collection']['shared']
    assert len(sent) == count
    assert before == {t: h.ctx.store.all(t) for t in before}
    status = h.call('GET', f"/api/subjects/{sibling['id']}/book-collection/analysis").json()
    assert status['jobs'][0]['map_id'] == mid
    assert h.call('GET', f"/api/subjects/{sibling['id']}/book-collection/preview").json()['estimate_high_usd'] == 0
    selected = h.call('POST', f'/api/subject-maps/{mid}/select', json={
        'subject_id': sibling['id'], 'expected_revision': 0, 'expected_review_revision': 1})
    assert selected.status_code == 200, selected.text
    assert selected.json()['teaching_selection']['active']
    assert not read(h, mid)['teaching_selection']['active']
    h.restart()
    assert h.call('GET', f"/api/subject-maps/{mid}?subject_id={sibling['id']}").json()['teaching_selection']['active']
    assert h.call('POST', f'/api/subjects/{origin}/knowledge-file', role='tutor').status_code == 403


def test_reuse_checks_pdf_bytes_and_editing_forks_shared_collection(mapped):
    h, mid, sent, base, _ = mapped
    origin = int(base.split('/')[3]); sibling = target(h)
    payload = {'source_subject_id': origin, 'expected_revision': 0, 'expected_version_id': None}
    book = h.ctx.store.get('subject_maps', mid)['data']['books'][0]
    doc = h.ctx.store.get('documents', book['document_id'])
    path = h.ctx.files.resolve(doc['file_path']); original = path.read_bytes()
    path.write_bytes(b'changed edition')
    assert h.call('POST', f"/api/subjects/{sibling['id']}/reuse-knowledge", json=payload).status_code == 400
    assert not h.ctx.store.find('subject_collections', subject_id=sibling['id'])
    path.write_bytes(original)
    result = h.call('POST', f"/api/subjects/{sibling['id']}/reuse-knowledge", json=payload).json()
    view = result['collection']; source_before = h.call('GET', base).json()
    change = {'name': 'Different reading order', 'expected_revision': view['revision'], 'books': [
        {'key': b['key'], 'document_id': b['document_id'], 'role': b['role'], 'edition': b['edition'],
         'position': b['position'], 'is_main': b['is_main'], 'companion_key': b['companion_key'], 'answer_for_key': b['answer_for_key']}
        for b in view['books']]}
    response = h.call('PUT', f"/api/subjects/{sibling['id']}/book-collection", json=change)
    assert response.status_code == 200, response.text
    assert response.json()['id'] != source_before['id']
    assert h.call('GET', base).json()['version_id'] == source_before['version_id']
    assert h.ctx.store.get('subject_maps', mid)
    assert len(sent) == 4
