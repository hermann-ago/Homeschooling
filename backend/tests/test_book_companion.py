"""Portable book extraction preserves source boundaries, private keys and checkpoints."""
import copy
import json

import pytest

from storage.backups import create_backup, verify_restore, export_excel
from tests.pdf_fixture import make_pdf
from tutoring import book_companion as companion


@pytest.fixture
def book(harness, monkeypatch):
    h = harness
    with h.ctx.store.transaction() as tx:
        child = tx.insert('children', {'name': 'Synthetic learner'})
        subject = tx.insert('subjects', {'child_id': child['id'], 'name': 'Synthetic Portuguese', 'grade': '3rd'})
    path = h.add_file(make_pdf([['Lesson One', 'Native text with no invented image details.'], ['Lesson Two', 'More original text.']]), 'Incoming Books/Portuguese.pdf')
    result = h.call('PUT', f"/api/subjects/{subject['id']}/book-collection", json={'name': 'Portuguese sources', 'expected_revision': 0,
        'books': [{'key': 'main', 'path': path, 'role': 'combined', 'edition': '2024', 'position': 0, 'is_main': True}]}).json()
    def forbidden(*a, **kw):
        raise AssertionError('Local book JSON operations must not purchase AI requests')
    monkeypatch.setattr(h.ctx.ai, 'generate', forbidden)
    doc = result['books'][0]['document_id']
    base = f"/api/subjects/{subject['id']}/book-companions/{doc}"
    return h, subject, doc, base


def exported(h, base):
    return h.call('GET', base + '/export').json()


def upload(h, base, body, revision=1, **kwargs):
    envelope = {'content_sha256': companion.digest(body), 'contents': body}
    return h.call('POST', base + '/import', files={'file': ('book.json', json.dumps(envelope).encode(), 'application/json')},
                  data={'expected_revision': revision}, **kwargs)


def checked(body):
    body = copy.deepcopy(body)
    for page in body['pages']:
        page.update(status='checked', review_method='visual', issues=[], student_safe=True,
                    reading_blocks=[page['text']], headings=[page['text'].splitlines()[0]])
    body['producer'] = 'Synthetic inspected fixture'
    body['pages'][0]['elements'] = [{'id': 'page1-diagram', 'kind': 'diagram', 'description': 'Two labeled boxes linked by a right-pointing arrow.'}]
    return companion.Companion.model_validate(body).model_dump()


def test_local_draft_has_all_pages_no_certified_visuals_and_survives_restore(book, tmp_path):
    h, s, doc, base = book
    first = h.call('POST', base, key='create-json')
    assert first.status_code == 200, first.text
    assert first.json()['checked_pages'] == 0 and first.json()['pending_pages'] == 2
    body = exported(h, base)
    assert body['content_sha256'] == companion.digest(body['contents'])
    assert len(body['contents']['pages']) == 2
    assert all(p['status'] == 'native_draft' and not p['student_safe'] for p in body['contents']['pages'])
    assert not h.ctx.store.all('book_units')
    assert not any(k in body['contents'] for k in ('children', 'attempts', 'guides', 'responses'))
    assert h.ctx.files.read(first.json()['path'])
    assert h.call('POST', base, key='create-json').json() == first.json()
    assert h.call('POST', base).json() == first.json()
    h.restart()
    assert exported(h, base) == body
    backup = create_backup(h.ctx.store, tmp_path / 'backup')
    assert verify_restore(tmp_path / 'backup' / backup['name'])['counts']['book_companions'] == 1
    assert export_excel(h.ctx.store)
    assert h.call('GET', base + '/export', role='tutor').status_code == 403
    assert h.call('GET', base + '/pages/1', role='tutor').status_code == 403


def test_checked_codex_json_reuses_existing_source_pipeline_without_reassessment(book):
    h, s, doc, base = book
    h.call('POST', base)
    body = checked(exported(h, base)['contents'])
    result = upload(h, base, body)
    assert result.status_code == 200, result.text
    assert result.json()['checked_pages'] == 2 and result.json()['visual_elements'] == 1
    preview = h.call('GET', f"/api/subjects/{s['id']}/book-collection/preview").json()
    assert preview['reusable_pages'] == 2
    assert h.ctx.books.page_index(h.ctx.store.get('documents', doc), 'combined')[1]['text'] == body['pages'][0]['text']
    # Refresh is lossless and does not buy, erase, or reinterpret evidence.
    refreshed = h.call('POST', base)
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()['checked_pages'] == 2
    assert not h.ctx.store.all('attempts') and not h.ctx.store.all('guides')


