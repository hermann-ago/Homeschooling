"""Assigned-passage text for tutor context and narration.

Only the assigned PDF pages are read. Lessons may start or stop partway through
a page, so the text is cut at the topic's ``start_at`` heading and just before
its ``stop_before`` heading. Extracted text is a *draft* until a parent or tutor
reviews it against the original pages; drafts never feed narration.

Drafts are cached locally by document checksum, page range, boundaries and
extraction version, so a changed book or changed boundaries re-extract.
Reviewed passages live in Drive (the subject's Lesson Content) and are indexed in the
Passages tab with the document checksum they were reviewed against.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import unicodedata
from datetime import datetime, timezone

from pypdf import PdfReader

from storage import layout

EXTRACTION_VERSION = "generic-2"  # 2: page furniture (watermarks, running heads) left out
MIN_PAGE_CHARACTERS = 40
# Page furniture: a line printed on nearly every page of a book, such as a buyer's
# watermark ("Licensed to <name> - <ID>"), a running head or a copyright footer.
# It is never lesson text, and a watermark can carry personal data.
FURNITURE_SAMPLE_PAGES = 24
FURNITURE_SHARE = 0.8
FURNITURE_MIN_PAGES = 6
_furniture: dict[str, frozenset] = {}
VERIFIED = "verified"
NEEDS_REVIEW = "needs_review"


def pdf_range(topic: dict) -> tuple[int, int]:
    offset = topic.get("pdf_page_offset") or 0
    return topic["page_start"] + offset, topic["page_end"] + offset


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("­", "")
    return re.sub(r"\s+", " ", text).strip()


def _find(haystack: str, needle: str, start: int = 0) -> int:
    """Case/space-insensitive search returning an index into ``haystack``."""
    if not needle:
        return -1
    pattern = r"\s+".join(re.escape(word) for word in _norm(needle).split(" "))
    match = re.compile(pattern, re.IGNORECASE).search(haystack, start)
    return match.start() if match else -1


def _sample_texts(pdf_bytes: bytes) -> list[str]:
    """Text of up to FURNITURE_SAMPLE_PAGES pages spread across the whole book."""
    def spread(count):
        return sorted({round(i * (count - 1) / (FURNITURE_SAMPLE_PAGES - 1)) for i in range(FURNITURE_SAMPLE_PAGES)}) if count > 1 else [0]
    try:  # PyMuPDF is many times faster than pypdf on heavy, illustrated books.
        import pymupdf
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
            return [pdf[i].get_text() for i in spread(len(pdf)) if len(pdf)]
    except ImportError:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        texts = []
        for i in spread(len(reader.pages)) if reader.pages else []:
            try:
                texts.append(reader.pages[i].extract_text() or "")
            except Exception:  # an undecodable page has no lines to vote with
                texts.append("")
        return texts


def page_furniture(pdf_bytes: bytes, sha256: str | None = None) -> frozenset:
    """Lines printed on at least 80% of a book's pages that have text, sampled across
    the whole book (a lesson's own pages are too few to tell). Content that recurs
    on many pages, such as an exercise heading, stays well below that share."""
    sha256 = sha256 or hashlib.sha256(pdf_bytes).hexdigest()
    if sha256 in _furniture:
        return _furniture[sha256]
    pages = []
    for text in _sample_texts(pdf_bytes):
        lines = {_norm(line) for line in text.splitlines() if _norm(line)}
        if sum(map(len, lines)) >= MIN_PAGE_CHARACTERS:
            pages.append(lines)
    found = frozenset()
    if len(pages) >= FURNITURE_MIN_PAGES:
        from collections import Counter
        votes = Counter(line for lines in pages for line in lines)
        found = frozenset(line for line, n in votes.items() if n >= FURNITURE_SHARE * len(pages) and len(line) >= 4)
    _furniture[sha256] = found
    return found


def document_furniture(files, document: dict | None) -> frozenset:
    """A stored book's page furniture; empty when its file cannot be read."""
    if not document or not document.get("sha256"):
        return frozenset()
    if document["sha256"] in _furniture:
        return _furniture[document["sha256"]]
    try:
        data = files.read(document["file_path"], document["sha256"])
    except Exception:
        return frozenset()
    return page_furniture(data, document["sha256"])


def without_furniture(page_text: str, furniture) -> str:
    """A page's text-layer lines, leaving out its book's furniture lines."""
    if not furniture:
        return page_text
    # Some text layers draw a running head twice ("MATH 4MATH 4").
    lines = set(furniture) | {line + line for line in furniture}
    return "\n".join(line for line in page_text.splitlines() if _norm(line) not in lines)


def strip_furniture(text: str, furniture) -> str:
    """Free text (a transcription or quotation) with furniture removed wherever it
    appears, also when it ran into a neighbouring line. Short lines (a bare title
    such as "MATH 2") are only removed as whole page lines, never inside text."""
    stripped = without_furniture(text, furniture)  # whole lines go with their line break
    for line in sorted(furniture or (), key=len, reverse=True):
        if len(line) >= 12:
            pattern = r"\s+".join(re.escape(word) for word in line.split(" "))
            stripped = re.sub(pattern, " ", stripped, flags=re.IGNORECASE)
    if stripped == text:
        return text
    stripped = re.sub(r"[ \t]+", " ", stripped)
    return re.sub(r" *\n *", "\n", stripped).strip()


def split_sentences(passage: str) -> list[dict]:
    sentences = []
    for paragraph_index, paragraph in enumerate(p for p in re.split(r"\n\s*\n", passage) if p.strip()):
        text = _norm(paragraph)
        parts = re.split(r"(?<=[.!?])[\"”’')\]]*\s+(?=[\"“‘'(\[]?[A-Z0-9])", text)
        position = 0
        for part in parts:
            # Keep closing quotes with the sentence they end.
            end = text.find(part, position) + len(part)
            while end < len(text) and text[end] in "\"”’')]":
                end += 1
            sentence = text[position:end].strip()
            position = end
            if sentence:
                sentences.append({"text": sentence, "paragraphIndex": paragraph_index})
    return sentences


def passage_sha256(passage: str) -> str:
    return hashlib.sha256(passage.encode("utf-8")).hexdigest()


def extract(pdf_bytes: bytes, pdf_start: int, pdf_end: int, start_at: str | None, stop_before: str | None) -> dict:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    issues = []
    if pdf_start < 1 or pdf_end > len(reader.pages) or pdf_start > pdf_end:
        return {"passage": "", "issues": [f"PDF pages {pdf_start}–{pdf_end} are outside this document"],
                "page_texts": []}
    page_texts = []
    furniture = page_furniture(pdf_bytes)
    for number in range(pdf_start, pdf_end + 1):
        text = without_furniture(reader.pages[number - 1].extract_text() or "", furniture)
        if len(_norm(text)) < MIN_PAGE_CHARACTERS:
            issues.append(f"PDF page {number} has little or no selectable text (scanned or image-only); "
                          "review the original page before narration")
        page_texts.append(text)
    joined = "\n\n".join(page_texts)
    begin = 0
    if start_at:
        begin = _find(joined, start_at)
        if begin < 0:
            issues.append(f"Start heading '{start_at}' was not found on the assigned pages")
            begin = 0
    end = len(joined)
    if stop_before:
        found = _find(joined, stop_before, begin + (len(start_at) if start_at else 0))
        if found < 0:
            issues.append(f"Stop heading '{stop_before}' was not found; the passage runs to the last assigned page")
        else:
            end = found
    passage = joined[begin:end]
    paragraphs = [re.sub(r"[ \t]*\n[ \t]*(?!\n)", " ", p).strip() for p in re.split(r"\n\s*\n", passage)]
    passage = "\n\n".join(p for p in paragraphs if p)
    return {"passage": passage, "issues": issues, "page_texts": page_texts}


def cache_key(document_sha256: str, pdf_start: int, pdf_end: int, start_at, stop_before) -> str:
    return hashlib.sha256(json.dumps([document_sha256, pdf_start, pdf_end, start_at, stop_before,
                                      EXTRACTION_VERSION]).encode()).hexdigest()


def student_package(topic: dict, document: dict | None, content: dict, status: str, issues: list[str],
                    passage_row: dict | None = None) -> dict:
    """Learner-safe passage description for the reader and narration."""
    pdf_start, pdf_end = pdf_range(topic)
    return {
        "topic_id": topic["id"], "source_key": topic.get("source_key"), "title": topic["title"],
        "document_id": topic.get("document_id"), "document_sha256": document["sha256"] if document else None,
        "printed_pages": {"start": topic["page_start"], "end": topic["page_end"]},
        "pdf_pages": {"start": pdf_start, "end": pdf_end}, "pdf_page_offset": topic.get("pdf_page_offset") or 0,
        "start_at": topic.get("start_at"), "stop_before": topic.get("stop_before"),
        "status": status, "issues": issues, "passage": content.get("passage", ""),
        "passage_sha256": passage_sha256(content.get("passage", "")),
        "sentences": content.get("sentences") or split_sentences(content.get("passage", "")),
        "images": [{k: image.get(k) for k in ("pdf_page", "classification", "alt", "caption", "before_sentence")}
                   for image in content.get("selected_images", [])],
        "passage_id": passage_row["id"] if passage_row else None,
        "hide_pdf": bool(topic.get("_combined")),
    }


def load(ctx, topic: dict) -> dict:
    """The verified passage when current; otherwise a cached or fresh draft needing review."""
    store = ctx.store
    document = store.get("documents", topic["document_id"]) if topic.get("document_id") else None
    combined = False
    if document is None:
        return student_package(topic, None, {"passage": ""}, NEEDS_REVIEW, ["This topic has no linked book"])
    if not document.get("file_path"):
        return student_package(topic, document, {"passage": ""}, NEEDS_REVIEW,
                               ["The book's file is missing from the Homeschooling folder"])
    pdf_start, pdf_end = pdf_range(topic)
    from . import library_materials
    if library_materials.book_for(store, topic['subject_id']):
        shared = library_materials.load(ctx, library_materials.passage_key(topic, document))
        if shared:
            return student_package(topic, document, shared['data'], VERIFIED, [], shared)
    rows = [r for r in store.find("passages", topic_id=topic["id"]) if r["status"] == VERIFIED]
    for row in sorted(rows, key=lambda r: r["reviewed_at"] or r["updated_at"], reverse=True):
        current = (row["document_sha256"] == document["sha256"] and row["pdf_start"] == pdf_start
                   and row["pdf_end"] == pdf_end and (row["start_at"] or None) == (topic.get("start_at") or None)
                   and (row["stop_before"] or None) == (topic.get("stop_before") or None))
        content = json.loads(ctx.file_bytes(row["passage_path"], None))
        if combined:
            current = current and bool(safe_text) and _norm(content["passage"]) == _norm(safe_text)
        if current and passage_sha256(content["passage"]) == row["passage_sha256"]:
            return student_package(topic, document, content, VERIFIED, [], row)
        # The book or boundaries changed since review: fall through to a fresh draft.
        stale = [f"A reviewed passage exists but no longer matches the {'book' if row['document_sha256'] != document['sha256'] else 'boundaries'}; review again"]
        break
    else:
        stale = []
    if combined:
        draft = {"passage": safe_text, "sentences": split_sentences(safe_text)}
        return student_package(topic, document, draft, NEEDS_REVIEW,
            stale + ["Review the selected student reading before narration" if safe_text else "Combined-book student reading needs source review"])
    key = cache_key(document["sha256"], pdf_start, pdf_end, topic.get("start_at"), topic.get("stop_before"))
    path = ctx.config.cache_dir / "passages" / f"{key}.json"
    if path.exists():
        draft = json.loads(path.read_text(encoding="utf-8"))
    else:
        pdf = ctx.file_bytes(document["file_path"], document["sha256"])
        draft = extract(pdf, pdf_start, pdf_end, topic.get("start_at"), topic.get("stop_before"))
        draft.pop("page_texts", None)
        draft["sentences"] = split_sentences(draft["passage"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
    if draft["issues"] and hasattr(ctx, "books"):
        indexed_text = ctx.books.topic_text(topic)
        if indexed_text:
            draft = {"passage": indexed_text, "sentences": split_sentences(indexed_text),
                "issues": ["Book preparation transcription: review the original pages before narration"]}
    issues = stale + draft["issues"] + ["Draft extraction: review the original pages before narration"]
    return student_package(topic, document, draft, NEEDS_REVIEW, issues)


def record_review(tx, topic: dict, document: dict, passage: str, reviewed_pages: list[int], notes: str,
                  images: list[dict] | None = None, sentences: list[dict] | None = None, source: str = "review",
                  reviewed_at=None) -> dict:
    """Save a reviewed passage in the Drive folder and index it; the tutor asserts it checked every page."""
    pdf_start, pdf_end = pdf_range(topic)
    missing = sorted(set(range(pdf_start, pdf_end + 1)) - set(reviewed_pages))
    if missing:
        raise ValueError(f"Review every assigned PDF page first; not yet reviewed: {missing}")
    content = {
        "schema_version": 2, "topic_id": topic["id"], "source_key": topic.get("source_key"), "title": topic["title"],
        "printed_pages": [topic["page_start"], topic["page_end"]], "pdf_pages": [pdf_start, pdf_end],
        "start_at": topic.get("start_at"), "stop_before": topic.get("stop_before"), "passage": passage,
        "passage_sha256": passage_sha256(passage), "sentences": sentences or split_sentences(passage),
        "selected_images": images or [], "review": {"pdf_pages": reviewed_pages, "notes": notes},
        "provenance": {"document_sha256": document["sha256"], "extraction_version": EXTRACTION_VERSION},
    }
    body = json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")
    name = f"passage-{topic.get('source_key') or topic['id']}-{content['passage_sha256'][:12]}.json"
    path, _ = tx.add_blob(body, layout.for_topic(tx, topic["id"], layout.LESSON_CONTENT), name, "application/json")
    row_id = f"{topic['id']}:{content['passage_sha256'][:16]}:{document['sha256'][:12]}"
    values = {"topic_id": topic["id"], "document_id": document["id"], "document_sha256": document["sha256"],
              "pdf_start": pdf_start, "pdf_end": pdf_end, "start_at": topic.get("start_at"),
              "stop_before": topic.get("stop_before"), "extraction_version": EXTRACTION_VERSION, "status": VERIFIED,
              "passage_path": path, "passage_sha256": content["passage_sha256"],
              "sentence_count": len(content["sentences"]), "character_count": len(passage), "review_notes": notes,
              "reviewed_at": reviewed_at or datetime.now(timezone.utc).replace(microsecond=0), "source": source}
    from .library_materials import remember_passage
    remember_passage(tx, topic, document, content)
    if tx.get("passages", row_id):
        return tx.update("passages", row_id, values)
    return tx.insert("passages", {"id": row_id, **values})
