"""The book pages are attached to a grading request only when they are needed."""
from tutoring import capture_policy, interactive, page_script
from tests.test_activity_engine import engine_lesson, event, invoke


def settled(monkeypatch, key, requirement='answer', **kwargs):
    monkeypatch.setattr(page_script, 'answer_for', lambda ctx, action: key)
    monkeypatch.setattr(capture_policy, 'activity_content', lambda ctx, action: {'evidence_requirement': requirement})
    return interactive.settled_answer(None, {}, kwargs.get('capture', {}), kwargs.get('images', []))


def test_a_typed_answer_with_a_settled_key_needs_no_pages(monkeypatch):
    assert settled(monkeypatch, {'answer_key': '1,820'})
    assert settled(monkeypatch, {'answer_key': 'leão'}, 'spelling')
    assert not settled(monkeypatch, None)  # no key: the pages carry the answer
    assert not settled(monkeypatch, {'answer_key': '1,820'}, images=[(b'photo', 'image/jpeg')])
    assert not settled(monkeypatch, {'answer_key': '1,820'}, capture={'evidence_ids': ['photo-1']})
    assert not settled(monkeypatch, {'answer_key': 'a neat T'}, 'handwriting')


def test_the_grader_is_asked_again_with_the_pages_when_it_cannot_decide_without_them(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state)
    monkeypatch.setattr(interactive, 'settled_answer', lambda *args: True)
    replies = [{'feedback': 'I cannot tell from this.', 'result': 'Source disputed', 'ready_to_continue': False},
               {'feedback': 'Yes.', 'result': 'Correct', 'ready_to_continue': True}]
    calls = []
    monkeypatch.setattr(interactive, 'gemini_turn', lambda *args, **kwargs: calls.append(kwargs) or replies[len(calls) - 1])
    state = event(engine, state, 'submit_response', {'response_id': 'answer', 'text': 'He united the tribes.'})
    state = event(engine, state, 'assess', {'response_id': 'answer'})
    assert len(calls) == 2 and state['active_activity']['messages'][-1]['text'] == 'Yes.'


def test_a_chat_question_is_answered_from_the_lesson_text_and_gets_the_pages_only_when_needed(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state)
    assert interactive.settled_answer(harness.ctx, {'kind': 'question'}, {}, [])
    assert not interactive.settled_answer(harness.ctx, {'kind': 'question'}, {}, [(b'photo', 'image/jpeg')])
    prompts = []
    def grader(prompt, *args, **kwargs):
        prompts.append(prompt)
        return {'feedback': 'A tribe is a community.', 'result': 'Unanswered', 'ready_to_continue': True}
    monkeypatch.setattr(interactive, 'gemini_turn', grader)
    state = event(engine, state, 'request_followup', {'prompt': 'What does tribe mean?'})
    assert len(prompts) == 1 and interactive.WITHOUT_PAGES in prompts[0]
    # A question about a picture on the page is asked again with the pages.
    replies = iter([{'feedback': 'Let me look at the page.', 'result': 'Source disputed', 'ready_to_continue': False},
                    {'feedback': 'The map shows the steppe.', 'result': 'Unanswered', 'ready_to_continue': True}])
    prompts.clear()
    monkeypatch.setattr(interactive, 'gemini_turn', lambda prompt, *a, **k: prompts.append(prompt) or next(replies))
    state = event(engine, engine.state(state['session_id']), 'request_followup', {'prompt': 'What does the map show?'})
    assert len(prompts) == 2 and interactive.WITHOUT_PAGES not in prompts[1]
    assert state['active_activity']['messages'][-1]['text'] == 'The map shows the steppe.'