@pytest.mark.parametrize('change', ['hash', 'pages', 'role', 'edition', 'duplicate', 'unknown', 'unsafe_key', 'fake_quote', 'bounds'])
def test_invalid_or_mismatched_json_saves_nothing(book, change):
    h, s, doc, base = book
    h.call('POST', base)
    body = checked(exported(h, base)['contents'])
    if change == 'hash': body['source']['sha256'] = '0' * 64
    if change == 'pages': body['source']['page_count'] = 3
    if change == 'role': body['source']['role'] = 'textbook'
    if change == 'edition': body['source']['edition'] = 'other edition'
    if change == 'duplicate': body['pages'][1]['page'] = 1
    if change == 'unknown': body['attempts'] = [{'outcome': 'correct'}]
    if change == 'unsafe_key': body['pages'][0].update(teacher_material=True, student_safe=True)
    if change == 'fake_quote': body['pages'][0]['reading_blocks'] = ['Made up material']
    if change == 'bounds': body['pages'][0]['elements'][0]['bbox'] = [0, 0, 4, 5]
    before = copy.deepcopy(h.ctx.store.all('book_companions'))
    result = upload(h, base, body)
    assert result.status_code == 400, result.text
    assert h.ctx.store.all('book_companions') == before and not h.ctx.store.all('book_units')


def test_stale_revision_and_modified_checksum_cannot_overwrite(book):
    h, s, doc, base = book
    h.call('POST', base)
    body = checked(exported(h, base)['contents'])
    assert upload(h, base, body, revision=0).status_code == 409
    assert not h.ctx.store.all('book_units')
    envelope = {'content_sha256': '0' * 64, 'contents': body}
    response = h.call('POST', base + '/import', files={'file': ('book.json', json.dumps(envelope).encode(), 'application/json')}, data={'expected_revision': 1})
    assert response.status_code == 400 and not h.ctx.store.all('book_units')


def test_unreviewed_partial_pages_do_not_become_source_cache(book):
    h, s, doc, base = book
    h.call('POST', base)
    body = checked(exported(h, base)['contents'])
    body['pages'][1].update(status='needs_review', issues=['Unclear diagram label'])
    assert upload(h, base, body).status_code == 200
    assert not h.ctx.store.all('book_units')


def test_only_assigned_public_checked_structure_enters_preparation(book):
    h, s, doc, base = book
    h.call('POST', base)
    body = checked(exported(h, base)['contents'])
    assert upload(h, base, body).status_code == 200
    topic = {'document_id': doc, 'page_start': 1, 'page_end': 1, 'pdf_page_offset': 0}
    context = companion.teaching_pages(h.ctx, topic)
    assert context[0]['elements'][0]['kind'] == 'diagram'
    assert 'native_text' not in str(context) and 'teacher_only' not in str(context)
    assert companion.teaching_pages(h.ctx, {**topic, 'stop_before': 'Later heading'}) == []


def test_test_mode_imports_are_isolated_from_real_sources_and_files(book):
    from services.test_mode import manager
    h, s, doc, base = book
    h.call('POST', base)
    before = copy.deepcopy(h.ctx.store.all('book_companions'))
    original_files = {str(p.relative_to(h.drive)) for p in h.drive.rglob('*.json')}
    token = h.call('POST', '/api/test-mode', json={'enabled': True}).json()['token']
    body = checked(exported(h, base)['contents'])
    payload = {'content_sha256': companion.digest(body), 'contents': body}
    response = h.client.post(base + '/import', headers={'X-Homeschooling-Mode': token},
        files={'file': ('book.json', json.dumps(payload).encode(), 'application/json')}, data={'expected_revision': 1})
    assert response.status_code == 200, response.text
    assert response.json()['checked_pages'] == 2
    assert h.ctx.store.all('book_companions') == before and not h.ctx.store.all('book_units')
    assert {str(p.relative_to(h.drive)) for p in h.drive.rglob('*.json')} == original_files
    assert manager(h.ctx).get(token).store.all('book_units')
    manager(h.ctx).end(token)


