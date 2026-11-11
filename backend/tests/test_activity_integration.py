"""Whole synthetic lessons through HTTP, including restart and desktop tools."""
import json
import sqlite3
import uuid

import pytest

from tests.test_activity_engine import engine_lesson, event, invoke
from tests.test_mcp_bridge import call, make_bridge
from tutoring import interactive
from tutoring.activity_engine import service
from tutoring.activities import ACTIVITY_KINDS
from storage.schema import SCHEMA_VERSION
from storage.store import Store


def http_event(h, state, kind, payload=None, operation=None):
    active = state['active_activity']
    operation = operation or str(uuid.uuid4())
    response = h.call('POST', f"/api/tutor/sessions/{state['session_id']}/activity-events", key=operation,
        json={'operation_id': operation, 'expected_revision': state['revision'], 'activity_id': active['id'],
              'interaction_id': active['interaction']['id'], 'type': kind, 'payload': payload or {}})
    assert response.status_code == 200, response.text
    assert response.headers['x-sync-state'] == 'saved'
    assert h.ctx.store.get('operation_receipts', response.json()['receipt_id'])
    return response.json()


def test_typed_history_slice_finishes_with_original_hint_revision_and_replay(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    assert state['active_activity']['kind'] == 'introduce'
    state = http_event(harness, state, 'continue')
    assert state['active_activity']['kind'] == 'read_source'
    state = http_event(harness, state, 'reading_done')
    state = http_event(harness, state, 'continue')
    assert state['active_activity']['kind'] == 'ask_question'
    state = http_event(harness, state, 'submit_response', {'response_id': 'synthetic-original', 'text': 'They stayed apart.'})
    monkeypatch.setattr(interactive, 'gemini_turn', lambda *args: {'feedback': 'Look again at the groups.', 'result': 'Not yet',
        'follow_up': 'What did he do with the tribes?', 'ready_to_continue': False})
    state = http_event(harness, state, 'assess', {'response_id': 'synthetic-original'}, 'assess-original-once')
    state = http_event(harness, state, 'submit_response', {'response_id': 'synthetic-revision', 'text': 'He united the tribes.'})
    state = http_event(harness, state, 'take_break')
    harness.restart()
    engine = service(harness.ctx)
    state = engine.state(state['session_id'])
    assert state['on_break'] and state['active_activity']['responses'][-1]['status'] == 'confirmed'
    state = http_event(harness, state, 'resume')
    monkeypatch.setattr(interactive, 'gemini_turn', lambda *args: {'feedback': 'Yes, the tribes joined together.', 'result': 'Correct', 'ready_to_continue': True})
    state = http_event(harness, state, 'assess', {'response_id': 'synthetic-revision'})
    attempts = harness.ctx.store.find('attempts', session_id=state['session_id'])
    assert len(attempts) == 2 and attempts[0]['first_answer'] == 'They stayed apart.'
    assert attempts[1]['revised_answer'] == 'He united the tribes.' and attempts[1]['independence'] == 'with_help'
    # An old assessment operation remains a read of the original result after a follow-up.
    state = engine.command(state['session_id'], 0, 'assess-original-once', state['active_activity']['id'],
        state['active_activity']['responses'][0]['interaction_id'], 'assess', {'response_id': 'synthetic-original'})
    assert len(harness.ctx.store.find('attempts', session_id=state['session_id'])) == 2
    state = http_event(harness, state, 'continue')
    assert state['active_activity']['kind'] == 'close_lesson'
    assert state['status'] != 'completed'
    assert state['playback']['slot_id'] is None
    before_progress=harness.call('GET',f"/api/progress/{state['child_id']}").json()
    subject_id=harness.ctx.store.get('tutor_sessions',state['session_id'])['subject_id']
    before_pages=next(s['completed_pages'] for s in before_progress['subjects'] if s['subject_id']==subject_id)
    state = http_event(harness, state, 'finish')
    assert state['status'] == 'completed' and state['active_activity'] is None
    topic=harness.ctx.store.get('topics',harness.ctx.store.get('tutor_sessions',state['session_id'])['topic_id'])
    assert topic['completed'] and topic['completed_at'] and topic['evidence_session_id']==state['session_id']
    after_progress=harness.call('GET',f"/api/progress/{state['child_id']}").json()
    after_pages=next(s['completed_pages'] for s in after_progress['subjects'] if s['subject_id']==subject_id)
    assert after_pages==before_pages+topic['page_end']-topic['page_start']+1
    assert state['completion_summary']['reading']['status'] == 'reached'
    assert state['completion_summary']['understanding'] == 'With help'
    assert not state['completion_summary']['pending_work']
    assert len(state['completion_summary']['attempt_ids']) == 2


def test_repeat_is_durable_and_preserves_the_complete_original_thread(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    monkeypatch.setattr(interactive, 'gemini_turn', lambda *args: {'feedback': 'Yes, the tribes joined together.', 'result': 'Correct', 'ready_to_continue': True})
    for _ in range(12):
        active = state['active_activity']
        if active is None:
            break
        kind = active['kind']
        command = 'finish' if kind == 'close_lesson' else 'reading_done' if kind == 'read_source' and active['status'] == 'pending' else 'submit_response' if kind == 'ask_question' and active['status'] == 'pending' else 'continue'
        state = http_event(harness, state, command, {'response_id': 'repeat-original-answer', 'text': 'He united the tribes.', 'assess_after_save': True} if command == 'submit_response' else {})
    assert state['status'] == 'completed'
    original_id = state['session_id']
    original = harness.ctx.store.get('tutor_sessions', original_id)
    snapshots = {table: harness.ctx.store.find(table, session_id=original_id) for table in
                 ('attempts', 'activity_responses', 'activity_interactions', 'lesson_dialogue', 'lesson_actions')}
    path = f'/api/tutor/sessions/{original_id}/repeat'
    assert harness.call('POST', path, role='tutor', json={'operation_id': 'repeat-original-lesson'}).status_code == 403
    response = harness.call('POST', path, json={'operation_id': 'repeat-original-lesson'})
    assert response.status_code == 200, response.text
    repeated = response.json()
    assert repeated['session_id'] != original_id
    assert repeated['playback']['guide_id'] == state['playback']['guide_id']
    assert repeated['status'] == 'active'
    harness.restart()
    recovered = harness.call('POST', path, json={'operation_id': 'repeat-original-lesson'})
    assert recovered.status_code == 200 and recovered.json()['session_id'] == repeated['session_id']
    assert harness.ctx.store.get('tutor_sessions', original_id) == original
    assert all(harness.ctx.store.find(table, session_id=original_id) == rows for table, rows in snapshots.items())
    resumed = harness.call('POST', path, json={'operation_id': 'another-repeat-operation'})
    assert resumed.status_code == 200 and resumed.json()['session_id'] == repeated['session_id']
    records = harness.call('GET', '/api/records', params={'view': 'lessons'}).json()['rows']
    assert next(row for row in records if row['id'] == original_id)['lesson_path'].endswith(f'session={original_id}')


def test_unfinished_continuation_visits_only_saved_work_and_closes_without_repeating_reading(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = http_event(harness, state, 'continue')
    state = http_event(harness, state, 'reading_done')
    state = http_event(harness, state, 'continue')
    state = http_event(harness, state, 'submit_response', {'response_id': 'saved-unchecked', 'text': 'Original answer.'})
    state = http_event(harness, state, 'skip')
    state = http_event(harness, state, 'continue')
    state = http_event(harness, state, 'finish')
    original_id = state['session_id']
    original_responses = harness.ctx.store.find('activity_responses', session_id=original_id)
    assert len(state['learning_summary']['pending_work']) == 1
    command = {'operation_id': 'continue-only-remaining', 'unfinished_only': True}
    url = f'/api/tutor/sessions/{original_id}/repeat'
    result = harness.call('POST', url, json=command)
    assert result.status_code == 200, result.text
    state = result.json()
    assert state['catch_up']['focused'] and state['catch_up']['remaining'] == 1
    assert state['active_activity']['kind'] == 'ask_question'
    assert not [a for a in state['activities'] if a['kind'] == 'read_source' and a['status'] != 'not_assigned']
    state = http_event(harness, state, 'skip')
    previous_interaction = state['active_activity']['interaction']['id']
    state = http_event(harness, state, 'focus_unfinished')
    assert state['active_activity']['interaction']['status'] == 'awaiting_input'
    assert state['active_activity']['interaction']['id'] != previous_interaction
    monkeypatch.setattr(interactive, 'gemini_turn', lambda *args: {'feedback': 'Checked.', 'result': 'Correct', 'ready_to_continue': True})
    state = http_event(harness, state, 'submit_response', {'response_id': 'remaining-answer', 'text': 'He united the tribes.', 'assess_after_save': True})
    state = http_event(harness, state, 'continue')
    assert state['active_activity']['kind'] == 'close_lesson'
    assert state['catch_up']['remaining'] == 0
    assert state['learning_summary']['reading']['total'] == 0
    state = http_event(harness, state, 'finish')
    assert state['status'] == 'completed' and not state['completion_summary']['pending_work']
    assert state['completion_summary']['reading']['status'] == 'not_assigned'
    assert harness.ctx.store.find('activity_responses', session_id=original_id) == original_responses
    assert len(harness.ctx.store.find('attempts', session_id=state['session_id'])) == 1
    harness.restart()
    replay = harness.call('POST', url, json=command)
    assert replay.status_code == 200 and replay.json()['status'] == 'completed'


def test_legacy_repeat_can_focus_after_saved_work_is_checked_without_another_reading(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = http_event(harness, state, 'continue')
    state = http_event(harness, state, 'reading_done')
    state = http_event(harness, state, 'continue')
    state = http_event(harness, state, 'skip')
    state = http_event(harness, state, 'continue')
    state = http_event(harness, state, 'finish')
    repeated = engine.repeat(state['session_id'], 'legacy-follow-up')
    assert repeated['catch_up']['remaining'] == 1 and not repeated['catch_up']['focused']
    monkeypatch.setattr(interactive, 'gemini_turn', lambda *args: {'feedback': 'Checked.', 'result': 'Correct', 'ready_to_continue': True})
    repeated = http_event(harness, repeated, 'submit_response', {'response_id': 'old-catch-up-answer', 'text': 'He united them.', 'assess_after_save': True})
    repeated = http_event(harness, repeated, 'continue')
    assert repeated['active_activity']['kind'] != 'close_lesson'
    attempts = harness.ctx.store.all('attempts')
    repeated = http_event(harness, repeated, 'focus_unfinished', operation='repair-catch-up')
    assert repeated['active_activity']['kind'] == 'close_lesson'
    assert repeated['catch_up']['remaining'] == 0
    assert harness.ctx.store.all('attempts') == attempts


def test_server_draft_is_not_an_attempt_and_survives_restart(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state)
    state = event(engine, state, 'save_draft', {'response_id': 'draft-answer', 'method': 'typed', 'text': 'An unfinished explanation'})
    revision = state['revision']
    assert not harness.ctx.store.all('attempts') and not harness.ctx.store.all('activity_responses')
    harness.restart()
    state = service(harness.ctx).state(state['session_id'])
    assert state['revision'] == revision
    assert state['active_activity']['draft']['text'] == 'An unfinished explanation'


def test_photo_is_only_transcribed_before_confirmation_and_parent_uncertainty_is_revisitable(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state, content={'prompt': 'What did you write?', 'response_modes': ['text', 'photo']})
    active = state['active_activity']
    with harness.ctx.store.transaction() as tx:
        harness.ctx.tutor.evidence(tx, state['session_id'], state['revision'], 'synthetic.png', b'not-a-real-image', 'image/png', None, active['id'])
    state = engine.state(state['session_id'])
    evidence = harness.ctx.store.find('evidence_files', session_id=state['session_id'])[0]
    seen = []
    def transcribe(prompt, **kwargs):
        seen.append(kwargs['schema'].__name__)
        return {'text': 'The trides joined.', 'uncertain': True}
    monkeypatch.setattr(harness.ctx.ai, 'generate', transcribe)
    state = event(engine, state, 'submit_response', {'response_id': 'photo-first', 'method': 'photo', 'evidence_ids': [evidence['id']]})
    assert seen == ['TranscriptionReply'] and not harness.ctx.store.all('attempts')
    assert state['active_activity']['responses'][0]['proposed_text'] == 'The trides joined.'
    with pytest.raises(Exception, match='Confirm'):
        event(engine, state, 'assess', {'response_id': 'photo-first'})
    state = event(engine, state, 'request_parent_review', {'response_id': 'photo-first'})
    state = event(engine, state, 'parent_review', {'response_id': 'photo-first', 'result': 'Unanswered', 'note': 'The photo needs a clearer view.'})
    assert not harness.ctx.store.all('attempts') and state['active_activity']['interaction']['status'] == 'parent_review'
    state = event(engine, state, 'parent_review', {'response_id': 'photo-first', 'result': 'Correct', 'text': 'The tribes joined.', 'note': 'Inspected the original physical page.'})
    assert harness.ctx.store.all('attempts')[0]['independence'] == 'not_assessed'


def test_desktop_tools_use_canonical_schemas_and_need_family_grant(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    bridge = make_bridge(harness)
    listed = bridge.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})['result']['tools']
    assert set(ACTIVITY_KINDS) <= {tool['name'] for tool in listed}
    question = next(tool for tool in listed if tool['name'] == 'ask_question')
    assert question['inputSchema']['properties']['content']['additionalProperties'] is False
    args = {'session_id': state['session_id'], 'expected_revision': state['revision'], 'operation_id': 'desktop-question-once', 'content': {'prompt': 'Explain the connection.'}}
    error, result = call(bridge, 'ask_question', args)
    assert error and result['status'] == 403
    harness.call('POST', f"/api/tutor/sessions/{state['session_id']}/activity-access", json={'enabled': True})
    error, shown = call(bridge, 'ask_question', args)
    assert not error, shown
    assert shown['result']['activity_result']['status'] == 'awaiting_input'
    error, again = call(bridge, 'ask_question', args)
    assert not error and again['receipt']['replayed']
    assert len([a for a in engine.state(state['session_id'])['activities'] if a['id'] == shown['result']['activity_id']]) == 1


def test_additive_v1_upgrade_preserves_old_rows_and_is_idempotent(tmp_path):
    database = tmp_path / 'old.sqlite3'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE _meta (key TEXT PRIMARY KEY,value TEXT)')
        db.execute("INSERT INTO _meta VALUES ('schema_version','1')")
        db.execute('CREATE TABLE children (id INTEGER PRIMARY KEY,name TEXT)')
        db.execute("INSERT INTO children VALUES (7,'Synthetic old learner')")
    store = Store(database).load()
    assert SCHEMA_VERSION == 2 and store.get('children', 7)['name'] == 'Synthetic old learner'
    assert store.all('activity_responses') == []
    assert Store(database).load().get('children', 7) == store.get('children', 7)
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT value FROM _meta WHERE key='schema_version'").fetchone()[0] == '2'


def test_tutor_requested_worked_example_uses_same_engine_and_retries_once(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state)
    original = state['active_activity']['id']
    state = event(engine, state, 'submit_response', {'response_id': 'needs-example', 'text': 'I think they stayed separate.'})
    monkeypatch.setattr(interactive, 'gemini_turn', lambda *args: {
        'feedback': 'Let us look at a similar situation.', 'result': 'Not yet', 'ready_to_continue': False,
        'activity_requests': [{'kind': 'worked_example', 'content': {'text': 'Watch how groups join.',
            'steps': [{'text': 'Start with two separate groups.'}, {'text': 'Bring them into one group.'}],
            'practice_prompt': 'Explain what changes when groups unite.', 'support_level': 'guided'}}]})
    state = event(engine, state, 'assess', {'response_id': 'needs-example'}, operation='adaptive-example-once')
    assert state['active_activity']['kind'] == 'worked_example'
    assert state['active_activity']['parent_activity_id'] == original
    child = state['active_activity']['id']
    response = harness.ctx.store.get('activity_responses', 'needs-example')
    state = engine.command(state['session_id'], 0, 'adaptive-example-once', original, response['interaction_id'],
        'assess', {'response_id': 'needs-example'})
    assert state['active_activity']['id'] == child
    assert len([a for a in state['activities'] if a['id'] == child]) == 1


def test_draft_conflict_keeps_the_first_device_copy(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state)
    state = event(engine, state, 'save_draft', {'response_id': 'first-device', 'text': 'Original draft', 'expected_draft_revision': 0})
    with pytest.raises(Exception, match='draft changed'):
        event(engine, state, 'save_draft', {'response_id': 'other-device', 'text': 'Stale replacement', 'expected_draft_revision': 0})
    assert engine.state(state['session_id'])['active_activity']['draft']['text'] == 'Original draft'


def test_break_tool_returns_to_its_origin_without_repeating_it(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    original = state['active_activity']['id']
    state = invoke(engine, state, 'take_break_and_return', {'text': 'Take a short break.'})
    state = event(engine, state, 'take_break')
    assert state['on_break']
    state = event(engine, state, 'resume')
    assert not state['on_break'] and state['active_activity']['id'] == original


def test_required_book_invocation_uses_the_pinned_assignment_not_tutor_labels(harness, monkeypatch):
    from tests.test_workbooks import add_catalog
    engine, state, seeded = engine_lesson(harness, monkeypatch)
    add_catalog(harness, seeded, count=1)
    with pytest.raises(Exception, match='version'):
        invoke(engine, state, content={'prompt': 'Use the source', 'source_refs': [
            {'exercise_id': 'exercise-test-0', 'version_id': 'a-missing-edition'}]})
    with harness.ctx.store.transaction() as tx:
        assignment = harness.ctx.books.assign_item(tx, tx.get('tutor_sessions', state['session_id']), 'exercise-test-0', 'version-test-0')
        old = tx.get('exercise_versions', 'version-test-0')
        tx.insert('exercise_versions', {'id': 'version-later', 'exercise_id': 'exercise-test-0', 'index_id': old['index_id'],
            'data': {**old['data'], 'prompt': 'A changed later edition question.', 'printed_page': '999'}})
        tx.update('exercises', 'exercise-test-0', {'active_version': 'version-later'})
    state = invoke(engine, state, 'request_book_work', {'prompt': 'An invented replacement', 'exercise_id': 'exercise-test-0',
        'book_name': 'Invented title', 'printed_page': '999', 'exercise_reference': 'invented'})
    content = state['active_activity']['content']
    assert content['prompt'] == assignment['snapshot']['prompt']
    assert content['printed_page'] == '79' and content['exercise_reference'] == '1'
    assert content['source_refs'] == [{'exercise_id': 'exercise-test-0', 'version_id': 'version-test-0'}]
    assert 'PRIVATE ANSWERS' not in json.dumps(content)


def test_closure_keeps_skipped_work_unassessed(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = event(engine, state, 'continue')
    state = event(engine, state, 'reading_done')
    state = event(engine, state, 'continue')
    pending = state['active_activity']['id']
    state = event(engine, state, 'skip')
    state = event(engine, state, 'continue')
    state = event(engine, state, 'finish')
    summary = state['completion_summary']
    assert summary['lesson_status'] == 'completed' and summary['reading']['status'] == 'reached'
    assert summary['understanding'] == 'Not assessed' and not summary['attempt_ids']
    assert summary['pending_work'][0]['activity_id'] == pending
    assert not harness.ctx.store.find('reviews', evidence_session_id=state['session_id'])


def test_return_orientation_acknowledgement_survives_refresh_and_does_not_follow_later_steps(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = http_event(harness, state, 'take_break')
    assert state['on_break'] and not state['orientation']
    state = http_event(harness, state, 'resume')
    assert state['orientation']
    state = http_event(harness, state, 'acknowledge_return')
    harness.restart()
    engine = service(harness.ctx)
    state = engine.state(state['session_id'])
    assert not state['orientation'] and not state['on_break']
    state = http_event(harness, state, 'take_break')
    state = http_event(harness, state, 'resume')
    assert state['orientation']
    state = http_event(harness, state, 'continue')
    assert state['active_activity']['kind'] == 'read_source' and not state['orientation']
