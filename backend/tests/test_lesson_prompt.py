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
    for block in (lesson_prompt.NON_NEGOTIABLES, lesson_prompt.HOW_TO_TEACH, lesson_prompt.OUTPUT_FORMAT):
        assert text.count(block) == 1
    assert 'Speak warmly.' in text and '"age": 9' in text and 'Teach the causes.' in text
    assert f'Preparation policy: {page_script.VERSION}' in text
    # Older stacked policy blocks are gone from the writer.
    for retired in ('MATERIAL CONTENT RESPONSIBILITY', 'TEACH DURING READING', 'AUTHORING FORMAT',
                    'overrides older', 'takes precedence over older'):
        assert retired not in text


def test_pages_and_boundaries_are_compact_and_pdf_lessons_have_no_text_source():
    text = prompt(visual_source=VISUAL)
    assert '"printed_page": 218' in text and '"blank": true' in text
    assert 'attachment_sha256' not in text and 'document_sha256' not in text
    assert '"start_at": "The Walls"' in text and 'stop_before' not in text.split('BOUNDARIES')[1].split('\n')[1]
    assert 'TEXT-ONLY SOURCE' not in text and '[0] The city had walls.' not in text


def test_text_only_lessons_number_their_sentences():
    text = prompt()
    assert 'TEXT-ONLY SOURCE' in text and '[0] The city had walls.' in text and '[1] They fell.' in text


def test_learning_memory_keeps_learning_without_record_identifiers():
    memory = {'version': 'v1', 'map_id': 'm', 'observations': [
        {'title': 'Walls', 'state': 'needs_help', 'evidence_ids': ['attempt:1'], 'review_ids': ['review:1']}]}
    text = prompt(learning_memory=memory, preferences={'tutoring_language': 'English'})
    assert '"state": "needs_help"' in text and '"tutoring_language": "English"' in text
    assert 'attempt:1' not in text and 'review:1' not in text and '"map_id"' not in text


def test_read_along_block_only_for_book_reading():
    assert lesson_prompt.READ_ALONG not in prompt(visual_source=VISUAL)
    assert lesson_prompt.READ_ALONG in prompt(visual_source=VISUAL, book_question_policy=READ_ALONG_POLICY)


def test_optional_sections_are_omitted_when_empty_and_shown_when_present():
    plain = prompt(visual_source=VISUAL)
    assert 'SOURCE NOTES' not in plain and 'REVISION FEEDBACK' not in plain
    noted = prompt(visual_source=VISUAL, source_annotations=[{'note': 'Footnote 3 is a printing error.'}],
                   review_feedback={'findings': [{'detail': 'Exercise 4 was missing.'}]})
    assert 'Footnote 3 is a printing error.' in noted and 'Exercise 4 was missing.' in noted
