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


def texts(pages):
    return answer_keys._texts(make_pdf(pages))


def test_key_section_and_chapter_label_select_pages_locally():
    t = texts(BOOKLET)
    start = answer_keys.key_start(t)
    assert start == 2
    labels = answer_keys.lesson_labels({'title': 'The Capture of Constantinople'}, [t[1]])
    assert labels == [('chapter', 24)]
    # Answers continue onto the next page until the next label.
    assert answer_keys.key_pages(t, start, ('chapter', 24)) == [4, 5]
    assert answer_keys.key_pages(t, start, ('chapter', 23)) == [3]
    assert answer_keys.key_pages(t, start, ('chapter', 99)) == []


def test_portuguese_headings_and_labels_are_recognised():
    t = texts([['Lição 3', 'Exercícios'], ['Gabarito'], ['Lição 3', '1. b 2. a'], ['Lição 4', '1. c']])
    assert answer_keys.key_start(t) == 1
    assert answer_keys.lesson_labels({'title': 'Lição 3 – O leão e o ratinho'}, []) == [('lesson', 3)]
    assert answer_keys.key_pages(t, 1, ('lesson', 3)) == [3]


def test_books_without_a_key_heading_have_no_key():
    assert answer_keys.key_start(texts([['Chapter 1'], ['Answers are in your heart.']])) is None
    assert answer_keys.key_start(texts([['Chapter 1']]), whole_document=True) == 0


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
    ctx = SimpleNamespace(store=SimpleNamespace(get=lambda table, key: rows.get((table, key))),
                          file_bytes=lambda path, sha: json.dumps(guide).encode())
    found = page_script.answer_for(ctx, {'session_id': 's', 'action_id': 'activity-1'})
    assert found['answer_key'] == 'Mehmed the Conqueror' and found['answer_key_page'] == 174
    assert page_script.answer_for(ctx, {'session_id': 's', 'action_id': 'activity-2'}) is None
    assert page_script.answer_for(ctx, {'session_id': 's', 'action_id': 'follow-up-9'}) is None


def test_true_false_answers_are_not_mistaken_for_leaks():
    compile_(work(prompt='15. True or false: the empire shrank.', answer='true', format='true_false'))


def test_family_review_lists_each_exercise_with_its_key_answer():
    snapshot = {'teaching_script': {'script': {'turns': [{'type': 'say', 'text': 'Hi.'}, work()]}}}
    assert page_script.answer_key(snapshot) == [{'prompt': work()['prompt'], 'answer': 'Mehmed the Conqueror',
                                                 'answer_page': 174}]
    assert page_script.answer_key({}) == []