def test_key_answers_are_private_source_evidence_and_cannot_be_invented(book):
    h, s, doc, base = book
    collection = h.call('GET', f"/api/subjects/{s['id']}/book-collection").json()
    source = collection['books'][0]
    path = h.add_file(make_pdf([['Question 1: blue']]), 'Incoming Books/AnswerKey.pdf')
    response = h.call('PUT', f"/api/subjects/{s['id']}/book-collection", json={'name': collection['name'], 'expected_revision': collection['revision'], 'books': [
        {'key': 'main', 'document_id': doc, 'role': 'combined', 'edition': '2024', 'position': 0, 'is_main': True},
        {'key': 'key', 'path': path, 'role': 'answer_key', 'edition': '', 'position': 1, 'is_main': False, 'answer_for_key': 'main'}]})
    assert response.status_code == 200, response.text
    keydoc = response.json()['books'][1]['document_id']
    keybase = f"/api/subjects/{s['id']}/book-companions/{keydoc}"
    assert h.call('POST', keybase).status_code == 200
    body = exported(h, keybase)['contents']
    page = body['pages'][0]
    page.update(status='checked', review_method='visual', issues=[])
    body['teacher_only']['answers'] = [{'reference': '1', 'pages': [1], 'answer': 'blue', 'evidence': 'Question 1: blue'}]
    result = upload(h, keybase, body)
    assert result.status_code == 200, result.text
    inventory = h.call('GET', f"/api/subjects/{s['id']}/book-companions").text
    assert 'blue' not in inventory
    assert all(p['teacher_material'] and not p['student_safe'] for p in exported(h, keybase)['contents']['pages'])
    pdf = h.call('GET', keybase + '/source-pdf/1')
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF')
    assert h.call('GET', keybase + '/source-pdf/1', role='tutor').status_code == 403
    body['teacher_only']['answers'][0]['answer'] = 'red'
    assert upload(h, keybase, body, revision=2).status_code == 400


def test_scan_method_aliases_keep_existing_paid_scans_reusable(book):
    from tutoring.books import ident, scan_version
    h, s, doc, base = book
    h.call('POST', base)
    body = checked(exported(h, base)['contents'])
    first, last, data = next(companion.units(body))
    for page in data['pages']:
        page['review_method'] = 'native'
    record = h.ctx.store.get('documents', doc)
    with h.ctx.store.transaction() as tx:
        tx.insert('book_units', {'id': ident(record['sha256'], 'combined', scan_version('combined'), 1),
            'sha256': record['sha256'], 'role': 'combined', 'version': scan_version('combined'), 'first_page': first, 'last_page': last, 'data': data})
    result = h.call('POST', base)
    assert result.status_code == 200, result.text
    assert result.json()['checked_pages'] == 2
    assert exported(h, base)['contents']['pages'][0]['review_method'] == 'native_checked'


def test_formatting_equivalent_quotes_preserve_actual_source_and_mathematical_signs():
    from tutoring.books import original_quote
    original = 'Heading\nA\no sair do buraco, o ratinho fi  cou parado .\nNext paragraph.'
    assert original_quote(original, 'Ao sair do buraco, o ratinho ficou parado.') == 'A\no sair do buraco, o ratinho fi  cou parado .'
    assert original_quote('A conta é −3 + 2.', 'A conta é -3 + 2.') == 'A conta é −3 + 2.'
    assert original_quote('A conta é −3 + 2.', 'A conta é 3 + 2.') is None
    assert original_quote(original, 'O ratinho fugiu.') is None
    assert original_quote('Lem-\nbro-me dos de-\nsenhos.', 'Lembro-me dos desenhos.') == 'Lem-\nbro-me dos de-\nsenhos.'
    assert original_quote('3 -\n2', '3 2') is None


