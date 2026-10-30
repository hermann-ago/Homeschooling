"""Book preparation and exercise catalog. AI proposes; source references are checked here.

Units are checkpointed outside long transactions. Catalog revisions are immutable, and
learner work references a version rather than whatever a parent edits tomorrow.
"""
from __future__ import annotations

import hashlib
import copy
import io
import json
import logging
import re
import threading
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from pypdf import PdfReader, PdfWriter

from storage import layout
from . import passages
from .activities import AnswerFormat, Choice, QuestionContent

log = logging.getLogger(__name__)
ROLES = ("textbook", "combined", "workbook", "test", "answer_key", "reference")
READING_ROLES = ("textbook", "combined")
PRACTICE_ROLES = ("workbook", "test", "combined")
SCAN_VERSION = "books-1"
UNIT_PAGES = 8


def scan_version(role):
    # New roles need the student-only blocks and individual key entries. Keep
    # existing textbook/workbook units reusable rather than rescanning old books.
    return "books-2" if role in ("combined", "answer_key") else SCAN_VERSION


def ident(*parts):
    return uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(parts, default=str)).hex


def norm(value):
    return passages._norm(value or "").casefold()


def original_quote(text, proposed):
    """Locate formatting-equivalent text, then return the original source span.

    PDF drop caps and ligatures often split a word. Ignore whitespace and
    typographic quote/dash variants only; never change letters or drop signs.
    """
    punctuation = str.maketrans({'“': '"', '”': '"', '‘': "'", '’': "'", '–': '-', '—': '-', '−': '-'})
    def indexed(value, join_wrapped_words=False):
        chars, positions = [], []
        for i, char in enumerate(value):
            if join_wrapped_words and char in ('-', '\u00ad') and i and value[i - 1].isalpha():
                # Optional end-of-line word hyphens; a minus sign in an equation
                # or an ordinary hyphenated expression remains in the source.
                before = re.search(r"[^\W\d_]{2,}$", value[:i], re.UNICODE)
                after = re.match(r"[ \t]*\r?\n[ \t]*[^\W\d_](?:[ \t]*[^\W\d_])", value[i + 1:], re.UNICODE)
                if before and after:
                    continue
            for normalized in unicodedata.normalize('NFKC', char).casefold().translate(punctuation):
                if not normalized.isspace():
                    chars.append(normalized)
                    positions.append(i)
        return ''.join(chars), positions
    targets = [proposed]
    # A generator sometimes adds a terminal sentence period. Return the exact
    # original span, rather than changing the source or relaxing numeric signs.
    if len(proposed.strip()) >= 15 and proposed.rstrip().endswith('.') and not proposed.rstrip().endswith('..'):
        targets.append(proposed.rstrip()[:-1])
    for candidate in targets:
        target, _ = indexed(candidate)
        for join in (False, True):
            source, positions = indexed(text, join)
            start = source.find(target) if target else -1
            if start >= 0:
                return text[positions[start]:positions[start + len(target) - 1] + 1]
    return None


def book_name(filename):
    return re.sub(r"^[0-9a-f]{32}_", "", filename, flags=re.I)


def question_number(reference):
    value = re.fullmatch(r"(?:Question\s*|Q\s*)?(\d+)[.)]?", reference.strip(), re.I)
    if not value:
        # A chapter-qualified label still identifies one original question.
        value = re.fullmatch(r"Chapter\s+\d+\s*[,;:]\s*(?:Question\s*|Q\s*)?(\d+)[.)]?", reference.strip(), re.I)
    return int(value[1]) if value else None


def numbered_source(ctx, sha, native, first, last):
    """Inventory the original numbering of an already identified test booklet."""
    documents = {d["id"] for d in ctx.store.find("documents", sha256=sha)}
    chapters = [c for c in ctx.store.all("chapters") if c["test_document_id"] in documents and c["test_pdf_start"] and c["test_pdf_end"]]
    return sorted({(c["chapter"], page, int(number)) for c in chapters for page in range(max(first, c["test_pdf_start"]), min(last, c["test_pdf_end"]) + 1)
        for number in re.findall(r"(?m)^\s*(\d+)[.)]\s", native.get(page, ""))})


class ScannedExercise(BaseModel):
    reference: str
    section: str = ""
    chapter: int | None = None
    pages: list[int]
    printed_page: str = ""
    prompt: str
    kind: str = "handwritten"
    optional: bool = False
    unnumbered: bool = False
    answer: str | None = None
    issue: str | None = None
    answer_format: AnswerFormat = "text"
    choices: list[Choice] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def answer_controls(self):
        controls = QuestionContent(prompt=self.prompt or "Source task", answer_format=self.answer_format,
                                   choices=self.choices)
        self.choices = controls.choices
        return self


class ScannedElement(BaseModel):
    id: str = ""
    kind: Literal["text", "illustration", "diagram", "table", "formula", "answer_space", "decoration"]
    text: str = ""
    description: str = ""
    bbox: list[float] | None = None
    rows: list[list[str]] = Field(default_factory=list)
    expression: str | None = None
    relates_to: list[str] = Field(default_factory=list)
    issue: str | None = None


class ReadingSpan(BaseModel):
    first_line: int = Field(ge=1)
    last_line: int = Field(ge=1)


