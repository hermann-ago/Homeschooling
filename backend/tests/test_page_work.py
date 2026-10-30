"""Synthetic page photos: one capture/confirmation, separate durable evidence."""
import copy

import pytest

from tests.test_activity_engine import engine_lesson, invoke, event
from tutoring.activity_engine import service
from tutoring import page_work
from tutoring.service import TutorConflict, TutorError


def page_lesson(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state, content={'prompt': 'Mark the first statement true or false.', 'answer_format': 'true_false', 'response_modes': ['text', 'choice']})
    db = harness.ctx.store
    root = db.get('lesson_actions', f"{state['session_id']}:{state['active_activity']['id']}")
    topic = db.get('topics', root['topic_id'])
    ref = {'document_id': topic['document_id'], 'page': 1, 'quote': root['prompt']}
    with db.transaction() as tx:
        for old in tx.find('lesson_actions', session_id=state['session_id']):
            if old['id'] != root['id']:
                tx.update('lesson_actions', old['id'], {'status': 'not_assigned'})
        root = tx.update('lesson_actions', root['id'], {'origin': 'required_book', 'parent_activity_id': None,
            'activity_order': 100, 'source_refs': [ref], 'return_cursor': None})
        for index in (2, 3):
            values = {k: copy.deepcopy(v) for k, v in root.items() if k not in ('id', 'revision', 'created_at', 'updated_at')}
            values.update(id=f"{state['session_id']}:page-item-{index}", action_id=f'page-item-{index}', activity_order=index * 100,
                prompt=f'Answer book question {index}.', next_prompt=None,
                source_refs=[{**ref, 'quote': f'Answer book question {index}.'}])
            values['activity_content']['prompt'] = values['prompt']
            tx.insert('lesson_actions', values)
        from storage import layout
        path, sha = tx.add_blob(b'synthetic page photograph', layout.for_topic(tx, topic['id'], layout.STUDENT_WORK), 'page.png', 'image/png')
        tx.insert('evidence_files', {'id': 'page-image', 'child_id': root['child_id'], 'session_id': state['session_id'],
            'action_id': root['action_id'], 'file_path': path, 'sha256': sha, 'mime_type': 'image/png'})
    return engine, engine.state(state['session_id'])


def transcribe(engine, state, monkeypatch, answers=None):
    state = event(engine, state, 'open_page_work')
    ids = [r['activity_id'] for r in state['page_work']['items']]
    rows = answers or [{'item_id': aid, 'text': 'False' if index == 0 else f'Written answer {index + 1}', 'uncertain': index == 2} for index, aid in enumerate(ids)]
    monkeypatch.setattr(engine.ctx.ai, 'generate', lambda *a, **k: k['schema'].model_validate({'items': rows}).model_dump())
    initial = state
    state = event(engine, state, 'submit_page_work', {'page_work_id': state['page_work']['id'], 'evidence_ids': ['page-image']}, operation='shared-transcription')
    return state, initial


def test_page_scope_stops_at_teaching_or_another_source_page(harness, monkeypatch):
    engine, state = page_lesson(harness, monkeypatch)
    assert state['page_work'] == {'available_count': 3}
    assert 'page-item-2' not in str(state['page_work'])  # No future questions until explicitly opened.
    with harness.ctx.store.transaction() as tx:
        tx.update('lesson_actions', f"{state['session_id']}:page-item-3", {'activity_kind': 'read_source'})
    assert engine.state(state['session_id'])['page_work']['available_count'] == 2
    with harness.ctx.store.transaction() as tx:
        tx.update('lesson_actions', f"{state['session_id']}:page-item-2", {'source_refs': [{'document_id': 999, 'page': 2, 'quote': 'Different page'}]})
    assert engine.state(state['session_id'])['page_work']['available_count'] == 0


