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
