import pytest

from tutoring import lesson_prompt, page_script
from tutoring.book_questions import VERSION as READ_ALONG_POLICY

PASSAGE = {'title': 'The Walls', 'sentences': [{'text': 'The city had walls.'}, {'text': 'They fell.'}]}
VISUAL = {'boundaries': {'start_at': 'The Walls', 'stop_before': None},
          'attachment_sha256': 'abc', 'document_sha256': 'def',
          'pages': [{'attachment_page': 1, 'document_id': 6, 'page': 233, 'printed_page': 218,
                     'role': 'assigned_reading', 'book_name': 'History.pdf', 'document_sha256': 'def'},
                    {'attachment_page': 2, 'document_id': 6, 'page': 234, 'printed_page': 219,
                     'role': 'assigned_reading', 'book_name': 'History.pdf', 'blank': True}]}


def prompt(**context):
    return page_script.prompt(PASSAGE, subject='History', learner='Lucas', grade='4', language='en-US',
        skill='## Guided reading\nTeach the causes.', learner_context={
            'family_tutoring': {'content': 'Speak warmly.', 'learner_profile': {'age': 9}}, **context})


def test_every_rule_block_appears_once():
    text = prompt(visual_source=VISUAL)
    for block in (lesson_prompt.NON_NEGOTIABLES, lesson_prompt.HOW_TO_TEACH):
        assert text.count(block) == 1
    assert text.count('OUTPUT FORMAT') == 1 and 'READ_FORMS' not in text
    assert 'Speak warmly.' in text and '"age": 9' in text and 'Teach the causes.' in text
    assert f'Preparation policy: {page_script.VERSION}' in text
    # Older stacked policy blocks are gone from the writer.
    for retired in ('MATERIAL CONTENT RESPONSIBILITY', 'TEACH DURING READING', 'AUTHORING FORMAT',
                    'overrides older', 'takes precedence over older'):
        assert retired not in text


def test_pages_and_boundaries_are_compact():
    text = prompt(visual_source=VISUAL)
    assert '"printed_page": 218' in text and '"blank": true' in text
    assert 'attachment_sha256' not in text and 'document_sha256' not in text
    assert '"start_at": "The Walls"' in text and 'stop_before' not in text.split('BOUNDARIES')[1].split('\n')[1]


def test_pdf_lessons_offer_numbered_text_to_reference_or_transcribe():
    text = prompt(visual_source=VISUAL)
    assert 'NUMBERED PAGE TEXT' in text and '[0] The city had walls.' in text
    assert lesson_prompt.READ_FORMS['pdf+numbered'] in text and 'TEXT-ONLY SOURCE' not in text


def test_pdf_lessons_without_a_text_layer_transcribe():
    text = page_script.prompt({**PASSAGE, 'sentences': []}, subject='History', learner='Lucas', grade='4',
                              language='en-US', learner_context={'visual_source': VISUAL})
    assert 'NUMBERED PAGE TEXT' not in text and lesson_prompt.TRANSCRIBED in text and '(a) first/last' not in text


def test_text_only_lessons_number_their_sentences():
    text = prompt()
    assert 'TEXT-ONLY SOURCE' in text and '[0] The city had walls.' in text and '[1] They fell.' in text
    assert lesson_prompt.READ_FORMS['text'] in text


SENTENCES = [{'text': 'First one.', 'paragraphIndex': 0}, {'text': 'Same paragraph.', 'paragraphIndex': 0},
             {'text': 'New paragraph.', 'paragraphIndex': 1}, {'text': 'Last.', 'paragraphIndex': 2}]
CONTEXT = {'visual_source': {'pages': [{'document_id': 6, 'page': 233, 'role': 'assigned_reading'}]}}


def script(*turns):
    return {'welcome': 'Hello.', 'turns': list(turns), 'closing': 'Bye.'}


def reads(plan):
    return [s for s in plan['segments'] if s['type'] == 'read']


