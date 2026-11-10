"""Book work answered with a photo: the lesson moves on while the check runs."""
import pytest

from tests.test_activity_engine import event, invoke
from tests.test_interactive import prepare, start
from tests.test_lesson_overview import reach_question
from tests.test_paced_book_work import PNG, photo
from tutoring import photo_check
from tutoring.activity_engine import service
from tutoring.service import TutorConflict, TutorError


def lesson(harness, monkeypatch, inline=True):
    """The seeded lesson with its question turned into required book work."""
    seeded, guide = prepare(harness, monkeypatch)
    legacy = start(harness, seeded, guide)
    engine = service(harness.ctx)
    engine.background_checks = not inline
    state = engine.state(legacy['session_id'])
    question = next(a for a in harness.ctx.store.find('lesson_actions', session_id=state['session_id']) if a['activity_kind'] == 'ask_question')
    with harness.ctx.store.transaction() as tx:
        tx.update('lesson_actions', question['id'], {'origin': 'required_book', 'activity_kind': 'request_book_work'})
    return engine, reach_question(engine, engine.state(state['session_id'])), question


def snap(harness, engine, state, name='page.png'):
    evidence = photo(harness, state, name)
    return event(engine, engine.state(state['session_id']), 'snap_work', {'evidence_ids': [evidence]})


def reader(result='Correct', answer='He united the tribes', uncertain=False, feedback='Well done.'):
    def read(prompt, **kwargs):
        assert 'teacher_key' in prompt and kwargs['images']
        import json
        tasks = json.loads(prompt[prompt.index('['):])
        return {'items': [{'item_id': t['item_id'], 'answer': answer, 'uncertain': uncertain, 'result': result, 'feedback': feedback} for t in tasks]}
    return read


def test_a_photo_moves_the_lesson_on_and_a_right_answer_turns_green(harness, monkeypatch):
    engine, state, question = lesson(harness, monkeypatch)
    assert state['active_activity']['snap'] is True
    monkeypatch.setattr(harness.ctx.ai, 'generate', reader())
    evidence = photo(harness, state)
    state = event(engine, engine.state(state['session_id']), 'snap_work', {'evidence_ids': [evidence]})
    assert state['active_activity']['kind'] == 'close_lesson' and state['checking'] is False
    row = harness.ctx.store.get('lesson_actions', question['id'])
    assert row['status'] == 'answered'
    assert state['progress']['items'] == [{'id': question['action_id'], 'outcome': 'first_try'}]
    attempt = harness.ctx.store.all('attempts')[0]
    assert attempt['first_result'] == 'Correct' and attempt['first_answer'] == 'He united the tribes'
    response = harness.ctx.store.find('activity_responses', session_id=state['session_id'])[0]
    assert response['method'] == 'photo' and response['status'] == 'assessed' and response['evidence_ids'] == [evidence]
    state = event(engine, state, 'finish')
    assert harness.ctx.store.get('tutor_sessions', state['session_id'])['status'] == 'completed'


def test_a_wrong_answer_waits_in_the_tracker_and_can_be_fixed_then_returns(harness, monkeypatch):
    engine, state, question = lesson(harness, monkeypatch)
    monkeypatch.setattr(harness.ctx.ai, 'generate', reader('Not yet', 'He fought them', feedback='Look again at the tribes.'))
    state = snap(harness, engine, state)
    item = state['progress']['items'][0]
    assert item['outcome'] == 'fix' and item['check']['read'] == 'He fought them' and item['check']['feedback'] == 'Look again at the tribes.'
    assert harness.ctx.store.get('lesson_actions', question['id'])['status'] == 'fix'
    closing = state['active_activity']['id']
    state = event(engine, state, 'fix_work', {'activity_id': question['action_id']})
    active = state['active_activity']
    assert active['id'] == question['action_id'] and active['status'] == 'pending' and active['snap']
    assert active['fix'] == {'read': 'He fought them', 'result': 'Not yet', 'feedback': 'Look again at the tribes.'}
    with pytest.raises(TutorConflict):  # One fix at a time.
        event(engine, state, 'fix_work', {'activity_id': question['action_id']})
    monkeypatch.setattr(harness.ctx.ai, 'generate', reader())
    state = snap(harness, engine, state, 'again.png')
    assert state['active_activity']['id'] == closing
    assert state['progress']['items'][0]['outcome'] == 'again'
    row = harness.ctx.store.get('lesson_actions', question['id'])
    assert row['status'] == 'answered' and not row['return_cursor']
    assert len(harness.ctx.store.find('activity_responses', session_id=state['session_id'])) == 2


def test_fix_later_returns_without_changing_the_result(harness, monkeypatch):
    engine, state, question = lesson(harness, monkeypatch)
    monkeypatch.setattr(harness.ctx.ai, 'generate', reader('Not yet', 'He fought them'))
    state = snap(harness, engine, state)
    closing = state['active_activity']['id']
    state = event(engine, state, 'fix_work', {'activity_id': question['action_id']})
    state = event(engine, state, 'fix_later')
    assert state['active_activity']['id'] == closing
    assert harness.ctx.store.get('lesson_actions', question['id'])['status'] == 'fix'
    # Finishing with something left to fix is allowed; it is recorded to practise, not owed later.
    state = event(engine, state, 'finish')
    summary = harness.ctx.store.get('tutor_sessions', state['session_id'])['completion_summary']
    assert summary['pending_work'] == [] and summary['photo_checks']['to_practise'] == [question['action_id']]
    assert state['progress']['items'][0]['outcome'] == 'practise'


