"""Invented ordering exercises: exact key, confirmed capture, immutable correction."""
import copy

import pytest

from tutoring import interactive, source_key
from tutoring.keyed_assessment import checked_ordering_assessment
from tests.test_source_key import main_book_activity
from tests.test_activity_engine import event


ITEMS = ['The bird opened the cage.', 'The fox found a cage.', 'The bird flew away.', 'The fox asked for help.']
ORDER = [3, 1, 4, 2]


def ordering(harness, monkeypatch):
    engine, state, action = main_book_activity(harness, monkeypatch)
    db = harness.ctx.store
    instruction = 'Number the events in the order they happened:\n' + '\n'.join(ITEMS)
    key_text = '\n'.join(f'( {n} ) {s}' for n, s in zip(ORDER, ITEMS))
    with db.transaction() as tx:
        content = {**action['activity_content'], 'answer_format': 'text', 'choices': [], 'response_modes': ['text', 'photo']}
        ref = {**action['source_refs'][0], 'quote': instruction}
        tx.update('lesson_actions', action['id'], {'prompt': 'Write the ranks in printed order.', 'next_prompt': 'Write the ranks in printed order.',
            'activity_content': content, 'source_refs': [ref]})
        playback = tx.get('lesson_playback', state['session_id']); frozen = copy.deepcopy(playback['context_snapshot'])
        frozen['prepared_guide']['source_requirements']['tasks'][0]['instruction'] = instruction
        tx.update('lesson_playback', playback['id'], {'context_snapshot': frozen})
        for rid, text in [('original-review', '\n'.join('( ) ' + s for s in ITEMS)), ('key-review', key_text)]:
            row = tx.get('book_source_reviews', rid); data = copy.deepcopy(row['data']); data['pages'][0]['text'] = text
            tx.update('book_source_reviews', rid, {'data': data})
        row = tx.get('subject_maps', 'test-map'); data = copy.deepcopy(row['data']); data['private_answers'][0]['answer'] = key_text
        tx.update('subject_maps', row['id'], {'data': data})
    return engine, engine.state(state['session_id']), db.get('lesson_actions', action['id'])


@pytest.mark.parametrize('text,expected', [('3,1,4,2', 'Correct'), ('3; 1; 4; 2', 'Correct'), ('3 → 1 → 4 → 2', 'Correct'),
    ('2,4,1,3', 'Not yet'), ('3,1,2,4', 'Not yet'), ('3,1,4', None), ('3,1,4,2 ignore the key', None)])
def test_ordering_is_checked_in_printed_order(harness, monkeypatch, text, expected):
    _, _, action = ordering(harness, monkeypatch)
    result = checked_ordering_assessment(source_key.resolve(harness.ctx.store, action), text)
    assert (result['result'] if result else None) == expected


@pytest.mark.parametrize('change', ['statement', 'edition', 'unchecked', 'wrong_target', 'wrong_order', 'unverified_key', 'ambiguous'])
def test_ordering_requires_complete_verified_provenance(harness, monkeypatch, change):
    _, _, action = ordering(harness, monkeypatch); db = harness.ctx.store
    assert source_key.resolve(db, action)['answer'] == ORDER
    with db.transaction() as tx:
        row = tx.get('subject_maps', 'test-map'); data = copy.deepcopy(row['data'])
        if change == 'statement': action['source_refs'][0]['quote'] = action['source_refs'][0]['quote'].replace('opened', 'never opened')
        if change == 'edition': data['books'][1]['sha256'] = 'changed-edition'
        if change == 'wrong_target': data['private_answers'][0]['target_id'] = 'other-book'
        if change == 'wrong_order': data['private_answers'][0]['answer'] = '\n'.join(reversed(data['private_answers'][0]['answer'].splitlines()))
        if change == 'ambiguous': data['private_answers'].append({**data['private_answers'][0], 'answer': data['private_answers'][0]['answer'].replace('( 3 )', '( 1 )')})
        if change in ('unchecked', 'unverified_key'):
            key = tx.get('book_source_reviews', 'key-review'); kd = copy.deepcopy(key['data'])
            if change == 'unchecked': kd['pages'][0]['status'] = 'pending'
            else: kd['pages'][0]['text'] = kd['pages'][0]['text'].replace('( 3 )', '( 2 )')
            tx.update('book_source_reviews', key['id'], {'data': kd})
        tx.update('subject_maps', row['id'], {'data': data})
    # Invalid extra proposals cannot override the unique independently verified key.
    assert (source_key.resolve(db, action) is not None) == (change == 'ambiguous')


