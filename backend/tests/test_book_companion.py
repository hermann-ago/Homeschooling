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


def test_key_target_book_numbers_are_not_mistaken_for_key_source_pages():
    from tutoring.books import normalize_scan
    raw = {'pages': [{'page': 1, 'text': 'Question 1: blue', 'native_reliable': False, 'headings': [], 'reading_blocks': []}],
           'exercises': [], 'answers': [{'reference': '1', 'pages': [81], 'answer': 'blue', 'evidence': 'Question 1: blue', 'issue': None}]}
    result = normalize_scan(copy.deepcopy(raw), 'answer_key', 1, 1, 1, {1: 'Question 1: blue'}, [])
    assert result['answers'][0]['pages'] == [1] and result['answers'][0]['issue'] is None
    raw['answers'][0].update(answer='red', evidence='Question 1: red')
    unresolved = normalize_scan(raw, 'answer_key', 1, 1, 1, {1: 'Question 1: blue'}, [])
    assert unresolved['answers'][0]['issue'] and unresolved['answers'][0]['pages'] == [1]


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


