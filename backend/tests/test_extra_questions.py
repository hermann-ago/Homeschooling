"""A subject set to "choices only" keeps the tutor's own questions to selections."""
import pytest
from pydantic import ValidationError

from services.ai_provider import strict_schema
from tutoring import extra_questions, lesson_prompt, page_script

PASSAGE = {'sentences': [{'text': 'Add the same amount to both numbers.'}]}
PAGES = {'pages': [{'document_id': 1, 'page': 1, 'printed_page': 1, 'role': 'assigned_reading'}]}
CONTEXT = {'extra_question_policy': extra_questions.POLICY, 'visual_source': PAGES}


def script(ask, book_format='text'):
    return {'welcome': 'Here is a quick way to subtract.', 'turns': [
        {'type': 'read', 'first': 0, 'last': 0, 'text': None, 'document_id': None, 'page_start': None, 'page_end': None},
        {'type': 'ask', 'prompt': 'Does adding 2 to both numbers change the difference?', **ask},
        {'type': 'book_work', 'document_id': 1, 'page': 1, 'prompt': '1. 36 - 28 =',
         'response': {'format': book_format}, 'answer': '8', 'answer_page': None}],
        'closing': 'Both numbers moved together.'}


@pytest.mark.parametrize('ask', [
    {'purpose': 'reasoning', 'response': {'format': 'text'}},
    {'purpose': 'discussion', 'response': {'format': 'text'}},
    {'purpose': 'retelling', 'response': {'format': 'true_false'}},
    {'purpose': 'discussion', 'response': {'format': 'multiple_select', 'choices': ['A', 'B']}}])
def test_open_tutor_questions_are_rejected(ask):
    with pytest.raises((ValidationError, ValueError), match='true/false or single choice'):
        page_script.compile_script(script(ask), PASSAGE, CONTEXT, 'en-US')


def test_choice_questions_compile_and_book_work_keeps_its_own_format():
    plan = page_script.compile_script(script({'purpose': 'discussion', 'response': {
        'format': 'single_choice', 'choices': ['Yes, it changes', 'No, it stays the same']}}), PASSAGE, CONTEXT, 'en-US')
    ask, book = [s for s in plan['segments'] if s['type'] == 'activity']
    assert ask['activity_kind'] == 'ask_question' and ask['content']['response_modes'] == ['choice']
    assert book['content']['response_modes'] != ['choice']


def test_writer_schema_and_prompt_offer_only_choice_questions():
    value = strict_schema(page_script.schema(PASSAGE, CONTEXT, 'en-US'))
    assert value['$defs']['Ask']['properties']['purpose']['enum'] == ['discussion']
    assert value['$defs']['Ask']['properties']['response']['$ref'] == '#/$defs/BookChoiceResponse'
    assert value['$defs']['BookWork']['properties']['response'].get('$ref') != '#/$defs/BookChoiceResponse'
    passage = {'title': 'Lesson 17', 'sentences': []}
    with_policy = lesson_prompt.writer_prompt(passage, subject='Math', learner='Lucas', grade='4th', language='en-US',
        learner_context=CONTEXT, policy=page_script.VERSION)
    without = lesson_prompt.writer_prompt(passage, subject='Math', learner='Lucas', grade='4th', language='en-US',
        learner_context={}, policy=page_script.VERSION)
    assert 'EXTRA QUESTION POLICY' in with_policy and 'EXTRA QUESTION POLICY' not in without


def test_subject_setting_is_frozen_into_new_preparations(harness):
    from tutoring.lesson_context import preparation
    from tests.test_app_features import seed
    _, subject, document = seed(harness)
    with harness.ctx.store.transaction() as tx:
        topic = tx.insert('topics', {'subject_id': subject['id'], 'title': 'Lesson', 'page_start': 1, 'page_end': 2,
                                     'document_id': document['id']})
    open_context = preparation(harness.ctx, subject['child_id'], topic, {})
    assert not extra_questions.enabled(open_context)
    saved = harness.call('PUT', f"/api/subjects/{subject['id']}", json={'extra_questions': 'choice'})
    assert saved.status_code == 200 and saved.json()['extra_questions'] == 'choice'
    choice_context = preparation(harness.ctx, subject['child_id'], topic, {})
    assert extra_questions.enabled(choice_context)
    assert choice_context['fingerprint'] != open_context['fingerprint']
    assert harness.call('PUT', f"/api/subjects/{subject['id']}", json={'extra_questions': 'essay'}).status_code == 422


def test_live_feedback_in_a_choices_only_lesson_cannot_ask_for_typing(harness, monkeypatch):
    from tests.test_activity_engine import engine_lesson, event, invoke
    from tutoring import interactive
    from tutoring.interactive import BookReadingAssessment
    engine, state, _ = engine_lesson(harness, monkeypatch)
    playback = harness.ctx.store.get('lesson_playback', state['session_id'])
    snapshot = playback['context_snapshot']
    with harness.ctx.store.transaction() as tx:
        tx.update('lesson_playback', playback['id'], {'context_snapshot': {**snapshot,
            'prepared_guide': {**(snapshot.get('prepared_guide') or {}), 'extra_question_policy': extra_questions.POLICY}}})
    calls = []
    def feedback(prompt, images, models, **kwargs):
        calls.append((prompt, kwargs))
        return {'feedback': 'Look at the tens again.', 'result': 'Not yet', 'ready_to_continue': False}
    monkeypatch.setattr(interactive, 'gemini_turn', feedback)
    state = invoke(engine, state, content={'prompt': 'What is 36 - 28?'})
    event(engine, state, 'submit_response', {'response_id': 'choice-lesson', 'text': '18', 'assess_after_save': True})
    prompt, kwargs = calls[-1]
    assert kwargs['schema'] is BookReadingAssessment and 'EXTRA QUESTION POLICY' in prompt
    with pytest.raises(ValidationError):
        BookReadingAssessment.model_validate({'feedback': 'Why?', 'result': 'Not yet', 'follow_up': 'Explain why.'})
