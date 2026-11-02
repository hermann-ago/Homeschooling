import json

from tools.lesson_eval import evaluate, main

PASSAGE = ('Chapter 1 The Walls 7 The city had strong walls. Its people trusted them. '
           'Chapter 1 The Walls 8 Then a new weapon arrived: gunpowder. The walls fell.')


def guide(reading, *, extra=()):
    return {'title': 'The Walls', 'segments': [
        {'type': 'intro', 'text': 'Today we read about a great city.'},
        {'type': 'read', 'text': reading},
        {'type': 'explain', 'text': 'Walls protected cities for centuries. Why might that change?'},
        {'type': 'read', 'text': 'The walls fell.'},
        *extra,
        {'type': 'recap', 'text': 'Well done.'}]}


def book_work(prompt, page=12):
    return {'type': 'activity', 'activity_kind': 'request_book_work', 'origin': 'required_book',
            'content': {'prompt': prompt, 'response_modes': ['text']},
            'source_refs': [{'document_id': 1, 'page': page}]}


EXPECTED = {
    'reading': [{'starts': 'The city had strong walls', 'ends': 'The walls fell'}],
    'ignore_patterns': ['chapter1thewalls[0-9]*'],
    'exercises': [
        {'id': '1', 'snippet': 'What new weapon', 'answer': 'gunpowder'},
        {'id': '2', 'snippet': 'Name the city', 'page': 12, 'number': 2},
    ]}


def test_complete_lesson_ignores_headers_and_pdf_spacing():
    # Text layers split ligatures and words; matching ignores spacing and punctuation.
    reading = 'The city had strong wa lls.\n\nIts people trusted them. Then a new weapon arrived: gunpowder.'
    report = evaluate(guide(reading, extra=[book_work('What new weapon broke the walls?'),
                                            book_work('Exercise 2: write the city’s name.')]),
                      {'package': {'passage': PASSAGE}}, EXPECTED)
    assert report['reading_coverage'] == 1
    assert report['reading_spans_complete'] == 1
    assert report['exercises_found'] == 2 and report['exercises_duplicated'] == []
    assert report['answer_leaks'] == []
    assert report['explanations'] == 1 and report['explanations_between_readings'] == 1
    assert report['narration_questions'] == ['Why might that change?']


def test_omissions_duplicates_and_leaks_are_reported():
    work = book_work('What new weapon did they use? (It was gunpowder.)')
    report = evaluate(guide('The city had strong walls.', extra=[work, work]),
                      {'package': {'passage': PASSAGE}}, EXPECTED)
    assert report['reading_coverage'] < 0.6
    assert report['reading_spans_complete'] == 0
    assert report['exercises_found'] == 1
    assert report['exercises_duplicated'] == ['1']
    assert report['answer_leaks'] == ['1']


def test_choice_options_are_not_leaks():
    choice = book_work('What new weapon did they use?')
    choice['content']['choices'] = [{'id': 'a', 'label': 'gunpowder'}, {'id': 'b', 'label': 'catapults'}]
    report = evaluate(guide('x', extra=[choice]), None, EXPECTED)
    assert report['answer_leaks'] == []


def test_cli_scores_every_eval_folder(tmp_path, capsys):
    for name in ('a', 'b'):
        folder = tmp_path / name
        folder.mkdir()
        (folder / 'before-guide.json').write_text(json.dumps(guide('The walls fell.')), encoding='utf-8')
    (tmp_path / 'a' / 'expected.json').write_text(json.dumps(EXPECTED), encoding='utf-8')
    main([str(tmp_path), '--all'])
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 4 and lines[2].startswith('| a |') and lines[3].startswith('| b |')
