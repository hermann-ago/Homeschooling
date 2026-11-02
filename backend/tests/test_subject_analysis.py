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


