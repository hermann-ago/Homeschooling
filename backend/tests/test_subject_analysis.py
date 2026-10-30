"""Subject review: real HTTP/SQLite, fake provider transport, durable paid recovery."""
import copy
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
import pytest

from services.ai_budget import BudgetLedger, BudgetError
from tests.pdf_fixture import make_pdf
from tutoring import books
from tutoring.subject_analysis import AnalysisService

READING = "The Mongol Empire connected distant places. Kublai Khan became emperor in 1260."
TRAVEL = "Marco Polo travelled to China in 1271. He learned about the Mongol Empire."
SECOND = "Trade linked China and Europe. Marco Polo followed trade routes."
PRIVATE = "PRIVATE TEACHER ANSWER: Kublai Khan"


def setup_collection(h, two=True):
    with h.ctx.store.transaction() as tx:
        child = tx.insert('children', {'name': 'Lucas'})
        subject = tx.insert('subjects', {'name': 'History', 'child_id': child['id']})
    data = [('main', 'Main.pdf', 'textbook', [READING, TRAVEL]),
            ('work', 'Practice.pdf', 'workbook', ['Who became emperor in 1260?', 'Teacher-only notes']),
            ('key', 'Key.pdf', 'answer_key', [PRIVATE])]
    if two:
        data.insert(1, ('second', 'Second.pdf', 'textbook', [SECOND]))
    selected = []
    for i, (key, name, role, pages) in enumerate(data):
        path = h.add_file(make_pdf([[p] for p in pages]), 'Incoming Books/' + name)
        selected.append({'key': key, 'path': path, 'role': role, 'edition': 'Volume 2', 'position': i, 'is_main': key == 'main',
                         'companion_key': 'main' if key == 'work' else None, 'answer_for_key': 'work' if key == 'key' else None})
    base = f"/api/subjects/{subject['id']}/book-collection"
    response = h.call('PUT', base, json={'name': 'History collection', 'expected_revision': 0, 'books': selected})
    assert response.status_code == 200, response.text
    view = response.json()
    with h.ctx.store.transaction() as tx:
        for b, (_, _, role, pages) in zip(view['books'], data):
            scan = {'pages': [{'page': p + 1, 'text': text, 'headings': [], 'student_safe': role != 'answer_key' and text != 'Teacher-only notes',
                              'teacher_material': role == 'answer_key' or text == 'Teacher-only notes'} for p, text in enumerate(pages)],
                    'exercises': [], 'answers': []}
            if role == 'workbook':
                scan['exercises'] = [{'reference': '1', 'chapter': 1, 'section': 'Mongols', 'pages': [1], 'prompt': pages[0], 'optional': False}]
            if role == 'answer_key':
                scan['answers'] = [{'reference': '1', 'chapter': 1, 'section': 'Mongols', 'pages': [1], 'answer': PRIVATE, 'evidence': PRIVATE, 'issue': None}]
            tx.insert('book_units', {'id': books.ident(b['sha256'], role, books.scan_version(role), 1), 'sha256': b['sha256'], 'role': role,
                                    'version': books.scan_version(role), 'first_page': 1, 'last_page': len(pages), 'data': scan})
    return subject, view, base