class ScannedPage(BaseModel):
    page: int
    text: str
    student_safe: bool = False
    issue: str | None = None
    native_reliable: bool = True
    teacher_material: bool = False
    public_fragments_only: bool = False
    # Only genuine lesson/subsection starts, with a verbatim heading from this page.
    headings: list[str] = Field(default_factory=list)
    reading_blocks: list[str] = Field(default_factory=list)
    reading_spans: list[ReadingSpan] = Field(default_factory=list, max_length=300)
    review_notes: list[str] = Field(default_factory=list, max_length=30)
    printed_page: str | None = None
    elements: list[ScannedElement] = Field(default_factory=list)
    review_method: Literal["native_checked", "visual"] = "visual"


class KeyQuote(BaseModel):
    page: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=12000)


class ScannedKeyAnswer(BaseModel):
    reference: str
    chapter: int | None = None
    section: str = ""
    pages: list[int]
    answer: str
    evidence: str
    evidence_element_ids: list[str] = Field(default_factory=list)
    evidence_quotes: list[KeyQuote] = Field(default_factory=list, max_length=30)
    issue: str | None = None


class ScanResult(BaseModel):
    pages: list[ScannedPage]
    exercises: list[ScannedExercise] = Field(default_factory=list)
    answers: list[ScannedKeyAnswer] = Field(default_factory=list)


def key_evidence_supported(entry, pages):
    selected = [p for p in pages if p["page"] in entry["pages"]]
    if not selected or {p["page"] for p in selected} != set(entry["pages"]) or any(not p.get("teacher_material") for p in selected):
        return False
    if entry.get('evidence_quotes'):
        indexed={p['page']:p for p in selected}
        if any(q['page'] not in indexed or not norm(q['quote']) or norm(q['quote']) not in norm(indexed[q['page']]['text']) for q in entry['evidence_quotes']):
            return False
        quote=norm('\n'.join(q['quote'] for q in entry['evidence_quotes']))
        return bool(norm(entry['answer'])) and norm(entry['answer']) in quote and bool(norm(entry['evidence'])) and norm(entry['evidence']) in quote
    quote = norm(entry["evidence"])
    if not norm(entry["answer"]) or norm(entry["answer"]) not in quote:
        return False
    if not entry.get("evidence_element_ids"):
        return bool(quote) and quote in norm("\n".join(p["text"] for p in selected))
    elements = {e["id"]: e for p in selected for e in p.get("elements", []) if e.get("id") and not e.get("issue")}
    if any(eid not in elements for eid in entry["evidence_element_ids"]):
        return False
    evidence = []
    for eid in entry["evidence_element_ids"]:
        element = elements[eid]
        evidence.extend([element.get("text", ""), element.get("description", "")])
        evidence.extend(" ".join(row) for row in element.get("rows", []))
    return bool(quote) and any(quote in norm(part) for part in evidence)


class Requirement(BaseModel):
    topic_id: int
    evidence: str


class ExerciseMatch(BaseModel):
    exercise_id: str
    requirements: list[Requirement] = Field(default_factory=list)
    clear: bool = False
    reason: str = ""
    needed_topic_ids: list[int] = Field(default_factory=list)


class MatchResult(BaseModel):
    matches: list[ExerciseMatch]


def ask(ctx, text, schema, pdf=None, max_output=16384):
    return ctx.ai.generate(text, schema=schema, pdf=pdf, category="books", max_output=max_output)


def proposal_id(sha, role, first, last):
    return "scan-proposal-" + ident(sha, role, first, last, "proposal-1")


def resolve_scan(db, unit, *, source_review_id=...):
    """Revalidate a saved proposal without changing the immutable source checkpoint."""
    reviews = db.find("book_source_reviews", sha256=unit["sha256"], role=unit["role"]) if source_review_id is not None else []
    if source_review_id is not ...:
        reviews=[r for r in reviews if r['id']==source_review_id]
    if reviews:
        from .book_companion import unit_data
        review = max(reviews, key=lambda r: r["version"])
        data = unit_data(review["data"], unit["first_page"], unit["last_page"])
        return {**unit, "data": data, "source_review_id": review["id"]}
    proposal = db.get("book_units", proposal_id(unit["sha256"], unit["role"], unit["first_page"], unit["last_page"]))
    if not proposal:
        return unit
    frozen = proposal["data"]
    data = normalize_scan(copy.deepcopy(frozen["result"]), unit["role"], unit["first_page"], unit["last_page"],
                          frozen["end"], {int(n): text for n, text in frozen["native"].items()}, frozen["inventory"])
    return {**unit, "data": data}


def scan_unit(ctx, pdf, role, first, last):
    raise ValueError('Whole-book source scanning is retired. Select original pages for a lesson instead.')


