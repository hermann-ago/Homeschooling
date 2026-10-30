"""Source-map inspection and durable parent corrections never invoke generation."""
import copy
import io
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from pypdf import PdfReader

from tests.test_subject_analysis import setup_collection, provider, start, PRIVATE, READING, TRAVEL
from tutoring import books
from services.test_mode import manager


@pytest.fixture
def mapped(harness, monkeypatch):
    h = harness
    _, collection, base = setup_collection(h)
    sent = provider(h, monkeypatch)
    job, _ = start(h, base)
    h.ctx.subject_analysis.process(job['id'])
    mid = h.ctx.store.get('collection_analysis_jobs', job['id'])['map_id']
    return h, mid, sent, base, collection


def read(h, mid):
    return h.call('GET', '/api/subject-maps/' + mid).json()


def edit(h, mid, item, **kwargs):
    body = dict(expected_revision=read(h, mid)['review_revision'], kind='concept', target_id=item['review_id'],
                status='corrected', note='Checked the printed passage.', changes={'title': 'Parent-selected title'})
    body.update(kwargs)
    return h.call('PUT', f'/api/subject-maps/{mid}/review', json=body)


def test_correction_reopens_exports_restores_and_keeps_originals_and_paid_usage(mapped):
    h, mid, sent, _, _ = mapped
    original = copy.deepcopy(h.ctx.store.get('subject_maps', mid))
    old_tables = {t: copy.deepcopy(h.ctx.store.all(t)) for t in ['attempts', 'reviews', 'topics', 'guides', 'audio_tracks', 'exercises', 'exercise_versions']}
    charge = h.ctx.ai.ledger.scope_summary(original['job_id'])
    count = len(sent)
    item = read(h, mid)['concepts'][0]
    response = edit(h, mid, item)
    assert response.status_code == 200, response.text
    assert response.json()['concepts'][0]['title'] == 'Parent-selected title'
    assert response.json()['review_revision'] == 1
    h.restart()
    current = read(h, mid)
    assert current['concepts'][0]['title'] == 'Parent-selected title'
    assert current['review_history'][0]['original']['title'] == item['title']
    export = h.call('GET', f'/api/subject-maps/{mid}/export')
    assert export.status_code == 200 and PRIVATE not in export.text
    assert export.json()['concepts'][0]['title'] == 'Parent-selected title'
    assert len(export.json()['review_history']) == 1
    response = edit(h, mid, item, status='unreviewed', note='', changes={})
    assert response.status_code == 200 and response.json()['concepts'][0]['title'] == item['title']
    assert len(response.json()['review_history']) == 2
    assert h.ctx.store.get('subject_maps', mid) == original
    assert old_tables == {t: h.ctx.store.all(t) for t in old_tables}
    assert charge == h.ctx.ai.ledger.scope_summary(original['job_id']) and len(sent) == count


def test_exact_source_pages_and_private_keys_are_protected(mapped):
    h, mid, sent, _, _ = mapped
    m = read(h, mid); unit = m['concepts'][0]['unit_id']
    response = h.call('GET', f'/api/subject-maps/{mid}/reading/{unit}')
    assert response.status_code == 200 and response.json()['pages'][0]['text'] == READING
    assert PRIVATE not in response.text
    doc = m['concepts'][0]['document_id']
    pdf = h.call('GET', f'/api/subject-maps/{mid}/source-pdf/{doc}/1')
    assert pdf.status_code == 200 and len(PdfReader(io.BytesIO(pdf.content)).pages) == 1
    key = next(b for b in m['books'] if b['role'] == 'answer_key')
    assert h.call('GET', f"/api/subject-maps/{mid}/source-pdf/{key['document_id']}/1").status_code == 403
    assert h.call('GET', f'/api/subject-maps/{mid}/source-pdf/{doc}/999').status_code == 403
    assert h.call('GET', f'/api/subject-maps/{mid}/reading/invented').status_code == 400
    for suffix in ['', '/export', f'/reading/{unit}', f'/source-pdf/{doc}/1']:
        assert h.call('GET', f'/api/subject-maps/{mid}{suffix}', role='tutor').status_code == 403
    assert len(sent) == 4