def test_visual_answer_evidence_requires_the_exact_key_page_element():
    from tutoring.books import key_evidence_supported
    page = {'page': 3, 'text': 'Matching exercise answer diagram', 'teacher_material': True,
            'elements': [{'id': 'p3:element:2', 'kind': 'table', 'rows': [['Estacou', 'Parou subitamente']]}]}
    answer = {'pages': [3], 'answer': 'Parou subitamente', 'evidence': 'Estacou Parou subitamente', 'evidence_element_ids': ['p3:element:2']}
    assert key_evidence_supported(answer, [page])
    assert not key_evidence_supported({**answer, 'evidence_element_ids': []}, [page])
    assert not key_evidence_supported({**answer, 'evidence_element_ids': ['p4:element:2']}, [page])
    assert not key_evidence_supported({**answer, 'pages': [2]}, [page])
    assert not key_evidence_supported({**answer, 'answer': 'Gritou'}, [page])


def test_multipage_key_quotes_preserve_actual_pages_and_reject_unobserved_answers():
    from tutoring.books import key_evidence_supported
    pages=[{'page':1,'text':'First official answer.','teacher_material':True},
           {'page':2,'text':'Second official answer.','teacher_material':True}]
    answer={'pages':[1,2],'answer':'First official answer.\nSecond official answer.',
        'evidence':'First official answer.\nSecond official answer.',
        'evidence_quotes':[{'page':1,'quote':'First official answer.'},{'page':2,'quote':'Second official answer.'}]}
    assert key_evidence_supported(answer,pages)
    assert not key_evidence_supported({**answer,'answer':'An inferred answer.'},pages)
    assert not key_evidence_supported({**answer,'evidence_quotes':[{'page':1,'quote':'Second official answer.'}]},pages)


def test_source_corrections_preserve_original_scan_history_and_survive_refresh(book):
    from tutoring import books
    h,s,doc,base=book
    h.call('POST',base)
    body=checked(exported(h,base)['contents'])
    first=upload(h,base,body)
    assert first.status_code==200,first.text
    original=copy.deepcopy(h.ctx.store.all('book_units'))
    body=exported(h,base)['contents']
    body['pages'][0]['text']+='\nA visually checked continuation.'
    body['pages'][0]['reading_blocks'].append('A visually checked continuation.')
    payload={'content_sha256':companion.digest(body),'contents':body}
    options={'files':{'file':('corrected.json',json.dumps(payload).encode(),'application/json')},
        'data':{'expected_revision':first.json()['revision'],'source_review':'true','note':'Compared the synthetic page with the original PDF.'}}
    saved=h.call('POST',base+'/import',**options)
    assert saved.status_code==200,saved.text
    assert h.ctx.store.all('book_units')==original
    assert len(h.ctx.store.all('book_source_reviews'))==1
    assert h.call('POST',base+'/import',**options).status_code==409
    assert h.call('POST',base).status_code==200
    assert exported(h,base)['contents']['pages'][0]['text'].endswith('A visually checked continuation.')
    assert h.call('GET',base+'/history').json()['reviews'][0]['version']==1
    assert not h.ctx.store.all('attempts') and not h.ctx.store.all('guides')


def test_line_spans_are_page_local_and_observations_do_not_block_reading():
    from tutoring.books import normalize_scan
    page={'page':1,'text':'','native_reliable':True,'student_safe':True,'teacher_material':False,'headings':[],
        'reading_blocks':['Text copied from another page.'],'reading_spans':[{'first_line':2,'last_line':2}],
        'review_notes':['The definition ends on this page.'],'issue':None}
    result=normalize_scan({'pages':[page],'exercises':[],'answers':[]},'combined',1,1,1,
        {1:'Original heading\nThe original sentence with its original punctuation\nWrite your own answer below.'},[])
    assert result['pages'][0]['reading_blocks']==['The original sentence with its original punctuation']
    assert not result['pages'][0]['issue'] and result['pages'][0]['review_notes']
    page['reading_spans']=[{'first_line':99,'last_line':100}]
    rejected=normalize_scan({'pages':[page],'exercises':[],'answers':[]},'combined',1,1,1,{1:'Original source text.'},[])
    assert rejected['pages'][0]['issue'] and not rejected['pages'][0]['reading_blocks']