def normalize_scan(result, role, first, last, end, native, inventory, *, allow_mixed_readings=False):
    numbers = [p["page"] for p in result["pages"]]
    if sorted(numbers) != list(range(first, last + 1)):
        raise ValueError("The scan omitted or duplicated a page; retry this unit")
    for page in result["pages"]:
        page["review_method"] = {"native": "native_checked", "native text checked against page image": "native_checked",
                                 "vision": "visual"}.get(page.get("review_method"), page.get("review_method") or "visual")
        if page.get("native_reliable", True) and len(norm(native[page["page"]])) >= passages.MIN_PAGE_CHARACTERS:
            page["text"] = native[page["page"]]
        elif not page["text"] and norm(native[page["page"]]):
            page["issue"] = page.get("issue") or "The page transcription needs checking"
        if page.get("reading_spans"):
            lines = page["text"].splitlines()
            spans = page["reading_spans"]
            if any(not (1 <= s["first_line"] <= s["last_line"] <= len(lines)) for s in spans):
                page["issue"] = "Reading line boundaries are outside this original page"
                page["reading_blocks"] = []
            else:
                page["reading_blocks"] = ['\n'.join(lines[s["first_line"]-1:s["last_line"]]) for s in spans]
        page["reading_blocks"] = [original_quote(page["text"], b) or b for b in page.get("reading_blocks", [])]
        page["headings"] = [original_quote(page["text"], h) or h for h in page.get("headings", [])]
        page["headings"] = [h for h in page["headings"] if norm(h) and norm(h) in norm(page["text"])]
        if role == "answer_key" or re.search(r"answer\s+key|answers\s+to|teacher.?s?\s+notes", page["text"], re.I):
            page["student_safe"] = False
            page["teacher_material"] = True
        if page.get("teacher_material"):
            page["student_safe"] = False
    if role == "combined":
        for page in result["pages"]:
            blocks = page.get("reading_blocks", [])
            mixed = allow_mixed_readings and page.get('teacher_material') and page.get('public_fragments_only') and blocks
            if (page.get("teacher_material") or not page.get("student_safe")) and not mixed:
                page["reading_blocks"] = []
                page["headings"] = []
            elif any(not norm(block) or norm(block) not in norm(page["text"]) for block in blocks):
                page["reading_blocks"] = []
                page["headings"] = []
                page["issue"] = "Combined-book reading must quote the original student text"
            page["headings"] = [h for h in page["headings"] if any(norm(h) in norm(b) for b in page.get("reading_blocks", []))]
    for item in result.get("answers", []):
        if role not in ("answer_key", "combined"):
            raise ValueError("Unexpected teacher answer entries for this resource")
        if not item["pages"] or min(item["pages"]) < first or min(item["pages"]) > last or max(item["pages"]) > end:
            # Keys often refer to the STUDENT book's printed pages. Relocate
            # only by unique observed key evidence, never by those numbers.
            anchors = [p["page"] for p in result["pages"] if key_evidence_supported({**item, "pages": [p["page"]]}, [p])]
            item["pages"] = anchors if len(anchors) == 1 else list(range(first, last + 1))
            if len(anchors) != 1:
                item["issue"] = "Answer location needs review; pages indicate the inspected range, not a verified citation"
        if not key_evidence_supported(item, result["pages"]):
            item["issue"] = item.get("issue") or "The key answer needs checking against its original page"
    for item in result["exercises"]:
        # Grading answers come from verified key entries, never a scan's inference.
        item["answer"] = None
        if not item["pages"] or min(item["pages"]) < first or min(item["pages"]) > last or max(item["pages"]) > end:
            raise ValueError("An exercise references pages outside its scan")
        if not item["prompt"].strip() or (not item["reference"].strip() and not item.get('unnumbered')):
            item["issue"] = "Exercise instructions or identity need checking"
        if item["kind"] not in ("answer", "handwritten", "activity"):
            item["kind"] = "handwritten"
    missing = [(chapter, page, number) for chapter, page, number in inventory if not any(question_number(e["reference"]) == number and page in e["pages"]
        and e.get("chapter") in (None, chapter) for e in result["exercises"])]
    if missing:
        raise ValueError(f"The scan omitted original test questions {missing[:8]}; retry these pages")
    if any(sum(question_number(e["reference"]) == number and page in e["pages"] and e.get("chapter") in (None, chapter)
        for e in result["exercises"]) > 1 for chapter, page, number in inventory):
        raise ValueError("The scan duplicated an original test question; retry these pages")
    return result


