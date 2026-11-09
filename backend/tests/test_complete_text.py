"""Malformed teacher text is rejected; linked pages carry the number printed in the book."""
import pytest
from tutoring import navigation, page_script
from tutoring.guide import GuideError

PASSAGE = {'title': 'T', 'sentences': [{'text': 'One.', 'paragraphIndex': 0}]}
CONTEXT = {'visual_source': {'pages': [{'document_id': 6, 'page': 1, 'role': 'assigned_reading'}]}}


def compile_(**parts):
    script = {'welcome': 'Hi there.', 'turns': [{'type': 'read', 'first': 0, 'last': 0}, {'type': 'say', 'text': 'A point.'}],
              'closing': 'See you soon.', **parts}
    return page_script.compile_script(script, PASSAGE, CONTEXT, 'en-US')


@pytest.mark.parametrize('parts', [{'closing': ': cost, choice, and the use of force.'},
                                   {'welcome': ', and then'},
                                   {'turns': [{'type': 'read', 'first': 0, 'last': 0}, {'type': 'say', 'text': '— cut'}]}])
def test_cut_off_teacher_text_is_an_invalid_reply(parts):
    with pytest.raises(GuideError) as error:
        compile_(**parts)
    assert error.value.invalid_response and 'cut off' in str(error.value)


def test_complete_text_may_open_with_quotes_or_numbers():
    compile_(closing='“Band of brothers” stays with us.', welcome='3 ideas today.')


def test_a_page_without_a_visible_number_takes_its_books_offset():
    pages = [{'document_id': 5, 'page': 102, 'role': 'test'},
             {'document_id': 5, 'page': 103, 'role': 'test', 'printed_page': 100},
             {'document_id': 5, 'page': 104, 'role': 'test', 'printed_page': 101},
             {'document_id': 6, 'page': 250, 'role': 'assigned_reading', 'printed_page': 235}]
    navigation.infer_printed_pages(pages)
    assert pages[0]['printed_page'] == 99
    mixed = [{'document_id': 5, 'page': 10, 'role': 'test'}, {'document_id': 5, 'page': 11, 'role': 'test', 'printed_page': 8},
             {'document_id': 5, 'page': 12, 'role': 'test', 'printed_page': 12}]
    navigation.infer_printed_pages(mixed)
    assert 'printed_page' not in mixed[0]  # no single offset: leave it unknown


def test_a_book_record_without_its_pdf_has_no_chapter_map():
    assert navigation.saved(None, {'id': 1, 'sha256': None}) is None
    assert navigation.saved(None, None) is None


def test_a_repeated_true_false_pair_is_dropped_but_other_choices_are_not():
    from tutoring.teaching_script import Response
    assert Response(format='true_false', choices=['True', 'False']).choices == []
    assert Response(format='true_false', choices=['Verdadeiro', 'Falso']).choices == []
    with pytest.raises(ValueError):
        Response(format='true_false', choices=['Fact', 'Opinion'])
