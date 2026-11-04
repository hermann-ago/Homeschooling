"""Extra questions stay one deep, and photo answers are read from the photo, as written."""
from tests.test_activity_engine import engine_lesson, event, invoke
from tests.test_try_first import NOT_YET, RIGHT, answers


def extra(prompt):
    return {'kind': 'ask_question', 'content': {'prompt': prompt, 'response_modes': ['choice'], 'answer_format': 'single_choice',
            'choices': [{'id': 'a', 'label': 'At the river'}, {'id': 'b', 'label': 'At home'}]}}


def adaptive(harness, state):
    return [a for a in harness.ctx.store.find('lesson_actions', session_id=state['session_id']) if a.get('origin') == 'adaptive' and a.get('parent_activity_id')]


def test_a_missed_extra_question_does_not_add_another_and_the_exercise_gets_one_at_most(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = event(engine, state, 'try_first')
    answers(monkeypatch, {**NOT_YET, 'activity_requests': [extra('Where did they stop?')]},
            {**NOT_YET, 'activity_requests': [extra('Which place was by the water?')]}, RIGHT,
            {**NOT_YET, 'activity_requests': [extra('Where was the camp?')]})
    state = event(engine, state, 'submit_response', {'response_id': 'first', 'text': 'A guess', 'assess_after_save': True})
    child = state['active_activity']
    assert child['parent_activity_id'] == 'action-1' and len(adaptive(harness, state)) == 1
    # A miss on the extra question: the same question again, with feedback, not a question about it.
    state = event(engine, state, 'submit_response', {'response_id': 'second', 'method': 'choice', 'choice_ids': ['b'], 'assess_after_save': True})
    assert state['active_activity']['id'] == child['id'] and len(adaptive(harness, state)) == 1
    state = event(engine, state, 'submit_response', {'response_id': 'third', 'method': 'choice', 'choice_ids': ['a'], 'assess_after_save': True})
    state = event(engine, state, 'continue')
    assert state['active_activity']['id'] == 'action-1'
    # A second miss on the exercise keeps it, without a second extra question.
    state = event(engine, state, 'submit_response', {'response_id': 'fourth', 'text': 'Still a guess', 'assess_after_save': True})
    assert state['active_activity']['id'] == 'action-1' and len(adaptive(harness, state)) == 1


def test_an_extra_question_repeating_the_exercise_is_not_added(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = event(engine, state, 'try_first')
    own = harness.ctx.store.get('lesson_actions', f"{state['session_id']}:action-1")['prompt']
    answers(monkeypatch, {**NOT_YET, 'activity_requests': [extra(own.split('. ', 1)[-1].upper())]})
    state = event(engine, state, 'submit_response', {'response_id': 'first', 'text': 'A guess', 'assess_after_save': True})
    assert state['active_activity']['id'] == 'action-1' and not adaptive(harness, state)
    assert state['active_activity']['interaction']['status'] == 'awaiting_followup'


def photo_lesson(harness, monkeypatch, content):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state, content=content)
    active = state['active_activity']
    with harness.ctx.store.transaction() as tx:
        harness.ctx.tutor.evidence(tx, state['session_id'], state['revision'], 'work.png', b'not-a-real-image', 'image/png', None, active['id'])
    evidence = harness.ctx.store.find('evidence_files', session_id=state['session_id'])[0]
    return engine, engine.state(state['session_id']), evidence


def test_a_photo_is_read_even_when_boxes_were_typed_before_switching(harness, monkeypatch):
    engine, state, evidence = photo_lesson(harness, monkeypatch, {'prompt': 'Complete: __umor, __orta', 'response_modes': ['text', 'photo'],
        'blanks': [{'id': 'blank-1', 'label': '__umor:'}, {'id': 'blank-2', 'label': '__orta:'}]})
    with harness.ctx.ai.reading_handwriting():
        careful = harness.ctx.ai.selection()
    seen = []
    def read(prompt, **kwargs):
        seen.append((prompt, harness.ctx.ai.selection()))
        return {'text': 'homen\nhorta', 'uncertain': False}
    monkeypatch.setattr(harness.ctx.ai, 'generate', read)
    state = event(engine, state, 'submit_response', {'response_id': 'photo', 'method': 'photo', 'evidence_ids': [evidence['id']],
        'blanks': {'blank-1': 'hu'}, 'text': '__umor: hu\n__orta:'})
    response = harness.ctx.store.get('activity_responses', 'photo')
    assert response['original']['text'] == '' and response['proposed_text'] == 'homen\nhorta'
    # Read by the careful model, told that printed words beside a blank never fix the handwriting.
    (prompt, model), = seen
    assert model == careful and 'character by character' in prompt and 'misspellings' in prompt
