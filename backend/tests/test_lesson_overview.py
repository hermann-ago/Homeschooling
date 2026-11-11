"""Observed summaries, repeat links, recap returns and deliberate support requests."""
import pytest

from tests.test_activity_engine import engine_lesson, event, invoke
from tests.test_interactive import correct
from tutoring import interactive
from tutoring.activity_engine import service
from tutoring.service import TutorConflict, TutorError


def reach_question(engine, state):
    state = event(engine, state, 'continue')
    state = event(engine, state, 'reading_done')
    return event(engine, state, 'continue')


def complete(engine, state):
    state = event(engine, state, 'submit_response', {'response_id': 'overview-answer', 'text': 'He united them.', 'assess_after_save': True})
    state = event(engine, state, 'continue')
    return event(engine, state, 'finish')


def test_recap_distinguishes_reading_capture_assessment_help_and_unfinished_work(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    assert state['learning_summary'] is None
    state = reach_question(engine, state)
    with harness.ctx.store.transaction() as tx:  # help recorded on this step, as in earlier lessons
        tx.update('lesson_actions', f"{state['session_id']}:{state['active_activity']['id']}", {'help_given': 'Think about groups.'})
    state = event(engine, state, 'submit_response', {'response_id': 'unassessed-original', 'text': 'An unfinished answer'})
    old_interaction = state['active_activity']['interaction']['id']
    state = event(engine, state, 'skip')
    state = event(engine, state, 'continue')
    summary = state['learning_summary']
    assert summary['reading'] == {'reached': 1, 'total': 1}
    assert summary['answers'] == {'captured': 1, 'checked': 0}
    assert summary['help']['activity_count'] == 1
    assert summary['help']['activity_labels'] == ['What did Genghis Khan do with the tribes?']
    target = summary['pending_work'][0]['activity_id']
    saved_response = harness.ctx.store.get('activity_responses', 'unassessed-original')
    assert not harness.ctx.store.all('attempts')
    state = event(engine, state, 'revisit_activity', {'activity_id': target}, operation='return-from-recap')
    assert state['active_activity']['id'] == target
    assert state['active_activity']['interaction']['id'] != old_interaction
    assert harness.ctx.store.get('activity_responses', 'unassessed-original') == saved_response
    assert state['active_activity']['interaction']['status'] == 'awaiting_input'
    # The original confirmation cannot be assessed as the new interaction's answer.
    with pytest.raises(TutorError):
        event(engine, state, 'assess', {'response_id': 'unassessed-original'})
    harness.restart()
    assert service(harness.ctx).state(state['session_id'])['active_activity']['id'] == target


def test_an_adaptive_recap_does_not_reveal_an_unreached_question(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state, 'close_lesson', {'text': 'Review our progress so far.'})
    assert state['active_activity']['kind'] == 'close_lesson'
    assert state['learning_summary']['pending_work'] == []
    assert state['learning_summary']['answers'] == {'captured': 0, 'checked': 0}


def test_repeat_family_links_resume_and_next_lesson_are_scoped_and_read_only(harness, monkeypatch):
    engine, state, seeded = engine_lesson(harness, monkeypatch)
    monkeypatch.setattr(interactive, 'gemini_turn', correct)
    state = complete(engine, reach_question(engine, state))
    original = state['session_id']
    row = harness.ctx.store.get('tutor_sessions', original)
    assert state['learning_summary']['answers'] == {'captured': 1, 'checked': 1}
    next_lesson = state['attempt_navigation']['next_lesson']
    assert next_lesson and f"learner={seeded['lucas']['id']}" in next_lesson['path']
    repeated = engine.repeat(original, 'overview-repeat-operation')
    navigation = engine.state(original)['attempt_navigation']
    assert navigation['resume_repeat']['id'] == repeated['session_id']
    assert [item['label'] for item in navigation['attempts']] == ['Original lesson', 'Repeat 1']
    assert repeated['attempt_navigation']['attempts'][0]['path'].endswith(f'session={original}')
    assert harness.ctx.store.get('tutor_sessions', original) == row
    assert engine.repeat(original, 'overview-repeat-operation')['session_id'] == repeated['session_id']
    with harness.ctx.store.transaction() as tx:
        tx.update('tutor_sessions', repeated['session_id'], {'status': 'completed'})
    assert engine.state(original)['attempt_navigation']['resume_repeat'] is None


def test_revisit_does_not_allow_skipping_ahead_from_an_active_question(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = reach_question(engine, state)
    with pytest.raises(TutorConflict):
        event(engine, state, 'revisit_activity', {'activity_id': state['active_activity']['id']})


def test_completed_unfinished_work_continues_in_a_new_attempt(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = reach_question(engine, state)
    target = state['active_activity']['id']
    state = event(engine, state, 'skip')
    state = event(engine, state, 'continue')
    state = event(engine, state, 'finish')
    assert state['learning_summary']['pending_work'][0]['activity_id'] == target
    assert state['learning_summary']['answers'] == {'captured': 0, 'checked': 0}
    original = harness.ctx.store.get('tutor_sessions', state['session_id'])
    continued = engine.repeat(state['session_id'], 'continue-unfinished-work')
    assert continued['session_id'] != state['session_id']
    assert continued['active_activity']['id'] == target
    assert continued['active_activity']['interaction']['status'] == 'awaiting_input'
    assert harness.ctx.store.get('tutor_sessions', state['session_id']) == original
    assert not harness.ctx.store.all('attempts')


