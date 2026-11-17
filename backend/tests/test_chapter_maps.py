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


def test_a_long_title_with_a_two_dot_leader_keeps_its_lesson():
    contents = '''Table of Contents
Lesson 51: Addition: Regrouping Ones and Tens

.................. 147
Lesson 52: Associative Property and Adding 3 One-Digit Numbers

.. 150
Lesson 53: Counting Dollars and Coins
.......................... 152
Lesson 54: Time: Part 9
....................................... 154
Lesson 55: Measuring: Part 3
.................................. 156'''
    entries = navigation.toc_entries(contents)
    assert [page for _, page in entries] == [147, 150, 152, 154, 156]
    assert entries[1][0] == 'Lesson 52: Associative Property and Adding 3 One-Digit Numbers'


def test_a_running_head_on_a_continued_contents_page_is_not_part_of_the_title():
    # The second contents page starts with the book's running head, drawn twice.
    contents = '''MATH 2MATH 2
Lesson 71: Dividing into Groups ................................ 206
Lesson 72: Dividing into Two Equal Groups ......................... 208
Lessons 89–90: Unit Assessment ................................ 258
Unit 4 ......................................................... 265
Lesson 91: Telling Time ........................................ 266'''
    assert navigation.toc_entries(contents) == [
        ('Lesson 71: Dividing into Groups', 206), ('Lesson 72: Dividing into Two Equal Groups', 208),
        ('Lessons 89–90: Unit Assessment', 258), ('Unit 4', 265), ('Lesson 91: Telling Time', 266)]
    assert navigation.lesson_title('Revisão Lição 4 – Ditado') == 'Lição 4 – Ditado'
    assert navigation.lesson_title('Unit 4') == 'Unit 4'


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
    assert navigation.printed_number('23Lições de Língua Portuguesa | 3º ano') == 23
    assert navigation.printed_number('3rd Grade Science') is None


def test_a_corrected_chapter_map_replaces_lessons_only_while_nothing_uses_them(harness):
    from types import SimpleNamespace
    store = harness.ctx.store
    with store.transaction() as tx:
        child = tx.insert("children", {"name": "Learner"})
        subject = tx.insert("subjects", {"child_id": child["id"], "name": "Math"})
        doc = tx.insert("documents", {"file_path": "Books/Course.pdf", "original_filename": "Course.pdf",
                                      "size_bytes": 1, "page_count": 30, "sha256": "a" * 64, "source": "drive"})
    service, book = SimpleNamespace(db=store), {"subject_id": subject["id"]}
    lesson = lambda n, start, end: {"title": f"Lesson {n}", "page_start": start, "page_end": end}
    live = lambda: sorted((t["chapter_order"], t["title"], t["page_start"], t["page_end"])
                          for t in store.find("topics", subject_id=subject["id"]) if not t.get("archived"))
    # The contents reader missed Lesson 2, so Lesson 1 ran over its pages.
    navigation.publish_topics(service, book, doc, {"data": {"chapters": [lesson(1, 1, 9), lesson(3, 10, 12)]}})
    kept = next(t for t in store.find("topics", subject_id=subject["id"]) if t["title"] == "Lesson 3")
    corrected = [lesson(1, 1, 5), lesson(2, 6, 9), lesson(3, 10, 12)]
    navigation.publish_topics(service, book, doc, {"data": {"chapters": corrected}})
    assert live() == [(0, "Lesson 1", 1, 5), (1, "Lesson 2", 6, 9), (2, "Lesson 3", 10, 12)]
    assert store.get("topics", kept["id"])["chapter_order"] == 2  # unchanged lessons keep their record
    # Once a lesson is planned or done, a later map never changes the book's lessons.
    first = next(t for t in store.find("topics", subject_id=subject["id"]) if t["title"] == "Lesson 1" and not t.get("archived"))
    with store.transaction() as tx:
        tx.update("topics", first["id"], {"completed": True})
    navigation.publish_topics(service, book, doc, {"data": {"chapters": [lesson(1, 1, 12)]}})
    assert live() == [(0, "Lesson 1", 1, 5), (1, "Lesson 2", 6, 9), (2, "Lesson 3", 10, 12)]


