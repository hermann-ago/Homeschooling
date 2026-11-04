"""Books without a key: proposed answers wait for a grown-up's approval, then check instantly."""
import json

import pytest

from tutoring import page_script

PASSAGE = {'sentences': [{'text': 'O pitu muda de cor.'}]}
PAGES = {'pages': [{'document_id': 1, 'page': 1, 'printed_page': 21, 'role': 'assigned_reading', 'book_name': 'Português'}]}


def script(**work):
    return {'welcome': 'Vamos ler.', 'turns': [
        {'type': 'read', 'first': 0, 'last': 0},
        {'type': 'book_work', 'document_id': 1, 'page': 1, 'prompt': 'Complete com h.',
         'response': {'format': 'blanks', 'blanks': ['__umor:', '__orta:']}, **work}], 'closing': 'Muito bem.'}


def test_proposed_answers_are_one_per_box_and_only_without_a_key():
    page_script.compile_script(script(proposed_answers=['humor', 'horta']), PASSAGE, {'visual_source': PAGES}, 'pt-BR')
    with pytest.raises(ValueError, match='one short key answer per blank'):
        page_script.compile_script(script(proposed_answers=['humor']), PASSAGE, {'visual_source': PAGES}, 'pt-BR')
    with pytest.raises(ValueError, match='only for blanks the answer key does not cover'):
        page_script.compile_script(script(answer='humor; horta', answers=['humor', 'horta'], proposed_answers=['humor', 'horta']),
                                   PASSAGE, {'visual_source': PAGES}, 'pt-BR')


class Store:
    def __init__(self, rows):
        self.rows = rows

    def get(self, table, key):
        return self.rows.get(table, {}).get(key)

    def find(self, table, **equals):
        return [r for r in self.rows.get(table, {}).values() if all(r.get(k) == v for k, v in equals.items())]


def lesson(approvals=()):
    turns = script(proposed_answers=['humor', 'horta'])['turns']
    guide = {'activities': [{'id': 'activity-1', 'origin': 'required_book', 'kind': 'request_book_work'}]}
    ctx = type('Ctx', (), {})()
    ctx.store = Store({'lesson_playback': {'s1': {'guide_id': 'g1', 'context_snapshot': {'prepared_guide': {
                           'teaching_script': {'script': {'turns': turns}}}}}},
                       'guides': {'g1': {'guide_path': 'g1.json'}},
                       'answer_approvals': {a['id']: a for a in approvals}})
    ctx.file_bytes = lambda path, sha=None: json.dumps(guide).encode()
    return ctx, {'session_id': 's1', 'action_id': 'activity-1'}


def test_proposals_are_never_used_until_approved():
    ctx, action = lesson()
    assert page_script.answer_for(ctx, action) is None
    ctx, action = lesson([{'id': 'g1:0', 'guide_id': 'g1', 'work_index': 0, 'answers': ['humor', 'horta']}])
    key = page_script.answer_for(ctx, action)
    assert key['answer_items'] == ['humor', 'horta'] and 'Approved by a grown-up' in key['note']


def test_family_approves_edits_and_withdraws_answers(harness, monkeypatch):
    from tests.test_activity_engine import engine_lesson
    engine, state, _ = engine_lesson(harness, monkeypatch)
    guide_id = harness.ctx.store.get('lesson_playback', state['session_id'])['guide_id']
    row = harness.ctx.store.get('guides', guide_id)
    with harness.ctx.store.transaction() as tx:
        tx.update('guides', guide_id, {'context_snapshot': {**(row['context_snapshot'] or {}),
            'teaching_script': {'script': script(proposed_answers=['humor', 'horta'])}}})
    path = f'/api/tutor/guides/{guide_id}'
    entry = harness.call('GET', path + '/review').json()['answer_key'][0]
    assert entry['proposed_answers'] == ['humor', 'horta'] and entry['approved_answers'] is None
    assert harness.call('PUT', path + '/answers/0', json={'answers': ['humor']}).status_code == 400
    assert harness.call('PUT', path + '/answers/0', role='tutor', json={'answers': ['humor', 'horta']}).status_code == 403
    saved = harness.call('PUT', path + '/answers/0', json={'answers': ['humor', ' horta ']})
    assert saved.status_code == 200 and saved.json()['approved_answers'] == ['humor', 'horta']
    assert harness.call('GET', path + '/review').json()['answer_key'][0]['approved_answers'] == ['humor', 'horta']
    assert harness.call('DELETE', path + '/answers/0').status_code == 204
    assert harness.call('GET', path + '/review').json()['answer_key'][0]['approved_answers'] is None
