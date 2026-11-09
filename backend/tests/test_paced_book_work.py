"""Paced subjects: the child does book work in the book and moves on; photos can be checked at the end."""
import pytest

from tests.test_activity_engine import event
from tests.test_interactive import prepare, start
from tests.test_lesson_overview import reach_question
from tutoring.activity_engine import service
from tutoring.service import TutorError

PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 200


def paced_lesson(harness, monkeypatch, mode='paced'):
    seeded, guide = prepare(harness, monkeypatch)
    with harness.ctx.store.transaction() as tx:
        tx.update('subjects', seeded['history']['id'], {'book_work': mode})
    legacy = start(harness, seeded, guide)
    engine = service(harness.ctx)
    return engine, engine.state(legacy['session_id']), seeded


def photo(harness, state, name='page.png'):
    response = harness.call('POST', f"/api/tutor/sessions/{state['session_id']}/evidence",
        data={'expected_revision': str(state['revision']), 'action_id': state['active_activity']['id']},
        files={'file': (name, PNG, 'image/png')})
    assert response.status_code == 200, response.text
    return response.json()['evidence_id']


def test_done_in_book_moves_on_without_an_answer_and_is_never_owed_later(harness, monkeypatch):
    engine, state, seeded = paced_lesson(harness, monkeypatch)
    assert state['book_work'] == 'paced' and state['page_work'] == {}
    state = reach_question(engine, state)
    question = state['active_activity']
    assert question['paced'] is True
    state = event(engine, state, 'done_in_book')
    row = harness.ctx.store.get('lesson_actions', f"{state['session_id']}:{question['id']}")
    assert row['status'] == 'in_book' and not harness.ctx.store.all('activity_responses')
    assert state['active_activity']['kind'] == 'close_lesson'
    assert state['progress']['items'] == [{'id': question['id'], 'outcome': 'done'}]
    assert state['learning_summary']['pending_work'] == []
    assert state['book_check'] == {'count': 1, 'status': None}
    state = event(engine, state, 'finish')
    session = harness.ctx.store.get('tutor_sessions', state['session_id'])
    assert session['status'] == 'completed' and session['completion_summary']['pending_work'] == []
    assert session['completion_summary']['book_work'] == {'mode': 'paced', 'in_book': [question['id']], 'check': None}
    # A later lesson in this subject is not asked to return to it.
    packet = harness.ctx.tutor.context(seeded['lucas']['id'], seeded['history']['id'])
    assert not [a for a in packet['pending_actions'] if a['session_id'] == state['session_id']]


def test_subjects_that_check_answers_keep_their_flow(harness, monkeypatch):
    engine, state, _ = paced_lesson(harness, monkeypatch, mode='tutor')
    assert state['book_work'] == 'tutor' and state['book_check'] is None
    state = reach_question(engine, state)
    assert state['active_activity']['paced'] is False
    with pytest.raises(TutorError):
        event(engine, state, 'done_in_book')


def test_the_mode_is_frozen_when_the_lesson_starts(harness, monkeypatch):
    engine, state, seeded = paced_lesson(harness, monkeypatch)
    with harness.ctx.store.transaction() as tx:
        tx.update('subjects', seeded['history']['id'], {'book_work': 'tutor'})
    assert engine.state(state['session_id'])['book_work'] == 'paced'


