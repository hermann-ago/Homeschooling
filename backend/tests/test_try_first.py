"""Let me try first: skip the teaching, attempt the exercise, see the teaching only after a miss."""
import pytest

from tests.test_activity_engine import engine_lesson, event


def answers(monkeypatch, *replies):
    from tutoring import interactive
    queue = list(replies)
    monkeypatch.setattr(interactive, 'gemini_turn', lambda *a, **k: queue.pop(0))


NOT_YET = {'feedback': 'Look at the river again.', 'result': 'Not yet', 'ready_to_continue': False}
RIGHT = {'feedback': 'Yes.', 'result': 'Correct', 'ready_to_continue': True}


def statuses(harness, state):
    return {a['action_id']: a['status'] for a in harness.ctx.store.find('lesson_actions', session_id=state['session_id'])}


def test_trying_first_sets_the_teaching_aside_and_a_miss_brings_it_back(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    assert state['active_activity']['can_try_first']
    state = event(engine, state, 'try_first')
    active = state['active_activity']
    assert active['id'] == 'action-1' and active['status'] == 'pending'
    assert statuses(harness, state)['segment-1'] == 'answered'  # the welcome counts as seen
    assert statuses(harness, state)['segment-2'] == 'not_assigned'  # the reading waits, neither done nor owed
    assert active['teaching_available'] and not active['can_try_first']

    answers(monkeypatch, NOT_YET, RIGHT)
    state = event(engine, state, 'submit_response', {'response_id': 'first', 'text': 'A guess', 'assess_after_save': True})
    retry = state['active_activity']['interaction']['id']
    state = event(engine, state, 'show_teaching')
    assert state['active_activity']['id'] == 'segment-2' and statuses(harness, state)['segment-2'] == 'pending'
    state = event(engine, state, 'reading_done')
    state = event(engine, state, 'continue')
    # Back at the same exercise and prompt, ready for the second try.
    assert state['active_activity']['id'] == 'action-1' and state['active_activity']['interaction']['id'] == retry
    assert not state['active_activity']['teaching_available']
    state = event(engine, state, 'submit_response', {'response_id': 'second', 'text': 'The river', 'assess_after_save': True})
    assert state['active_activity']['status'] == 'answered'


def test_a_first_try_success_leaves_the_reading_unread_but_not_owed(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = event(engine, state, 'try_first')
    answers(monkeypatch, RIGHT)
    state = event(engine, state, 'submit_response', {'response_id': 'only', 'text': 'The river', 'assess_after_save': True})
    state = event(engine, state, 'continue')
    assert state['active_activity']['kind'] == 'close_lesson'
    assert 'segment-2' not in str(state['active_activity']['content'].get('unfinished') or [])
    state = event(engine, state, 'finish')
    summary = harness.ctx.store.get('tutor_sessions', state['session_id'])['completion_summary']
    assert summary['reading']['status'] == 'incomplete' and summary['reading']['set_aside_ids'] == ['segment-2']
    assert summary['pending_work'] == []


def test_try_first_only_from_teaching_with_an_exercise_ahead(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = event(engine, state, 'try_first')
    with pytest.raises(Exception, match='no exercise ahead'):
        event(engine, state, 'try_first')
    answers(monkeypatch, RIGHT)
    state = event(engine, state, 'submit_response', {'response_id': 'only', 'text': 'The river', 'assess_after_save': True})
    state = event(engine, state, 'continue')
    assert not state['active_activity']['can_try_first'] and not state['active_activity']['teaching_available']


def test_show_me_how_replaces_an_extra_question_the_tutor_added_after_a_miss(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = event(engine, state, 'try_first')
    extra = {'kind': 'ask_question', 'content': {'prompt': 'Where did they stop?', 'response_modes': ['choice'],
             'answer_format': 'single_choice', 'choices': [{'id': 'a', 'label': 'At the river'}, {'id': 'b', 'label': 'At home'}]}}
    answers(monkeypatch, {**NOT_YET, 'activity_requests': [extra]}, RIGHT)
    state = event(engine, state, 'submit_response', {'response_id': 'first', 'text': 'A guess', 'assess_after_save': True})
    child = state['active_activity']
    assert child['parent_activity_id'] == 'action-1' and child['teaching_available']
    state = event(engine, state, 'show_teaching')
    assert state['active_activity']['id'] == 'segment-2' and statuses(harness, state)[child['id']] == 'not_assigned'
    state = event(engine, state, 'reading_done')
    state = event(engine, state, 'continue')
    assert state['active_activity']['id'] == 'action-1'
    state = event(engine, state, 'submit_response', {'response_id': 'second', 'text': 'The river', 'assess_after_save': True})
    state = event(engine, state, 'continue')
    state = event(engine, state, 'finish')  # nothing left pending behind the scenes
    assert harness.ctx.store.get('tutor_sessions', state['session_id'])['status'] == 'completed'