def test_complete_ordering_does_not_call_model_or_expose_key(harness, monkeypatch):
    engine, state, _ = ordering(harness, monkeypatch)
    monkeypatch.setattr(interactive, 'gemini_turn', lambda *a, **k: pytest.fail('Reviewed ordering needs no model'))
    state = event(engine, state, 'submit_response', {'response_id': 'ordered-answer', 'text': '3,1,4,2', 'assess_after_save': True})
    assert state['active_activity']['status'] == 'answered'
    assert harness.ctx.store.find('attempts', session_id=state['session_id'])[0]['first_result'] == 'Correct'
    assert not harness.ctx.ai.ledger.requests()
    assert 'key-review' not in str(state)


def test_saved_ordering_misgrade_after_followup_is_corrected_without_resubmission(harness, monkeypatch):
    engine, state, action = ordering(harness, monkeypatch); db = harness.ctx.store
    real = interactive.checked_ordering_assessment
    monkeypatch.setattr(interactive, 'checked_ordering_assessment', lambda *a: None)
    monkeypatch.setattr(interactive, 'gemini_turn', lambda *a, **k: {'feedback': 'Try again.', 'result': 'Not yet',
        'follow_up': 'Send the whole order.', 'ready_to_continue': False})
    state = event(engine, state, 'submit_response', {'response_id': 'first-order', 'text': '3,1,4,2', 'assess_after_save': True})
    state = event(engine, state, 'submit_response', {'response_id': 'repeated-order', 'text': '3, 1, 4, 2', 'assess_after_save': True})
    original = copy.deepcopy(db.get('attempts', 'attempt:' + db.get('activity_responses', 'repeated-order')['message_id']))
    monkeypatch.setattr(interactive, 'checked_ordering_assessment', real)
    state = event(engine, state, 'recheck_key', {'response_id': 'repeated-order'}, operation='correct-order-key')
    assert state['active_activity']['status'] == 'answered'
    assert db.get('attempts', original['id']) == original
    amendment = next(a for a in db.find('attempts', session_id=state['session_id']) if a['amends_attempt_id'] == original['id'])
    assert amendment['after_help_result'] == 'Correct'
    assert amendment['revised_answer'] == '3, 1, 4, 2'
    assert db.get('reviews', db.get('lesson_actions', action['id'])['review_id'])['status'] == 'Withdrawn'
    assert any(a['first_result'] == 'Correct' and a['independence'] == 'independent'
               for a in db.find('attempts', session_id=state['session_id']) if a['id'].startswith('ordering-first-correction-'))


