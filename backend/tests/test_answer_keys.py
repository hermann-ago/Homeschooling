import json
from types import SimpleNamespace

import pytest

from tests.pdf_fixture import make_pdf
from tutoring import answer_keys, page_script

BOOKLET = [
    ['Chapter 23 Test', '1. Who ruled?'],
    ['Chapter 24 Test: The Ottoman Empire', '3. ____ the Conqueror captured Constantinople.'],
    ['ANSWER KEY', 'Chapter 23 Test', '1. Osman'],
    ['Chapter 24 Test', '3. Mehmed 4. Istanbul', '19. The last remnants of Rome disappeared.'],
    ['20. true 21. false 22. The empire grew because its armies kept winning.', 'Chapter 25 Test', '1. China'],
]


def prints(pages):
    return answer_keys.fingerprint_of(answer_keys._read(make_pdf(pages)))


def test_key_section_and_chapter_label_select_pages_locally():
    f = prints(BOOKLET)
    start = answer_keys.key_start(f)
    assert start == 2
    labels = answer_keys.lesson_labels({'title': 'The Capture of Constantinople'}, [f['labels'][1]])
    assert labels == [('chapter', 24)]
    # Answers continue onto the next page until the next label.
    assert answer_keys.key_pages(f, start, ('chapter', 24)) == [4, 5]
    assert answer_keys.key_pages(f, start, ('chapter', 23)) == [3]
    assert answer_keys.key_pages(f, start, ('chapter', 99)) == []


def test_portuguese_headings_and_labels_are_recognised():
    # From text: the tiny fixture PDF's base font cannot carry 'ã' faithfully.
    f = answer_keys.fingerprint_of(['Lição 3\nExercícios', 'Gabarito', 'Lição 3\n1. b 2. a', 'Lição 4\n1. c'])
    assert answer_keys.key_start(f) == 1
    assert answer_keys.lesson_labels({'title': 'Lição 3 – O leão e o ratinho'}, []) == [('lesson', 3)]
    assert answer_keys.key_pages(f, 1, ('lesson', 3)) == [3]


def test_books_without_a_key_heading_have_no_key():
    assert answer_keys.key_start(prints([['Chapter 1'], ['Answers are in your heart.']])) is None
    assert answer_keys.key_start(prints([['Chapter 1']]), whole_document=True) == 0


def test_whole_key_pdfs_count_only_labels_that_head_a_page():
    f = prints([['Warm-up: review what you learned in Lesson 11 before starting.'], ['Lesson 11', '1. 24 2. 36']])
    assert answer_keys.key_pages(f, 0, ('lesson', 11), opening_only=True) == [2]


PRACTICE = ['Complete the problems below and show your work carefully on the lines',
            'Round each number to the nearest ten and then add the rounded numbers together',
            'How many apples did the farmer pick if he filled six baskets with eight apples each']


def test_filled_in_copies_are_matched_to_the_lesson_pages_they_repeat():
    course = prints([['Lesson 1: Numbers in Nature', 'Read the story about the bees.'], PRACTICE, ['Lesson 2: Addition']])
    key = prints([['Contents of this answer key'], ['Lesson 2 answers', '1. 10 2. 20'], PRACTICE + ['48 apples', '1. 30']])
    # Lesson 1's practice page (2) is repeated, with answers, on key page 3; the story page has no copy.
    assert answer_keys.matching_pages([course['phrases'][0], course['phrases'][1]], key['phrases']) == [3]
    assert answer_keys.ranges([3, 4, 7]) == [[3, 4], [7, 7]]


def test_a_key_declared_for_another_book_is_not_used_for_this_lesson():
    books = [{'key': 'course', 'document_id': 21, 'role': 'combined', 'answer_for_keys': []},
             {'key': 'spelling', 'document_id': 23, 'role': 'combined', 'answer_for_keys': []},
             {'key': 'spelling-key', 'document_id': 24, 'role': 'answer_key', 'answer_for_keys': ['spelling']},
             {'key': 'any-key', 'document_id': 25, 'role': 'answer_key', 'answer_for_keys': []}]
    # Both books have a "Lição 6"; only the spelling book's lessons may search its key.
    assert answer_keys.keys_for(books, {21}) == {25}
    assert answer_keys.keys_for(books, {23}) == {24, 25}