def provider(h, monkeypatch, invalid=False, fail=False, invalid_date=False, incomplete_links=False):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key-never-real-account')
    h.config.update(ai={'provider': 'openai', 'monthly_generation_enabled': True, 'limits': {'teaching': 3, 'books': 2, 'voice': 2}})
    sent = []
    def respond(request):
        assert not h.ctx.store._lock._is_owned(), 'Provider requests must be outside database transactions'
        if request.url.path.endswith('/input_tokens'):
            return httpx.Response(200, json={'input_tokens': 1000})
        body = json.loads(request.content)
        prompt = body['input'][0]['content'][0]['text']
        assert PRIVATE not in prompt
        sent.append(body['text']['format']['name'])
        if fail:
            raise httpx.ReadTimeout('lost paid response')
        name = sent[-1]
        if name == 'SectionSummary':
            quote = SECOND if SECOND in prompt else READING
            result = {'overview': 'The reading connects travel and the Mongol Empire.', 'concepts': [
                {'title': 'Trade routes' if quote == SECOND else 'Mongol Empire', 'explanation': 'People and places were connected.',
                 'objective': 'Explain the connection.', 'vocabulary': [], 'evidence': [{'page': 1, 'quote': 'This quotation was invented.' if invalid else quote}]}],
                'events': [] if quote == SECOND else [{'title': 'Marco Polo travels', 'date_text': '1271', 'start_year': 127 if invalid_date else 1271, 'end_year': None,
                    'approximate': False, 'evidence': {'page': 2, 'quote': TRAVEL}}]}
        elif name == 'LinkBatch':
            batch = json.loads(re.search(r'Exercises: (.*?)\nFull reading outline:', prompt, re.S)[1])
            pages = json.loads(prompt.split('Candidate original pages: ')[1])
            target = next(p for p in pages if READING in p['text'])
            result = {'links': [{'exercise_id': e['id'], 'clear': True, 'reason': 'The source names the emperor.', 'needed_unit_ids': [],
                'evidence': [{'unit_id': target['unit_id'], 'page': 1, 'quote': READING}]} for e in batch]}
        else:
            nodes = json.loads(prompt.split('Source summaries: ')[1])
            assert all(e['start_year'] == 1271 for n in nodes for e in n['events'])
            assert all(n['reading_order'] for n in nodes)
            ids = [c for n in nodes for c in n['concept_ids']]
            result = {'overview': 'These books connect the Mongol Empire, trade, and travel.', 'important_concept_ids': ids,
                      'connections': [{'from_concept': ids[0], 'to_concept': ids[-1], 'relationship': 'related topic', 'explanation': 'Travel connects these subjects.'}] if len(ids) > 1 else [], 'issues': []}
        return httpx.Response(200, json={'status': 'incomplete' if incomplete_links and name == 'LinkBatch' else 'completed', 'usage': {'input_tokens': 1000, 'output_tokens': 700},
            'output': [{'content': [{'type': 'output_text', 'text': json.dumps(result)}]}]})
    h.ctx.ai.http = httpx.Client(transport=httpx.MockTransport(respond))
    return sent


def start(h, base, cap=.02):
    preview = h.call('GET', base + '/preview')
    assert preview.status_code == 200, preview.text
    response = h.call('POST', base + '/analyze', json={'fingerprint': preview.json()['fingerprint'], 'maximum_usd': cap})
    assert response.status_code == 200, response.text
    return response.json(), preview.json()


def test_full_collection_map_is_grounded_private_replayable_and_non_destructive(harness, monkeypatch):
    h = harness
    subject, collection, base = setup_collection(h)
    sent = provider(h, monkeypatch)
    before = {t: copy.deepcopy(h.ctx.store.all(t)) for t in ('topics', 'subject_books', 'exercises', 'exercise_versions', 'attempts', 'reviews', 'teacher_keys', 'tutor_sessions')}
    job, preview = start(h, base)
    assert preview['reusable_pages'] == preview['pages'] and preview['unprocessed_pages'] == 0
    assert h.call('POST', base + '/analyze', json={'fingerprint': preview['fingerprint'], 'maximum_usd': 1}).json()['id'] == job['id']
    assert h.ctx.ai.ledger.scope_summary(job['id'])['maximum_usd'] == .02
    h.ctx.subject_analysis.process(job['id'])
    finished = h.ctx.store.get('collection_analysis_jobs', job['id'])
    assert finished['status'] == 'ready', finished['error']
    result = h.call('GET', '/api/subject-maps/' + finished['map_id'])
    assert result.status_code == 200 and PRIVATE not in result.text
    m = result.json()
    assert m['coverage']['books'] == 4 and len(m['concepts']) == 2 and len(m['connections']) == 1
    assert m['exercises'][0]['answer_link_status'] == 'linked'
    assert m['exercise_links'][0]['evidence'][0]['quote'] == READING
    assert m['events'][0]['start_year'] == 1271
    assert PRIVATE in json.dumps(h.ctx.store.get('subject_maps', finished['map_id'])['data']['private_answers'])
    count = len(sent)
    h.call('GET', base + '/preview')
    h.call('GET', '/api/subject-maps/' + finished['map_id'])
    h.ctx.subject_analysis.process(job['id'])
    assert len(sent) == count == 4
    assert before == {t: h.ctx.store.all(t) for t in before}
    assert h.call('GET', '/api/subject-maps/' + finished['map_id'], role='tutor').status_code == 403


