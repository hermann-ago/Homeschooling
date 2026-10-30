"""Invented source statements/keys: preserve qualifiers and private provenance."""
import copy
import json

import pytest

from tutoring import interactive, source_key
from tutoring.keyed_assessment import checked_binary_assessment
from tests.test_activity_engine import engine_lesson, invoke, event


STATEMENT = 'The fox escaped from the trap immediately.'


def main_book_activity(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state, content={'prompt': STATEMENT, 'answer_format': 'true_false',
        'choices': [{'id': 'true', 'label': 'True'}, {'id': 'false', 'label': 'False'}],
        'response_modes': ['choice', 'text']})
    db = harness.ctx.store
    action = db.get('lesson_actions', f"{state['session_id']}:{state['active_activity']['id']}")
    session = db.get('tutor_sessions', state['session_id'])
    topic = db.get('topics', session['topic_id'])
    doc = db.get('documents', topic['document_id'])
    ref = {'document_id': doc['id'], 'page': 2, 'quote': 'True or false:\n' + STATEMENT}
    with db.transaction() as tx:
        keydoc = tx.insert('documents', {'original_filename': 'Invented key.pdf', 'page_count': 1, 'sha256': 'key-sha'})
        tx.insert('book_collections', {'id': 'source-test', 'name': 'Invented sources'})
        tx.insert('subject_collections', {'id': 'test-binding', 'collection_id': 'source-test', 'subject_id': session['subject_id']})
        tx.insert('collection_versions', {'id': 'test-version', 'collection_id': 'source-test', 'number': 1, 'fingerprint': 'test', 'manifest': {}})
        tx.insert('collection_analysis_jobs', {'id': 'test-analysis', 'collection_id': 'source-test', 'version_id': 'test-version',
            'subject_id': session['subject_id'], 'status': 'completed', 'plan': {}})
        for rid, sha, content_hash, text, role in [
                ('original-review', doc['sha256'], 'original-content', '(    ) ' + STATEMENT, 'combined'),
                ('key-review', 'key-sha', 'key-content', '( F ) ' + STATEMENT, 'answer_key')]:
            tx.insert('book_source_reviews', {'id': rid, 'sha256': sha, 'role': role, 'version': 1,
                'content_sha256': content_hash, 'note': 'Checked synthetic pages.', 'data': {'source': {'language': 'en'}, 'pages': [
                    {'page': 1 if role == 'answer_key' else 2, 'status': 'checked', 'issues': [], 'text': text}]}})
        tx.insert('subject_maps', {'id': 'test-map', 'collection_id': 'source-test', 'version_id': 'test-version', 'job_id': 'test-analysis',
            'data': {'books': [{'id': 'main', 'document_id': doc['id'], 'sha256': doc['sha256']},
                {'id': 'key', 'document_id': keydoc['id'], 'sha256': 'key-sha', 'role': 'answer_key', 'answer_for_id': 'main'}],
                'source_review_ids': {'main': 'original-review', 'key': 'key-review'},
                'source_companion_hashes': {str(doc['id']): 'original-content', str(keydoc['id']): 'key-content'},
                'private_answers': [{'source_id': 'key', 'target_id': 'main', 'answer': '( F ) ' + STATEMENT, 'pages': [1]}]}})
        playback = tx.get('lesson_playback', state['session_id'])
        frozen = copy.deepcopy(playback['context_snapshot'])
        frozen['prepared_guide'].update(learning_memory={'map_id': 'test-map'},
            source_requirements={'tasks': [{'document_id': doc['id'], 'page': 2, 'instruction': ref['quote']}]},
            visual_source={'pages': [{'document_id': doc['id'], 'document_sha256': doc['sha256'], 'page': 2}]})
        tx.update('lesson_playback', playback['id'], {'context_snapshot': frozen})
        tx.update('lesson_actions', action['id'], {'origin': 'required_book', 'source_refs': [ref]})
    return engine, engine.state(state['session_id']), db.get('lesson_actions', action['id'])


@pytest.mark.parametrize('answer', ['F', 'Falso', 'false'])
def test_main_book_exact_key_is_frozen_private_and_no_model_is_called(harness, monkeypatch, answer):
    engine, state, action = main_book_activity(harness, monkeypatch)
    monkeypatch.setattr(interactive, 'gemini_turn', lambda *a, **k: pytest.fail('A literal checked key needs no AI'))
    result = event(engine, state, 'submit_response', {'response_id': 'source-answer', 'text': answer, 'assess_after_save': True})
    assert result['active_activity']['status'] == 'answered'
    assert harness.ctx.store.find('attempts', session_id=state['session_id'])[0]['first_result'] == 'Correct'
    job = next(j for j in harness.ctx.store.find('activity_jobs', response_id='source-answer') if j['kind'] == 'assessment')
    frozen = job['input_snapshot']['assessment_request']
    assert frozen['source_key']['answer'] == 'false'
    assert 'immediately' in frozen['prompt'] and 'Exact source-bound original' in frozen['prompt']
    assert all(secret not in json.dumps(result, default=str) for secret in ['key-sha', 'key-content', 'key-review', 'literal-key-'])
    # A later source edit cannot change the assessment purchased/saved for this response.
    with harness.ctx.store.transaction() as tx:
        keydoc = tx.get('documents', frozen['source_key']['answer_source']['document_id'])
        tx.update('documents', keydoc['id'], {'sha256': 'a-new-edition'})
    message = harness.ctx.store.get('lesson_dialogue', harness.ctx.store.get('activity_responses', 'source-answer')['message_id'])
    assert source_key.resolve(harness.ctx.store, action) is None
    assert source_key.for_message(harness.ctx.store, action, message) == frozen['source_key']


