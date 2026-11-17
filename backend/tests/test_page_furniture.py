"""Page furniture (a buyer's watermark, running heads) never becomes lesson text."""
import hashlib

from tests.pdf_fixture import make_pdf
from tutoring import guide, passages

MARK = "Uso exclusivo de buyer@example.com - Pedido 123456"


def watermarked_book():
    pages = []
    for n in range(1, 11):
        lines = [f"Page {n} teaches the sound of a new letter with a short story."]
        if n % 3 == 0:
            lines.append("Vamos exercitar!")  # a heading on some pages is content, not furniture
        pages.append([*lines, MARK])
    pages.append([MARK])  # a page that is blank apart from the watermark
    return make_pdf(pages)


def test_a_line_on_nearly_every_page_is_left_out_of_the_lesson_text():
    pdf = watermarked_book()
    draft = passages.extract(pdf, 2, 3, None, None)
    assert "buyer@example.com" not in draft["passage"]
    assert "Page 2 teaches" in draft["passage"] and "Vamos exercitar!" in draft["passage"]
    blank = passages.extract(pdf, 11, 11, None, None)
    assert blank["passage"] == "" and "little or no selectable text" in blank["issues"][0]


def test_a_short_book_keeps_its_repeated_lines():
    pdf = make_pdf([[f"Page {n} of a short handout about letters and sounds.", MARK] for n in range(1, 5)])
    assert MARK in passages.extract(pdf, 1, 1, None, None)["passage"]


def test_furniture_in_transcribed_reading_and_quotations_is_removed_when_a_guide_is_saved(harness):
    pdf = watermarked_book()
    path = harness.add_file(pdf, "Books/Letters.pdf")
    with harness.ctx.store.transaction() as tx:
        child = tx.insert("children", {"name": "Learner"})
        subject = tx.insert("subjects", {"child_id": child["id"], "name": "Reading"})
        doc = tx.insert("documents", {"file_path": path, "original_filename": "Letters.pdf", "size_bytes": len(pdf),
                                      "page_count": 11, "sha256": hashlib.sha256(pdf).hexdigest(), "source": "drive"})
        topic = tx.insert("topics", {"subject_id": subject["id"], "document_id": doc["id"], "title": "Letter P",
                                     "page_start": 1, "page_end": 2})
    passages._furniture.clear()
    ref = {"document_id": doc["id"], "page": 1, "quote": f"P p P p PATO {MARK}"}
    written = {"segments": [
        {"type": "explain", "text": "Today we read about the letter P."},
        {"type": "read", "text": f"P p P p PATO\n{MARK}\nPIPOCA {MARK}", "source_refs": [dict(ref)]},
        {"type": "activity", "content": {"prompt": "Circle the P words.", "source_refs": [dict(ref)]}, "source_refs": [dict(ref)]}],
        "sentences": []}
    with harness.ctx.store.transaction() as tx:
        cleaned = guide.without_page_furniture(tx, topic, written)
    assert "buyer@example.com" not in str(cleaned)
    assert cleaned["segments"][1]["text"] == "P p P p PATO\nPIPOCA"
    assert cleaned["segments"][2]["content"]["source_refs"][0]["quote"] == "P p P p PATO"
    assert cleaned["segments"][0] == written["segments"][0] and MARK in str(written)  # the input is not changed


def test_a_running_head_drawn_twice_by_the_text_layer_is_still_furniture():
    assert passages.without_furniture("MATH 4MATH 4\nLesson 24: Estimating", frozenset({"MATH 4"})) == "Lesson 24: Estimating"
    assert passages.strip_furniture("THE MATH 4 BOOK", frozenset({"MATH 4"})) == "THE MATH 4 BOOK"  # too short to cut inside text


def test_a_running_heads_digit_is_not_read_as_the_page_number():
    from types import SimpleNamespace
    from tutoring.exercise_assignment import printed_page
    page = SimpleNamespace(extract_text=lambda: "INDEPENDENT REVIEW\nMATH 2MATH 2\n77\nAdd the numbers.\n+ 4\n+ 5")
    assert printed_page(page, 14, frozenset({"MATH 2"})) == 7  # "77": the number drawn twice
    # Also when the running head is on too few pages to count as furniture.
    assert printed_page(page, 14) == 7
    heading_only = SimpleNamespace(extract_text=lambda: "23Lições de Língua Portuguesa | 3º ano\nTexto da lição")
    assert printed_page(heading_only, 30) == 23


def test_the_books_page_offset_settles_pages_whose_edges_are_ambiguous():
    from types import SimpleNamespace
    from tutoring.exercise_assignment import printed_page
    page = lambda text: SimpleNamespace(extract_text=lambda: text)  # noqa: E731
    # A world map whose markers are numbers on their own lines; the book's offset is 19.
    assert printed_page(page("1\n2\n7\nWorld map\n5\n4"), 23, offset=19) == 4
    # A heading repeated on every page ("LESSON 1") does not number the page.
    assert printed_page(page("PALEONTOLOGY\nLESSON 1\nDiscovering Fossils\nText"), 26, offset=19) == 7
    # One clear number that differs: the book's numbering restarts (a second part).
    assert printed_page(page("3\nPart two begins\nText of the page"), 50, offset=19) == 3