def test_allowance_pause_resume_restart_and_unchanged_sections_are_not_rebought(harness, monkeypatch):
    h = harness
    subject, view, base = setup_collection(h)
    sent = provider(h, monkeypatch)
    job, _ = start(h, base, .002)
    h.ctx.subject_analysis.process(job['id'])
    assert h.ctx.store.get('collection_analysis_jobs', job['id'])['status'] == 'paused_allowance'
    assert sent == ['SectionSummary']
    h.restart()
    sent_after = provider(h, monkeypatch)
    assert h.call('POST', f"/api/subject-analysis/{job['id']}/continue", json={'maximum_usd': .02}).status_code == 200
    h.ctx.subject_analysis.process(job['id'])
    assert h.ctx.store.get('collection_analysis_jobs', job['id'])['status'] == 'ready'
    assert sent_after == ['SectionSummary', 'Synthesis', 'LinkBatch']
    # A membership/edition update needs a new global map, while unchanged
    # section summaries and reading links remain cached.
    payload = {'name': view['name'], 'expected_revision': view['revision'], 'books': [
        {k: b[k] for k in ('key', 'document_id', 'role', 'edition', 'position', 'is_main', 'companion_key', 'answer_for_key')} for b in view['books']]}
    payload['books'][0]['edition'] = 'Corrected edition label'
    assert h.call('PUT', base, json=payload).status_code == 200
    second, _ = start(h, base, .02)
    before_count = len(sent_after)
    h.ctx.subject_analysis.process(second['id'])
    assert h.ctx.store.get('collection_analysis_jobs', second['id'])['status'] == 'ready'
    assert len(sent_after) == before_count
    assert h.ctx.ai.ledger.scope_summary(second['id'])['used_usd'] == 0


def test_paid_result_survives_failure_before_main_database_checkpoint(harness, monkeypatch):
    h = harness
    _, _, base = setup_collection(h)
    sent = provider(h, monkeypatch)
    job, _ = start(h, base)
    service = h.ctx.subject_analysis
    original = service.checkpoint
    def interrupted(kind, identity, data):
        if kind == 'summary':
            raise RuntimeError('crash before checkpoint')
        return original(kind, identity, data)
    monkeypatch.setattr(service, 'checkpoint', interrupted)
    service.process(job['id'])
    assert h.ctx.store.get('collection_analysis_jobs', job['id'])['status'] == 'failed'
    assert sent == ['SectionSummary']
    h.restart()
    after = provider(h, monkeypatch)
    h.call('POST', f"/api/subject-analysis/{job['id']}/continue", json={})
    h.ctx.subject_analysis.process(job['id'])
    assert h.ctx.store.get('collection_analysis_jobs', job['id'])['status'] == 'ready'
    assert after == ['SectionSummary', 'Synthesis', 'LinkBatch']


def test_uncertain_charge_is_held_without_resending_on_restart(harness, monkeypatch):
    h = harness
    _, _, base = setup_collection(h)
    sent = provider(h, monkeypatch, fail=True)
    job, _ = start(h, base)
    h.ctx.subject_analysis.process(job['id'])
    held = h.ctx.ai.ledger.scope_summary(job['id'])
    assert held['uncertain_usd'] > 0 and len(sent) == 1
    h.restart()
    after = provider(h, monkeypatch)
    h.call('POST', f"/api/subject-analysis/{job['id']}/continue", json={})
    h.ctx.subject_analysis.process(job['id'])
    assert not after
    assert h.ctx.ai.ledger.scope_summary(job['id'])['uncertain_usd'] == held['uncertain_usd']


def test_invalid_source_proposals_are_flagged_and_never_paid_retried(harness, monkeypatch):
    h = harness
    _, _, base = setup_collection(h, two=False)
    sent = provider(h, monkeypatch, invalid=True)
    job, _ = start(h, base)
    h.ctx.subject_analysis.process(job['id'])
    final = h.ctx.store.get('collection_analysis_jobs', job['id'])
    assert final['status'] == 'needs_review'
    m = h.call('GET', '/api/subject-maps/' + final['map_id']).json()
    assert not m['concepts'] and m['flagged_items'] > 0
    assert len(sent) == 2  # one section summary and one exercise batch; no speculative synthesis


