"""Chapter maps from contents pages, as real course books lay them out."""
from tutoring import navigation

CONTENTS = '''Table of Contents
Unit 1
............................................ 1
Lesson 1: Numbers in Nature
........................................ 2
Lesson 2: Similar and Congruen
t Figures
 
................................... 5
Lesson 3: Long Division: Part 4
 
................................... 9
Lessons 4–5: Unit Assessment
....................................... 12'''


def test_wrapped_titles_join_their_leaders_and_page_numbers():
    assert navigation.toc_entries(CONTENTS) == [
        ('Unit 1', 1), ('Lesson 1: Numbers in Nature', 2), ('Lesson 2: Similar and Congruent Figures', 5),
        ('Lesson 3: Long Division: Part 4', 9), ('Lessons 4–5: Unit Assessment', 12)]


def test_lessons_inside_units_become_the_chapters():
    chapters = [{'title': f'Lesson {n}', 'page_start': n, 'page_end': n} for n in range(1, 11)]
    with_units = [{'title': 'Unit 1', 'page_start': 0, 'page_end': 0}, *chapters,
                  {'title': 'Lessons 11–12: Unit Assessment', 'page_start': 11, 'page_end': 12}]
    assert [c['title'] for c in navigation.prefer_lessons(with_units)][-1] == 'Lessons 11–12: Unit Assessment'
    assert 'Unit 1' not in [c['title'] for c in navigation.prefer_lessons(with_units)]
    # A book that is simply chapters keeps them all.
    few = [{'title': 'Chapter 1', 'page_start': 1, 'page_end': 9}, {'title': 'Lesson 1', 'page_start': 10, 'page_end': 12}]
    assert navigation.prefer_lessons(few) == few


def test_merged_file_bookmarks_and_doubled_page_numbers():
    assert navigation.FILE_BOOKMARK.search('Math 4 Course Book_1.4_HOME.pdf')
    assert navigation.FILE_BOOKMARK.search('covers') and not navigation.FILE_BOOKMARK.search('Covering Distance')
    assert navigation.printed_number('1919') == 19 and navigation.printed_number('44') == 4
    assert navigation.printed_number('123') == 123 and navigation.printed_number('© Jenny Phillips') is None