def test_one_exercise_parts_are_default_but_other_questions_stay_hidden(harness, monkeypatch):
    engine, state = page_lesson(harness, monkeypatch)
    actions = page_work.candidates(engine, state['session_id'])
    with engine.db.transaction() as tx:
        for action, label in zip(actions, 'AB'):
            tx.update('lesson_actions', action['id'], {'source_refs': [
                {'document_id': 1, 'page': 1, 'quote': f'Fill in the blanks: {label.lower()}) The original blank ___.'}]})
        tx.update('lesson_actions', actions[2]['id'], {'source_refs': [
            {'document_id': 1, 'page': 1, 'quote': 'A different exercise: a) Other work ___.'}]})
    state = engine.state(state['session_id'])
    exercise = state['page_work']['exercise']
    assert exercise['instruction'] == 'Fill in the blanks:'
    assert [p['label'] for p in exercise['items']] == ['A', 'B']
    assert actions[2]['action_id'] not in str(exercise)
    assert state['page_work']['available_count'] == 3  # Optional wider page capture still exists.
    state = event(engine, state, 'open_page_work', {'scope': 'exercise'})
    assert state['page_work']['scope'] == 'exercise'
    assert [p['label'] for p in state['page_work']['items']] == ['A', 'B']
    assert len(state['page_work']['items']) == 2
    assert not engine.db.all('attempts')
    harness.restart()
    restored = service(harness.ctx).state(state['session_id'])
    assert restored['page_work']['instruction'] == 'Fill in the blanks:'
    assert restored['page_work']['items'][1]['label'] == 'B'


@pytest.mark.parametrize('quote', ['Choose an answer: a) One b) Two', 'a) A standalone question',
    'An ordinary sentence about a book.'])
def test_exercise_grouping_does_not_guess_from_option_labels_or_prose(quote):
    assert page_work.exercise_part({'source_refs': [{'quote': quote}]}) is None


def test_six_blanks_use_one_photo_and_one_check_with_six_saved_results(harness, monkeypatch):
    engine, state = page_lesson(harness, monkeypatch)
    root = page_work.candidates(engine, state['session_id'])[0]
    with engine.db.transaction() as tx:
        for index, label in enumerate('ABCDEF', 1):
            aid = root['action_id'] if index == 1 else f'page-item-{index}'
            ref = {'document_id': 1, 'page': 1, 'quote': f'Fill in the blanks: {label.lower()}) Sentence {index} ___.'}
            patch = {'source_refs': [ref], 'activity_order': index * 100, 'prompt': f'Fill part {label}.'}
            existing = tx.get('lesson_actions', f"{state['session_id']}:{aid}")
            if existing:
                tx.update('lesson_actions', existing['id'], patch)
            else:
                values = {k: copy.deepcopy(v) for k, v in root.items() if k not in ('id', 'revision', 'created_at', 'updated_at')}
                tx.insert('lesson_actions', {**values, **patch, 'id': f"{state['session_id']}:{aid}", 'action_id': aid})
    state = event(engine, engine.state(state['session_id']), 'open_page_work', {'scope': 'exercise'})
    ids = [p['activity_id'] for p in state['page_work']['items']]
    assert len(ids) == 6
    calls = []
    def generate(prompt, **kwargs):
        calls.append(prompt)
        if len(calls) == 1:
            return kwargs['schema'].model_validate({'items': [{'item_id': aid, 'text': f'Written {i}', 'uncertain': False} for i, aid in enumerate(ids)]}).model_dump()
        return kwargs['schema'].model_validate({'feedback': 'Checked.', 'items': [{'item_id': aid, 'feedback': 'Matches.', 'result': 'Correct', 'ready_to_continue': True} for aid in ids]}).model_dump()
    monkeypatch.setattr(engine.ctx.ai, 'generate', generate)
    state = event(engine, state, 'submit_page_work', {'page_work_id': state['page_work']['id'], 'evidence_ids': ['page-image']})
    state = event(engine, state, 'confirm_page_work', {'page_work_id': state['page_work']['id'], 'items': [
        {'item_id': p['activity_id'], 'text': p['text']} for p in state['page_work']['items']]})
    assert state['page_work']['status'] == 'completed' and len(calls) == 2
    assert len(engine.db.find('activity_responses', session_id=state['session_id'])) == 6
    assert len(engine.db.find('attempts', session_id=state['session_id'])) == 6
    assert len(engine.db.find('evidence_files', session_id=state['session_id'])) == 1
    state = event(engine, state, 'continue')
    assert state['active_activity'] is None or state['active_activity']['id'] not in ids