def test_missing_extraction_is_checkpointed_and_not_repeated_after_restart(harness, monkeypatch):
    h = harness
    _, view, base = setup_collection(h)
    src = view['books'][0]
    sid = books.ident(src['sha256'], src['role'], books.scan_version(src['role']), 1)
    scan = copy.deepcopy(h.ctx.store.get('book_units', sid)['data'])
    with h.ctx.store.transaction() as tx:
        tx.delete('book_units', sid)
    extracted = []
    def extract(ctx, pdf, role, first, last):
        assert not ctx.store._lock._is_owned()
        extracted.append((role, first, last))
        return scan
    monkeypatch.setattr(books, 'scan_unit', extract)
    provider(h, monkeypatch)
    job, preview = start(h, base, .001)
    assert preview['unprocessed_pages'] == 2
    h.ctx.subject_analysis.process(job['id'])
    assert h.ctx.store.get('collection_analysis_jobs', job['id'])['status'] == 'paused_allowance'
    assert h.ctx.store.get('book_units', sid)['data'] == scan
    h.restart()
    provider(h, monkeypatch)
    h.call('POST', f"/api/subject-analysis/{job['id']}/continue", json={'maximum_usd': .02})
    h.ctx.subject_analysis.process(job['id'])
    assert h.ctx.store.get('collection_analysis_jobs', job['id'])['status'] == 'ready'
    assert extracted == [('textbook', 1, 2)]


def test_parent_pause_during_reservation_keeps_pause_and_sends_no_generation(harness, monkeypatch):
    h = harness
    _, _, base = setup_collection(h)
    sent = provider(h, monkeypatch)
    job, _ = start(h, base)
    original = h.ctx.ai.ledger.reserve
    def pause(*args, **kwargs):
        response = h.call('POST', f"/api/subject-analysis/{job['id']}/pause")
        assert response.status_code == 200
        assert response.json()['in_flight']
        assert h.call('POST', f"/api/subject-analysis/{job['id']}/continue", json={}).status_code == 400
        return original(*args, **kwargs)
    monkeypatch.setattr(h.ctx.ai.ledger, 'reserve', pause)
    h.ctx.subject_analysis.process(job['id'])
    assert h.ctx.store.get('collection_analysis_jobs', job['id'])['status'] == 'paused'
    assert not sent
    assert not h.ctx.subject_analysis.public_job(h.ctx.store.get('collection_analysis_jobs', job['id']))['in_flight']


@pytest.mark.parametrize('first,last,offset,quote,expected', [(1, 1, 1, TRAVEL, 2), (1, 2, 0, READING + ' ' + TRAVEL, 1)])
def test_preserved_question_links_use_printed_page_offset_and_current_boundaries(harness, monkeypatch, first, last, offset, quote, expected):
    h = harness
    subject, view, base = setup_collection(h, two=False)
    main, work = view['books'][:2]
    with h.ctx.store.transaction() as tx:
        topic = tx.insert('topics', {'subject_id': subject['id'], 'document_id': main['document_id'], 'title': 'Travel',
            'page_start': first, 'page_end': last, 'pdf_page_offset': offset})
        book = tx.insert('subject_books', {'id': 'old-work', 'subject_id': subject['id'], 'document_id': work['document_id'], 'role': 'workbook'})
        tx.insert('exercises', {'id': 'old-question', 'book_id': book['id'], 'active_version': 'old-version'})
        tx.insert('exercise_versions', {'id': 'old-version', 'exercise_id': 'old-question', 'parent_edited': True, 'data': {
            'source_sha256': work['sha256'], 'reference': '1', 'chapter': 1, 'pages': [1], 'status': 'matched',
            'requirements': [{'topic_id': topic['id'], 'evidence': quote}]}})
    sent = provider(h, monkeypatch)
    job, _ = start(h, base)
    h.ctx.subject_analysis.process(job['id'])
    row = h.ctx.store.get('collection_analysis_jobs', job['id'])
    assert row['status'] == 'ready', row['error']
    result = h.call('GET', '/api/subject-maps/' + row['map_id']).json()
    link = result['exercise_links'][0]
    assert link['status'] == 'preserved' and link['exercise_version_id'] == 'old-version'
    assert link['evidence'][0]['page'] == expected and 'LinkBatch' not in sent
    if last > first:
        assert link['evidence'][0]['page_end'] == 2 and link['evidence'][0]['pages'] == [1, 2]
    # A subsequently changed lesson boundary cannot inherit that quotation.
    with h.ctx.store.transaction() as tx:
        tx.update('topics', topic['id'], {'pdf_page_offset': 0, 'page_end': 1})
    read_units = {s['id']: {'document_id': main['document_id'], 'pages': {1: READING, 2: TRAVEL}} for s in result['sections']}
    assert h.ctx.subject_analysis.inherited_link(result['exercises'][0], row, read_units) is None


