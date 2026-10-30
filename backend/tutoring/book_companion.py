"""Portable, source-bound book representations shared by Codex and in-app analysis.

Draft extraction never certifies a page. Only checked, complete scan units enter
the existing book cache; private keys use the same separation as book preparation.
The PDF remains the original. No learner records belong in this format.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pypdf import PdfReader

from storage import layout
from storage.store import RevisionConflict
from . import books

FORMAT = "homeschooling.book-companion"
VERSION = 1
MAX_JSON_BYTES = 32 * 1024 * 1024


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Element(StrictModel):
    id: str = Field(min_length=1, max_length=150)
    kind: Literal["text", "illustration", "diagram", "table", "formula", "answer_space", "decoration"]
    text: str = Field(default="", max_length=20000)
    description: str = Field(default="", max_length=12000)
    # Normalized [left, top, right, bottom], when inspected. Never guessed.
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    rows: list[list[str]] = Field(default_factory=list, max_length=100)
    expression: str | None = Field(default=None, max_length=4000)
    relates_to: list[str] = Field(default_factory=list, max_length=100)
    issue: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def bounds(self):
        if self.bbox is not None:
            left, top, right, bottom = self.bbox
            if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
                raise ValueError("Element coordinates must be normalized, ordered page bounds")
        if sum(len(c) for row in self.rows for c in row) > 40000:
            raise ValueError("A table is too large")
        return self


class Page(StrictModel):
    page: int = Field(ge=1)
    printed_page: str | None = Field(default=None, max_length=40)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    native_text: str = Field(max_length=100000)
    text: str = Field(max_length=100000)
    status: Literal["native_draft", "checked", "needs_review"] = "native_draft"
    review_method: Literal["native_checked", "visual"] | None = None
    issues: list[str] = Field(default_factory=list, max_length=30)
    notes: list[str] = Field(default_factory=list, max_length=30)
    student_safe: bool = False
    teacher_material: bool = False
    headings: list[str] = Field(default_factory=list, max_length=100)
    reading_blocks: list[str] = Field(default_factory=list, max_length=300)
    elements: list[Element] = Field(default_factory=list, max_length=300)


class Source(StrictModel):
    filename: str = Field(min_length=1, max_length=500)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_count: int = Field(ge=1, le=10000)
    role: Literal["textbook", "combined", "workbook", "test", "answer_key", "reference"]
    edition: str = Field(default="", max_length=150)
    language: str = Field(default="", max_length=40)
    text_extractor: str = Field(default='pypdf',max_length=100)


class SourceSection(StrictModel):
    id:str=Field(min_length=1,max_length=150)
    title:str=Field(min_length=1,max_length=200)
    kind:Literal['lesson','unit','chapter','teacher_tip','front_matter','assessment','appendix']
    number:int | None=Field(default=None,ge=1)
    part:str=Field(default='',max_length=100)
    pages:list[int]=Field(min_length=1,max_length=10000)
    printed_page:str=Field(default='',max_length=40)


class Exercise(books.ScannedExercise):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=150)


class TeacherOnly(StrictModel):
    answers: list[books.ScannedKeyAnswer] = Field(default_factory=list, max_length=10000)


class Companion(StrictModel):
    format: Literal["homeschooling.book-companion"] = FORMAT
    format_version: Literal[1] = VERSION
    source: Source
    producer: str = Field(min_length=1, max_length=200)
    pages: list[Page] = Field(min_length=1, max_length=10000)
    sections:list[SourceSection]=Field(default_factory=list,max_length=10000)
    exercises: list[Exercise] = Field(default_factory=list, max_length=10000)
    teacher_only: TeacherOnly = Field(default_factory=TeacherOnly)

    @model_validator(mode="after")
    def coverage(self):
        if [p.page for p in self.pages] != list(range(1, self.source.page_count + 1)):
            raise ValueError("Include every PDF page exactly once, in original order")
        ids = [e.id for e in self.exercises] + [e.id for p in self.pages for e in p.elements] + [s.id for s in self.sections]
        if len(ids) != len(set(ids)):
            raise ValueError("Element and exercise identities must be unique throughout the book")
        known = set(ids)
        for section in self.sections:
            if section.pages!=sorted(set(section.pages)) or not 1<=min(section.pages)<=max(section.pages)<=self.source.page_count:
                raise ValueError('A source section must identify ordered pages in its exact PDF')
        for page in self.pages:
            if page.status == "checked" and (not page.review_method or page.issues or any(e.issue for e in page.elements)):
                raise ValueError("A checked page needs a review method and no unresolved issues")
            if page.student_safe and page.teacher_material:
                raise ValueError("Teacher material cannot be student-safe")
            if any(books.norm(b) not in books.norm(page.text) or not books.norm(b) for b in page.reading_blocks + page.headings):
                raise ValueError("Reading blocks and headings must quote the page transcription")
            for element in page.elements:
                if any(ref not in known for ref in element.relates_to):
                    raise ValueError("An element points to an unknown exercise or element")
        for exercise in self.exercises:
            if exercise.answer is not None:
                raise ValueError("Exercise answers belong only in teacher_only.answers")
            if not exercise.pages or min(exercise.pages) < 1 or max(exercise.pages) > self.source.page_count:
                raise ValueError("An exercise references a page outside this book")
            if any(self.pages[n - 1].teacher_material for n in exercise.pages) and not exercise.issue:
                raise ValueError("An exercise proposal on a teacher page must remain flagged for source review")
        if self.teacher_only.answers and self.source.role not in ("combined", "answer_key"):
            raise ValueError("This book role cannot contain private answer entries")
        for answer in self.teacher_only.answers:
            if not answer.pages or min(answer.pages) < 1 or max(answer.pages) > self.source.page_count:
                raise ValueError("An answer references a page outside this book")
            if not answer.issue and not books.key_evidence_supported(answer.model_dump(), [p.model_dump() for p in self.pages]):
                raise ValueError("An answer must quote supporting evidence from its original key page")
            if any(not self.pages[n - 1].teacher_material for n in answer.pages):
                raise ValueError("Answer-key source pages must be private teacher material")
        if self.source.role == "answer_key" and (self.exercises or any(p.student_safe or not p.teacher_material for p in self.pages)):
            raise ValueError("All answer-key pages must remain teacher material")
        return self


class Envelope(StrictModel):
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    contents: Companion


def digest(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def row_id(sha, role):
    return "companion-" + books.ident(sha, role, VERSION)


def source_for(ctx, subject_id, document_id):
    from .collections import view
    source = next((b for b in view(ctx.store, subject_id)["books"] if b["document_id"] == document_id), None)
    if not source:
        raise ValueError("Choose a book in this subject's collection")
    return source, ctx.store.get("documents", document_id)


def summary(row):
    if not row:
        return {"revision": 0, "status": "not_created", "checked_pages": 0, "pending_pages": 0}
    body = row["data"]
    checked = sum(p["status"] == "checked" for p in body["pages"])
    pending_exercises = sum(bool(e.get("issue")) for e in body["exercises"])
    pending_answers = sum(bool(a.get("issue")) for a in body["teacher_only"]["answers"])
    return {"revision": row["revision"], "status": "checked" if checked == len(body["pages"]) and not pending_exercises and not pending_answers else "needs_review",
            "checked_pages": checked, "pending_pages": len(body["pages"]) - checked,
            "pages": len(body["pages"]), "exercises": len(body["exercises"]),
            "pending_exercises": pending_exercises, "pending_answers": pending_answers,
            "visual_elements": sum(e["kind"] in ("illustration", "diagram", "table", "formula") for p in body["pages"] for e in p["elements"]),
            "content_sha256": row["content_sha256"], "path": row["file_path"], "format_version": VERSION}


def inventory(ctx, subject_id):
    from .collections import view
    return [{"document_id": b["document_id"], "name": b["name"], "role": b["role"], "page_count": b["page_count"],
             **summary(ctx.store.get("book_companions", row_id(b["sha256"], b["role"])))}
            for b in view(ctx.store, subject_id)["books"]]


def native(pdf, filename, role, edition=""):
    reader = PdfReader(io.BytesIO(pdf))
    pages = []
    for n, page in enumerate(reader.pages, 1):
        raw = page.extract_text() or ""
        # Keep exact extraction separately. Licensing watermarks are not teaching text.
        text = re.sub(r"(?m)^Licenciado para - .*?(?:\n|$)", "", raw).strip()
        issues = ["Visual structure and exercise inventory have not been checked"]
        if re.search(r"/[a-z]\.beg|\ufffd", text):
            issues.append("Font extraction artifacts require comparison with the PDF")
        if len(text) < 40:
            issues.append("Little native text; inspect the PDF for scanned content or front matter")
        pages.append(Page(page=n, width=float(page.mediabox.width), height=float(page.mediabox.height),
                          native_text=raw, text=text, issues=issues, teacher_material=role == "answer_key").model_dump())
    return Companion(source=Source(filename=filename, sha256=hashlib.sha256(pdf).hexdigest(), page_count=len(pages),
                                    role=role, edition=edition), producer="Homeschooling native extraction", pages=pages).model_dump()


def link_element_references(pages, exercises):
    known = {e["id"] for p in pages for e in p.get("elements", [])} | {e["id"] for e in exercises}
    for page in pages:
        for element in page.get("elements", []):
            refs = []
            for ref in element.get("relates_to", []):
                if ref in known:
                    refs.append(ref)
                    continue
                candidates = [e["id"] for e in exercises if page["page"] in e["pages"] and books.norm(e["reference"]) == books.norm(ref)]
                if len(candidates) == 1:
                    refs.append(candidates[0])
                else:
                    issue = f"Visual task reference needs checking: {ref}"
                    element["issue"] = element.get("issue") or issue
                    page.setdefault("issues", []).append(issue)
                    page["status"] = "needs_review"
            element["relates_to"] = list(dict.fromkeys(refs))


def from_scans(ctx, source, doc):
    old = ctx.store.get("book_companions", row_id(doc["sha256"], source["role"]))
    body = copy.deepcopy(old["data"]) if old else native(ctx.file_bytes(doc["file_path"], doc["sha256"]),
                                                        books.book_name(doc["original_filename"]), source["role"], source.get("edition", ""))
    body["producer"] = "Homeschooling checked source scans"
    exercises, answers, scanned = [], [], set()
    for unit in ctx.store.find("book_units", sha256=doc["sha256"], role=source["role"], version=books.scan_version(source["role"])):
        unit = books.resolve_scan(ctx.store, unit)
        for raw in unit["data"]["pages"]:
            n = raw["page"]
            page = body["pages"][n - 1]
            issues = ([raw["issue"]] if raw.get("issue") else []) + [e["issue"] for e in raw.get("elements", []) if e.get("issue")]
            values = {k: raw[k] for k in ("text", "student_safe", "teacher_material", "headings", "reading_blocks") if k in raw}
            elements = [{**e, "id": e.get("id") or f"p{n}:element:{i + 1}"} for i, e in enumerate(raw.get("elements", []))]
            method = {"native": "native_checked", "vision": "visual", "native text checked against page image": "native_checked"}.get(raw.get("review_method"), raw.get("review_method") or "visual")
            if method not in ("native_checked", "visual"):
                issues.append("The scan's review method needs checking")
                method = None
            page.update(values, status="needs_review" if issues else "checked", review_method=method, issues=issues,
                        notes=raw.get("review_notes", []), elements=elements)
            page["printed_page"] = raw.get("printed_page") or page.get("printed_page")
            if source["role"] == "answer_key":
                page.update(student_safe=False, teacher_material=True)
            scanned.add(n)
        for i, exercise in enumerate(unit["data"].get("exercises", [])):
            if any(body["pages"][n - 1]["teacher_material"] for n in exercise["pages"]):
                exercise = {**exercise, "issue": exercise.get("issue") or "Source includes teacher material; check the exercise and page classification"}
            ids = unit["data"].get("exercise_ids", [])
            eid = ids[i] if i < len(ids) else "exercise-" + books.ident(doc["sha256"], source["role"], unit["first_page"], i)
            exercises.append({**exercise, "answer": None, "id": eid})
        answers.extend(unit["data"].get("answers", []))
    # Partial Codex drafts can contain inspected pages not yet promoted as a full cache unit.
    body["exercises"] = [e for e in body["exercises"] if min(e["pages"]) not in scanned] + exercises
    body["teacher_only"]["answers"] = [a for a in body["teacher_only"]["answers"] if min(a["pages"]) not in scanned] + answers
    link_element_references(body["pages"], body["exercises"])
    return Companion.model_validate(body).model_dump()


def persist(ctx, tx, subject_id, doc, body, expected_revision=None):
    body = Companion.model_validate(body).model_dump()
    sha = digest(body)
    key = row_id(doc["sha256"], body["source"]["role"])
    previous = tx.get("book_companions", key)
    if expected_revision is not None and expected_revision != (previous["revision"] if previous else 0):
        raise RevisionConflict("This book representation changed. Reload before importing.", summary(previous))
    if previous and previous["content_sha256"] == sha:
        return previous
    envelope = {"content_sha256": sha, "contents": body}
    payload = json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8")
    name = f"{books.book_name(doc['original_filename']).rsplit('.', 1)[0]}-{body['source']['role']}-{sha[:12]}.book.json"
    path, file_sha = tx.add_blob(payload, layout.for_subject(tx, subject_id, layout.BOOKS), name, "application/json")
    values = {"document_id": doc["id"], "sha256": doc["sha256"], "role": body["source"]["role"],
              "content_sha256": sha, "data": body, "file_path": path, "file_sha256": file_sha}
    return tx.update("book_companions", key, values) if previous else tx.insert("book_companions", {"id": key, **values})


def refresh(ctx, subject_id, document_id):
    source, doc = source_for(ctx, subject_id, document_id)
    # PDF IO and extraction happen outside the write transaction.
    prior = ctx.store.get("book_companions", row_id(doc["sha256"], source["role"]))
    body = from_scans(ctx, source, doc)
    with ctx.store.transaction(kind="books.companion", summary="Saved a source-bound book JSON without learner records") as tx:
        return persist(ctx, tx, subject_id, doc, body, prior["revision"] if prior else 0)


def unit_data(body, first, last):
    pages = body['pages'][first - 1:last]
    return {"pages": [{"page": p["page"], "text": p["text"], "student_safe": p["student_safe"],
                       "native_reliable": False, "teacher_material": p["teacher_material"],
                       "issue": '; '.join(p['issues']) or (None if p['status'] == 'checked' else 'Source page needs review'),
                       "headings": p["headings"], "reading_blocks": p["reading_blocks"], "printed_page": p["printed_page"],
                       "elements": p["elements"], "review_method": p["review_method"], "review_notes": p.get('notes', [])} for p in pages],
            "exercises": [{k: v for k, v in e.items() if k != "id"} for e in body["exercises"] if first <= min(e["pages"]) <= last],
            "exercise_ids": [e["id"] for e in body["exercises"] if first <= min(e["pages"]) <= last],
            "answers": [a for a in body["teacher_only"]["answers"] if first <= min(a["pages"]) <= last]}


def units(body):
    count = body["source"]["page_count"]
    role = body["source"]["role"]
    for first in range(1, count + 1, books.UNIT_PAGES):
        last = min(first + books.UNIT_PAGES - 1, count)
        pages = body["pages"][first - 1:last]
        if not all(p["status"] == "checked" for p in pages):
            continue
        yield first, last, unit_data(body, first, last)


def import_file(ctx, tx, subject_id, document_id, payload, expected_revision, *, source_review=False, note=''):
    source, doc = source_for(ctx, subject_id, document_id)
    envelope = Envelope.model_validate(payload)
    body = envelope.contents.model_dump()
    # Hash the parsed source object before normalization too: no undetected edits.
    if digest(payload["contents"]) != envelope.content_sha256:
        raise ValueError("This JSON checksum does not match its contents")
    src = body["source"]
    if (src["sha256"], src["page_count"], src["role"], src["edition"]) != (doc["sha256"], doc["page_count"], source["role"], source.get("edition", "")):
        raise ValueError("This JSON belongs to a different PDF, page count, role or edition")
    current = tx.get("book_companions", row_id(doc["sha256"], source["role"]))
    if current and any(a['native_text'] != b['native_text'] for a,b in zip(current['data']['pages'], body['pages'])):
        raise ValueError('Keep the original automatic extraction unchanged; corrections belong in page transcription')
    if current and current["content_sha256"] == digest(body):
        return persist(ctx, tx, subject_id, doc, body, expected_revision)
    related = {s["collection_id"] for s in tx.find("collection_books", document_id=document_id)}
    if any(j["collection_id"] in related and j["status"] in ("queued", "running", "paused", "paused_allowance", "failed")
           for j in tx.all("collection_analysis_jobs")):
        raise ValueError("Finish the saved collection review before importing a different representation")
    if source_review and (not current or not note.strip() or len(note) > 2000):
        raise ValueError('A source correction needs an existing JSON and a short review note')
    for first, last, data in units(body):
        key = books.ident(doc["sha256"], source["role"], books.scan_version(source["role"]), first)
        existing = tx.get("book_units", key)
        if existing:
            # Preserve immutable cached material and historical source identities.
            def semantic_scan(scan):
                value = books.ScanResult.model_validate(scan).model_dump()
                for page in value["pages"]:
                    page.pop("native_reliable", None)  # Capture transport, not source content.
                    for i, element in enumerate(page["elements"], 1):
                        element["id"] = element["id"] or f"p{page['page']}:element:{i}"
                ids = scan.get("exercise_ids", [])
                refs = [{**e, "id": ids[i] if i < len(ids) else "exercise-" + books.ident(doc["sha256"], source["role"], first, i)}
                        for i, e in enumerate(value["exercises"])]
                link_element_references(value["pages"], refs)
                return value
            old = semantic_scan(books.resolve_scan(ctx.store, existing)["data"])
            new = semantic_scan(data)
            if old != new and not source_review:
                raise ValueError("These pages already have a saved source scan. Use source review to correct existing material; it was not overwritten")
        else:
            tx.insert("book_units", {"id": key, "sha256": doc["sha256"], "role": source["role"],
                                    "version": books.scan_version(source["role"]), "first_page": first, "last_page": last, "data": data})
    saved = persist(ctx, tx, subject_id, doc, body, expected_revision)
    if source_review:
        history = tx.find('book_source_reviews', sha256=doc['sha256'], role=source['role'])
        version = max((r['version'] for r in history), default=0) + 1
        tx.insert('book_source_reviews', {'id':'source-review-' + books.ident(doc['sha256'], source['role'], version, saved['content_sha256']),
            'sha256':doc['sha256'], 'role':source['role'], 'version':version, 'content_sha256':saved['content_sha256'],
            'previous_sha256':current['content_sha256'], 'data':body, 'file_path':saved['file_path'], 'note':note.strip()})
    return saved


def teaching_pages(ctx, topic):
    """Only checked, public visual structure in the assigned range; never the archive."""
    if not topic.get("document_id"):
        return []
    doc = ctx.store.get("documents", topic["document_id"])
    from .passages import pdf_range
    first, last = pdf_range(topic)
    result = []
    for role in books.READING_ROLES:
        row = ctx.store.get("book_companions", row_id(doc["sha256"], role))
        if not row:
            continue
        for page in row["data"]["pages"][first - 1:last]:
            if page["status"] != "checked" or not page["student_safe"] or page["teacher_material"]:
                continue
            # Partial-page boundaries need region-to-passage mapping before visual context is safe.
            if topic.get("start_at") or topic.get("stop_before"):
                continue
            elements = [{k: e[k] for k in ("id", "kind", "text", "description", "bbox", "rows", "expression")}
                        for e in page["elements"] if not e["issue"] and e["kind"] != "decoration"]
            if elements or page['reading_blocks']:
                result.append({"pdf_page": page["page"], "printed_page": page["printed_page"], "elements": elements,
                               'reading_blocks':page['reading_blocks']})
    return result