def test_a_planned_lesson_counts_as_in_use(harness):
    store = harness.ctx.store
    with store.transaction() as tx:
        child = tx.insert("children", {"name": "Learner"})
        subject = tx.insert("subjects", {"child_id": child["id"], "name": "Math"})
        topic = tx.insert("topics", {"subject_id": subject["id"], "title": "Lesson 1", "page_start": 1, "page_end": 2})
    assert not navigation.topics_in_use(store, [topic])
    with store.transaction() as tx:
        tx.insert("scheduled_slots", {"child_id": child["id"], "subject_id": subject["id"], "topic_id": topic["id"],
                                      "date": "2026-11-18", "time_start": "14:00", "time_end": "15:00"})
    assert navigation.topics_in_use(store, [topic])


def test_a_chapter_added_at_the_end_of_the_editor_takes_its_place_by_page():
    doc = {"page_count": 12}
    rows = [{"title": "Lesson 1", "page_start": 1, "page_end": 5}, {"title": "Lesson 3", "page_start": 10, "page_end": 12},
            {"title": "Lesson 2", "page_start": 6, "page_end": 9}]
    assert [r["title"] for r in navigation.validate(doc, rows)] == ["Lesson 1", "Lesson 2", "Lesson 3"]
    import pytest
    with pytest.raises(ValueError):
        navigation.validate(doc, [*rows, {"title": "Overlap", "page_start": 4, "page_end": 6}])


def test_lessons_not_made_from_a_chapter_map_are_never_replaced(harness):
    from types import SimpleNamespace
    store = harness.ctx.store
    with store.transaction() as tx:
        child = tx.insert("children", {"name": "Learner"})
        subject = tx.insert("subjects", {"child_id": child["id"], "name": "Spelling"})
        doc = tx.insert("documents", {"file_path": "Books/Spelling.pdf", "original_filename": "Spelling.pdf",
                                      "size_bytes": 1, "page_count": 20, "sha256": "b" * 64, "source": "drive"})
        # An unused supporting book indexed some other way, with its own language and role.
        indexed = tx.insert("topics", {"subject_id": subject["id"], "document_id": doc["id"], "title": "Lição 1 — Fonemas",
                                       "page_start": 1, "page_end": 9, "is_core": False, "language": "pt"})
    navigation.publish_topics(SimpleNamespace(db=store), {"subject_id": subject["id"]}, doc,
                              {"data": {"chapters": [{"title": "Lição 1 – Fonemas", "page_start": 1, "page_end": 9}]}})
    assert [t["id"] for t in store.find("topics", subject_id=subject["id"]) if not t.get("archived")] == [indexed["id"]]
    assert store.get("topics", indexed["id"])["is_core"] is False


def test_a_second_book_waits_as_an_extra_book_while_the_main_book_is_unfinished(harness):
    from types import SimpleNamespace
    store = harness.ctx.store
    with store.transaction() as tx:
        child = tx.insert("children", {"name": "Learner"})
        subject = tx.insert("subjects", {"child_id": child["id"], "name": "Reading"})
        main = tx.insert("documents", {"file_path": "Books/Volume 2.pdf", "original_filename": "Volume 2.pdf",
                                       "size_bytes": 1, "page_count": 20, "sha256": "c" * 64, "source": "drive"})
        new = tx.insert("documents", {"file_path": "Books/Volume 1.pdf", "original_filename": "Volume 1.pdf",
                                      "size_bytes": 1, "page_count": 20, "sha256": "d" * 64, "source": "drive"})
        last = tx.insert("topics", {"subject_id": subject["id"], "document_id": main["id"], "title": "Letter W",
                                    "page_start": 1, "page_end": 8, "chapter_order": 10, "is_core": True})
    service, book = SimpleNamespace(db=store), {"subject_id": subject["id"]}
    chapters = {"data": {"chapters": [{"title": "Sentences", "page_start": 1, "page_end": 9},
                                      {"title": "Words", "page_start": 10, "page_end": 20}]}}
    navigation.publish_topics(service, book, new, chapters)
    added = [t for t in store.find("topics", subject_id=subject["id"]) if t["document_id"] == new["id"]]
    assert len(added) == 2 and not any(t["is_core"] for t in added)  # Letter W is still planned first
    # Once the main book is finished, a newly mapped book is planned by itself (a new course book).
    with store.transaction() as tx:
        tx.update("topics", last["id"], {"completed": True})
        tx.delete("topics", added[0]["id"]); tx.delete("topics", added[1]["id"])
    navigation.publish_topics(service, book, new, chapters)
    assert all(t["is_core"] for t in store.find("topics", subject_id=subject["id"]) if t["document_id"] == new["id"])