def test_photos_at_the_end_are_read_once_and_record_no_grade(harness, monkeypatch):
    engine, state, _ = paced_lesson(harness, monkeypatch)
    state = event(engine, reach_question(engine, state), 'done_in_book')
    question = state['activities'][[a['kind'] for a in state['activities']].index('ask_question')]['id']
    with pytest.raises(TutorError):
        event(engine, state, 'submit_book_check', {'evidence_ids': []})
    first = photo(harness, engine.state(state['session_id']))
    second = photo(harness, engine.state(state['session_id']), 'page-2.png')
    calls = []

    def read(prompt, **kwargs):
        calls.append(kwargs)
        assert 'teacher_key' in prompt and len(kwargs['images']) == 2
        return {'items': [{'item_id': question, 'answer': 'He fought them', 'result': 'check_again',
                           'note': 'Look again at what he did with the tribes.'}], 'summary': 'One answer to look at again.'}
    monkeypatch.setattr(harness.ctx.ai, 'generate', read)
    state = event(engine, engine.state(state['session_id']), 'submit_book_check', {'evidence_ids': [first, second]}, operation='check-1')
    check = state['book_check']
    assert check['status'] == 'completed' and check['photos'] == 2
    assert check['items'][0]['result'] == 'check_again' and check['summary'] == 'One answer to look at again.'
    # Replaying the same request reuses the saved result.
    state = event(engine, engine.state(state['session_id']), 'submit_book_check', {'evidence_ids': [first, second]}, operation='check-1')
    assert len(calls) == 1 and not harness.ctx.store.all('attempts')
    state = event(engine, state, 'finish')
    check = harness.ctx.store.get('tutor_sessions', state['session_id'])['completion_summary']['book_work']['check']
    assert check['check_again'] == [question]


def test_a_failed_check_keeps_the_photos_and_can_be_tried_again(harness, monkeypatch):
    engine, state, _ = paced_lesson(harness, monkeypatch)
    state = event(engine, reach_question(engine, state), 'done_in_book')
    first = photo(harness, state)

    def fail(*args, **kwargs):
        raise RuntimeError('provider down')
    monkeypatch.setattr(harness.ctx.ai, 'generate', fail)
    state = event(engine, engine.state(state['session_id']), 'submit_book_check', {'evidence_ids': [first]})
    assert state['book_check']['status'] == 'failed' and 'nothing was marked wrong' in state['book_check']['error']
    question = next(a['id'] for a in state['activities'] if a['kind'] == 'ask_question')
    monkeypatch.setattr(harness.ctx.ai, 'generate', lambda *a, **k: {'items': [{'item_id': question, 'answer': 'He united them',
        'result': 'looks_right', 'note': ''}], 'summary': 'All good.'})
    state = event(engine, engine.state(state['session_id']), 'retry_book_check')
    assert state['book_check']['status'] == 'completed'


def test_one_press_finishes_a_whole_true_or_false_exercise(harness, monkeypatch):
    from tests.test_activity_engine import invoke
    engine, state, _ = paced_lesson(harness, monkeypatch)
    statements = ('The Mongols lived in tents.', 'Genghis Khan was born in Rome.', 'The tribes were united.')
    for statement in statements:
        state = invoke(engine, state, content={'prompt': statement, 'answer_format': 'true_false'})
    rows = sorted((a for a in harness.ctx.store.find('lesson_actions', session_id=state['session_id']) if a['prompt'] in statements and (a.get('activity_content') or {}).get('answer_format') == 'true_false'),
                  key=lambda a: statements.index(a['prompt']))
    assert len(rows) == 3
    with harness.ctx.store.transaction() as tx:
        for order, row in enumerate(rows):
            tx.update('lesson_actions', row['id'], {'origin': 'required_book', 'source_refs': [{'document_id': 1, 'page': 9}], 'parent_activity_id': None,
                                                    'activity_order': -300 + order})
        tx.update('lesson_playback', state['session_id'], {'action_id': rows[0]['action_id']})
    state = engine.state(state['session_id'])
    first = state['active_activity']
    assert first['practice_section']['total'] == 3 and first['paced']
    state = event(engine, state, 'done_in_book')
    statuses = {a['status'] for a in harness.ctx.store.find('lesson_actions', session_id=state['session_id']) if a['id'] in {r['id'] for r in rows}}
    assert statuses == {'in_book'}


def test_the_lesson_api_accepts_the_paced_events(harness, monkeypatch):
    engine, state, _ = paced_lesson(harness, monkeypatch)
    state = reach_question(engine, state)
    active = state['active_activity']
    response = harness.call('POST', f"/api/tutor/sessions/{state['session_id']}/activity-events", json={
        'operation_id': 'api-done-1', 'expected_revision': state['revision'], 'activity_id': active['id'],
        'interaction_id': active['interaction']['id'], 'type': 'done_in_book', 'payload': {}})
    assert response.status_code == 200, response.text
    assert response.json()['active_activity']['kind'] == 'close_lesson'
