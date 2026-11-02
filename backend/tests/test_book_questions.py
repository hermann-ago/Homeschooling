"""Structured authoring -> source review -> selection -> feedback -> resume."""
import copy

import pytest
from pydantic import ValidationError

from services.ai_provider import strict_schema, validated, InvalidStructuredResponseError
from tutoring import book_questions, page_script
from tutoring.interactive import BookReadingAssessment


def script(response=None, purpose='discussion'):
    return {'welcome': 'Let us enjoy this story.', 'turns': [
        {'type': 'read', 'first': 0, 'last': 0},
        {'type': 'ask', 'prompt': 'Did both people expect to benefit?', 'purpose': purpose,
         'response': response or {'format': 'single_choice', 'choices': ['Yes', 'No']}}],
        'closing': 'We can return to this idea later.'}


PASSAGE = {'sentences': [{'text': 'Both people expected to benefit from the trade.'}]}
CONTEXT = {'book_question_policy': 'book-choice-2'}


@pytest.mark.parametrize('response', [
    {'format': 'single_choice', 'choices': ['Yes', 'No']},
    {'format': 'single_choice', 'choices': ['Both people', 'Neither person', 'Only one person']},
    {'format': 'true_false'}])
def test_book_checks_compile_to_selection_without_reasoning(response):
    schema = page_script.schema(PASSAGE, CONTEXT, 'en-US')
    result = schema.model_validate(script(response)).model_dump()
    plan = page_script.compile_script(result, PASSAGE, CONTEXT, 'en-US')
    question = plan['segments'][2]
    assert question['activity_kind'] == 'ask_question'
    assert question['content']['response_modes'] == ['choice']
    assert question['content']['evidence_requirement'] == 'answer'
    assert not question['content']['require_reasoning']
    assert len(question['content']['choices']) in (2, 3)


@pytest.mark.parametrize('response,purpose', [
    ({'format': 'text'}, 'discussion'),
    ({'format': 'single_choice', 'choices': ['Yes', 'No']}, 'reasoning'),
    ({'format': 'single_choice', 'choices': ['Yes', 'No']}, 'retelling'),
    ({'format': 'multiple_select', 'choices': ['A', 'B']}, 'discussion'),
    ({'format': 'single_choice', 'choices': ['Yes', 'YES']}, 'discussion'),
    ({'format': 'single_choice', 'choices': list('ABCDE')}, 'discussion')])
def test_nonselection_checks_rejected_before_save_but_curriculum_still_accepts_text(response, purpose):
    with pytest.raises(ValidationError):
        page_script.schema(PASSAGE, CONTEXT, 'en-US').model_validate(script(response, purpose))
    page_script.schema(PASSAGE, {}, 'en-US').model_validate(script({'format': 'text'}, 'reasoning'))


def test_provider_schema_restricts_generated_and_printed_checks_in_both_adapters():
    schema = page_script.schema(PASSAGE, CONTEXT, 'pt-BR')
    for value in (strict_schema(schema), schema.google_json_schema()):
        ask = value['$defs']['Ask']['properties']
        assert ask['purpose']['enum'] == ['discussion']
        assert ask['response']['$ref'] == '#/$defs/BookChoiceResponse'
        assert value['$defs']['BookWork']['properties']['response']['$ref'] == '#/$defs/BookChoiceResponse'
    value = script({'format': 'text'})
    import json
    with pytest.raises(InvalidStructuredResponseError):
        validated(json.dumps(value), schema)


@pytest.mark.parametrize('patch', [
    {'follow_up': 'Explain why in your own words.'},
    {'activity_requests': [{'kind': 'tell_it_back', 'content': {'prompt': 'Retell it.'}}]},
    {'activity_requests': [{'kind': 'ask_question', 'content': {'prompt': 'Why?', 'response_modes': ['text']}}]}])
def test_live_feedback_cannot_escape_into_writing(patch):
    with pytest.raises(ValidationError):
        BookReadingAssessment.model_validate({'feedback': 'Think about the trade.', 'result': 'Not yet', **patch})


def test_live_question_can_be_selection_without_extra_explanation():
    result = BookReadingAssessment.model_validate({'feedback': 'Try this choice.', 'result': 'Not yet',
        'activity_requests': [{'kind': 'ask_question', 'content': {'prompt': 'Who expected to benefit?',
            'choices': [{'id': 'both', 'label': 'Both people'}, {'id': 'none', 'label': 'Neither person'}]}}]})
    assert result.activity_requests[0].content.response_modes == ['choice']


def test_printed_book_work_cannot_bypass_selection_policy():
    value = script()
    value['turns'].append({'type': 'book_work', 'document_id': 1, 'page': 1,
        'prompt': 'Write the answer in your book.', 'response': {'format': 'text'}})
    with pytest.raises(ValidationError, match='true/false or single-choice'):
        page_script.schema(PASSAGE, CONTEXT, 'en-US').model_validate(value)
    with pytest.raises(ValueError, match='true/false or single-choice'):
        book_questions.validate_activities([{'kind': 'request_book_work', 'content':
            {'prompt': 'Write it.', 'response_modes': ['text'], 'answer_format': 'text'}}])