def test_numeric_date_must_match_the_whole_source_year(harness, monkeypatch):
    h = harness
    _, _, base = setup_collection(h, two=False)
    provider(h, monkeypatch, invalid_date=True)
    job, _ = start(h, base)
    h.ctx.subject_analysis.process(job['id'])
    row = h.ctx.store.get('collection_analysis_jobs', job['id'])
    assert row['status'] == 'needs_review', row['error']
    result = h.call('GET', '/api/subject-maps/' + row['map_id']).json()
    assert not result['events'] and any('Date for' in i for i in result['issues'])


def test_spending_pause_keeps_an_immutable_whole_book_overview(harness, monkeypatch):
    h = harness
    _, _, base = setup_collection(h, two=False)
    sent = provider(h, monkeypatch)
    job, _ = start(h, base, .004)
    h.ctx.subject_analysis.process(job['id'])
    row = h.ctx.store.get('collection_analysis_jobs', job['id'])
    assert row['status'] == 'paused_allowance' and row['map_id']
    partial = h.call('GET', '/api/subject-maps/' + row['map_id']).json()
    assert partial['coverage']['complete'] is False and partial['coverage']['pending_exercises'] == 1
    assert partial['concepts'] and partial['events'] and PRIVATE not in json.dumps(partial)
    assert sent == ['SectionSummary', 'Synthesis']
    h.restart()
    after = provider(h, monkeypatch)
    h.call('POST', f"/api/subject-analysis/{job['id']}/continue", json={'maximum_usd': .02})
    h.ctx.subject_analysis.process(job['id'])
    final = h.ctx.store.get('collection_analysis_jobs', job['id'])
    assert final['status'] == 'ready' and final['map_id'] != row['map_id']
    assert h.call('GET', '/api/subject-maps/' + row['map_id']).json() == partial
    assert h.call('GET', '/api/subject-maps/' + final['map_id']).json()['coverage']['complete'] is True
    assert after == ['LinkBatch']


def test_rehearsal_can_open_while_a_real_partial_overview_is_paused(harness, monkeypatch):
    from services.test_mode import manager
    h = harness
    _, _, base = setup_collection(h, two=False)
    provider(h, monkeypatch)
    job, _ = start(h, base, .004)
    h.ctx.subject_analysis.process(job['id'])
    real = copy.deepcopy(h.ctx.store.get('collection_analysis_jobs', job['id']))
    assert real['status'] == 'paused_allowance' and real['map_id']
    response = h.call('POST', '/api/test-mode', json={'enabled': True})
    assert response.status_code == 200, response.text
    token = response.json()['token']
    test = manager(h.ctx).get(token)
    assert not test.store.get('collection_analysis_jobs', job['id'])
    snapshot = test.store.all('collection_analysis_jobs')[0]
    assert snapshot['rehearsal_snapshot'] and snapshot['source_job_id'] == job['id']
    assert test.store.get('subject_maps', real['map_id'])['job_id'] == snapshot['id']
    assert test.store.all('collection_analysis_units')
    assert real == h.ctx.store.get('collection_analysis_jobs', job['id'])
    assert h.ctx.store.get('subject_maps', real['map_id'])
    assert h.client.post(f"/api/subject-analysis/{job['id']}/continue", headers={'X-Homeschooling-Mode': token}, json={}).status_code == 404
    assert h.client.post(f"/api/subject-analysis/{snapshot['id']}/continue", headers={'X-Homeschooling-Mode': token}, json={}).status_code == 400
    assert h.client.post(f"/api/subject-analysis/{snapshot['id']}/pause", headers={'X-Homeschooling-Mode': token}).status_code == 400
    assert h.client.get(f"/api/subject-maps/{real['map_id']}", headers={'X-Homeschooling-Mode': token}).status_code == 200
    manager(h.ctx).end(token)