@pytest.mark.parametrize('change', ['qualifier', 'other_target', 'key_edition', 'source_edition', 'unchecked', 'disputed', 'ambiguous', 'other_subject', 'unbound_quote'])
def test_unverified_or_wrong_source_cannot_supply_a_key(harness, monkeypatch, change):
    _, _, action = main_book_activity(harness, monkeypatch)
    db = harness.ctx.store
    assert source_key.resolve(db, action)['answer'] == 'false'
    with db.transaction() as tx:
        row = tx.get('subject_maps', 'test-map'); data = copy.deepcopy(row['data'])
        if change == 'qualifier': action['prompt'] = STATEMENT.replace(' immediately', '')
        if change == 'other_target': data['private_answers'][0]['target_id'] = 'another-book'
        if change == 'key_edition': data['books'][1]['sha256'] = 'other-key-edition'
        if change == 'source_edition': data['books'][0]['sha256'] = 'other-textbook-edition'
        if change == 'disputed': data['private_answers'][0]['issue'] = 'Disputed key'
        if change == 'ambiguous': data['private_answers'][0]['answer'] += '\n( V ) ' + STATEMENT
        if change == 'unchecked':
            review = tx.get('book_source_reviews', 'key-review'); edited = copy.deepcopy(review['data'])
            edited['pages'][0]['status'] = 'pending'; tx.update('book_source_reviews', review['id'], {'data': edited})
        if change == 'other_subject': tx.delete('subject_collections', 'test-binding')
        if change == 'unbound_quote': action['source_refs'][0]['quote'] = 'Another source quotation'
        tx.update('subject_maps', row['id'], {'data': data})
    assert source_key.resolve(db, action) is None


def test_saved_teacher_error_can_be_amended_once_without_revising_child_answer(harness, monkeypatch):
    engine, state, action = main_book_activity(harness, monkeypatch)
    # Simulate an old response graded without the new literal check.
    monkeypatch.setattr(interactive, 'checked_binary_assessment', lambda *a: None)
    monkeypatch.setattr(interactive, 'gemini_turn', lambda *a, **k: {'feedback': 'It escaped, so it is true.',
        'result': 'Not yet', 'help': 'It escaped.', 'follow_up': 'Try again.', 'ready_to_continue': False})
    state = event(engine, state, 'submit_response', {'response_id': 'wrong-old-grade', 'text': 'F', 'assess_after_save': True})
    db = harness.ctx.store
    original = db.find('attempts', session_id=state['session_id'])[0]
    capture = db.get('activity_responses', 'wrong-old-grade')
    assert state['active_activity']['responses'][0]['key_recheck_available']
    request = {'operation_id': 'repair-book-key-once', 'expected_revision': state['revision'],
        'activity_id': state['active_activity']['id'], 'interaction_id': state['active_activity']['interaction']['id'],
        'type': 'recheck_key', 'payload': {'response_id': capture['id']}}
    url = f"/api/tutor/sessions/{state['session_id']}/activity-events"
    result = harness.call('POST', url, json=request)
    assert result.status_code == 200, result.text
    assert result.json()['active_activity']['status'] == 'answered'
    assert db.get('attempts', original['id']) == original
    assert db.get('activity_responses', capture['id']) == capture
    attempts = db.find('attempts', session_id=state['session_id'])
    assert len(attempts) == 2
    amended = next(a for a in attempts if a.get('amends_attempt_id'))
    assert amended['first_result'] == 'Correct' and amended['first_answer'] == 'F'
    assert amended['independence'] == 'independent'
    assert db.get('reviews', db.get('lesson_actions', action['id'])['review_id'])['status'] == 'Withdrawn'
    harness.restart()
    assert harness.call('POST', url, json=request).status_code == 200
    assert len(harness.ctx.store.find('attempts', session_id=state['session_id'])) == 2


@pytest.mark.parametrize('introduction', ['', 'Decide whether the statement is true or false.\n'])
def test_complete_original_statement_survives_followup_prompt(harness, monkeypatch, introduction):
    engine, state, action = main_book_activity(harness, monkeypatch)
    action['prompt'] = introduction + STATEMENT
    action['next_prompt'] = 'Did the fox escape?'
    message = {'id': 'preview-only', 'text': 'F', 'evidence_ids': []}
    prompt, _, _ = engine.tutor.interactive._prompt(engine._session(state['session_id']), action, message)
    assert json.dumps(source_key.original_refs(action), ensure_ascii=False) in prompt
    assert STATEMENT in prompt and 'immediately' in prompt
    assert not checked_binary_assessment({**source_key.resolve(harness.ctx.store, action), 'require_reasoning': True}, 'F')