def test_parent_link_requires_real_safe_reading_and_retains_question_identity(mapped):
    h, mid, _, _, _ = mapped
    m = read(h, mid); link = m['exercise_links'][0]
    unit = m['concepts'][0]['unit_id']
    response = edit(h, mid, link, kind='exercise_link', changes={'evidence': [{'unit_id': unit, 'page': 2, 'quote': 'A fabricated original quotation.'}]})
    assert response.status_code == 400 and 'quotation' in response.text
    response = edit(h, mid, link, kind='exercise_link', changes={'evidence': [{'unit_id': unit, 'page': 2, 'quote': TRAVEL}], 'reason': 'Use the travel passage.'})
    assert response.status_code == 200, response.text
    corrected = response.json()['exercise_links'][0]
    assert corrected['exercise_id'] == link['exercise_id'] and corrected['evidence'][0]['page'] == 2
    assert response.json()['exercises'] == m['exercises']
    assert edit(h, mid, link, kind='exercise_link', changes={'evidence': []}).status_code == 400
    assert edit(h, mid, link, changes={'answer': PRIVATE}).status_code == 422


def test_two_parents_cannot_overwrite_each_other(mapped):
    h, mid, _, _, _ = mapped
    item = read(h, mid)['concepts'][0]
    payload = dict(expected_revision=0, kind='concept', target_id=item['review_id'], status='approved', changes={}, note='Checked.')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: h.call('PUT', f'/api/subject-maps/{mid}/review', json=payload).status_code, range(2)))
    assert sorted(results) == [200, 409]
    assert len(read(h, mid)['review_history']) == 1


def test_review_is_idempotent_and_cannot_forge_item_or_cross_map_concepts(mapped):
    h, mid, _, _, _ = mapped
    m = read(h, mid); item = m['concepts'][0]
    payload = dict(expected_revision=0, kind='concept', target_id=item['review_id'], status='approved', changes={}, note='Checked.')
    for _ in range(2):
        assert h.call('PUT', f'/api/subject-maps/{mid}/review', key='same-review-click', json=payload).status_code == 200
    assert len(read(h, mid)['review_history']) == 1
    assert edit(h, mid, item, target_id='invented').status_code == 400
    assert edit(h, mid, m['connections'][0], kind='connection', changes={'from_concept': 'another-collection-concept'}).status_code == 400
    assert edit(h, mid, item, status='rejected', note='', changes={}).status_code == 400
    assert h.call('PUT', f'/api/subject-maps/{mid}/review', role='tutor', json=payload).status_code == 403


def test_timeline_correction_checks_years_and_marks_parent_authorship(mapped):
    h, mid, _, _, _ = mapped
    event = read(h, mid)['events'][0]
    assert edit(h, mid, event, kind='event', changes={'start_year': 0}).status_code == 400
    assert edit(h, mid, event, kind='event', changes={'start_year': 1300, 'end_year': 1200}).status_code == 400
    response = edit(h, mid, event, kind='event', changes={'start_year': None, 'end_year': None, 'date_text': 'Uncertain source date', 'approximate': True})
    assert response.status_code == 200 and response.json()['events'][0]['start_year'] is None
    assert response.json()['events'][0]['parent_review']['status'] == 'corrected'


def test_reviews_survive_new_snapshot_without_replacing_them_with_ai(mapped):
    h, mid, _, base, collection = mapped
    item = read(h, mid)['concepts'][0]
    assert edit(h, mid, item).status_code == 200
    selected = [{k: b[k] for k in ('key', 'document_id', 'role', 'edition', 'position', 'is_main', 'companion_key', 'answer_for_key')} for b in collection['books']]
    selected[0]['edition'] = 'Parent updated edition label'
    assert h.call('PUT', base, json={'name': collection['name'], 'expected_revision': collection['revision'], 'books': selected}).status_code == 200
    job, _ = start(h, base)
    h.ctx.subject_analysis.process(job['id'])
    new_id = h.ctx.store.get('collection_analysis_jobs', job['id'])['map_id']
    assert new_id != mid
    current = read(h, new_id)
    assert current['concepts'][0]['title'] == 'Parent-selected title'
    assert not current['unapplied_reviews']
    # Same source identity with newly generated wording retains what was checked.
    row = copy.deepcopy(h.ctx.store.get('subject_maps', new_id))
    row['data']['concepts'][0]['objective'] = 'A newly generated learning goal.'
    with h.ctx.store.transaction() as tx:
        tx.insert('subject_maps', {k: v for k, v in row.items() if k not in ('id', 'revision', 'updated_at')} | {'id': 'new-wording-map'})
    frozen = read(h, 'new-wording-map')['concepts'][0]
    assert frozen['objective'] == item['objective']
    assert frozen['ai_proposal']['objective'] == 'A newly generated learning goal.'
    # A replacement reading no longer claims that the old correction applies.
    row = copy.deepcopy(h.ctx.store.get('subject_maps', new_id)); row['data']['concepts'] = row['data']['concepts'][1:]
    with h.ctx.store.transaction() as tx:
        tx.insert('subject_maps', {k: v for k, v in row.items() if k not in ('id', 'revision', 'updated_at')} | {'id': 'changed-source-map'})
    assert read(h, 'changed-source-map')['unapplied_reviews'][0]['target_id'] == item['review_id']