def typed_exercise(harness, monkeypatch):
    engine, state = page_lesson(harness, monkeypatch)
    root = page_work.candidates(engine, state['session_id'])[0]
    with engine.db.transaction() as tx:
        for index, label in enumerate('ABCDEF', 1):
            aid = root['action_id'] if index == 1 else f'page-item-{index}'
            values = {k: copy.deepcopy(v) for k, v in root.items() if k not in ('id', 'revision', 'created_at', 'updated_at')}
            prompt = f'Write the accented word in part {label}.'
            values.update(action_id=aid, activity_kind='request_book_work', prompt=prompt, next_prompt=prompt, activity_order=index * 100,
                source_refs=[{'document_id': 1, 'page': 1, 'quote': f'Add the accent: {label.lower()}) word{index}.'}],
                activity_content={'prompt': prompt, 'answer_format': 'text', 'response_modes': ['text', 'photo'], 'evidence_requirement': 'spelling'})
            existing = tx.get('lesson_actions', f"{state['session_id']}:{aid}")
            if existing: tx.update('lesson_actions', existing['id'], values)
            else: tx.insert('lesson_actions', {**values, 'id': f"{state['session_id']}:{aid}", 'action_id': aid})
        tx.update('activity_interactions', state['active_activity']['interaction']['id'], {'status': 'awaiting_work'})
    state = engine.state(state['session_id'])
    return engine, state, state['page_work']['exercise']['items']


def test_six_typed_answers_check_once_without_transcription_or_confirmation_and_replay_after_restart(harness, monkeypatch):
    engine, initial, items = typed_exercise(harness, monkeypatch)
    assert initial['page_work']['exercise']['can_type']
    rows = [{'item_id': item['activity_id'], 'text': text} for item, text in zip(items, ['leão', 'irmã', 'corações', 'coração', 'mãe', 'limões'])]
    calls = []
    def assess(prompt, **kwargs):
        calls.append(prompt)
        assert 'original typed answers' in prompt and not kwargs.get('images')
        responses = harness.ctx.store.find('activity_responses', session_id=initial['session_id'])
        assert len(responses) == 6 and all(r['status'] == 'confirmed' and r['method'] == 'typed' for r in responses)
        assert not harness.ctx.store.all('attempts')
        return kwargs['schema'].model_validate({'feedback': 'Checked.', 'items': [
            {'item_id': r['item_id'], 'feedback': 'The accent is correct.', 'result': 'Correct', 'ready_to_continue': True} for r in rows]}).model_dump()
    monkeypatch.setattr(engine.ctx.ai, 'generate', assess)
    from tests.test_activity_api import ensure_router
    ensure_router(harness)
    response = harness.call('POST', f"/api/tutor/sessions/{initial['session_id']}/activity-events", json={
        'operation_id': 'six-typed-once', 'expected_revision': initial['revision'],
        'activity_id': initial['active_activity']['id'], 'interaction_id': initial['active_activity']['interaction']['id'],
        'type': 'submit_exercise_answers', 'payload': {'items': rows}})
    assert response.status_code == 200, response.text
    state = response.json()
    assert state['page_work']['status'] == 'completed' and state['page_work']['capture_method'] == 'typed'
    assert len(calls) == 1 and len(harness.ctx.store.all('attempts')) == 6
    assert not any(r.get('proposed_text') or r.get('transcription_status') for r in harness.ctx.store.all('activity_responses'))
    assert {r['original']['text'] for r in harness.ctx.store.all('activity_responses')} == {r['text'] for r in rows}
    harness.restart(); engine = service(harness.ctx)
    monkeypatch.setattr(engine.ctx.ai, 'generate', lambda *a, **k: pytest.fail('A lost response cannot purchase another check'))
    state = event(engine, initial, 'submit_exercise_answers', {'items': rows}, operation='six-typed-once')
    assert state['page_work']['status'] == 'completed' and len(harness.ctx.store.all('attempts')) == 6
    state = event(engine, state, 'continue')
    assert state['active_activity'] is None or state['active_activity']['id'] not in {i['activity_id'] for i in items}