class BookService:
    def __init__(self, ctx):
        self.ctx = ctx
        self.lock = threading.RLock()
        self._native_pages = {}

    @property
    def db(self):
        return self.ctx.store

    def backfill(self):
        """Add explicit links without changing existing lessons or attempts."""
        with self.db.transaction(kind="books.backfill") as tx:
            for topic in tx.all("topics"):
                if not topic.get("document_id"):
                    continue
                book_id = f"book-{topic['subject_id']}-{topic['document_id']}"
                if tx.get("subject_books", book_id):
                    continue
                doc = tx.get("documents", topic["document_id"])
                is_test = "sotw2_tests" in doc["original_filename"].lower()
                role = "test" if is_test else "textbook" if topic["is_core"] else "reference"
                tx.insert("subject_books", {"id": book_id, "subject_id": topic["subject_id"],
                    "document_id": doc["id"], "role": role, "status": "not_prepared"})
                if is_test:
                    for t in tx.find("topics", subject_id=topic["subject_id"], document_id=doc["id"]):
                        tx.update("topics", t["id"], {"archived": True, "is_core": False})

    def begin(self, tx, subject_id, path, role, companion=None, answer_for=None):
        if role not in ROLES or not tx.get("subjects", subject_id):
            raise ValueError("Choose a subject and book role")
        if companion:
            linked = tx.get("subject_books", companion)
            if not linked or linked["subject_id"] != subject_id or linked["role"] not in READING_ROLES:
                raise ValueError("Choose a companion textbook in this subject")
        if role == "answer_key":
            target = tx.get("subject_books", answer_for) if answer_for else None
            if not target or target["subject_id"] != subject_id or target["role"] not in PRACTICE_ROLES or target["archived"]:
                raise ValueError("Choose the workbook or combined book this answer key belongs to")
        data = self.ctx.files.read(path)
        from services.documents import MAX_PDF_BYTES, add_drive_document
        if len(data) > MAX_PDF_BYTES or not data.startswith(b"%PDF"):
            raise ValueError("Choose a PDF smaller than 250 MiB")
        reader = PdfReader(io.BytesIO(data))
        sha = hashlib.sha256(data).hexdigest()
        document = add_drive_document(tx, path, path.rsplit("/", 1)[-1], len(data), len(reader.pages), sha)
        book_id = f"book-{subject_id}-{document['id']}"
        book = tx.get("subject_books", book_id)
        existing = next((j for j in tx.find("book_imports", book_id=book_id) if j["status"] in ("queued", "running")), None)
        if existing:
            if book["role"] != role or (companion and book["companion_id"] != companion) or (answer_for and book.get("answer_for_id") != answer_for):
                raise ValueError("Finish the current preparation before changing this book's role or companion")
            return existing
        if not book:
            tx.insert("subject_books", {"id": book_id, "subject_id": subject_id, "document_id": document["id"],
                "role": role, "companion_id": companion, "answer_for_id": answer_for, "answer_for_ids":[answer_for] if answer_for else [], "status": "queued"})
        else:
            tx.update("subject_books", book_id, {"role": role, "companion_id": companion or book["companion_id"],
                "answer_for_id": (answer_for or book.get("answer_for_id")) if role=='answer_key' else None,
                "answer_for_ids": ([answer_for] if answer_for else book.get('answer_for_ids',[])) if role=='answer_key' else [],
                "archived": False, "status": "queued"})
        job_id = f"import-{uuid.uuid4().hex}"
        return tx.insert("book_imports", {"id": job_id, "book_id": book_id, "status": "queued", "stage": "Reading table of contents",
            "done": 0, "total": len(reader.pages), "source_path": document["file_path"], "source_sha256": sha,
            "index_id": f"index-{uuid.uuid4().hex}"})

    def retry(self, tx, job_id):
        job = tx.get("book_imports", job_id)
        if not job or job["status"] not in ("failed", "waiting"):
            raise ValueError("Choose an unfinished preparation to retry")
        book = tx.get("subject_books", job["book_id"])
        completed = sum(u["last_page"] - u["first_page"] + 1 for u in
            tx.find("book_units", sha256=job["source_sha256"], role=book["role"], version=scan_version(book["role"]))
            if u["first_page"] and u["last_page"])
        tx.update("subject_books", job["book_id"], {"status": "ready" if job.get("mode") == "rematch" and book["active_index"] else "queued"})
        return tx.update("book_imports", job_id, {"status": "queued", "error": None, "done": completed,
            "stage": "Reading pages" if completed < job["total"] else "Linking to lessons"})

    def rematch(self, tx, book_id, topic_id=None):
        book = tx.get("subject_books", book_id)
        if not book or book["role"] not in PRACTICE_ROLES or not book["active_index"] or book["status"] != "ready":
            raise ValueError("Prepare this workbook before improving its reading links")
        if topic_id:
            topic = tx.get("topics", topic_id)
            if not topic or topic["subject_id"] != book["subject_id"] or topic["archived"]:
                raise ValueError("Choose a reading section in this subject")
        active = next((j for j in tx.find("book_imports", book_id=book_id) if j["status"] in ("queued", "running")), None)
        if active:
            return active
        doc = tx.get("documents", book["document_id"])
        return tx.insert("book_imports", {"id": "import-" + uuid.uuid4().hex, "book_id": book_id,
            "mode": "rematch", "target_topic_id": topic_id, "status": "queued", "stage": "Improving remaining reading links",
            "done": doc["page_count"], "total": doc["page_count"], "source_path": doc["file_path"], "source_sha256": doc["sha256"],
            "index_id": "index-" + uuid.uuid4().hex})

    def _index_answers(self, book, doc):
        from .book_sources import index_answers
        index_answers(self, book, doc)

    def page_index(self, doc, role):
        pages = {}
        for unit in self.db.find("book_units", sha256=doc["sha256"], role=role, version=scan_version(role)):
            unit = resolve_scan(self.db, unit)
            for page in unit["data"]["pages"]:
                pages[page["page"]] = page
        return pages

    def topic_text(self, topic):
        doc = self.db.get("documents", topic["document_id"])
        first, last = passages.pdf_range(topic)
        draft = passages.extract(self.ctx.file_bytes(doc['file_path'], doc['sha256']), first, last,
                                 topic.get('start_at'), topic.get('stop_before'))
        return draft['passage'] if not draft['issues'] else ''

    def process(self, job_id):
        with self.lock:
            job = self.db.get("book_imports", job_id)
            if not job or job["status"] not in ("queued", "running"):
                return
            try:
                self._process(job)
            except Exception as exc:
                log.warning("Book import %s paused: %s", job_id, type(exc).__name__)
                detail = str(exc)[:800]
                if "prepayment credits are depleted" in detail.lower():
                    detail = "Gemini's prepaid credits are exhausted. Your scanned pages are saved. Add credits in AI Studio, then retry remaining work."
                with self.db.transaction(kind="books.failed") as tx:
                    tx.update("book_imports", job_id, {"status": "failed", "error": detail})
                    tx.update("subject_books", job["book_id"], {"status": "ready" if job.get("mode") == "rematch" else "failed"})

    def _process(self, job):
        book = self.db.get("subject_books", job["book_id"])
        with self.db.transaction(kind="books.running") as tx:
            if job.get("mode") != "rematch":
                tx.update("subject_books", book["id"], {"status": "running"})
        doc = self.db.get("documents", book["document_id"])
        pdf = self.ctx.file_bytes(doc["file_path"], job["source_sha256"])
        from . import navigation
        nav = navigation.extract(self.ctx, doc)
        if book['role'] in (*READING_ROLES, 'workbook', 'test'):
            navigation.publish_topics(self, book, doc, nav)
        with self.db.transaction(kind='books.navigation_ready') as tx:
            tx.update('subject_books', book['id'], {'status': 'ready', 'active_index': nav['id']})
            tx.update('book_imports', job['id'], {'status': 'ready', 'stage': 'Chapter map ready' if nav['data']['chapters'] else 'Choose chapter pages',
                'done': len(nav['data']['toc_pages']), 'total': len(nav['data']['toc_pages']), 'error': None, 'pending_ranges': []})
        self._move(job, book, doc, pdf)

    def _stage(self, job_id, stage):
        with self.db.transaction(kind="books.stage") as tx:
            tx.update("book_imports", job_id, {"stage": stage})

    def _topics(self, book, doc, *, allow_partial=False):
        from . import navigation
        return navigation.publish_topics(self, book, doc, navigation.extract(self.ctx, doc))

    def _raw_exercises(self, book, doc):
        items = []
        occurrences = {}
        pages = self.page_index(doc, book["role"])
        for unit in sorted(self.db.find("book_units", sha256=doc["sha256"], role=book["role"], version=scan_version(book["role"])), key=lambda u: u["first_page"]):
            unit = resolve_scan(self.db, unit)
            for raw in unit["data"]["exercises"]:
                raw = dict(raw)
                if any(pages.get(p, {}).get("teacher_material") for p in raw["pages"]):
                    continue
                if not all(pages.get(p, {}).get("student_safe") for p in raw["pages"]):
                    raw["issue"] = raw.get("issue") or "The source page includes private or unchecked material"
                if book["role"] == "test":
                    known = next((c for c in self.db.find("chapters", subject_id=book["subject_id"]) if c["test_document_id"] == doc["id"]
                        and c["test_pdf_start"] and c["test_pdf_end"] and c["test_pdf_start"] <= min(raw["pages"]) <= c["test_pdf_end"]), None)
                    if known and raw.get("chapter") is None:
                        raw["chapter"] = known["chapter"]
                    elif known and raw["chapter"] != known["chapter"]:
                        raw["issue"] = "The chapter label conflicts with the reviewed source range"
                number = question_number(raw["reference"])
                start_page = next((p for p in sorted(raw["pages"]) if number is not None and number in
                    {int(q) for q in re.findall(r"(?m)^\s*(\d+)[.)]\s", pages.get(p, {}).get("text", ""))}), min(raw["pages"]))
                source_identity = (start_page, number if number is not None else "activity")
                occurrences[source_identity] = occurrences.get(source_identity, 0) + 1
                exercise_id = "exercise-" + ident(book["id"], *source_identity, occurrences[source_identity])
                items.append({**raw, "exercise_id": exercise_id})
        return items

    def _check_catalog(self, book, doc, catalog):
        if book["role"] != "test":
            return
        pages = self.page_index(doc, book["role"])
        original = numbered_source(self.ctx, doc["sha256"], {n: p["text"] for n,p in pages.items()}, 1, doc["page_count"])
        missing_pages = {page for chapter,page,number in original if sum(e.get("chapter") == chapter and question_number(e["reference"]) == number
            and page in e["pages"] for e in catalog) != 1}
        chapters = {c["chapter"]: c for c in self.db.find("chapters", subject_id=book["subject_id"]) if c["test_document_id"] == doc["id"]}
        for mapping in self.db.find("question_maps", subject_id=book["subject_id"]):
            chapter = chapters.get(mapping["chapter"])
            if chapter and not any(e.get("chapter") == mapping["chapter"] and question_number(e["reference"]) == mapping["question"] for e in catalog):
                missing_pages.update(range(chapter["test_pdf_start"], chapter["test_pdf_end"] + 1))
        if missing_pages:
            # These units did not finish their exercise inventory. Leave all valid units cached.
            with self.db.transaction(kind="books.incomplete_inventory") as tx:
                for page in missing_pages:
                    first = ((page - 1) // UNIT_PAGES) * UNIT_PAGES + 1
                    unit_id = ident(doc["sha256"], book["role"], SCAN_VERSION, first)
                    if tx.get("book_units", unit_id):
                        tx.delete("book_units", unit_id)
            raise ValueError(f"Some original questions on PDF pages {sorted(missing_pages)[:12]} need another scan. Retry remaining work")

    def _matches(self, book, doc, companion, job):
        topics = [t for t in self.db.find("topics", subject_id=book["subject_id"], document_id=companion["document_id"]) if not t.get("archived")]
        texts = {t["id"]: self.topic_text(t) for t in topics}
        catalog = self._raw_exercises(book, doc)
        self._check_catalog(book, doc, catalog)
        from .book_sources import match_remaining
        results = match_remaining(self, book, doc, topics, texts, catalog, job)
        # Reviewed History maps and known exceptions override guesses without being re-derived.
        test_chapters = {c["chapter"] for c in self.db.find("chapters", subject_id=book["subject_id"]) if c["test_document_id"] == doc["id"]}
        for item in catalog:
            if book["role"] != "test" or item.get("chapter") not in test_chapters:
                continue
            number = question_number(item["reference"])
            if number is None:
                continue
            existing = next((m for m in self.db.find("question_maps", subject_id=book["subject_id"])
                             if m["chapter"] == item.get("chapter") and m["question"] == number), None)
            if existing and existing["topic_id"] in texts:
                boundaries = {k: self.db.get("topics", existing["topic_id"]).get(k) for k in ("document_id", "page_start", "page_end", "pdf_page_offset", "start_at", "stop_before")}
                exercise = self.db.get("exercises", item["exercise_id"])
                previous = self.snapshot(exercise) if exercise else None
                if previous and previous["data"].get("mapping_boundaries") and previous["data"]["mapping_boundaries"] != boundaries:
                    results[item["exercise_id"]] = {"requirements": [], "status": "needs_review", "mapping_note": "Reading boundaries changed; confirm the reviewed mapping"}
                    continue
                results[item["exercise_id"]] = {"requirements": [{"topic_id": existing["topic_id"], "evidence": existing["evidence"]}],
                    "status": "matched", "mapping_note": "Preserved reviewed History mapping", "mapping_source": "reviewed_import", "mapping_boundaries": boundaries}
                key = next((k for k in self.db.find("teacher_keys", subject_id=book["subject_id"])
                    if k["chapter"] == item["chapter"] and k["question_start"] <= number <= k["question_end"]), None)
                if key:
                    results[item["exercise_id"]].update(answer=key["answer"], exception=key["exception"])
        return results

    def _publish(self, book, doc, job, matches, status):
        from .book_sources import key_for, identity_counts
        pages = self.page_index(doc, book["role"])
        catalog = self._raw_exercises(book, doc)
        counts = identity_counts(catalog)
        active_ids = {item["exercise_id"] for item in catalog}
        with self.db.transaction(kind="books.publish") as tx:
            for item in catalog:
                ex_id = item.pop("exercise_id")
                data = {**item, **matches.get(ex_id, {"requirements": [], "status": "waiting" if status == "waiting" else "needs_review"}),
                    "source_sha256": doc["sha256"], "book_name": book_name(doc["original_filename"]),
                    "student_safe": all(p in pages and pages[p]["student_safe"] and not pages[p].get("issue") for p in item["pages"])}
                if item.get("issue"):
                    data["status"] = "needs_review"
                exercise = tx.get("exercises", ex_id)
                previous = tx.get("exercise_versions", exercise["active_version"]) if exercise and exercise["active_version"] else None
                if previous and previous["parent_edited"]:
                    data = dict(previous["data"])
                    if not all(tx.get("topics", r["topic_id"]) and norm(r["evidence"]) in norm(self.topic_text(tx.get("topics", r["topic_id"]))) for r in data.get("requirements", [])):
                        data.update(status="needs_review", mapping_note="The reading changed; check your saved mapping")
                data.update(key_for(self, book, data, counts))
                if not exercise:
                    tx.insert("exercises", {"id": ex_id, "book_id": book["id"]})
                ver_id = "version-" + ident(ex_id, data)
                if not tx.get("exercise_versions", ver_id):
                    tx.insert("exercise_versions", {"id": ver_id, "exercise_id": ex_id, "index_id": job["index_id"], "data": data,
                        "parent_edited": bool(previous and previous["parent_edited"])})
                tx.update("exercises", ex_id, {"active_version": ver_id, "archived": False})
                self._link_legacy(tx, book, ex_id, data)
            for previous in tx.find("exercises", book_id=book["id"]):
                if previous["id"] not in active_ids:
                    tx.update("exercises", previous["id"], {"archived": True})
            tx.update("subject_books", book["id"], {"active_index": job["index_id"], "status": status})
            if status == "waiting":
                tx.update("book_imports", job["id"], {"status": "waiting", "stage": "Waiting for textbook"})

    def _move(self, job, book, doc, pdf):
        if not job["source_path"].startswith(layout.INCOMING_BOOKS + "/"):
            return
        if doc["file_path"] != job["source_path"] and not job.get("destination_path"):
            return  # Another child's import already filed this shared source.
        # Shared assigned sources are left in place. Only the intake copy is consumed.
        folder = layout.for_subject(self.db, book["subject_id"], layout.BOOKS)
        with self.db.transaction(kind="books.destination") as tx:
            path, sha = tx.add_blob(pdf, folder, doc["original_filename"], "application/pdf")
            if sha != job["source_sha256"]:
                raise ValueError("The destination book failed verification")
            tx.update("documents", doc["id"], {"file_path": path})
            tx.update("book_imports", job["id"], {"destination_path": path})
        self.ctx.files.read(path, job["source_sha256"])
        source = self.ctx.files.resolve(job["source_path"])
        if source.exists():
            if hashlib.sha256(source.read_bytes()).hexdigest() != job["source_sha256"]:
                log.info("Retained the changed incoming file for import %s", job["id"])
                return  # Our verified destination is saved; this is now a different incoming book.
            if not any(d["file_path"] == job["source_path"] for d in self.db.all("documents")):
                self.ctx.files.remove(job["source_path"])

    def snapshot(self, exercise):
        return self.db.get("exercise_versions", exercise["active_version"])

    def _link_legacy(self, tx, book, exercise_id, data):
        """Connect explicit old numbered answers without rewriting their immutable records."""
        chapter = next((c for c in tx.find("chapters", subject_id=book["subject_id"])
            if c["chapter"] == data.get("chapter") and c["test_document_id"] == book["document_id"]), None)
        number = question_number(data["reference"])
        if book["role"] != "test" or not chapter or number is None:
            return
        child_id = tx.get("subjects", book["subject_id"])["child_id"]
        for attempt in tx.find("attempts", child_id=child_id, chapter=chapter["chapter"]):
            named = re.match(r"^Q(\d+)(?:\s*/|$)", attempt["question_ref"], re.I)
            topic = tx.get("topics", attempt["topic_id"])
            if not named or int(named[1]) != number or topic["subject_id"] != book["subject_id"]:
                continue
            link_id = "legacy-" + ident(exercise_id, attempt["id"])
            if not tx.get("exercise_attempt_links", link_id):
                tx.insert("exercise_attempt_links", {"id": link_id, "exercise_id": exercise_id, "attempt_id": attempt["id"]})

    def attempts(self, exercise_id, child_id):
        attempts = {a["id"]: a for a in self.db.find("attempts", exercise_id=exercise_id, child_id=child_id)}
        for link in self.db.find("exercise_attempt_links", exercise_id=exercise_id):
            attempt = self.db.get("attempts", link["attempt_id"])
            if attempt["child_id"] == child_id:
                attempts[attempt["id"]] = attempt
        return sorted(attempts.values(), key=lambda a: (a["created_at"], a["id"]))

    @staticmethod
    def legacy_completed(attempts):
        return bool(attempts) and (attempts[-1]["after_help_result"] or attempts[-1]["first_result"]) in ("Correct", "With help")

    @staticmethod
    def public(data):
        result = {k: v for k, v in data.items() if k not in ("answer", "exception", "answer_source", "source_sha256", "mapping_source", "mapping_boundaries")}
        if data.get("student_safe") is False and not data.get("source_reviewed"):
            result.update(prompt="The exercise instructions need source review before student use.",
                choices=[], answer_format="text", issue="This source contains private or unchecked material", mapping_note="Parent source review required")
        return result

    def exercises(self, book_id):
        book = self.db.get("subject_books", book_id)
        if not book:
            raise ValueError("Unknown book")
        if book["role"] == "answer_key":
            return []
        subject = self.db.get("subjects", book["subject_id"])
        result = []
        for ex in self.db.find("exercises", book_id=book_id):
            if ex.get("archived"):
                continue
            version = self.snapshot(ex)
            if not version:
                continue
            items = self.db.find("assignment_items", exercise_id=ex["id"], child_id=subject["child_id"])
            attempts = self.attempts(ex["id"], subject["child_id"])
            latest = max(items, key=lambda x: x["created_at"], default=None)
            actions = self.db.find("lesson_actions", child_id=subject["child_id"])
            linked_actions = [a for a in actions if any(i["id"] == a.get("assignment_item_id") for i in items)]
            messages = [m for a in linked_actions for m in self.db.find("lesson_dialogue", session_id=a["session_id"], action_id=a["action_id"])]
            feedback = [m["text"] for m in messages if m["role"] == "teacher"]
            submissions = [{"text": m["text"], "created_at": m["created_at"], "status": m["status"]} for m in messages if m["role"] == "student"]
            evidence_paths = {path for a in attempts for path in (a["evidence_paths"] or [])}
            submitted_ids = {e for m in messages for e in (m["evidence_ids"] or [])}
            evidence = [{"id": e["id"], "filename": e["filename"]} for e in self.db.find("evidence_files", child_id=subject["child_id"]) if e["file_path"] in evidence_paths or e["id"] in submitted_ids]
            result.append({"id": ex["id"], "version_id": version["id"], "revision": ex["revision"], "document_id": book["document_id"],
                **self.public(version["data"]), "work_status": latest["status"] if latest else "reviewed" if self.legacy_completed(attempts) else "pending" if attempts else "available",
                "assignment_item_id": latest["id"] if latest else None,
                "ready_for_practice": bool(version["data"].get("requirements")) and all(self.db.get("topics", r["topic_id"])["completed"] for r in version["data"].get("requirements", [])),
                "feedback": feedback, "evidence": evidence, "submissions": submissions,
                "attempts": [{k:a[k] for k in ("id", "first_answer", "first_result", "help_given", "revised_answer", "after_help_result", "independence", "amends_attempt_id")} for a in attempts]})
        return sorted(result, key=lambda x: (min(x["pages"]), x["reference"]))

    def edit(self, tx, exercise_id, revision, requirements, optional, prompt=None, source_reviewed=False):
        exercise = tx.get("exercises", exercise_id)
        if not exercise:
            raise ValueError("Unknown exercise")
        book = tx.get("subject_books", exercise["book_id"])
        data = dict(tx.get("exercise_versions", exercise["active_version"])["data"])
        if prompt is not None and prompt.strip() != data["prompt"]:
            if not source_reviewed or not prompt.strip():
                raise ValueError("Check the corrected instructions against the source page first")
            data.update(prompt=prompt.strip(), issue=None, source_reviewed=True)
        elif source_reviewed:
            data.update(issue=None, source_reviewed=True)
        for req in requirements:
            topic = tx.get("topics", req["topic_id"])
            if not topic or topic["subject_id"] != book["subject_id"] or topic.get("archived"):
                raise ValueError("Choose reading sections in this subject")
            if len(norm(req["evidence"])) < 12 or norm(req["evidence"]) not in norm(self.topic_text(topic)):
                raise ValueError("Supporting evidence must quote the selected reading section")
        data.update(requirements=requirements, optional=optional, status="matched" if requirements and not data.get("issue") else "needs_review")
        version_id = "version-" + uuid.uuid4().hex
        tx.insert("exercise_versions", {"id": version_id, "exercise_id": exercise_id, "index_id": book["active_index"], "data": data, "parent_edited": True})
        tx.update("exercises", exercise_id, {"active_version": version_id}, expected_revision=revision)
        return version_id

    def reading_changed(self, tx, topic):
        for book in tx.find("subject_books", subject_id=topic["subject_id"]):
            companion = tx.get("subject_books", book["companion_id"]) if book["companion_id"] else None
            if book["role"] not in PRACTICE_ROLES or not companion or companion["document_id"] != topic["document_id"]:
                continue
            if any(j["status"] in ("queued", "running") for j in tx.find("book_imports", book_id=book["id"])):
                continue
            doc = tx.get("documents", book["document_id"])
            tx.insert("book_imports", {"id": "import-" + uuid.uuid4().hex, "book_id": book["id"], "status": "queued", "stage": "Linking to lessons",
                "done": doc["page_count"], "total": doc["page_count"], "source_path": doc["file_path"], "source_sha256": doc["sha256"],
                "index_id": "index-" + uuid.uuid4().hex})
            tx.update("subject_books", book["id"], {"status": "queued"})

    def eligible(self, topic, include_optional=False):
        subject = self.db.get("subjects", topic["subject_id"])
        result = []
        for book in self.db.find("subject_books", subject_id=subject["id"]):
            if book["archived"] or book["status"] != "ready" or book["role"] not in PRACTICE_ROLES:
                continue
            for exercise in self.db.find("exercises", book_id=book["id"]):
                if exercise.get("archived"):
                    continue
                version = self.snapshot(exercise)
                d = version["data"]
                reqs = d.get("requirements") or []
                if d["status"] != "matched" or d.get("issue") or (d["optional"] and not include_optional):
                    continue
                if not any(r["topic_id"] == topic["id"] for r in reqs):
                    continue
                if not all(r["topic_id"] == topic["id"] or self.db.get("topics", r["topic_id"])["completed"] for r in reqs):
                    continue
                assigned = self.db.find("assignment_items", exercise_id=exercise["id"], child_id=subject["child_id"])
                if any(a["status"] == "reviewed" for a in assigned):
                    continue
                if not assigned and self.legacy_completed(self.attempts(exercise["id"], subject["child_id"])):
                    continue
                result.append({"id": exercise["id"], "version_id": version["id"], **self.public(d)})
        return sorted(result, key=lambda x: (x["book_name"], min(x["pages"]),
            (0, question_number(x["reference"])) if question_number(x["reference"]) is not None else (1, x["reference"])))

    def fingerprint(self, subject_id):
        values = [(b["id"], b["active_index"], b["status"], b["archived"], b["role"], b["companion_id"]) for b in self.db.find("subject_books", subject_id=subject_id)]
        values += [(e["id"], e["active_version"]) for b in self.db.find("subject_books", subject_id=subject_id)
                   for e in self.db.find("exercises", book_id=b["id"])]
        return ident(sorted(values, key=lambda x: x[0]))

    def assign_item(self, tx, session, exercise_id, version_id):
        ex = tx.get("exercises", exercise_id)
        ver = tx.get("exercise_versions", version_id)
        book = tx.get("subject_books", ex["book_id"]) if ex else None
        if not book or book["subject_id"] != session["subject_id"] or not ver or ver["exercise_id"] != exercise_id:
            raise ValueError("This exercise does not belong to the session")
        if book["role"] == "answer_key":
            raise ValueError("Answer keys cannot provide student assignments")
        if ver["data"]["status"] != "matched" or ver["data"].get("issue"):
            raise ValueError("This exercise's source needs review before assignment")
        existing = next((i for i in tx.find("assignment_items", exercise_id=exercise_id, child_id=session["child_id"])
                         if i["status"] != "reviewed"), None)
        if existing:
            return existing
        assignment_id = f"{session['id']}-workbook"
        if not tx.get("assignments", assignment_id):
            tx.insert("assignments", {"id": assignment_id, "session_id": session["id"], "child_id": session["child_id"],
                "topic_id": session["topic_id"], "questions": [], "status": "assigned", "note": "Workbook exercises"})
        return tx.insert("assignment_items", {"id": "item-" + ident(session["id"], exercise_id), "assignment_id": assignment_id,
            "exercise_id": exercise_id, "version_id": version_id, "child_id": session["child_id"], "topic_id": session["topic_id"],
            "status": "assigned", "snapshot": ver["data"]})


class ImportWorker(threading.Thread):
    def __init__(self, service):
        super().__init__(name="book-preparation", daemon=True)
        self.service, self.stopping = service, threading.Event()

    def run(self):
        while not self.stopping.is_set():
            jobs = [j for j in self.service.db.all("book_imports") if j["status"] in ("queued", "running")]
            # Textbooks before their companion workbook when both are uploaded together.
            jobs.sort(key=lambda j: (self.service.db.get("subject_books", j["book_id"])["role"] not in READING_ROLES, j["created_at"]))
            for job in jobs:
                if self.stopping.is_set():
                    break
                self.service.process(job["id"])
            self.stopping.wait(2)

    def stop(self):
        self.stopping.set()