PASSAGE = {'title': 'T', 'sentences': [{'text': 'Mehmed took the city.', 'paragraphIndex': 0}]}
CONTEXT = {'visual_source': {'pages': [{'document_id': 5, 'page': 94, 'role': 'test', 'book_name': 'Tests'}]}}


def work(prompt='3. ____ the Conqueror captured Constantinople.', answer='Mehmed the Conqueror', **response):
    return {'type': 'book_work', 'document_id': 5, 'page': 94, 'prompt': prompt,
            'response': {'format': 'text', **response}, 'answer': answer, 'answer_page': 174}


def compile_(*turns):
    return page_script.compile_script({'welcome': 'Hi.', 'turns': list(turns), 'closing': 'Bye.'},
                                      PASSAGE, CONTEXT, 'en-US')


def test_key_answers_never_reach_compiled_child_content():
    plan = compile_({'type': 'read', 'first': 0, 'last': 0}, work())
    assert 'Mehmed the Conqueror' not in json.dumps([s for s in plan['segments'] if s['type'] == 'activity'])


def test_explanations_and_prompts_cannot_reveal_the_key():
    with pytest.raises(ValueError, match='reveals its answer'):
        compile_({'type': 'say', 'text': 'Remember, it was Mehmed the Conqueror.'}, work())
    with pytest.raises(ValueError, match='reveals its answer'):
        compile_(work(prompt='Mehmed the Conqueror captured the city. Who captured it?'))
    # Choices list the original options, including the right one.
    compile_(work(prompt='9. Which weapon?', answer='gunpowder', format='single_choice',
                  choices=['warships', 'gunpowder']))


def test_grading_finds_the_pinned_answer_for_each_book_activity():
    script = {'turns': [{'type': 'read', 'first': 0, 'last': 0}, work(), work(prompt='4. Renamed?', answer=None)]}
    guide = {'activities': [{'id': 'segment-1', 'kind': 'read_source', 'origin': 'required_book'},
                            {'id': 'activity-1', 'kind': 'request_book_work', 'origin': 'required_book'},
                            {'id': 'activity-2', 'kind': 'request_book_work', 'origin': 'required_book'}]}
    rows = {('lesson_playback', 's'): {'guide_id': 'g', 'context_snapshot': {
                'prepared_guide': {'teaching_script': {'script': script}}}},
            ('guides', 'g'): {'guide_path': 'g.json', 'guide_file_sha256': None}}
    ctx = SimpleNamespace(store=SimpleNamespace(get=lambda table, key: rows.get((table, key)), find=lambda table, **equals: []),
                          file_bytes=lambda path, sha: json.dumps(guide).encode())
    found = page_script.answer_for(ctx, {'session_id': 's', 'action_id': 'activity-1'})
    assert found['answer_key'] == 'Mehmed the Conqueror' and found['answer_key_page'] == 174
    assert page_script.answer_for(ctx, {'session_id': 's', 'action_id': 'activity-2'}) is None
    assert page_script.answer_for(ctx, {'session_id': 's', 'action_id': 'follow-up-9'}) is None


def test_true_false_answers_are_not_mistaken_for_leaks():
    compile_(work(prompt='15. True or false: the empire shrank.', answer='true', format='true_false'))


def test_family_review_lists_each_exercise_with_its_key_answer():
    snapshot = {'teaching_script': {'script': {'turns': [{'type': 'say', 'text': 'Hi.'}, work()]}}}
    assert page_script.answer_key(snapshot) == [{'index': 0, 'prompt': work()['prompt'], 'answer': 'Mehmed the Conqueror',
        'answer_page': 174, 'blanks': [], 'proposed_answers': [], 'approved_answers': None}]
    assert page_script.answer_key({}) == []


def test_hands_on_book_work_waits_for_a_grown_up():
    plan = compile_({'type': 'book_work', 'document_id': 5, 'page': 94, 'prompt': 'Colour the letter T.',
                     'response': {'format': 'parent_check'}, 'answer': None, 'answer_page': None})
    work = [s for s in plan['segments'] if s['type'] == 'activity']
    assert work[0]['activity_kind'] == 'explain_or_observe' and work[0]['content']['parent_check'] is True
    assert work[0]['origin'] == 'required_book'