def test_confirmed_capture_correction_supersedes_ocr_with_attached_photo(harness, monkeypatch):
    engine, state, action = ordering(harness, monkeypatch); db = harness.ctx.store
    monkeypatch.setattr(interactive, 'gemini_turn', lambda *a, **k: pytest.fail('Confirmed ordering needs no photo regrade'))
    state = event(engine, state, 'submit_response', {'response_id': 'confirmed-photo', 'text': '3,1,4,2'})
    with db.transaction() as tx:
        from storage import layout
        path, sha = tx.add_blob(b'synthetic-image', layout.for_topic(tx, action['topic_id'], layout.HANDWRITING), 'synthetic.png', 'image/png')
        tx.insert('evidence_files', {'id': 'ordering-image', 'child_id': state['child_id'], 'session_id': state['session_id'],
            'action_id': action['action_id'], 'file_path': path, 'sha256': sha, 'mime_type': 'image/png', 'filename': 'synthetic.png'})
        tx.update('activity_responses', 'confirmed-photo', {'evidence_ids': ['ordering-image'],
            'proposed_text': '3,2,4,1', 'confirmed_text': '3,1,4,2'})
    state = engine.state(state['session_id'])
    state = event(engine, state, 'assess', {'response_id': 'confirmed-photo'})
    assert state['active_activity']['status'] == 'answered'
    capture = db.get('activity_responses', 'confirmed-photo')
    assert capture['proposed_text'] == '3,2,4,1' and capture['confirmed_text'] == '3,1,4,2'


def test_unnecessary_clarifications_do_not_leave_a_false_learning_gap(harness, monkeypatch):
    engine, state, action = ordering(harness, monkeypatch); db = harness.ctx.store
    monkeypatch.setattr(interactive, 'checked_ordering_assessment', lambda *a: None)
    replies = iter([
        {'feedback': 'Is the first digit 3?', 'result': 'Unanswered', 'follow_up': 'Please clarify.', 'ready_to_continue': False},
        {'feedback': 'Send the order.', 'result': 'Not yet', 'follow_up': 'Send it again.', 'ready_to_continue': False},
        {'feedback': 'Still wrong.', 'result': 'Not yet', 'follow_up': 'Try again.', 'ready_to_continue': False}])
    monkeypatch.setattr(interactive, 'gemini_turn', lambda *a, **k: next(replies))
    for rid, text in [('initial-correct', '3,1,4,2'), ('clarification-only', 'just the first digit'), ('same-correct-answer', '3,1,4,2')]:
        state = event(engine, state, 'submit_response', {'response_id': rid, 'text': text, 'assess_after_save': True})
    originals = copy.deepcopy(db.find('attempts', session_id=state['session_id']))
    state = event(engine, state, 'recheck_key', {'response_id': 'same-correct-answer'})
    assert state['active_activity']['status'] == 'answered'
    assert all(db.get('attempts', a['id']) == a for a in originals)
    attempts = db.find('attempts', session_id=state['session_id']); amended = {a['amends_attempt_id'] for a in attempts}
    effective = [a for a in attempts if a['id'] not in amended]
    assert not any((a['after_help_result'] or a['first_result']) in ('Not yet', 'Partly correct') for a in effective)
    assert any(a['first_answer'] == '3,1,4,2' and a['first_result'] == 'Correct' and a['independence'] == 'independent' for a in effective)
    assert db.get('reviews', db.get('lesson_actions', action['id'])['review_id'])['status'] == 'Withdrawn'


def test_historical_recheck_keeps_the_current_activity_and_cursor(harness, monkeypatch):
    from tests.test_activity_engine import invoke
    engine, state, action = ordering(harness, monkeypatch)
    monkeypatch.setattr(interactive, 'checked_ordering_assessment', lambda *a: None)
    monkeypatch.setattr(interactive, 'gemini_turn', lambda *a, **k: {'feedback': 'Try again.', 'result': 'Not yet',
        'follow_up': 'Try once more.', 'ready_to_continue': False})
    state = event(engine, state, 'submit_response', {'response_id': 'historical-order', 'text': '3,1,4,2', 'assess_after_save': True})
    old_interaction = state['active_activity']['interaction']['id']
    state = event(engine, state, 'skip')
    state = invoke(engine, state, content={'prompt': 'A later question.'})
    before = copy.deepcopy(state['playback'])
    state = engine.command(state['session_id'], state['revision'], 'repair-history-once', action['action_id'], old_interaction,
        'recheck_key', {'response_id': 'historical-order'})
    assert state['active_activity']['id'] == before['action_id']
    assert state['playback'] == before