def test_prepared_json_review_retry_restart_and_second_reader(harness, monkeypatch):
    from tests.test_library import child
    from tests.pdf_fixture import make_pdf
    from tests.test_activity_engine import event
    from tutoring.script_review import Review
    from tutoring.activity_engine import service
    from tutoring import library_materials, library
    from services.documents import add_drive_document
    from dependencies import select_context
    from fastapi import BackgroundTasks
    from routers.tutor import ReaderGuideRequest, reader_guide
    import hashlib
    h = harness
    first, second = child(h), child(h, 'Future reader')
    data = make_pdf([[PASSAGE['sentences'][0]['text']]])
    path = h.add_file(data, 'Family Library/Books/story.pdf')
    with h.ctx.store.transaction() as tx:
        doc = add_drive_document(tx, path, 'story.pdf', len(data), 1, hashlib.sha256(data).hexdigest())
        tx.update('library_books', 'library-02', {'document_id': doc['id']})
    readings = []
    for kid in (first, second):
        with h.ctx.store.transaction() as tx:
            reading = library.enroll(tx, tx.get('library_books', 'library-02'), kid)
            job = h.ctx.books.begin(tx, reading['subject_id'], path, 'textbook')
        h.ctx.books.process(job['id'])
        readings.append(library.reading_view(h.ctx.store, reading))
    neutral_context = library_materials.neutral_context
    monkeypatch.setattr(library_materials, 'neutral_context', lambda ctx, data:
        {**neutral_context(ctx, data), 'book_question_policy': 'book-choice-2'})
    requests = []

    def generate(prompt, **kwargs):
        schema = kwargs['schema']
        requests.append((prompt, schema))
        if issubclass(schema, Review):
            assert 'BOOK READING QUESTION POLICY' in prompt
            assert '"response_modes": ["choice"]' in prompt
            return {'findings': []}
        assert 'exactly one JSON object' in prompt
        assert 'BOOK READING QUESTION POLICY' in prompt
        return schema.model_validate(script()).model_dump()

    monkeypatch.setattr(h.ctx.ai, 'generate', generate)
    def prepare(kid, reading):
        with select_context(h.ctx):
            return reader_guide(ReaderGuideRequest(learner=kid['id'],
                topic=reading['topics'][0]['id'], prepare_voice=False), BackgroundTasks())
    def book_event(state, kind, payload=None):
        with select_context(h.ctx):
            return event(service(h.ctx), state, kind, payload)
    made = prepare(first, readings[0])
    assert made['script_review']['status'] == 'approved'
    assert len(requests) == 2
    row = h.ctx.store.get('guides', made['guide_id'])
    assert row['context_snapshot']['teaching_script']['script'] == page_script.Script.model_validate(script()).model_dump()
    assert row['context_snapshot']['book_question_policy'] == 'book-choice-2'
    original = copy.deepcopy(row)
    reused = prepare(second, readings[1])
    assert reused['reused_book_material'] and len(requests) == 2
    with select_context(h.ctx), h.ctx.store.transaction() as tx:
        session_id = h.ctx.tutor.interactive.start(tx, first['id'], readings[0]['topics'][0]['id'], made['guide_id'])
    state = book_event(service(h.ctx).state(session_id), 'continue')
    state = book_event(state, 'reading_done')
    state = book_event(state, 'continue')
    choices = state['active_activity']['content']['choices']
    assert state['active_activity']['content']['response_modes'] == ['choice']

    def feedback(prompt, **kwargs):
        assert issubclass(kwargs['schema'], BookReadingAssessment)
        assert 'BOOK READING FEEDBACK POLICY' in prompt
        return {'feedback': 'Think about what each person expected.', 'result': 'Not yet', 'ready_to_continue': False}
    monkeypatch.setattr(h.ctx.ai, 'generate', feedback)
    state = book_event(state, 'submit_response', {'response_id': 'wrong-selection',
        'method': 'choice', 'choice_ids': [choices[1]['id']], 'assess_after_save': True})
    assert state['active_activity']['status'] == 'pending'
    assert state['active_activity']['content']['choices'] == choices
    assert state['active_activity']['interaction']['prompt'] == script()['turns'][1]['prompt']
    h.restart()
    state = service(h.ctx).state(state['session_id'])
    monkeypatch.setattr(h.ctx.ai, 'generate', lambda *a, **k: {'feedback': 'Yes, both expected a benefit.',
        'result': 'Correct', 'ready_to_continue': True})
    state = book_event(state, 'submit_response', {'response_id': 'revised-selection',
        'method': 'choice', 'choice_ids': [choices[0]['id']], 'assess_after_save': True})
    assert state['active_activity']['status'] == 'answered'
    assert all(a['independence'] != 'independent' for a in h.ctx.store.all('attempts'))
    state = book_event(state, 'continue')
    assert state['active_activity']['kind'] == 'close_lesson'
    assert h.ctx.store.get('guides', made['guide_id']) == original
    assert not h.ctx.store.find('tutor_sessions', child_id=second['id'])
    assert library_materials.VERSION == row['context_snapshot']['library_shared_policy']