def test_shared_book_facts_point_to_each_collections_selected_document(harness, monkeypatch):
    h = harness
    _, view, base = setup_collection(h, two=False)
    provider(h, monkeypatch)
    first, _ = start(h, base)
    h.ctx.subject_analysis.process(first['id'])
    original = h.ctx.store.get('documents', view['books'][0]['document_id'])
    path = h.add_file(h.ctx.file_bytes(original['file_path'], original['sha256']), 'Incoming Books/SharedBook.pdf')
    with h.ctx.store.transaction() as tx:
        child = tx.insert('children', {'name': 'Mila'})
        subject = tx.insert('subjects', {'name': 'History', 'child_id': child['id']})
        # Existing imports can contain separate document records for identical
        # bytes; a fresh upload would correctly deduplicate them by checksum.
        duplicate = tx.insert('documents', {k: v for k, v in original.items() if k != 'id'} | {'file_path': path})
    second_base = f"/api/subjects/{subject['id']}/book-collection"
    response = h.call('PUT', second_base, json={'name': 'Other collection', 'expected_revision': 0,
        'books': [{'key': 'copy', 'document_id': duplicate['id'], 'role': 'textbook', 'position': 0, 'is_main': True}]})
    assert response.status_code == 200, response.text
    selected = response.json()['books'][0]
    assert selected['document_id'] != original['id'] and selected['sha256'] == original['sha256']
    sent = provider(h, monkeypatch)
    second, _ = start(h, second_base)
    h.ctx.subject_analysis.process(second['id'])
    row = h.ctx.store.get('collection_analysis_jobs', second['id'])
    assert row['status'] == 'ready', row['error']
    result = h.call('GET', '/api/subject-maps/' + row['map_id']).json()
    assert all(c['document_id'] == selected['document_id'] for c in [*result['concepts'], *result['events']])
    assert 'SectionSummary' not in sent


def test_incomplete_paid_exercise_reply_is_flagged_without_blocking_or_rebuying(harness, monkeypatch):
    h = harness
    _, view, base = setup_collection(h, two=False)
    sent = provider(h, monkeypatch, incomplete_links=True)
    job, _ = start(h, base)
    h.ctx.subject_analysis.process(job['id'])
    row = h.ctx.store.get('collection_analysis_jobs', job['id'])
    assert row['status'] == 'needs_review', row['error']
    result = h.call('GET', '/api/subject-maps/' + row['map_id']).json()
    assert result['exercise_links'][0]['status'] == 'needs_review'
    assert 'no automatic retry' in result['exercise_links'][0]['reason']
    assert sent == ['SectionSummary', 'Synthesis', 'LinkBatch']
    # A new membership snapshot still uses the charged failed-batch checkpoint.
    selected = [{k: b[k] for k in ('key', 'document_id', 'role', 'edition', 'position', 'is_main', 'companion_key', 'answer_for_key')} for b in view['books']]
    selected[0]['edition'] = 'Revised label'
    h.call('PUT', base, json={'name': view['name'], 'expected_revision': view['revision'], 'books': selected})
    next_job, _ = start(h, base)
    h.ctx.subject_analysis.process(next_job['id'])
    assert h.ctx.store.get('collection_analysis_jobs', next_job['id'])['status'] == 'needs_review'
    assert len(sent) == 3


def test_hierarchical_collection_synthesis_retains_all_books_and_recovers_root_response(harness, monkeypatch):
    h = harness
    _, view, base = setup_collection(h, two=False)
    selected = [{k: b[k] for k in ('key', 'document_id', 'role', 'edition', 'position', 'is_main', 'companion_key', 'answer_for_key')} for b in view['books']]
    for i in range(8):
        text = SECOND + f' This is supplementary volume {i + 1}.'
        path = h.add_file(make_pdf([[text]]), f'Incoming Books/Volume{i + 1}.pdf')
        selected.append({'key': f'volume-{i}', 'path': path, 'role': 'textbook', 'position': i + 3, 'is_main': False})
    response = h.call('PUT', base, json={'name': view['name'], 'expected_revision': view['revision'], 'books': selected})
    assert response.status_code == 200, response.text
    with h.ctx.store.transaction() as tx:
        for i, b in enumerate(response.json()['books'][3:]):
            text = SECOND + f' This is supplementary volume {i + 1}.'
            tx.insert('book_units', {'id': books.ident(b['sha256'], 'textbook', books.scan_version('textbook'), 1),
                'sha256': b['sha256'], 'role': 'textbook', 'version': books.scan_version('textbook'), 'first_page': 1, 'last_page': 1,
                'data': {'pages': [{'page': 1, 'text': text, 'headings': [], 'student_safe': True, 'teacher_material': False}], 'exercises': [], 'answers': []}})
    sent = provider(h, monkeypatch)
    job, _ = start(h, base, .03)
    original = h.ctx.subject_analysis.checkpoint
    def crash_at_root(kind, identity, data):
        if kind == 'synthesis' and len(identity[0]) == 2:
            raise RuntimeError('root response arrived before restart')
        return original(kind, identity, data)
    monkeypatch.setattr(h.ctx.subject_analysis, 'checkpoint', crash_at_root)
    h.ctx.subject_analysis.process(job['id'])
    assert h.ctx.store.get('collection_analysis_jobs', job['id'])['status'] == 'failed'
    assert sent.count('SectionSummary') == 9 and sent.count('Synthesis') == 3
    h.restart()
    after = provider(h, monkeypatch)
    h.call('POST', f"/api/subject-analysis/{job['id']}/continue", json={})
    h.ctx.subject_analysis.process(job['id'])
    row = h.ctx.store.get('collection_analysis_jobs', job['id'])
    assert row['status'] == 'ready', row['error']
    result = h.call('GET', '/api/subject-maps/' + row['map_id']).json()
    assert len(result['concepts']) == 9 and len(result['books']) == 11 and result['events'][0]['start_year'] == 1271
    assert {s['source_id'] for s in result['sections']} == {b['id'] for b in result['books'] if b['role'] == 'textbook'}
    assert after == ['LinkBatch']