def test_a_new_books_lessons_take_the_language_the_subject_records(harness):
    from types import SimpleNamespace
    store = harness.ctx.store
    with store.transaction() as tx:
        child = tx.insert("children", {"name": "Learner"})
        subject = tx.insert("subjects", {"child_id": child["id"], "name": "Leitura"})
        other = tx.insert("subjects", {"child_id": child["id"], "name": "Numbers"})
        doc = tx.insert("documents", {"file_path": "Books/Volume 1.pdf", "original_filename": "Volume 1.pdf",
                                      "size_bytes": 1, "page_count": 20, "sha256": "e" * 64, "source": "drive"})
        tx.insert("topics", {"subject_id": subject["id"], "title": "Letra W", "page_start": 1, "page_end": 2,
                             "completed": True, "is_core": True, "language": "pt"})
    chapters = {"data": {"chapters": [{"title": "Frase", "page_start": 1, "page_end": 9}]}}
    service = SimpleNamespace(db=store)
    navigation.publish_topics(service, {"subject_id": subject["id"]}, doc, chapters)
    navigation.publish_topics(service, {"subject_id": other["id"]}, doc, chapters)
    language = lambda s: [t.get("language") for t in store.find("topics", subject_id=s["id"]) if t["title"] == "Frase"]
    assert language(subject) == ["pt-BR"] and language(other) == [None]


def test_map_lessons_carry_their_books_name_so_the_curriculum_can_choose_the_book(harness):
    from types import SimpleNamespace
    store = harness.ctx.store
    with store.transaction() as tx:
        child = tx.insert("children", {"name": "Learner"})
        fresh = tx.insert("subjects", {"child_id": child["id"], "name": "Reading"})
        earlier = tx.insert("subjects", {"child_id": child["id"], "name": "Math"})
        doc = tx.insert("documents", {"file_path": "Books/Volume 1.pdf", "original_filename": "Volume 1.pdf",
                                      "size_bytes": 1, "page_count": 20, "sha256": "f" * 64, "source": "drive"})
        older = tx.insert("topics", {"subject_id": earlier["id"], "document_id": doc["id"], "title": "Old map lesson",
                                     "page_start": 15, "page_end": 20, "source_key": "ch-older", "completed": True})
    navigation.publish_topics(SimpleNamespace(db=store), {"subject_id": fresh["id"]}, doc,
                              {"data": {"chapters": [{"title": "Frase", "page_start": 1, "page_end": 9}]}})
    assert [t["pdf_filename"] for t in store.find("topics", subject_id=fresh["id"])] == ["Volume 1.pdf"]
    harness.ctx.books.backfill()  # lessons mapped before the name was recorded get it at startup
    assert store.get("topics", older["id"])["pdf_filename"] == "Volume 1.pdf"
    assert store.get("topics", older["id"])["completed"] is True
    continued = harness.call("PUT", f"/api/subjects/{fresh['id']}/books/set-main-book",
                             params={"pdf_filename": "Volume 1.pdf", "document_id": doc["id"], "continues": True})
    assert continued.status_code == 200, continued.text


def test_contents_that_run_past_the_last_page_are_reported_not_dropped(harness):
    import hashlib
    from tests.pdf_fixture import make_pdf
    contents = ["Table of Contents"] + [f"Lesson {n}: Topic {n} ........................ {2 * n - 1}" for n in range(1, 6)]
    # A book merged from parts with the last part left out: printed pages 1-5 only.
    pdf = make_pdf([contents] + [[str(n), f"Printed page {n} of the course book with its lesson text."] for n in range(1, 6)])
    path = harness.add_file(pdf, "Books/Course.pdf")
    with harness.ctx.store.transaction() as tx:
        doc = tx.insert("documents", {"file_path": path, "original_filename": "Course.pdf", "size_bytes": len(pdf),
                                      "page_count": 6, "sha256": hashlib.sha256(pdf).hexdigest(), "source": "drive"})
    nav = navigation.extract(harness.ctx, doc)
    assert [c["title"] for c in nav["data"]["chapters"]] == ["Lesson 1: Topic 1", "Lesson 2: Topic 2", "Lesson 3: Topic 3"]
    assert nav["data"]["beyond_end"] == [{"title": "Lesson 4: Topic 4", "printed_page": 7},
                                         {"title": "Lesson 5: Topic 5", "printed_page": 9}]
    # A family edit of the map keeps the warning about the missing pages.
    with harness.ctx.store.transaction() as tx:
        edited = navigation.persist(tx, doc, nav["data"]["chapters"][:2], "parent_checked")
    assert edited["data"]["beyond_end"] == nav["data"]["beyond_end"]
