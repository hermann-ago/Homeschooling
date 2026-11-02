import pytest
from tutoring import book_questions, guide, lesson_quality, page_script


def test_explanations_have_no_numeric_quota_for_short_or_long_readings():
    context = {'book_teaching_policy': page_script.BOOK_TEACHING_POLICY}
    for words in (3, 330):
        passage = {'sentences': [{'text': 'Source ' * words}]}
        script = {'welcome': 'Let us begin.', 'turns': [{'type': 'read', 'first': 0, 'last': 0}], 'closing': 'We can return to the idea.'}
        page_script.compile_script(script, passage, context, 'en-US')
        script['turns'].append({'type': 'say', 'text': 'A brief useful link.'})
        page_script.compile_script(script, passage, context, 'en-US')


def test_teaching_breaks_survive_compilation_without_changing_or_reordering_source():
    source = ['The lake had many fish.', 'Many people caught fish every day.', 'Fewer fish remained to grow.']
    passage = {'sentences': [{'text': text} for text in source]}
    script = {'welcome': 'Let us read about the lake.', 'turns': [
        {'type': 'read', 'first': 0, 'last': 1},
        {'type': 'say', 'text': 'A shared resource is something several people can use. Imagine a jar of pencils in a classroom: taking a pencil changes what is available to the next person.'},
        {'type': 'read', 'first': 2, 'last': 2},
        {'type': 'say', 'text': 'Notice the link between catching fish now and the stock of fish left for later.'}],
        'closing': 'We followed what changed in the lake.'}
    plan = page_script.compile_script(script, passage, {}, 'en-US')
    plan = lesson_quality.coherent_readings(plan)
    built = guide.build(passage['sentences'], plan, faithful=True, instruction_only=True)
    assert [s['text'] for s in built['sentences'] if s['kind'] == 'book'] == source
    assert [a['kind'] for a in built['activities']] == ['introduce', 'read_source', 'explain_or_observe', 'read_source', 'explain_or_observe', 'close_lesson']
    summary = page_script.teaching_summary(script, passage)
    assert summary['explanations'] == 2 and summary['between_readings'] == 1


@pytest.mark.parametrize('source', [
    'The traveller shared a meal.\n\nFor reflection\n\nWhat does generosity mean?',
    'Water evaporates and later condenses.\n\nThink about it: Where might the water go?',
    'The stars shine above the sea.\n\nWhat images stay with you?',
])
def test_any_genre_can_read_printed_questions_without_assessment(source):
    # The reading-only policy (book-read-along-3) that earlier chapters keep.
    context = {'book_question_policy': 'book-read-along-3',
        'visual_source': {'pages': [{'document_id': 1, 'page': 1, 'role': 'assigned_reading'}]}}
    passage = {'sentences': [{'text': source}]}
    value = {'welcome': 'Let us read.', 'turns': [{'type': 'read', 'text': source,
        'document_id': 1, 'page_start': 1, 'page_end': 1}], 'closing': 'That is our reading for today.'}
    assigned = page_script.schema(passage, context, 'en-US')
    for schema in (assigned.provider_json_schema(), assigned.google_json_schema()):
        assert schema['properties']['turns']['items']['anyOf'] == [
            {'$ref': '#/$defs/Say'}, {'$ref': '#/$defs/Read'}]
    plan = page_script.compile_script(assigned.model_validate(value).model_dump(), passage, context, 'en-US')
    assert [s['type'] for s in plan['segments']] == ['intro', 'read', 'recap']
    assert plan['segments'][1]['text'] == source
    built = guide.build(passage['sentences'], plan, faithful=True, instruction_only=True)
    assert not any(a['kind'] in ('ask_question', 'request_book_work') for a in built['activities'])
    assert '?' in next(a['content']['text'] for a in built['activities'] if a['kind'] == 'read_source')
    book_questions.validate_activities(built['activities'], context)
    for kind in ('ask', 'book_work'):
        bad = {**value, 'turns': [*value['turns'], ({'type': 'ask', 'prompt': 'What happened?',
            'purpose': 'discussion', 'response': {'format': 'true_false'}} if kind == 'ask' else
            {'type': 'book_work', 'document_id': 1, 'page': 1, 'prompt': 'Write it.', 'response': {'format': 'text'}})]}
        with pytest.raises(ValueError, match='without requiring answers'):
            assigned.model_validate(bad)
    with pytest.raises(ValueError, match='without requiring answers'):
        book_questions.validate_activities([{'kind': 'ask_question', 'content': {
            'choices': [{'label': 'Yes'}, {'label': 'No'}], 'answer_format': 'single_choice', 'response_modes': ['choice']}}], context)


def test_read_along_chapters_end_with_a_short_choice_quiz():
    context = {'book_question_policy': book_questions.VERSION,
        'visual_source': {'pages': [{'document_id': 1, 'page': 1, 'role': 'assigned_reading'}]}}
    source = 'The traveller shared a meal.\n\nFor reflection\n\nWhat does generosity mean?'
    passage = {'sentences': [{'text': source}]}
    read = {'type': 'read', 'text': source, 'document_id': 1, 'page_start': 1, 'page_end': 1}
    quiz = {'type': 'ask', 'prompt': 'What did the traveller do?', 'purpose': 'discussion',
            'response': {'format': 'single_choice', 'choices': ['Shared a meal', 'Ran away']}}
    assigned = page_script.schema(passage, context, 'en-US')
    assert {'$ref': '#/$defs/Ask'} in assigned.provider_json_schema()['properties']['turns']['items']['anyOf']
    script = {'welcome': 'Let us read.', 'turns': [read, {'type': 'say', 'text': 'Sharing costs something.'}, quiz],
              'closing': 'Well read.'}
    plan = page_script.compile_script(assigned.model_validate(script).model_dump(), passage, context, 'en-US')
    built = guide.build(passage['sentences'], plan, faithful=True, instruction_only=True)
    asked = [a for a in built['activities'] if a['kind'] == 'ask_question']
    assert len(asked) == 1 and asked[0]['content']['response_modes'] == ['choice']
    book_questions.validate_activities(built['activities'], context)
    # The printed questions are still read, never answered; no question comes before the reading ends.
    with pytest.raises(ValueError, match='before any quiz'):
        assigned.model_validate({**script, 'turns': [quiz, read]})
    with pytest.raises(ValueError):
        assigned.model_validate({**script, 'turns': [read, {**quiz, 'response': {'format': 'text'}}]})