def test_bounded_retrieval_includes_each_questions_best_page_and_requested_sources():
    names = ['merovingian', 'visigothic', 'byzantine', 'carolingian', 'abbasid', 'seljuk', 'ottoman', 'timurid']
    units = {name: {'pages': {i + 1: ('Generic context ' * 300) + f'The {name} people travelled together.' for i in range(8)}} for name in names}
    batch = [{'prompt': f'Explain the {name} journey', 'section': ''} for name in names]
    for extra in ([], ['abbasid', 'seljuk', 'ottoman', 'timurid']):
        pages = AnalysisService.match_pages(batch, units, extra)
        assert sum(len(p['text']) for p in pages) <= 24000
        assert {p['unit_id'] for p in pages} == set(names)
        for name in names:
            assert any(f'The {name} people' in p['text'] for p in pages if p['unit_id'] == name)
        assert all(p['text'] in units[p['unit_id']]['pages'][p['page']] for p in pages)


def test_rehearsal_analysis_keeps_real_records_and_paid_results_reusable(harness, monkeypatch):
    from services.test_mode import manager
    h = harness
    _, _, base = setup_collection(h)
    provider(h, monkeypatch)
    token = h.call('POST', '/api/test-mode', json={'enabled': True}).json()['token']
    test = manager(h.ctx).get(token)
    test.analysis_worker.stop()
    test.analysis_worker.join(timeout=5)
    test.subject_analysis.stopping.clear()
    test.ai.http = h.ctx.ai.http
    before = {t: copy.deepcopy(h.ctx.store.all(t)) for t in ('children', 'subjects', 'attempts', 'reviews', 'tutor_sessions', 'subject_maps')}
    preview = h.client.get(base + '/preview', headers={'X-Homeschooling-Mode': token}).json()
    response = h.client.post(base + '/analyze', headers={'X-Homeschooling-Mode': token},
        json={'fingerprint': preview['fingerprint'], 'maximum_usd': .02})
    assert response.status_code == 200, response.text
    jid = response.json()['id']
    test.subject_analysis.process(jid)
    assert test.store.get('collection_analysis_jobs', jid)['status'] == 'ready'
    assert test.ai.ledger.scope_summary(jid)['used_usd'] > 0
    assert before == {t: h.ctx.store.all(t) for t in before}
    # Both modes share durable exact-input provider results; the real review
    # can rebuild its own map without buying the rehearsal responses again.
    h.client.cookies.clear()
    sent = provider(h, monkeypatch)
    actual, _ = start(h, base)
    h.ctx.subject_analysis.process(actual['id'])
    assert h.ctx.store.get('collection_analysis_jobs', actual['id'])['status'] == 'ready'
    assert not sent and h.ctx.ai.ledger.scope_summary(actual['id'])['used_usd'] == 0
    manager(h.ctx).end(token)


def test_preview_staleness_and_double_clicks_never_create_two_jobs(harness, monkeypatch):
    h = harness
    _, view, base = setup_collection(h)
    provider(h, monkeypatch)
    preview = h.call('GET', base + '/preview').json()
    def begin(_):
        return h.call('POST', base + '/analyze', json={'fingerprint': preview['fingerprint'], 'maximum_usd': .02}).json()['id']
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert len(set(pool.map(begin, range(4)))) == 1
    assert len(h.ctx.store.all('collection_analysis_jobs')) == 1
    assert h.call('POST', base + '/analyze', json={'fingerprint': 'stale', 'maximum_usd': .02}).status_code == 400
    h.config.update(ai={'provider': 'google'})
    assert h.call('POST', base + '/analyze', json={'fingerprint': preview['fingerprint'], 'maximum_usd': .02}).status_code == 400


