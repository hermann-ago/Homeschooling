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
import uuid

from pydantic import BaseModel
from pypdf import PdfReader

from storage import layout
from . import passages

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


def book_name(filename):
    return re.sub(r"^[0-9a-f]{32}_", "", filename, flags=re.I)


def question_number(reference):
    value = re.fullmatch(r"(?:Question\s*|Q\s*)?(\d+)[.)]?", reference.strip(), re.I)
    if not value:
        # A chapter-qualified label still identifies one original question.
        value = re.fullmatch(r"Chapter\s+\d+\s*[,;:]\s*(?:Question\s*|Q\s*)?(\d+)[.)]?", reference.strip(), re.I)
    return int(value[1]) if value else None


class Requirement(BaseModel):
    topic_id: int
    evidence: str


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

    def prepare_collection(self, tx, subject_id):
        """Set up each collection book not yet prepared, as the book import does:
        readers first, then companions and references, then answer keys."""
        from .collections import view
        members = view(tx, subject_id)["books"]
        ids = {b["key"]: f"book-{subject_id}-{b['document_id']}" for b in members}
        # Books already taught from (they have lessons) keep their records and files as they are.
        new = [b for b in members if b["prepared_status"] == "not_prepared"
               and not tx.find("topics", subject_id=subject_id, document_id=b["document_id"])]
        order = {"textbook": 0, "combined": 0, "workbook": 1, "test": 1, "reference": 1, "answer_key": 2}
        jobs = []
        for b in sorted(new, key=lambda b: (order[b["role"]], b["position"])):
            try:  # begin() validates before writing; an unlinked key waits for its family link.
                jobs.append(self.begin(tx, subject_id, b["path"], b["role"],
                                       ids.get(b["companion_key"]) if b["role"] in ("workbook", "test") else None,
                                       ids.get(b["answer_for_key"]) if b["role"] == "answer_key" else None))
            except ValueError as exc:
                log.info("Collection book %s not set up: %s", b["document_id"], exc)
        return jobs

    def retry(self, tx, job_id):
        job = tx.get("book_imports", job_id)
        if not job or job["status"] not in ("failed", "waiting"):
            raise ValueError("Choose an unfinished preparation to retry")
        tx.update("subject_books", job["book_id"], {"status": "queued"})
        return tx.update("book_imports", job_id, {"status": "queued", "error": None, "done": 0,
            "stage": "Reading table of contents"})


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
                with self.db.transaction(kind="books.failed") as tx:
                    tx.update("book_imports", job_id, {"status": "failed", "error": str(exc)[:800]})
                    tx.update("subject_books", job["book_id"], {"status": "failed"})

    def _process(self, job):
        book = self.db.get("subject_books", job["book_id"])
        with self.db.transaction(kind="books.running") as tx:
            tx.update("subject_books", book["id"], {"status": "running"})
        doc = self.db.get("documents", book["document_id"])
        pdf = self.ctx.file_bytes(doc["file_path"], job["source_sha256"])
        from . import navigation
        nav = navigation.extract(self.ctx, doc)
        if book['role'] in (*READING_ROLES, 'workbook', 'test'):
            navigation.publish_topics(self, book, doc, nav)
        if book['role'] != 'reference':
            # Reading a large book's text can take minutes; do it now, not while a lesson is prepared.
            from .answer_keys import fingerprint
            fingerprint(self.ctx, doc)
        with self.db.transaction(kind='books.navigation_ready') as tx:
            tx.update('subject_books', book['id'], {'status': 'ready', 'active_index': nav['id']})
            tx.update('book_imports', job['id'], {'status': 'ready', 'stage': 'Chapter map ready' if nav['data']['chapters'] else 'Choose chapter pages',
                'done': len(nav['data']['toc_pages']), 'total': len(nav['data']['toc_pages']), 'error': None, 'pending_ranges': []})
        self._move(job, book, doc, pdf)


    def _topics(self, book, doc, *, allow_partial=False):
        from . import navigation
        return navigation.publish_topics(self, book, doc, navigation.extract(self.ctx, doc))


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