@pytest.mark.parametrize('invalid', ['foreign', 'duplicate', 'empty', 'visual'])
def test_invalid_typed_groups_are_atomic_and_cannot_bypass_visual_evidence(harness, monkeypatch, invalid):
    engine, state, items = typed_exercise(harness, monkeypatch)
    rows = [{'item_id': items[0]['activity_id'], 'text': 'mãe'}]
    if invalid == 'foreign': rows[0]['item_id'] = 'different-exercise'
    if invalid == 'duplicate': rows *= 2
    if invalid == 'empty': rows[0]['text'] = ' '
    if invalid == 'visual':
        target = engine._action(engine.db, state['session_id'], items[1]['activity_id'])
        with engine.db.transaction() as tx:
            tx.update('lesson_actions', target['id'], {'activity_content': {**target['activity_content'], 'evidence_requirement': 'diagram', 'response_modes': ['photo']}})
        state = engine.state(state['session_id'])
        assert not state['page_work']['exercise']['can_type']
    with pytest.raises(TutorError): event(engine, state, 'submit_exercise_answers', {'items': rows})
    assert not engine.db.all('activity_responses') and not engine.db.all('attempts') and not engine.db.all('activity_jobs')


def test_partial_typed_batch_preserves_pending_answers_and_shared_retry(harness, monkeypatch):
    engine, state, items = typed_exercise(harness, monkeypatch)
    rows = [{'item_id': i['activity_id'], 'text': 'mãe'} for i in items[:2]]
    monkeypatch.setattr(engine.ctx.ai, 'generate', lambda *a, **k: (_ for _ in ()).throw(ValueError('Provider unavailable')))
    state = event(engine, state, 'submit_exercise_answers', {'items': rows})
    assert state['page_work']['status'] == 'assessment_failed'
    responses = engine.db.all('activity_responses')
    assert len(responses) == 2 and not engine.db.all('attempts')
    with pytest.raises(TutorConflict, match='saved exercise'):
        event(engine, state, 'submit_exercise_answers', {'items': rows})
    calls = []
    def assess(prompt, **kwargs):
        calls.append(prompt)
        return kwargs['schema'].model_validate({'feedback': 'Checked.', 'items': [
            {'item_id': row['item_id'], 'feedback': 'Checked separately.', 'result': 'Correct' if n == 0 else 'Not yet', 'ready_to_continue': n == 0}
            for n, row in enumerate(rows)]}).model_dump()
    monkeypatch.setattr(engine.ctx.ai, 'generate', assess)
    # The existing individual retry also recovers the original batch, not a new per-item purchase.
    state = event(engine, state, 'assess', {'response_id': responses[0]['id']})
    assert state['page_work']['status'] == 'completed' and len(calls) == 1
    assert len(engine.db.all('attempts')) == 2
    assert all(engine._action(engine.db, state['session_id'], i['activity_id'])['status'] == 'pending' for i in items[2:])