def test_reviews_are_backed_up_and_test_mode_changes_only_its_copy(mapped):
    h, mid, _, _, _ = mapped
    item = read(h, mid)['concepts'][0]
    assert edit(h, mid, item).status_code == 200
    backup = h.ctx.backup_now()
    path = next(p for p in backup['copies'] if p.endswith('.sqlite3') and ':' in p)
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT COUNT(*) FROM subject_map_reviews').fetchone()[0] == 1
    response = h.call('POST', '/api/test-mode', json={'enabled': True})
    token = response.json()['token']
    payload = dict(expected_revision=1, kind='concept', target_id=item['review_id'], status='rejected', changes={}, note='Rehearsal only.')
    response = h.client.put(f'/api/subject-maps/{mid}/review', headers={'X-Homeschooling-Mode': token}, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['concepts'][0]['parent_review']['status'] == 'rejected'
    live = h.client.get('/api/subject-maps/' + mid, headers={'X-Homeschooling-Mode': 'live'}).json()
    assert live['concepts'][0]['parent_review']['status'] == 'corrected'
    manager(h.ctx).end(token)


def test_combined_books_show_only_checked_reading_and_never_full_mixed_pages(mapped):
    h, mid, _, _, _ = mapped
    row = copy.deepcopy(h.ctx.store.get('subject_maps', mid))
    src = row['data']['books'][0]; src['role'] = 'combined'
    original = h.ctx.subject_analysis.cached_scan({**src, 'role': 'textbook'}, {'first': 1, 'last': 2})
    scan = copy.deepcopy(original['data'])
    scan['pages'][0]['reading_blocks'] = [READING]
    scan['pages'][1].update(teacher_material=True, student_safe=False, text=PRIVATE)
    with h.ctx.store.transaction() as tx:
        tx.insert('book_units', {'id': books.ident(src['sha256'], 'combined', books.scan_version('combined'), 1), 'sha256': src['sha256'],
            'role': 'combined', 'version': books.scan_version('combined'), 'first_page': 1, 'last_page': 2, 'data': scan})
        tx.insert('subject_maps', {k: v for k, v in row.items() if k not in ('id', 'revision', 'updated_at')} | {'id': 'combined-source-map'})
    unit = row['data']['concepts'][0]['unit_id']
    response = h.call('GET', f'/api/subject-maps/combined-source-map/reading/{unit}')
    assert response.status_code == 200 and PRIVATE not in response.text
    assert [p['page'] for p in response.json()['pages']] == [1]
    assert response.json()['pages'][0]['pdf_available'] is False
    assert h.call('GET', f"/api/subject-maps/combined-source-map/source-pdf/{src['document_id']}/1").status_code == 403


def test_page_spanning_parent_link_requires_all_original_checked_pages(mapped):
    h, mid, _, _, _ = mapped
    m = read(h, mid); link = m['exercise_links'][0]; unit = m['concepts'][0]['unit_id']
    cite = {'unit_id': unit, 'page': 1, 'page_end': 2, 'unit_ids': [unit], 'quote': READING + ' ' + TRAVEL}
    response = edit(h, mid, link, kind='exercise_link', changes={'evidence': [cite]})
    assert response.status_code == 200, response.text
    assert response.json()['exercise_links'][0]['evidence'][0]['page_end'] == 2
    cite['page_end'] = 3
    assert edit(h, mid, link, kind='exercise_link', changes={'evidence': [cite]}).status_code == 400


def test_missing_or_changed_source_is_reported_without_rebuying(mapped):
    h, mid, sent, _, _ = mapped
    m = read(h, mid); link = m['exercise_links'][0]; unit = m['concepts'][0]['unit_id']
    cite = {'unit_id': unit, 'page': 2, 'quote': TRAVEL}
    assert edit(h, mid, link, kind='exercise_link', changes={'evidence': [cite]}).status_code == 200
    source = m['books'][0]
    scan = h.ctx.subject_analysis.cached_scan(source, {'first': 1, 'last': 2})
    data = copy.deepcopy(scan['data']); data['pages'][1]['student_safe'] = False
    with h.ctx.store.transaction() as tx:
        tx.update('book_units', scan['id'], {'data': data})
        tx.update('documents', source['document_id'], {'sha256': 'different-edition'})
    assert read(h, mid)['unapplied_reviews'][0]['target_id'] == link['review_id']
    assert h.call('GET', f"/api/subject-maps/{mid}/source-pdf/{source['document_id']}/1").status_code == 403
    assert len(sent) == 4