def test_saved_paid_proposal_revalidation_never_repeats_generation_or_rewrites_checkpoint(book, monkeypatch):
    from tutoring import books
    h, s, docid, base = book
    h.call('POST', base)
    doc = h.ctx.store.get('documents', docid)
    pdf = h.ctx.file_bytes(doc['file_path'], doc['sha256'])
    proposal = {'pages': [{'page': n, 'text': '', 'native_reliable': True, 'student_safe': True,
        'teacher_material': False, 'issue': None, 'headings': [], 'reading_blocks': [text]}
        for n, text in [(1, 'Native text with no invented image details.'), (2, 'More original text.')]], 'exercises': [], 'answers': []}
    calls = []
    def generate(*a, **kw):
        calls.append(1)
        return copy.deepcopy(proposal)
    monkeypatch.setattr(h.ctx.ai, 'generate', generate)
    data = books.scan_unit(h.ctx, pdf, 'combined', 1, 2)
    assert books.scan_unit(h.ctx, pdf, 'combined', 1, 2) == data and len(calls) == 1
    prior = copy.deepcopy(data)
    prior['pages'][0].update(issue='Combined-book reading must quote the original student text', reading_blocks=[])
    with h.ctx.store.transaction() as tx:
        tx.insert('book_units', {'id': 'old-checkpoint', 'sha256': doc['sha256'], 'role': 'combined', 'version': books.scan_version('combined'),
                                'first_page': 1, 'last_page': 2, 'data': prior})
    unit = h.ctx.store.get('book_units', 'old-checkpoint')
    resolved = books.resolve_scan(h.ctx.store, unit)
    assert resolved['data']['pages'][0]['issue'] is None
    assert resolved['data']['pages'][0]['reading_blocks']
    assert h.ctx.store.get('book_units', 'old-checkpoint')['data'] == prior
    assert len(calls) == 1


def test_key_target_book_numbers_are_not_mistaken_for_key_source_pages():
    from tutoring.books import normalize_scan
    raw = {'pages': [{'page': 1, 'text': 'Question 1: blue', 'native_reliable': False, 'headings': [], 'reading_blocks': []}],
           'exercises': [], 'answers': [{'reference': '1', 'pages': [81], 'answer': 'blue', 'evidence': 'Question 1: blue', 'issue': None}]}
    result = normalize_scan(copy.deepcopy(raw), 'answer_key', 1, 1, 1, {1: 'Question 1: blue'}, [])
    assert result['answers'][0]['pages'] == [1] and result['answers'][0]['issue'] is None
    raw['answers'][0].update(answer='red', evidence='Question 1: red')
    unresolved = normalize_scan(raw, 'answer_key', 1, 1, 1, {1: 'Question 1: blue'}, [])
    assert unresolved['answers'][0]['issue'] and unresolved['answers'][0]['pages'] == [1]


def test_export_import_round_trip_keeps_native_capture_metadata_out_of_source_identity(book):
    from tutoring import books
    h, s, docid, base = book
    h.call('POST', base)
    body = checked(exported(h, base)['contents'])
    first, last, data = next(companion.units(body))
    for page in data['pages']:
        page['native_reliable'] = True
        for element in page['elements']:
            element['id'] = ''
    doc = h.ctx.store.get('documents', docid)
    with h.ctx.store.transaction() as tx:
        tx.insert('book_units', {'id': books.ident(doc['sha256'], 'combined', books.scan_version('combined'), first),
            'sha256': doc['sha256'], 'role': 'combined', 'version': books.scan_version('combined'),
            'first_page': first, 'last_page': last, 'data': data})
    saved = h.call('POST', base).json()
    body = exported(h, base)['contents']
    body['producer'] = 'Codex inspected export'
    result = upload(h, base, body, revision=saved['revision'])
    assert result.status_code == 200, result.text
    assert result.json()['checked_pages'] == 2


