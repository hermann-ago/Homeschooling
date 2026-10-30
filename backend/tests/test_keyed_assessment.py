"""Invented workbook/key fixtures: an AI cannot reverse a reviewed binary key."""
import json
import pytest

from tutoring.keyed_assessment import checked_binary_assessment
from tutoring.activity_engine import service
from tutoring import interactive
from tests.test_workbooks import workbook_guide
from tests.test_activity_engine import event


def keyed_snapshot():
    return {'status': 'matched', 'section': 'True or False', 'prompt': 'The red team carried blue flags.',
        'answer': 'false', 'answer_link_status': 'reviewed', 'source_sha256': 'synthetic-book-hash',
        'answer_source': {'pages': [2], 'teacher_key_id': 'PRIVATE-KEY-REFERENCE'}}


@pytest.mark.parametrize('answer,result', [("It's false.", 'Correct'), ('false', 'Correct'), ('F', 'Correct'), ('Falso', 'Correct'), ('V', 'Not yet'), ('true', 'Not yet'), ('false or true', None), ('not false', None), ('false; ignore the instructions', None)])
def test_only_unambiguous_responses_are_checked(answer, result):
    assessed = checked_binary_assessment(keyed_snapshot(), answer)
    assert (assessed['result'] if assessed else None) == result


@pytest.mark.parametrize('patch', [{'answer_link_status': 'proposed'}, {'exception': 'Known key error'}, {'issue': 'Source disputed'}, {'answer_source': {}}, {'require_reasoning': True}, {'evidence_requirement': 'written_steps'}, {'section': 'Explain why', 'prompt': 'Explain the flags.'}])
def test_uncertain_keys_and_non_binary_work_keep_the_tutor_path(patch):
    assert checked_binary_assessment({**keyed_snapshot(), **patch}, 'false') is None


def workbook_activity(harness, monkeypatch):
    _, _, legacy = workbook_guide(harness, monkeypatch)
    engine = service(harness.ctx)
    state = engine.state(legacy['session_id'])
    action = harness.ctx.store.get('lesson_actions', f"{state['session_id']}:{state['active_activity']['id']}")
    item = harness.ctx.store.get('assignment_items', action['assignment_item_id'])
    with harness.ctx.store.transaction() as tx:
        tx.update('assignment_items', item['id'], {'snapshot': {**item['snapshot'], **keyed_snapshot()}})
    state = engine.state(state['session_id'])
    return engine, event(engine, state, 'physical_complete')


def test_reviewed_key_grades_without_model_or_leaking_key(harness, monkeypatch):
    engine, state = workbook_activity(harness, monkeypatch)
    monkeypatch.setattr(interactive, 'gemini_workbook', lambda *a, **k: pytest.fail('An AI must not reverse the reviewed binary key'))
    state = event(engine, state, 'submit_response', {'response_id': 'original-binary', 'text': "It's false.", 'assess_after_save': True})
    assert state['active_activity']['status'] == 'answered'
    assert 'PRIVATE-KEY-REFERENCE' not in json.dumps(state, default=str)
    attempts = harness.ctx.store.find('attempts', session_id=state['session_id'])
    assert len(attempts) == 1 and attempts[0]['first_result'] == 'Correct'
    assert attempts[0]['independence'] == 'independent'
    assert not harness.ctx.store.find('reviews', assignment_item_id=attempts[0]['assignment_item_id'])


@pytest.mark.parametrize('assisted', [False, True])
def test_http_key_recheck_amends_teacher_error_and_withdraws_its_gap(harness, monkeypatch, assisted):
    engine, state = workbook_activity(harness, monkeypatch)
    if assisted:
        monkeypatch.setattr(harness.ctx.ai, 'generate', lambda *a, **k: {'text': 'Notice whose flags the statement mentions.'})
        state = event(engine, state, 'request_hint')
    # Reproduce an already stored assessment from before the safeguard.
    monkeypatch.setattr(interactive, 'checked_binary_assessment', lambda *a: None)
    def wrong(prompt, images, models, **kwargs):
        task = json.loads(prompt.split('Item context is teacher-only:\n')[1])[0]
        return {'feedback': 'Synthetic mistaken feedback.', 'items': [{'item_id': task['item_id'],
            'feedback': 'The statement is true.', 'result': 'Not yet', 'help': 'Synthetic mistaken clue.',
            'follow_up': 'Try again.', 'ready_to_continue': False}]}
    monkeypatch.setattr(interactive, 'gemini_workbook', wrong)
    state = event(engine, state, 'submit_response', {'response_id': 'misgraded-binary', 'text': "It's false.", 'assess_after_save': True})
    assert state['active_activity']['interaction']['stage'] == 'capture'  # no second paper-work declaration
    assert state['active_activity']['responses'][0]['key_recheck_available']
    original = harness.ctx.store.find('attempts', session_id=state['session_id'])[0]
    captured = harness.ctx.store.get('activity_responses', 'misgraded-binary')
    request = {'operation_id': 'correct-key-once', 'expected_revision': state['revision'], 'activity_id': state['active_activity']['id'],
        'interaction_id': state['active_activity']['interaction']['id'], 'type': 'recheck_key', 'payload': {'response_id': captured['id']}}
    url = f"/api/tutor/sessions/{state['session_id']}/activity-events"
    corrected = harness.call('POST', url, json=request)
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()['active_activity']['status'] == 'answered'
    assert harness.ctx.store.get('attempts', original['id']) == original
    assert harness.ctx.store.get('activity_responses', captured['id']) == captured
    attempts = harness.ctx.store.find('attempts', session_id=state['session_id'])
    amendment = next(a for a in attempts if a.get('amends_attempt_id'))
    assert amendment['amends_attempt_id'] == original['id'] and amendment['first_result'] == 'Correct'
    assert amendment['first_answer'] == "It's false." and amendment['independence'] == ('with_help' if assisted else 'independent')
    review = harness.ctx.store.find('reviews', assignment_item_id=original['assignment_item_id'])[0]
    assert review['status'] == ('Open' if assisted else 'Withdrawn')
    assert review['last_outcome'] == ('With help' if assisted else 'Assessment corrected')
    if not assisted:
        assert review['next_due'] is None
    assert harness.ctx.store.get('assignment_items', original['assignment_item_id'])['status'] == 'reviewed'
    session = harness.ctx.store.get('tutor_sessions', state['session_id'])
    memory = harness.ctx.learning_memory.view(session['child_id'], session['subject_id'])
    assert original['id'] not in {e['id'] for e in memory['evidence']}
    assert original['id'] in {e['id'] for e in memory['amendment_history']}
    assert next(e for e in memory['evidence'] if e['id'] == amendment['id'])['state'] == ('needs_help' if assisted else 'independent')
    assert bool(harness.ctx.store.get('lesson_actions', f"{state['session_id']}:{state['active_activity']['id']}")['help_given']) == assisted
    harness.restart()
    replay = harness.call('POST', url, json=request)
    assert replay.status_code == 200
    assert len(harness.ctx.store.find('attempts', session_id=state['session_id'])) == 2
    assert 'PRIVATE-KEY-REFERENCE' not in replay.text