def test_shared_transcription_creates_no_attempt_and_survives_restart(harness, monkeypatch):
    engine, state = page_lesson(harness, monkeypatch)
    state, initial = transcribe(engine, state, monkeypatch)
    assert state['page_work']['status'] == 'confirmation'
    assert len(state['page_work']['items']) == 3
    assert state['page_work']['items'][2]['uncertain']
    assert not harness.ctx.store.all('activity_responses') and not harness.ctx.store.all('attempts')
    with pytest.raises(TutorError): event(engine, state, 'confirm_page_work', {'page_work_id': 'another-page', 'items': []})
    harness.restart(); engine = service(harness.ctx)
    monkeypatch.setattr(engine.ctx.ai, 'generate', lambda *a, **k: pytest.fail('Completed transcription must not be purchased twice'))
    replay = event(engine, initial, 'submit_page_work', {'page_work_id': state['page_work']['id'], 'evidence_ids': ['page-image']}, operation='shared-transcription')
    assert replay['page_work']['status'] == 'confirmation'


def test_batch_assessment_records_only_confirmed_answers_and_retries_once(harness, monkeypatch):
    engine, state = page_lesson(harness, monkeypatch)
    state, _ = transcribe(engine, state, monkeypatch)
    db = harness.ctx.store
    items = [{'item_id': item['activity_id'], 'text': item['text']} for item in state['page_work']['items'][:2]]
    items[0]['text'] = 'F'  # A capture amendment, not a learner answer revision.
    calls = []
    def assess(prompt, **kwargs):
        calls.append(prompt)
        return kwargs['schema'].model_validate({'feedback': 'Page checked.', 'items': [{'item_id': row['item_id'],
            'feedback': 'A specific check.', 'result': 'Correct', 'ready_to_continue': True} for row in items]}).model_dump()
    monkeypatch.setattr(engine.ctx.ai, 'generate', assess)
    initial = state
    payload = {'page_work_id': state['page_work']['id'], 'items': items}
    state = event(engine, state, 'confirm_page_work', payload, operation='confirm-page-once')
    assert state['page_work']['status'] == 'completed' and len(calls) == 1
    assert state['active_activity']['status'] == 'answered'
    responses = db.find('activity_responses', session_id=state['session_id'])
    assert len(responses) == 2 and all(r['evidence_ids'] == ['page-image'] for r in responses)
    first = next(r for r in responses if r['activity_id'] == items[0]['item_id'])
    assert first['original']['text'] == 'False' and first['confirmed_text'] == 'F'
    attempts = db.find('attempts', session_id=state['session_id'])
    assert len(attempts) == 2 and all(a['first_result'] == 'Correct' for a in attempts)
    assert db.get('lesson_actions', f"{state['session_id']}:page-item-3")['status'] == 'pending'
    assert len(db.find('evidence_files', session_id=state['session_id'])) == 1
    event(engine, initial, 'confirm_page_work', payload, operation='confirm-page-once')
    assert len(calls) == 1 and len(db.find('attempts', session_id=state['session_id'])) == 2
    state = event(engine, state, 'continue')
    assert state['active_activity']['id'] == 'page-item-3'


def test_wrong_or_ambiguous_response_ids_cannot_be_confirmed(harness, monkeypatch):
    engine, state = page_lesson(harness, monkeypatch)
    state, _ = transcribe(engine, state, monkeypatch)
    for items in ([{'item_id': 'foreign', 'text': 'Something'}], [{'item_id': state['active_activity']['id'], 'text': ''}],
                  [{'item_id': state['active_activity']['id'], 'text': 'A'}] * 2):
        with pytest.raises(TutorError): event(engine, state, 'confirm_page_work', {'page_work_id': state['page_work']['id'], 'items': items})
    assert not harness.ctx.store.all('attempts') and not harness.ctx.store.all('activity_responses')