def test_an_unsure_reading_is_not_marked_wrong(harness, monkeypatch):
    engine, state, question = lesson(harness, monkeypatch)
    monkeypatch.setattr(harness.ctx.ai, 'generate', reader('Not yet', 'He ??? them', uncertain=True, feedback='I could not read this.'))
    state = snap(harness, engine, state)
    assert state['progress']['items'][0]['check']['result'] == 'Unreadable'
    assert harness.ctx.store.all('attempts')[0]['first_result'] == 'Unreadable'


def test_a_failed_check_keeps_the_photo_and_retries(harness, monkeypatch):
    engine, state, question = lesson(harness, monkeypatch)

    def fail(*args, **kwargs):
        raise RuntimeError('provider down')
    monkeypatch.setattr(harness.ctx.ai, 'generate', fail)
    state = snap(harness, engine, state)
    item = state['progress']['items'][0]
    assert item['outcome'] == 'unchecked' and 'Nothing was marked wrong' in item['check']['error']
    assert state['checking'] is False and not harness.ctx.store.all('attempts')
    monkeypatch.setattr(harness.ctx.ai, 'generate', reader())
    state = event(engine, state, 'retry_photo_check', {'activity_id': question['action_id']})
    assert state['progress']['items'][0]['outcome'] == 'first_try'


def test_one_photo_covers_a_whole_true_or_false_set_with_separate_results(harness, monkeypatch):
    engine, state, _ = lesson(harness, monkeypatch)
    statements = ('The Mongols lived in tents.', 'Genghis Khan was born in Rome.', 'The tribes were united.')
    for statement in statements:
        state = invoke(engine, state, content={'prompt': statement, 'answer_format': 'true_false'})
    rows = sorted((a for a in harness.ctx.store.find('lesson_actions', session_id=state['session_id'])
                   if a['prompt'] in statements and (a.get('activity_content') or {}).get('answer_format') == 'true_false'),
                  key=lambda a: statements.index(a['prompt']))
    with harness.ctx.store.transaction() as tx:
        for order, row in enumerate(rows):
            tx.update('lesson_actions', row['id'], {'origin': 'required_book', 'source_refs': [{'document_id': 1, 'page': 9}],
                                                    'parent_activity_id': None, 'activity_order': -300 + order})
        tx.update('lesson_playback', state['session_id'], {'action_id': rows[0]['action_id']})
    state = engine.state(state['session_id'])

    def read(prompt, **kwargs):
        return {'items': [{'item_id': row['action_id'], 'answer': 'T', 'uncertain': False,
                           'result': 'Not yet' if index == 1 else 'Correct', 'feedback': 'Checked.'} for index, row in enumerate(rows)]}
    monkeypatch.setattr(harness.ctx.ai, 'generate', read)
    state = snap(harness, engine, state)
    statuses = [harness.ctx.store.get('lesson_actions', row['id'])['status'] for row in rows]
    assert statuses == ['answered', 'fix', 'answered']
    assert len(harness.ctx.store.find('activity_jobs', session_id=state['session_id'], kind='photo_check')) == 1


def test_a_running_check_holds_the_finish_and_a_stale_result_is_not_applied(harness, monkeypatch):
    engine, state, question = lesson(harness, monkeypatch, inline=False)
    started = []
    monkeypatch.setattr(photo_check.threading, 'Thread', lambda **kwargs: type('T', (), {'start': lambda self: started.append(kwargs)})())
    state = snap(harness, engine, state)
    assert state['checking'] is True and state['progress']['items'][0]['outcome'] == 'checking' and len(started) == 1
    assert harness.ctx.store.get('lesson_actions', question['id'])['status'] == 'checking'
    with pytest.raises(TutorConflict):
        event(engine, state, 'finish')
    # The child goes back to the exercise before the result arrives: that result must not overwrite the new try.
    state = event(engine, engine.state(state['session_id']), 'go_back')
    assert state['active_activity']['id'] == question['action_id'] and state['active_activity']['status'] == 'pending'
    monkeypatch.setattr(harness.ctx.ai, 'generate', reader('Not yet', 'old photo'))
    job = harness.ctx.store.find('activity_jobs', session_id=state['session_id'], kind='photo_check')[0]
    photo_check.run(engine, job['id'])
    assert harness.ctx.store.get('activity_jobs', job['id'])['status'] == 'completed'
    assert harness.ctx.store.get('lesson_actions', question['id'])['status'] == 'pending' and not harness.ctx.store.all('attempts')


def test_paced_lessons_and_other_steps_do_not_take_photo_answers(harness, monkeypatch):
    engine, state, question = lesson(harness, monkeypatch)
    state = event(engine, state, 'skip')
    assert not state['active_activity'].get('snap')
    with pytest.raises(TutorError):
        event(engine, state, 'snap_work', {'evidence_ids': ['x']})
    assert PNG