def test_scoped_reservations_are_atomic_across_jobs_months_and_reconciliation(tmp_path):
    now = [datetime(2026, 10, 8, tzinfo=timezone.utc)]
    ledger = BudgetLedger(tmp_path / 'ledger.sqlite3', lambda: now[0])
    ledger.configure_scope('a', 10000)
    ledger.configure_scope('b', 10000)
    def reserve(i):
        try:
            ledger.reserve(str(i), 'books', 5000, {'books': .015}, provider='openai', model='gpt-6-luna', operation='summary', scope_id='a' if i % 2 else 'b')
            return i
        except BudgetError:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        winners = [i for i in pool.map(reserve, range(20)) if i is not None]
    assert len(winners) == 20
    now[0] = datetime(2026, 11, 8, tzinfo=timezone.utc)
    restarted = BudgetLedger(ledger.path, lambda: now[0])
    assert restarted.scope_summary('a')['used_usd'] + restarted.scope_summary('b')['used_usd'] == .1
    restarted.recover_interrupted()
    charged = str(winners[0])
    scope = 'a' if winners[0] % 2 else 'b'
    prior = restarted.scope_summary(scope)['used_usd']
    restarted.reconcile(charged, 1000)
    assert restarted.scope_summary(scope)['used_usd'] == pytest.approx(prior - .004)


def test_test_mode_cannot_pause_or_continue_real_jobs(harness, monkeypatch):
    h = harness
    _, _, base = setup_collection(h)
    provider(h, monkeypatch)
    job, _ = start(h, base)
    token = h.client.post('/api/test-mode', headers={'X-Homeschooling-Mode': 'live'}, json={'enabled': True}).json()['token']
    response = h.client.post(f"/api/subject-analysis/{job['id']}/pause", headers={'X-Homeschooling-Mode': token})
    assert response.status_code == 404
    assert h.ctx.store.get('collection_analysis_jobs', job['id'])['status'] == 'queued'
    assert h.ctx.ai.ledger.scope_summary(job['id'])['maximum_usd'] == .02


def test_unnumbered_exercises_preserve_both_source_proposals_without_guessing_key_links(harness, monkeypatch):
    h = harness
    _, _, base = setup_collection(h)
    provider(h, monkeypatch)
    public, _ = start(h, base)
    job = h.ctx.store.get('collection_analysis_jobs', public['id'])
    source = next(s for s in job['plan']['sources'] if s['role'] == 'workbook')
    step = next(s for s in job['plan']['steps'] if s['source_id'] == source['id'])
    data = {'pages': [{'page': 1, 'student_safe': True, 'teacher_material': False}],
            'exercises': [{'reference': '', 'chapter': 1, 'section': 'Reading', 'pages': [1], 'prompt': p,
                           'issue': 'Exercise identity needs checking'} for p in ['First original question?', 'Second original question?']]}
    scans = {source['id']: [(step, data)]}
    first, private = h.ctx.subject_analysis.exercises(job, scans, [source])
    second, _ = h.ctx.subject_analysis.exercises(job, scans, [source])
    assert len(first) == 2 and len({e['id'] for e in first}) == 2
    assert first == second and not private
    assert all(not e['student_safe'] and e['issue'] and e['answer_link_status'] == 'needs_review' for e in first)
    assert not h.ctx.store.all('guides') and not h.ctx.store.all('attempts')


def test_visually_checked_unnumbered_tasks_keep_their_distinct_companion_ids(harness, monkeypatch):
    h=harness
    _,_,base=setup_collection(h)
    provider(h,monkeypatch)
    public,_=start(h,base)
    job=h.ctx.store.get('collection_analysis_jobs',public['id'])
    source=next(s for s in job['plan']['sources'] if s['role']=='workbook')
    step=next(s for s in job['plan']['steps'] if s['source_id']==source['id'])
    data={'pages':[{'page':1,'student_safe':True,'teacher_material':False}],
        'exercise_ids':['original-task-a','original-task-b'],
        'exercises':[{'reference':'','unnumbered':True,'chapter':1,'section':'Practice','pages':[1],
            'prompt':p,'issue':None} for p in ('Original question one?','Original question two?')]}
    items,_=h.ctx.subject_analysis.exercises(job,{source['id']:[(step,data)]},[source])
    assert len({e['id'] for e in items})==2
    assert all(e['student_safe'] and not e['issue'] for e in items)
    assert [e['source_item_id'] for e in items]==data['exercise_ids']
