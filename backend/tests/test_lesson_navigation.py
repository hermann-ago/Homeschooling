"""Navigation replays saved teaching without rewriting learner evidence."""
import pytest

from tests.test_activity_engine import engine_lesson, event
from tests.test_lesson_overview import reach_question
from tests.test_interactive import correct
from tutoring import interactive
from tutoring.activity_engine import service
from tutoring.service import TutorConflict, TutorError


def test_repeated_back_moves_to_beginning_and_keeps_pending_draft_after_restart(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    assert not state['can_go_back']
    state = reach_question(engine, state)
    question = state['active_activity']
    state = event(engine, state, 'save_draft', {'text': 'Still thinking', 'draft_revision': 0})
    state = event(engine, state, 'take_break')
    before = state
    state = event(engine, state, 'go_back', operation='back-from-break')
    assert state['active_activity']['kind'] == 'read_source' and not state['on_break']
    assert state['active_activity']['interaction']['replay_of']
    assert event(engine, before, 'go_back', operation='back-from-break')['active_activity']['id'] == state['active_activity']['id']
    with pytest.raises(TutorConflict):
        event(engine, before, 'go_back', operation='stale-navigation')
    state = event(engine, state, 'go_back')
    assert state['active_activity']['kind'] == 'introduce' and not state['can_go_back']
    with pytest.raises(TutorConflict): event(engine, state, 'go_back')
    harness.restart()
    engine = service(harness.ctx)
    state = event(engine, engine.state(state['session_id']), 'continue')
    state = event(engine, state, 'reading_done')
    state = event(engine, state, 'continue')
    assert state['active_activity']['interaction']['id'] == question['interaction']['id']
    assert state['active_activity']['draft']['text'] == 'Still thinking'
    assert not harness.ctx.store.all('attempts')


def test_start_over_keeps_answers_saved_but_shows_a_fresh_lesson(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = reach_question(engine, state)
    monkeypatch.setattr(interactive, 'gemini_turn', correct)
    state = event(engine, state, 'submit_response', {'response_id': 'old-answer', 'text': 'He united them.', 'assess_after_save': True})
    old_question = state['active_activity']
    state = event(engine, state, 'continue')
    snapshots = {table: harness.ctx.store.all(table) for table in ('attempts', 'activity_responses', 'lesson_dialogue', 'guides', 'audio_tracks')}
    before = state
    state = event(engine, state, 'restart_lesson', operation='restart-original-lesson')
    assert state['active_activity']['kind'] == 'introduce' and not state['can_go_back']
    first_interaction = state['active_activity']['interaction']['id']
    assert event(engine, before, 'restart_lesson', operation='restart-original-lesson')['active_activity']['interaction']['id'] == first_interaction
    assert {table: harness.ctx.store.all(table) for table in snapshots} == snapshots
    harness.restart()
    engine = service(harness.ctx)
    state = reach_question(engine, engine.state(state['session_id']))
    active = state['active_activity']
    assert active['interaction']['id'] != old_question['interaction']['id']
    assert active['interaction']['replay_of'] == old_question['interaction']['id']
    assert active['interaction']['status'] == 'awaiting_input'
    assert active['interaction']['prompt'] == old_question['content']['prompt']
    # The old answer stays saved but is no longer part of the lesson on screen.
    assert active['responses'] == [] and active['messages'] == []
    assert harness.ctx.store.get('activity_responses', 'old-answer')
    with pytest.raises(TutorError): event(engine, state, 'assess', {'response_id': 'old-answer'})
    state = event(engine, state, 'submit_response', {'response_id': 'new-answer', 'text': 'They joined together.'})
    assert [r['id'] for r in state['active_activity']['responses']] == ['new-answer']
    assert {table: harness.ctx.store.all(table) for table in ('attempts', 'lesson_dialogue')} == {table: snapshots[table] for table in ('attempts', 'lesson_dialogue')}


def test_navigation_api_is_family_only_and_never_generates_ai_material(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = reach_question(engine, state)
    monkeypatch.setattr(harness.ctx.ai, 'generate', lambda *_a, **_k: pytest.fail('Navigation must not buy AI content'))
    active = state['active_activity']
    payload = {'operation_id': 'api-back-step-operation', 'expected_revision': state['revision'],
               'activity_id': active['id'], 'interaction_id': active['interaction']['id'], 'type': 'go_back'}
    path = f"/api/tutor/sessions/{state['session_id']}/activity-events"
    assert harness.call('POST', path, role='tutor', json=payload).status_code == 403
    result = harness.call('POST', path, json=payload)
    assert result.status_code == 200, result.text
    assert result.json()['active_activity']['kind'] == 'read_source'
    assert harness.call('POST', path, json=payload).json()['active_activity']['id'] == result.json()['active_activity']['id']


def test_back_restores_parked_reading_offset_but_replaying_a_finished_read_starts_fresh(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = event(engine, state, 'continue')
    interaction = state['active_activity']['interaction']['id']
    cursor = {'sentence_index': state['active_activity']['start_sentence'], 'track_id': 'saved-voice', 'part_index': 1, 'offset_seconds': 4.25}
    state = event(engine, state, 'go_back', {'cursor': cursor})
    state = event(engine, state, 'continue')
    assert state['playback']['narration_cursor'] == cursor
    assert state['active_activity']['interaction']['id'] == interaction
    state = event(engine, state, 'reading_done')
    state = event(engine, state, 'continue')
    state = event(engine, state, 'go_back')
    assert state['playback']['narration_cursor'] is None
    assert state['active_activity']['interaction']['replay_of'] == interaction


def test_restart_during_confirmation_keeps_capture_and_assistance_but_never_reuses_it_as_a_new_answer(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = reach_question(engine, state)
    monkeypatch.setattr(harness.ctx.ai, 'generate', lambda *_a, **_k: {'text': 'Think about groups.'})
    state = event(engine, state, 'request_hint')
    state = event(engine, state, 'submit_response', {'response_id': 'unconfirmed', 'text': 'They united.', 'method': 'dictation'})
    saved = harness.ctx.store.get('activity_responses', 'unconfirmed')
    state = event(engine, state, 'restart_lesson')
    state = reach_question(engine, state)
    assert state['active_activity']['interaction']['status'] == 'awaiting_input'
    assert harness.ctx.store.get('activity_responses', 'unconfirmed') == saved
    assert saved['status'] == 'awaiting_confirmation'
    with pytest.raises(TutorError): event(engine, state, 'confirm_response', {'response_id': 'unconfirmed', 'text': 'Changed'})
    state = event(engine, state, 'submit_response', {'response_id': 'after-restart', 'text': 'A new answer'})
    assert 'groups' in harness.ctx.store.get('activity_responses', 'after-restart')['support_snapshot']['this']
    assert not harness.ctx.store.all('attempts')


def test_start_over_on_finished_lesson_starts_at_introduction_not_unfinished_carryover(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = reach_question(engine, state)
    state = event(engine, state, 'skip')
    state = event(engine, state, 'continue')
    state = event(engine, state, 'finish')
    original = harness.ctx.store.get('tutor_sessions', state['session_id'])
    repeated = engine.repeat(state['session_id'], 'restart-finished-operation', from_beginning=True)
    assert repeated['session_id'] != state['session_id']
    assert repeated['active_activity']['kind'] == 'introduce'
    assert harness.ctx.store.get('tutor_sessions', state['session_id']) == original
    repeated = event(engine, repeated, 'continue')
    recovered = engine.repeat(state['session_id'], 'restart-finished-operation', from_beginning=True)
    assert recovered['active_activity']['kind'] == 'read_source'
    assert recovered['active_activity']['interaction']['id'] == repeated['active_activity']['interaction']['id']
    with pytest.raises(TutorConflict): engine.repeat(state['session_id'], 'restart-finished-operation')