def test_transcription_failure_keeps_photo_and_retries_original_request(harness, monkeypatch):
    engine, state = page_lesson(harness, monkeypatch)
    state = event(engine, state, 'open_page_work')
    monkeypatch.setattr(engine.ctx.ai, 'generate', lambda *a, **k: (_ for _ in ()).throw(ValueError('Provider unavailable')))
    state = event(engine, state, 'submit_page_work', {'page_work_id': state['page_work']['id'], 'evidence_ids': ['page-image']})
    assert state['page_work']['status'] == 'transcription_failed'
    assert state['page_work']['evidence_ids'] == ['page-image']
    assert not harness.ctx.store.all('attempts')
    ids = [i['activity_id'] for i in state['page_work']['items']]
    monkeypatch.setattr(engine.ctx.ai, 'generate', lambda *a, **k: k['schema'].model_validate({'items': [{'item_id': i, 'text': '', 'uncertain': True} for i in ids]}).model_dump())
    state = event(engine, state, 'retry_page_work', {'page_work_id': state['page_work']['id']})
    assert state['page_work']['status'] == 'confirmation'
    assert not harness.ctx.store.all('attempts')


def test_page_locator_accepts_checked_positions_without_quotes(harness, monkeypatch):
    engine, state = page_lesson(harness, monkeypatch)
    with engine.db.transaction() as tx:
        for action in page_work.candidates(engine, state['session_id']):
            tx.update('lesson_actions', action['id'], {'source_refs': [
                {k: v for k, v in ref.items() if k != 'quote'} for ref in action['source_refs']]})
    assert engine.state(state['session_id'])['page_work']['available_count'] == 3


def test_workbook_page_comes_from_frozen_assignment_and_original_book(harness, monkeypatch):
    from tests.test_workbooks import add_catalog
    engine, state = page_lesson(harness, monkeypatch)
    root = engine._action(engine.db, state['session_id'], state['active_activity']['id'])
    seeded = {'history': engine.db.get('subjects', root['subject_id']), 'genghis': engine.db.get('topics', root['topic_id'])}
    book = add_catalog(harness, seeded)
    with engine.db.transaction() as tx:
        assigned = engine.ctx.books.assign_item(tx, engine._session(state['session_id']), 'exercise-test-0', 'version-test-0')
        action = tx.update('lesson_actions', root['id'], {'assignment_item_id': assigned['id']})
    assert 'document_id' not in assigned['snapshot']
    assert page_work.location(engine, action) == ((book['document_id'], 1),)


def test_shared_photo_must_belong_to_current_learner_session_and_root(harness, monkeypatch):
    engine, state = page_lesson(harness, monkeypatch)
    state = event(engine, state, 'open_page_work')
    db = engine.db
    with db.transaction() as tx:
        other_child = tx.insert('children', {'name': 'Other synthetic learner'})
    for patch in ({'child_id': other_child['id']}, {'session_id': '2026-09-24-genghis'}, {'action_id': 'page-item-2'}):
        original = db.get('evidence_files', 'page-image')
        with db.transaction() as tx: tx.update('evidence_files', 'page-image', patch)
        with pytest.raises(TutorError):
            event(engine, state, 'submit_page_work', {'page_work_id': state['page_work']['id'], 'evidence_ids': ['page-image']})
        with db.transaction() as tx: tx.update('evidence_files', 'page-image', {k: original[k] for k in patch})
    assert not db.all('activity_responses') and not db.all('attempts')


def test_failed_assessment_preserves_confirmed_work_and_frozen_request(harness, monkeypatch):
    engine, state = page_lesson(harness, monkeypatch)
    state, _ = transcribe(engine, state, monkeypatch)
    items = [{'item_id': row['activity_id'], 'text': row['text']} for row in state['page_work']['items'][:2]]
    calls = []
    def fail(prompt, **kwargs):
        calls.append(prompt)
        raise ValueError('Unknown provider outcome')
    monkeypatch.setattr(engine.ctx.ai, 'generate', fail)
    state = event(engine, state, 'confirm_page_work', {'page_work_id': state['page_work']['id'], 'items': items})
    assert state['page_work']['status'] == 'assessment_failed'
    assert len(engine.db.all('activity_responses')) == 2 and not engine.db.all('attempts')
    harness.restart(); engine = service(harness.ctx)
    def recover(prompt, **kwargs):
        assert prompt == calls[0]
        return kwargs['schema'].model_validate({'feedback': 'Checked.', 'items': [
            {'item_id': row['item_id'], 'feedback': 'Checked separately.', 'result': 'Correct', 'ready_to_continue': True}
            for row in items]}).model_dump()
    monkeypatch.setattr(engine.ctx.ai, 'generate', recover)
    state = event(engine, engine.state(state['session_id']), 'retry_page_work', {'page_work_id': state['page_work']['id']})
    assert state['page_work']['status'] == 'completed'
    assert len(engine.db.all('activity_responses')) == len(engine.db.all('attempts')) == 2


