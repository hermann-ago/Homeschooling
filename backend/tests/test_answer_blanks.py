"""One answer box per printed problem, checked against the pinned key without the AI."""
import pytest

from tutoring import page_script
from tutoring.keyed_assessment import checked_blanks_assessment

BOXES = [{'id': 'blank-1', 'label': '58 - 27 ='}, {'id': 'blank-2', 'label': '92 - 61 ='},
         {'id': 'blank-3', 'label': '65 - 18 ='}]


def test_numbers_compare_by_value_and_wrong_boxes_are_named():
    right = checked_blanks_assessment(BOXES, ['31', '31', '47'], {'blank-1': '31', 'blank-2': ' 31. ', 'blank-3': '47'})
    assert right['result'] == 'Correct' and right['ready_to_continue'] and right['feedback'] == 'All 3 correct!'
    partly = checked_blanks_assessment(BOXES, ['31', '31', '47'], {'blank-1': '31', 'blank-2': '30', 'blank-3': 'cat'})
    assert partly['result'] == 'Partly correct' and not partly['ready_to_continue'] and partly['follow_up'] is None
    assert partly['blank_results'] == {'blank-1': True, 'blank-2': False, 'blank-3': False}
    assert '92 - 61 =' in partly['feedback'] and '65 - 18 =' in partly['feedback'] and '31' not in partly['feedback']


@pytest.mark.parametrize('expected,given,correct', [
    ('1,250', '1250', True), ('1/2', '2/4', True), ('0.5', '1/2', True), ('−3', '-3', True),
    ('Hexagon', 'hexagon.', True), ('49', '94', False)])
def test_equivalent_short_answers(expected, given, correct):
    box = [{'id': 'b', 'label': 'x'}]
    assert checked_blanks_assessment(box, [expected], {'b': given})['blank_results'] == {'b': correct}


@pytest.mark.parametrize('expected,given', [('square, triangle', 'triangle and square'), ('Answers may vary', 'Add to Both')])
def test_unclear_word_answers_are_left_to_the_tutor(expected, given):
    assert checked_blanks_assessment([{'id': 'b', 'label': 'x'}], [expected], {'b': given}) is None


def test_portuguese_feedback():
    result = checked_blanks_assessment(BOXES[:1], ['31'], {'blank-1': '30'}, 'pt-BR')
    assert result['feedback'].startswith('0 de 1 certas')


PASSAGE = {'sentences': [{'text': 'Subtract the tens, then the ones.'}]}
PAGES = {'pages': [{'document_id': 1, 'page': 1, 'printed_page': 53, 'role': 'assigned_reading', 'book_name': 'Math 4'}]}


def script(**work):
    return {'welcome': 'Mental math today.', 'turns': [
        {'type': 'read', 'first': 0, 'last': 0},
        {'type': 'book_work', 'document_id': 1, 'page': 1, 'prompt': '1. Use Number Line Hopping.',
         'response': {'format': 'blanks', 'blanks': ['58 - 27 =', '92 - 61 =']}, 'answer': '31; 31',
         'answer_page': 20, **work}], 'closing': 'Well done.'}


def test_blanks_compile_to_labelled_boxes_without_their_answers():
    plan = page_script.compile_script(script(answers=['31', '31']), PASSAGE, {'visual_source': PAGES}, 'en-US')
    work = [s for s in plan['segments'] if s['type'] == 'activity'][0]
    assert work['content']['blanks'] == [{'id': 'blank-1', 'label': '58 - 27 ='}, {'id': 'blank-2', 'label': '92 - 61 ='}]
    assert work['content']['response_modes'] == ['text', 'photo']
    assert '31' not in str(work['content'])
    with pytest.raises(ValueError, match='one short key answer per blank'):
        page_script.compile_script(script(answers=['31']), PASSAGE, {'visual_source': PAGES}, 'en-US')


def test_typed_boxes_are_checked_instantly_and_retry_keeps_the_boxes(harness, monkeypatch):
    from tests.test_activity_engine import engine_lesson, event, invoke
    from tutoring import interactive
    engine, state, _ = engine_lesson(harness, monkeypatch)
    monkeypatch.setattr(interactive, 'gemini_turn', lambda *a, **k: pytest.fail('the AI was asked to check a keyed answer'))
    monkeypatch.setattr(page_script, 'answer_for', lambda ctx, action: {'answer_key': '31; 31', 'answer_items': ['31', '31']})
    state = invoke(engine, state, kind='request_book_work', content={'prompt': '1. Use Number Line Hopping.',
        'response_modes': ['text', 'photo'], 'blanks': BOXES[:2], 'book_name': 'Math 4', 'printed_page': '53'})
    assert state['active_activity']['interaction']['status'] == 'awaiting_input'  # no "finished writing in my book" step
    with pytest.raises(Exception, match='Fill in every answer box'):
        event(engine, state, 'submit_response', {'response_id': 'half', 'blanks': {'blank-1': '31'}, 'assess_after_save': True})
    state = event(engine, state, 'submit_response', {'response_id': 'first-try',
        'blanks': {'blank-1': '31', 'blank-2': '30'}, 'assess_after_save': True})
    active = state['active_activity']
    assert active['status'] == 'pending' and active['content']['blanks'] == BOXES[:2]
    assert active['responses'][0]['blank_results'] == {'blank-1': True, 'blank-2': False}
    assert active['responses'][0]['original']['text'] == '58 - 27 = 31\n92 - 61 = 30'
    state = event(engine, state, 'submit_response', {'response_id': 'second-try',
        'blanks': {'blank-1': '31', 'blank-2': '31'}, 'assess_after_save': True})
    assert state['active_activity']['status'] == 'answered'


def test_a_correct_finished_answer_gets_no_extra_question(harness, monkeypatch):
    from tests.test_activity_engine import engine_lesson, event, invoke
    from tutoring import interactive
    engine, state, _ = engine_lesson(harness, monkeypatch)
    extra = {'kind': 'ask_question', 'content': {'prompt': 'Which choice explains why?', 'response_modes': ['choice', 'text'],
             'answer_format': 'single_choice', 'choices': [{'id': 'a', 'label': 'Same gap'}, {'id': 'b', 'label': 'Bigger gap'}]}}
    monkeypatch.setattr(interactive, 'gemini_turn', lambda *a, **k: {'feedback': 'Exactly right.', 'result': 'Correct',
        'ready_to_continue': True, 'follow_up': 'Why?', 'activity_requests': [extra]})
    state = invoke(engine, state, content={'prompt': 'Why does the gap stay the same?'})
    asked = state['active_activity']['id']
    state = event(engine, state, 'submit_response', {'response_id': 'right', 'text': 'Both moved 2.', 'assess_after_save': True})
    assert state['active_activity']['id'] == asked and state['active_activity']['status'] == 'answered'
    assert not [a for a in harness.ctx.store.find('lesson_actions', session_id=state['session_id']) if 'Which choice' in (a['prompt'] or '')]