def test_visual_task_references_resolve_only_an_exact_unique_question_on_the_same_page():
    pages = [{'page': 1, 'status': 'checked', 'issues': [], 'elements': [
        {'id': 'picture', 'relates_to': ['1', 'already-linked']},
        {'id': 'already-linked', 'relates_to': []}]}]
    tasks = [{'id': 'exercise-one', 'reference': '1', 'pages': [1]},
             {'id': 'elsewhere', 'reference': '1', 'pages': [2]}]
    companion.link_element_references(pages, tasks)
    assert pages[0]['elements'][0]['relates_to'] == ['exercise-one', 'already-linked']
    assert pages[0]['status'] == 'checked'
    tasks.append({'id': 'ambiguous', 'reference': '1', 'pages': [1]})
    pages[0]['elements'][0]['relates_to'] = ['1']
    companion.link_element_references(pages, tasks)
    assert pages[0]['elements'][0]['relates_to'] == []
    assert pages[0]['status'] == 'needs_review'
    assert pages[0]['elements'][0]['issue']


def test_imported_exercise_identity_survives_cache_refresh(book):
    h, s, doc, base = book
    h.call('POST', base)
    body = checked(exported(h, base)['contents'])
    body['exercises'] = [{'id': 'codex-source-question', 'reference': '1', 'pages': [1],
        'prompt': body['pages'][0]['text'], 'answer': None, 'issue': None}]
    body['pages'][0]['elements'][0]['relates_to'] = ['codex-source-question']
    result = upload(h, base, body)
    assert result.status_code == 200, result.text
    assert h.call('POST', base).status_code == 200
    saved = exported(h, base)['contents']
    assert saved['exercises'][0]['id'] == 'codex-source-question'
    assert saved['pages'][0]['elements'][0]['relates_to'] == ['codex-source-question']


@pytest.mark.parametrize('fail', [False, True])
def test_parallel_source_scans_checkpoint_completed_pages_in_the_same_job_scope(book, monkeypatch, fail):
    import threading
    from services.ai_provider import _generation_scope
    from tutoring import books
    h, s, doc, base = book
    collection = h.call('GET', f"/api/subjects/{s['id']}/book-collection").json()
    path = h.add_file(make_pdf([[f'Synthetic original page {n}'] for n in range(1, 25)]), 'Incoming Books/Parallel.pdf')
    response = h.call('PUT', f"/api/subjects/{s['id']}/book-collection", json={'name': collection['name'], 'expected_revision': collection['revision'],
        'books': [{'key': 'parallel', 'path': path, 'role': 'combined', 'edition': '', 'position': 0, 'is_main': True}]})
    assert response.status_code == 200, response.text
    source = response.json()['books'][0]
    assert h.call('POST', f"/api/subjects/{s['id']}/book-companions/{source['document_id']}").status_code == 200
    service = h.ctx.subject_analysis
    preview = service.preview(s['id'])
    with h.ctx.store.transaction() as tx:
        jid = service.start(tx, s['id'], preview['fingerprint'], 100000)
    with h.ctx.store.transaction() as tx:
        tx.update('collection_analysis_jobs', jid, {'status': 'running'})
    job = h.ctx.store.get('collection_analysis_jobs', jid)
    barrier = threading.Barrier(3)
    scopes = []
    def scan(ctx, pdf, role, first, last):
        scopes.append(_generation_scope.get())
        barrier.wait(timeout=8)
        if fail and first == 9:
            raise ValueError('Synthetic provider failure; no automatic repeat purchase')
        return {'pages': [{'page': n, 'text': f'Synthetic original page {n}', 'student_safe': True,
            'teacher_material': False, 'issue': None, 'headings': [], 'reading_blocks': [], 'elements': []} for n in range(first, last + 1)],
            'exercises': [], 'answers': []}
    monkeypatch.setattr(books, 'scan_unit', scan)
    if fail:
        with pytest.raises(ValueError, match='Synthetic provider failure'):
            service._scan_companion_pages(job, job['plan']['sources'])
    else:
        service._scan_companion_pages(job, job['plan']['sources'])
    assert scopes == [jid, jid, jid]
    expected = 2 if fail else 3
    assert len(h.ctx.store.find('book_units', sha256=source['sha256'], role='combined')) == expected
    inventory = companion.inventory(h.ctx, s['id'])
    assert inventory[0]['checked_pages'] == expected * 8
    assert h.ctx.store.get('collection_analysis_jobs', jid)['done'] == expected
    assert not h.ctx.store.all('attempts')