def test_wrong_answer_keeps_its_followup_and_assistance_separate(harness, monkeypatch):
    engine, state = page_lesson(harness, monkeypatch)
    root = engine._action(engine.db, state['session_id'], state['active_activity']['id'])
    with engine.db.transaction() as tx: tx.update('lesson_actions', root['id'], {'help_given': 'A hint for the first question.'})
    state, _ = transcribe(engine, engine.state(state['session_id']), monkeypatch)
    original_interaction = state['active_activity']['interaction']['id']
    items = [{'item_id': row['activity_id'], 'text': row['text']} for row in state['page_work']['items'][:2]]
    monkeypatch.setattr(engine.ctx.ai, 'generate', lambda *args, **kwargs: kwargs['schema'].model_validate({
        'feedback': 'Checked.', 'items': [
            {'item_id': items[0]['item_id'], 'result': 'Not yet', 'feedback': 'Try the first statement again.', 'follow_up': 'Look at the tribes.', 'ready_to_continue': False},
            {'item_id': items[1]['item_id'], 'result': 'Correct', 'feedback': 'The second answer is correct.', 'ready_to_continue': True}]}).model_dump())
    state = event(engine, state, 'confirm_page_work', {'page_work_id': state['page_work']['id'], 'items': items})
    assert state['active_activity']['status'] == 'pending'
    assert state['active_activity']['interaction']['id'] != original_interaction
    assert state['active_activity']['interaction']['status'] == 'awaiting_followup'
    attempts = engine.db.all('attempts')
    assisted = next(a for a in attempts if a['question_ref'] == items[0]['item_id'])
    independent = next(a for a in attempts if a['question_ref'] == items[1]['item_id'])
    assert assisted['help_given'] == 'A hint for the first question.' and assisted['independence'] == 'with_help'
    assert not independent['help_given'] and independent['independence'] == 'independent'


def test_individual_retry_after_closing_failed_batch_recovers_shared_purchase(harness,monkeypatch):
    engine,state=page_lesson(harness,monkeypatch)
    state,_=transcribe(engine,state,monkeypatch)
    items=[{'item_id':r['activity_id'],'text':r['text']} for r in state['page_work']['items'][:2]]
    prompts=[]
    def failed(prompt,**kwargs):
        prompts.append(prompt)
        raise ValueError('Unknown provider outcome')
    monkeypatch.setattr(engine.ctx.ai,'generate',failed)
    state=event(engine,state,'confirm_page_work',{'page_work_id':state['page_work']['id'],'items':items})
    job_id=state['page_work']['id']
    response=next(r for r in engine.db.all('activity_responses') if r['activity_id']==state['active_activity']['id'])
    state=event(engine,state,'close_page_work',{'page_work_id':job_id})
    assert 'id' not in state['page_work']
    def recover(prompt,**kwargs):
        assert prompt==prompts[0] and kwargs['schema'].__name__=='WorkbookAssessmentExact'
        return kwargs['schema'].model_validate({'feedback':'Checked.','items':[
            {'item_id':r['item_id'],'result':'Correct','feedback':'Checked this original answer.','ready_to_continue':True} for r in items]}).model_dump()
    monkeypatch.setattr(engine.ctx.ai,'generate',recover)
    state=event(engine,state,'assess',{'response_id':response['id']})
    assert engine.db.get('activity_jobs',job_id)['status']=='completed'
    assert len(engine.db.all('attempts'))==2
    assert not [j for j in engine.db.all('activity_jobs') if j['kind']=='assessment']