def test_sentence_references_compile_to_exact_text_with_paragraphs():
    passage = {'title': 'T', 'sentences': SENTENCES}
    plan = page_script.compile_script(script(
        {'type': 'read', 'first': 0, 'last': 2},
        {'type': 'say', 'text': 'Why did that matter?'},
        {'type': 'read', 'text': 'Last.', 'document_id': 6, 'page_start': 233, 'page_end': 233}), passage, CONTEXT, 'en-US')
    first, second = reads(plan)
    assert first['text'] == 'First one. Same paragraph.\n\nNew paragraph.' and (first['from'], first['to']) == (0, 2)
    assert second['text'] == 'Last.' and second['source_refs'] == [{'document_id': 6, 'page': 233}]


def test_long_references_split_at_paragraphs_into_readable_segments():
    long = [{'text': 'x' * 4000 + '.', 'paragraphIndex': i} for i in range(6)]
    chunks = page_script.referenced_reading(long, 0, 5)
    assert [(a, b) for a, b, _ in chunks] == [(0, 1), (2, 3), (4, 5)]
    assert all(len(text) <= page_script.READING_CHUNK for _, _, text in chunks)
    plan = page_script.compile_script(script({'type': 'read', 'first': 0, 'last': 5}),
                                      {'title': 'T', 'sentences': long}, CONTEXT, 'en-US')
    assert len(reads(plan)) == 3


def test_references_move_forward_and_need_a_complete_form():
    passage = {'title': 'T', 'sentences': SENTENCES}
    with pytest.raises(ValueError, match='move forward'):
        page_script.compile_script(script({'type': 'read', 'first': 0, 'last': 2},
                                          {'type': 'read', 'first': 2, 'last': 3}), passage, CONTEXT, 'en-US')
    with pytest.raises(ValueError, match='either its text'):
        page_script.compile_script(script({'type': 'read', 'first': 0}), passage, CONTEXT, 'en-US')


def test_schema_offers_both_reading_forms_only_with_a_text_layer():
    passage = {'title': 'T', 'sentences': SENTENCES}
    both = page_script.schema(passage, CONTEXT, 'en-US').provider_json_schema()['$defs']['Read']
    assert set(both['required']) == {'type', 'text', 'document_id', 'page_start', 'page_end', 'first', 'last'}
    assert both['properties']['first']['type'] == ['integer', 'null']
    pdf_only = page_script.schema({**passage, 'sentences': []}, CONTEXT, 'en-US').provider_json_schema()['$defs']['Read']
    assert 'first' not in pdf_only['properties'] and pdf_only['properties']['text']['type'] == 'string'


def test_learning_memory_keeps_learning_without_record_identifiers():
    memory = {'version': 'v1', 'map_id': 'm', 'observations': [
        {'title': 'Walls', 'state': 'needs_help', 'evidence_ids': ['attempt:1'], 'review_ids': ['review:1']}]}
    text = prompt(learning_memory=memory, preferences={'tutoring_language': 'English'})
    assert '"state": "needs_help"' in text and '"tutoring_language": "English"' in text
    assert 'attempt:1' not in text and 'review:1' not in text and '"map_id"' not in text


def test_read_along_block_only_for_book_reading():
    assert 'READ-ALONG BOOK' not in prompt(visual_source=VISUAL)
    assert lesson_prompt.READ_ALONG_QUIZ in prompt(visual_source=VISUAL, book_question_policy=READ_ALONG_POLICY)
    assert lesson_prompt.READ_ALONG in prompt(visual_source=VISUAL, book_question_policy='book-read-along-3')


def test_optional_sections_are_omitted_when_empty_and_shown_when_present():
    plain = prompt(visual_source=VISUAL)
    assert 'SOURCE NOTES' not in plain and 'REVISION FEEDBACK' not in plain
    noted = prompt(visual_source=VISUAL, source_annotations=[{'note': 'Footnote 3 is a printing error.'}],
                   review_feedback={'findings': [{'detail': 'Exercise 4 was missing.'}]})
    assert 'Footnote 3 is a printing error.' in noted and 'Exercise 4 was missing.' in noted
