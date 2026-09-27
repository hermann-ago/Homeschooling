"""Import the Lucas – History tutoring project into the Homeschooling Database.

    python -m migration.import_history --source "G:\\My Drive\\Casa, Família e Vida Prática\\Homeschooling\\Lucas - History" [--dry-run]

The source folder is only read; nothing in it is changed (the originals stay
until migration is verified). The textbook, the tests, evidence photos and
audio are copied into the app's Drive folders (Books, Student Work, Audio), so
the History folder can be archived later without breaking any record.

* Topics are merged by source document and passage (page range), never by
  title alone. Ambiguous matches are reported, not overwritten.
* The workbook's sessions, answers (first answers verbatim, help and
  revisions separately) and reviews become tutoring records.
* The recovered Genghis Khan discussion becomes an unfinished session with
  its observations and next prompt. It is not a completed lesson or mastery.
* Reviewed passages keep their sentences, boundaries and notes. Cached
  Neural2 narration is marked synchronized only when its original hash
  (voice, rate and passage text) matches the reviewed passage. ElevenLabs
  Robin Hood audio is preserved as legacy audio.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from datetime import date, datetime, time, timezone
from pathlib import Path

from storage import layout
from tutoring import passages
from tutoring.service import RESULTS

from .common import Report, sha256_file, staged

RECOVERED_DATE = date(2026, 9, 24)
HEADERS = {"Topic ID": "topics", "Chapter": "chapters", "Session ID": "sessions", "Answer ID": "answers",
           "Review ID": "reviews"}
PROFILE_KEYS = {
    "Age at setup": "age_at_setup", "Tutoring language": "tutoring_language",
    "Sessions per week": "sessions_per_week", "Parent present": "parent_present",
    "Earlier coverage": "earlier_coverage", "Preferred reading support": "preferred_reading_support",
    "Interests and helpful approaches": "interests",
}


# ── reading the source ───────────────────────────────────────────────────────

def _title_key(title: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _text(value):
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return text or None


def _date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for pattern in ("%d %b %Y", "%Y-%m-%d", "%d/%m/%Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date {text!r}")


def _noon(day: date | None):
    return datetime.combine(day, time(12), tzinfo=timezone.utc) if day else None


def read_tracker(path: Path) -> dict:
    """Rows of each workbook table, found by their header rows rather than fixed positions."""
    import openpyxl
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    tables, profile = {}, {}
    profile_labels = {"Learner", "Starting topic", "Current location", *PROFILE_KEYS}
    try:
        for sheet in book.worksheets:
            header, kind = None, None
            for row in sheet.iter_rows(values_only=True):
                cells = list(row)
                first = _text(cells[0]) if cells else None
                if header is None and first in HEADERS and len([c for c in cells if c not in (None, "")]) > 3:
                    header = [_text(c) for c in cells]
                    kind = HEADERS[first]
                    tables.setdefault(kind, [])
                elif header is not None:
                    if any(c not in (None, "") for c in cells):
                        tables[kind].append({h: cells[i] if i < len(cells) else None
                                             for i, h in enumerate(header) if h})
                elif first in profile_labels and first not in profile:
                    profile[first] = _text(cells[1]) if len(cells) > 1 else None
    finally:
        book.close()
    return {"profile": profile, **tables}


MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".heic": "image/heic",
        ".pdf": "application/pdf", ".mp3": "audio/mpeg", ".wav": "audio/wav"}


def copy_source_file(tx, source: Path, relative: str, folder: str, prefix: str = "") -> tuple[str, str] | None:
    """Copy one file from the History folder into an app folder; None when it is missing."""
    relative = relative.strip().replace("\\", "/")
    path = (source / relative).resolve()
    if source.resolve() not in path.parents or not path.is_file():
        return None
    return tx.add_blob(path.read_bytes(), folder, f"{prefix}{path.name}",
                       MIME.get(path.suffix.lower(), "application/octet-stream"))


def legacy_passage_hash(voice: str, rate: float, passage: str) -> str:
    rate_text = str(int(rate)) if float(rate).is_integer() else repr(float(rate))
    return hashlib.sha256(f"{voice}\n{rate_text}\n{passage}".encode("utf-8")).hexdigest()


# ── import ───────────────────────────────────────────────────────────────────

def import_history(store, source: Path, report: Report, *, create_unmatched: bool = False) -> Report:
    source = Path(source)
    config = json.loads((source / "tutor.json").read_text(encoding="utf-8"))
    curriculum = json.loads((source / "subject" / "curriculum.json").read_text(encoding="utf-8"))
    tracker_path = source / config["tracker"]
    tracker_sha = sha256_file(tracker_path)
    tracker = read_tracker(tracker_path)
    report.notes.append(f"Tracker {config['tracker']} sha256 {tracker_sha}")
    for kind in ("topics", "chapters", "sessions", "answers", "reviews"):
        report.count(kind, source=len(tracker.get(kind, [])))

    pending = source / "pending_updates.json"
    if pending.exists():
        queued = json.loads(pending.read_text(encoding="utf-8") or "null")
        if queued:
            report.conflict("pending_updates", "pending_updates.json holds evidence never written to the workbook; "
                            "reconcile it with the parent before cutover", entries=len(queued) if isinstance(queued, list) else 1)

    # Learner and subject.
    learner_name = tracker["profile"].get("Learner") or config.get("learner") or "Lucas"
    children = [c for c in store.all("children") if c["name"].strip().lower() == learner_name.lower()]
    if len(children) > 1:
        raise RuntimeError(f"Several children are named {learner_name}; choose one explicitly")
    textbook_path = source / curriculum["sources"]["text"]
    if not textbook_path.exists():
        textbook_path = source / Path(curriculum["sources"]["text"]).stem
    tests_path = source / curriculum["sources"]["tests"]
    textbook_sha, tests_sha = sha256_file(textbook_path), sha256_file(tests_path)
    from pypdf import PdfReader
    ids: dict = {}
    textbook_pages = len(PdfReader(textbook_path).pages)
    curriculum_titles = {_title_key(part) for entry in curriculum["topics"] for part in entry["title"].split(" / ")}

    def in_history(relative: str) -> bool:
        """Whether a Drive-folder path lies inside the History folder (which may be archived later)."""
        try:
            return store.files.resolve(relative).is_relative_to(source.resolve())
        except (OSError, PermissionError, ValueError):
            return False

    def same_book(tx, subject_id):
        """The app's copy of the textbook under another file: same page count, and at least
        90% of the curriculum's topic titles already on it for this subject."""
        by_document: dict = {}
        for topic in tx.find("topics", subject_id=subject_id):
            if topic.get("document_id"):
                by_document.setdefault(topic["document_id"], []).append(topic)
        for document_id, group in by_document.items():
            document = tx.get("documents", document_id)
            if not document or document["sha256"] == tests_sha or document.get("page_count") != textbook_pages:
                continue
            shared = len({_title_key(t["title"]) for t in group} & curriculum_titles)
            if shared >= 0.9 * len(curriculum["topics"]):
                return document, shared
        return None, 0

    def setup(tx):
        child = children[0] if children else tx.insert("children", {"name": learner_name, "color": "#4A90D9"})
        subjects = [s for s in tx.find("subjects", child_id=child["id"]) if "history" in s["name"].lower()]
        if len(subjects) > 1:
            raise RuntimeError("Several History subjects exist for this learner; choose one explicitly")
        name = config.get("subject", "History")
        subject = subjects[0] if subjects else tx.insert("subjects", {
            "child_id": child["id"], "name": name, "folder": layout.subject_folder(child, name)})
        books = layout.for_subject(tx, subject["id"], layout.BOOKS)
        docs = {}
        for key, sha, path in (("textbook", textbook_sha, textbook_path), ("tests", tests_sha, tests_path)):
            existing = next((d for d in tx.all("documents") if d["sha256"] == sha), None)
            if existing and existing.get("file_path") and not in_history(existing["file_path"]):
                docs[key] = existing
                continue
            name = path.name if path.suffix.lower() == ".pdf" else path.name + ".pdf"
            relative, copied = tx.add_blob(path.read_bytes(), books, name, "application/pdf")
            if copied != sha:
                report.conflict("book_checksum", f"{path.name} changed while it was being copied")
            if existing:  # the app has this book, but without a file or only inside the History folder
                docs[key] = tx.update("documents", existing["id"], {"file_path": relative})
                continue
            twin, shared = same_book(tx, subject["id"]) if key == "textbook" else (None, 0)
            if twin:
                # One History book: the app's record keeps its ID and topics but now uses the
                # History folder's copy, which the reviewed passages were checked against.
                report.notes.append(
                    f"Document {twin['id']} ({twin['original_filename']}) is the same book as {path.name}: "
                    f"{textbook_pages} pages, {shared} of {len(curriculum_titles)} topic titles shared. "
                    f"It now uses the History folder's copy (was sha256 {twin['sha256']}).")
                docs[key] = tx.update("documents", twin["id"], {
                    "file_path": relative, "original_filename": name, "size_bytes": path.stat().st_size,
                    "sha256": sha, "source": "history"})
                continue
            docs[key] = tx.insert("documents", {
                "file_path": relative, "original_filename": name, "size_bytes": path.stat().st_size,
                "page_count": len(PdfReader(path).pages), "sha256": sha, "source": "history"})
        ids.update(child=child["id"], subject=subject["id"], textbook=docs["textbook"]["id"], tests=docs["tests"]["id"])
    staged(store, "import-history-setup", "History learner, subject and books", setup, report)
    if not ids:  # resumed run: look the records up again
        child = children[0] if children else next(c for c in store.all("children") if c["name"] == learner_name)
        subject = next(s for s in store.find("subjects", child_id=child["id"]) if "history" in s["name"].lower())
        ids.update(child=child["id"], subject=subject["id"],
                   textbook=next(d for d in store.all("documents") if d["sha256"] == textbook_sha)["id"],
                   tests=next(d for d in store.all("documents") if d["sha256"] == tests_sha)["id"])

    overlays = {}
    reviewed_dir = source / config["cache"] / "reviewed"
    for path in sorted(reviewed_dir.glob("C*.json")) if reviewed_dir.exists() else []:
        overlay = json.loads(path.read_text(encoding="utf-8"))
        overlays[overlay["topic_id"]] = overlay

    # Topics, merged by document and passage.
    tracker_topics = {_text(r["Topic ID"]): r for r in tracker.get("topics", [])}
    topic_ids: dict[str, int] = {}

    def topics(tx):
        existing = [t for t in tx.find("topics", subject_id=ids["subject"])]
        # On the same book, a topic may also be recognised by its title (a combined tracker
        # topic such as "A / B" by any of its parts) when exactly one app topic carries it.
        by_title: dict = {}
        for t in existing:
            if not t["source_key"] and t["document_id"] == ids["textbook"]:
                by_title.setdefault(_title_key(t["title"]), []).append(t)
        taken: set = set()

        def title_match(entry):
            for part in entry["title"].split(" / "):
                found = [c for c in by_title.get(_title_key(part), []) if c["id"] not in taken]
                if len(found) == 1:
                    return found[0]
            return None

        planned = []
        for entry in curriculum["topics"]:
            key = entry["id"]
            row = tracker_topics.get(key, {})
            offset = entry["pdf_start"] - entry["start"]
            start_at = (overlays.get(key) or {}).get("start_at") or entry["title"].split(" / ")[0]
            values = {
                "title": entry["title"], "page_start": entry["start"], "page_end": entry["end"],
                "pdf_page_offset": offset, "document_id": ids["textbook"], "source_key": key, "start_at": start_at,
                "stop_before": entry.get("stop_before"), "chapter_order": entry["order"],
                "pdf_filename": curriculum["sources"]["text"], "language": "en",
                "understanding": _text(row.get("Understanding")), "last_checked": _date(row.get("Last checked")),
                "evidence_session_id": _text(row.get("Evidence / session ID")),
                "next_step": _text(row.get("Next teaching step")),
            }
            coverage = _text(row.get("Coverage"))
            completed = coverage == "Completed"
            match = next((t for t in existing if t["source_key"] == key), None) or next(
                (t for t in existing if not t["source_key"] and t["document_id"] == ids["textbook"]
                 and t["id"] not in taken and t["page_start"] == entry["start"] and t["page_end"] == entry["end"]
                 and (t["pdf_page_offset"] or 0) == offset), None) or title_match(entry)
            if match:
                taken.add(match["id"])
            planned.append((entry, values, completed, coverage, _date(row.get("Date completed")), match))
        matched = {m["id"] for *_, m in planned if m}
        # Pass 1: matches by document and passage (or title on the same book).
        kept_unknown = 0
        for entry, values, completed, coverage, day, match in planned:
            if not match:
                continue
            if match["completed"] and not completed:
                if coverage in (None, "Unknown"):  # the tracker has no record either way
                    kept_unknown += 1
                else:
                    report.conflict("topic_completion", f"{entry['id']}: the app marks it complete but the History "
                                    f"tracker says {coverage!r}; the app's completion was kept", topic_id=match["id"])
            # Another app topic inside a combined tracker topic ("A / B") would repeat part of it.
            for part in entry["title"].split(" / "):
                for other in by_title.get(_title_key(part), []):
                    if other["id"] not in matched and entry["start"] <= other["page_start"] <= entry["end"]:
                        report.conflict("topic_absorbed", f"{entry['id']} ({entry['title']}) also covers app topic "
                                        f"{other['id']} ({other['title']}); both were kept — remove one in the app "
                                        "if it is a duplicate", topic_id=other["id"])
            changes = dict(values)
            if completed and not match["completed"]:
                changes.update(completed=True, completed_at=_noon(day))
            tx.update("topics", match["id"], changes)
            topic_ids[entry["id"]] = match["id"]
        # Pass 2: create the rest unless they collide with unmatched app topics for the same book.
        # The app groups a subject's books by file name: keep the book's other topics under the same name.
        for t in existing:
            if t["document_id"] == ids["textbook"] and t["id"] not in matched \
                    and t["pdf_filename"] != curriculum["sources"]["text"]:
                tx.update("topics", t["id"], {"pdf_filename": curriculum["sources"]["text"]})
        if kept_unknown:
            report.notes.append(f"{kept_unknown} topics the app marks complete have no tracker record "
                                "(Coverage 'Unknown'); the app's completion was kept")
        unmatched = [t for t in existing if t["id"] not in matched and not t["source_key"]
                     and t["document_id"] == ids["textbook"]]
        for entry, values, completed, coverage, day, match in planned:
            if match:
                continue
            overlapping = [t["id"] for t in unmatched if t["page_start"] <= entry["end"] and t["page_end"] >= entry["start"]]
            if overlapping and not create_unmatched:
                report.conflict("topic_ambiguous", f"{entry['id']} overlaps existing topics {overlapping} with "
                                "different boundaries; not created (rerun with --create-unmatched after review)")
                continue
            created = tx.insert("topics", {**values, "subject_id": ids["subject"], "is_core": True,
                                           "completed": completed, "completed_at": _noon(day) if completed else None})
            topic_ids[entry["id"]] = created["id"]
    staged(store, "import-history-topics", "History topics", topics, report)
    if not topic_ids:
        topic_ids.update({t["source_key"]: t["id"] for t in store.find("topics", subject_id=ids["subject"])
                          if t["source_key"]})
    order = [e["id"] for e in curriculum["topics"]]

    # Chapters and teacher keys.
    chapter_rows = {int(r["Chapter"]): r for r in tracker.get("chapters", []) if _text(r.get("Chapter"))}
    key_db = source / config["answer_key"]
    exceptions = json.loads((source / "subject" / "key_exceptions.json").read_text(encoding="utf-8")) \
        if (source / "subject" / "key_exceptions.json").exists() else []

    def chapters(tx):
        for entry in curriculum["chapters"]:
            row = chapter_rows.get(entry["chapter"], {})
            tx.insert("chapters", {
                "id": f"{ids['subject']}:{entry['chapter']}", "subject_id": ids["subject"], "chapter": entry["chapter"],
                "title": entry["title"], "book_start": entry["book_start"], "book_end": entry["book_end"],
                "test_pdf_start": entry["test_pdf_start"], "test_pdf_end": entry["test_pdf_end"],
                "test_print_start": entry["test_print_start"], "test_print_end": entry["test_print_end"],
                "key_pdf_page": entry["key_pdf"][0], "test_document_id": ids["tests"],
                "test_status": _text(row.get("Test status")), "test_date": _date(row.get("Test date")),
                "session_id": _text(row.get("Session ID")), "items_to_revisit": _text(row.get("Items to revisit")),
                "note": _text(row.get("Parent / tutor note"))})
        if not key_db.exists():
            report.warnings.append("Teacher answer key database not found; grading will rely on the test PDF")
            return
        connection = sqlite3.connect(f"file:{key_db}?mode=ro", uri=True)
        try:
            pages = {c: (p, pp) for c, p, pp in connection.execute(
                "select chapter, key_pdf_page, key_printed_page from chapters")}
            db_exceptions = connection.execute(
                "select chapter, question, issue, action, source_reference from exceptions").fetchall()
            answers = connection.execute("select chapter, question_start, question_end, answer from answers").fetchall()
        finally:
            connection.close()
        notes = {}
        for chapter, question, issue, action, reference in db_exceptions:
            notes[(chapter, question)] = (f"{issue} {action}".strip(), reference)
        for item in exceptions:
            notes[(item["chapter"], item["question"])] = (f"{item['issue']} {item['action']}".strip(),
                                                          item.get("source_reference"))
        for chapter, start, end, answer in answers:
            note = next((notes[(chapter, q)] for q in range(start, end + 1) if (chapter, q) in notes), (None, None))
            tx.insert("teacher_keys", {
                "id": f"{ids['subject']}:{chapter}:{start}-{end}", "subject_id": ids["subject"], "chapter": chapter,
                "question_start": start, "question_end": end, "answer": answer,
                "key_pdf_page": pages.get(chapter, (None, None))[0], "key_printed_page": pages.get(chapter, (None, None))[1],
                "exception": note[0], "source_reference": note[1]})
        report.count("teacher_keys", imported=len(answers))
    staged(store, "import-history-chapters", "History chapters and teacher key", chapters, report)

    # Question-to-topic mappings.
    def mappings(tx):
        count = 0
        mapping_dir = source / "subject" / "question-mappings"
        for path in sorted(mapping_dir.glob("C*.json")) if mapping_dir.exists() else []:
            chapter = int(re.sub(r"\D", "", path.stem))
            data = json.loads(path.read_text(encoding="utf-8"))
            review_path = source / "subject" / "reviews" / path.name
            anchors = json.loads(review_path.read_text(encoding="utf-8")).get("questions", {}) \
                if review_path.exists() else {}
            for topic_key, questions in data.get("topics", {}).items():
                if topic_key not in topic_ids:
                    report.conflict("mapping_topic", f"Mapping for {topic_key} has no imported topic")
                    continue
                for question in questions:
                    tx.insert("question_maps", {
                        "id": f"{ids['subject']}:{chapter}:{question}", "subject_id": ids["subject"],
                        "chapter": chapter, "question": question, "topic_id": topic_ids[topic_key],
                        "anchor": (anchors.get(str(question)) or [None, None])[1],
                        "evidence": data.get("evidence", {}).get(str(question)),
                        "note": data.get("question_notes", {}).get(str(question))})
                    count += 1
        report.count("question_maps", imported=count)
        report.notes.append("Question mappings imported for chapters with reviewed mapping files only")
    staged(store, "import-history-mappings", "History question mappings", mappings, report)

    # Preferences from the tracker's profile.
    def preferences(tx):
        for label, key in PROFILE_KEYS.items():
            value = tracker["profile"].get(label)
            if value:
                tx.insert("preferences", {"id": f"{ids['child']}:{key}", "child_id": ids["child"], "key": key,
                                          "value": value, "confirmed_by": "parent (History tracker profile)"})
    staged(store, "import-history-preferences", "Learner preferences", preferences, report)

    # Sessions, answers, evidence photos and reviews.
    def next_topic(key):
        index = order.index(key)
        return topic_ids.get(order[index + 1]) if index + 1 < len(order) else None

    photo_ids: dict[str, str] = {}

    def records(tx):
        def known(kind, row, key):
            if key in topic_ids:
                return True
            report.conflict("record_topic_missing", f"{kind} {row.get(kind)} refers to {key}, which was not imported")
            return False

        for row in tracker.get("sessions", []):
            key = _text(row.get("Topic ID"))
            if not known("Session ID", row, key):
                continue
            day = _date(row.get("Date"))
            tx.insert("tutor_sessions", {
                "id": _text(row["Session ID"]), "child_id": ids["child"], "subject_id": ids["subject"],
                "topic_id": topic_ids[key], "date": day, "status": "completed", "phase": "finished",
                "session_type": _text(row.get("Session type")), "reading_mode": _text(row.get("Reading mode")),
                "minutes": int(row["Minutes"]) if _text(row.get("Minutes")) else None,
                "learner_explained": _text(row.get("What Lucas explained / did")),
                "difficulty": _text(row.get("What was difficult")),
                "help_that_worked": _text(row.get("Help that worked")),
                "next_action": _text(row.get("Next lesson / action")),
                "parent_observation": _text(row.get("Parent observation")),
                "evidence": _text(row.get("Photo / note path")), "next_topic_id": next_topic(key),
                "source": f"History tracker (sha256 {tracker_sha[:12]})", "finished_at": _noon(day)})
            for photo in (_text(row.get("Photo / note path")) or "").split(";"):
                photo = photo.strip()
                if not photo:
                    continue
                copied = copy_source_file(tx, source, photo, layout.for_subject(tx, ids["subject"], layout.STUDENT_WORK),
                                          f"{_text(row['Session ID'])}-")
                if not copied:
                    report.conflict("evidence_missing", f"Photo {photo} was not found in the History folder")
                    continue
                photo_ids[photo] = copied[0]
                tx.insert("evidence_files", {"id": f"{_text(row['Session ID'])}-{Path(photo).name}",
                                             "child_id": ids["child"], "session_id": _text(row["Session ID"]),
                                             "file_path": copied[0], "sha256": copied[1],
                                             "filename": Path(photo).name,
                                             "mime_type": MIME.get(Path(photo).suffix.lower(), "image/jpeg"),
                                             "note": f"Migrated from {photo}"})
        imported_sessions = {s["id"] for s in tx.all("tutor_sessions")}
        for row in tracker.get("answers", []):
            if not known("Answer ID", row, _text(row.get("Topic ID"))) or \
                    _text(row.get("Session ID")) not in imported_sessions:
                continue
            result = _text(row.get("First result"))
            if result not in RESULTS:
                report.conflict("answer_result", f"{row['Answer ID']}: unknown result {result!r}")
                continue
            help_given = _text(row.get("Hint given"))
            revised = _text(row.get("Corrected answer"))
            after = _text(row.get("After-help result"))
            assisted = bool(help_given or revised or after)
            photo = _text(row.get("Photo path"))
            tx.insert("attempts", {
                "id": _text(row["Answer ID"]), "session_id": _text(row["Session ID"]), "child_id": ids["child"],
                "topic_id": topic_ids[_text(row["Topic ID"])], "chapter": int(row["Chapter"]),
                "question_ref": _text(row.get("Question / page")),
                "first_answer": _text(row.get("First answer (verbatim)")),
                "reading_certainty": _text(row.get("Reading certainty")), "first_result": result,
                "help_given": help_given, "revised_answer": revised, "after_help_result": after,
                "independence": "with_help" if assisted else ("independent" if result == "Correct" else "not_assessed"),
                "recheck_date": _date(row.get("Recheck date")),
                "evidence_paths": [photo_ids[photo]] if photo in photo_ids else None,
                "source_note": _text(row.get("Source / key / tutor note"))})
        for row in tracker.get("reviews", []):
            if not _text(row.get("Review ID")) or not known("Review ID", row, _text(row.get("Topic ID"))):
                continue
            tx.insert("reviews", {
                "id": _text(row["Review ID"]), "child_id": ids["child"], "topic_id": topic_ids[_text(row["Topic ID"])],
                "concept": _text(row.get("Concept to revisit")), "evidence": _text(row.get("Observed difficulty / evidence")),
                "last_practice": _date(row.get("Last practice")),
                "interval_days": int(row["Interval (days)"]) if _text(row.get("Interval (days)")) else None,
                "next_due": _date(row.get("Next due")), "status": _text(row.get("Status")),
                "last_outcome": _text(row.get("Last outcome")), "next_prompt": _text(row.get("Next prompt / strategy")),
                "action": _text(row.get("Action")), "evidence_session_id": _text(row.get("Evidence / session ID"))})
    staged(store, "import-history-records", "History sessions, answers and reviews", records, report)
    for table, kind in (("tutor_sessions", "sessions"), ("attempts", "answers"), ("reviews", "reviews")):
        report.count(kind, imported=len([r for r in store.find(table, child_id=ids["child"])
                                         if table != "tutor_sessions" or r["status"] == "completed"]))

    # The unfinished Genghis discussion (observations, not mastery).
    recovered_path = source / "context" / "recovered-genghis.json"
    checkpoint_path = source / "context" / "session.json"
    session_ids = {_text(r["Session ID"]) for r in tracker.get("sessions", [])}
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        later = [r for r in tracker.get("sessions", []) if _text(r.get("Topic ID")) == checkpoint.get("topic_id")]
        if checkpoint.get("session_id") in session_ids or later:
            report.skipped.append(f"context/session.json ({checkpoint.get('topic_id')}) is superseded by the "
                                  "workbook's recorded session")
        else:
            report.conflict("checkpoint_unrecorded", "context/session.json holds evidence not in the workbook")
    if recovered_path.exists():
        recovered = json.loads(recovered_path.read_text(encoding="utf-8"))

        def genghis(tx):
            key = recovered["topic_id"]
            if key not in topic_ids:
                report.conflict("record_topic_missing", f"The recovered discussion refers to {key}, which was not imported")
                return
            session_id = f"{RECOVERED_DATE.isoformat()}-{key}-recovered"
            tx.insert("tutor_sessions", {
                "id": session_id, "child_id": ids["child"], "subject_id": ids["subject"], "topic_id": topic_ids[key],
                "date": RECOVERED_DATE, "status": "unfinished", "phase": recovered.get("phase", "discussion"),
                "session_type": "Reading and discussion", "minutes": recovered.get("minutes"),
                "source": f"Recovered conversation {recovered.get('source_thread')}"})
            observations = []
            for item in recovered.get("observations", []):
                observation = {k: item[k] for k in ("prompt", "first_response", "help", "revision",
                                                    "explanation_supplied") if item.get(k)}
                observations.append(observation)
            tx.insert("checkpoints", {
                "id": f"{session_id}-cp", "session_id": session_id, "child_id": ids["child"],
                "topic_id": topic_ids[key], "phase": recovered.get("phase", "discussion"), "status": "open",
                "next_prompt": recovered["next_prompt"], "observations": observations,
                "basis": f"{recovered.get('basis')} Reading signal: {recovered.get('reading_signal')!r}."})
        staged(store, "import-history-genghis", "Unfinished Genghis Khan discussion", genghis, report)

    # Reviewed passages.
    textbook = store.get("documents", ids["textbook"])

    def passage_rows(tx):
        for key, overlay in overlays.items():
            if key not in topic_ids:
                continue
            topic = tx.get("topics", topic_ids[key])
            problems = []
            if overlay.get("provenance", {}).get("pdf") != textbook["sha256"]:
                problems.append("reviewed against a different PDF")
            if passages.passage_sha256(overlay["passage"]) != overlay.get("passage_sha256"):
                problems.append("passage text does not match its recorded hash")
            if list(passages.pdf_range(topic)) != list(overlay["pdf_pages"]):
                problems.append(f"PDF pages {overlay['pdf_pages']} differ from the topic's {passages.pdf_range(topic)}")
            validation = overlay.get("validation", {})
            if validation.get("status") != "verified":
                problems.append("overlay is not marked verified")
            review = overlay.get("review", {})
            # Older overlays were "adopted" and record their page check under validation instead.
            reviewed_pages = review.get("pdf_pages") or validation.get("verified_against_pdf_pages") or []
            pdf_start, pdf_end = passages.pdf_range(topic)
            unreviewed = sorted(set(range(pdf_start, pdf_end + 1)) - set(reviewed_pages))
            if unreviewed:
                problems.append(f"no record that PDF pages {unreviewed} were checked")
            if problems:
                report.conflict("passage", f"{key}: " + "; ".join(problems) + " — imported topic stays unreviewed")
                continue
            reviewed_at = review.get("reviewed_at") or validation.get("verified_on")
            images = [{**{k: image.get(k) for k in ("pdf_page", "classification", "alt", "caption", "crop",
                                                     "full_page_reason")},
                       "before_sentence": image.get("before_sentence"), "source_asset": image.get("asset")}
                      for image in overlay.get("selected_images", [])]
            passages.record_review(tx, topic, textbook, overlay["passage"], reviewed_pages,
                                   review.get("notes") or review.get("basis") or "Reviewed in the History project",
                                   images,
                                   [{"text": s["text"], "paragraphIndex": s.get("paragraphIndex", 0)}
                                    for s in overlay["sentences"]],
                                   source="history-reviewed-overlay",
                                   reviewed_at=_aware(datetime.fromisoformat(reviewed_at)) if reviewed_at else None)
        report.count("passages", source=len(overlays))
    staged(store, "import-history-passages", "Reviewed History passages", passage_rows, report)
    report.count("passages", imported=len([p for p in store.all("passages")
                                           if p["source"] == "history-reviewed-overlay"]))

    # Cached narration.
    reading = source / "assets" / "reading"

    def audio(tx):
        audio_folder = layout.for_subject(tx, ids["subject"], layout.AUDIO)
        verified = {}
        for key, topic_id in topic_ids.items():
            rows = [p for p in tx.find("passages", topic_id=topic_id) if p["status"] == "verified"]
            if rows:
                overlay = overlays[key]
                verified[key] = overlay
        manifests = sorted(reading.glob("*-google-neural2-manifest.json")) if reading.exists() else []
        for path in manifests:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            match = next((key for key, overlay in verified.items()
                          if legacy_passage_hash(manifest["voice"], manifest["speakingRate"], overlay["passage"])
                          == manifest["passageHash"]), None)
            key = match or _topic_from_label(manifest.get("label") or path.name)
            if key not in topic_ids:
                report.conflict("audio_topic", f"{path.name}: no topic could be identified; not imported")
                continue
            tracks, missing = [], []
            for track in manifest["tracks"]:
                copied = copy_source_file(tx, source, track["src"], audio_folder)
                if not copied:
                    missing.append(track["src"])
                    continue
                tracks.append({"path": copied[0], "sha256": copied[1], "startSentence": track["startSentence"],
                               "sentenceStarts": track["sentenceStarts"]})
            if missing:
                report.conflict("audio_missing", f"{path.name}: tracks missing in the History folder: {missing}")
                continue
            synchronized = bool(match) and manifest["sentenceCount"] == len(verified[match]["sentences"])
            new_manifest = {"version": 2, "migratedFrom": path.name, "provider": manifest["provider"],
                            "voice": manifest["voice"], "speakingRate": manifest["speakingRate"],
                            "sentenceCount": manifest["sentenceCount"], "characterCount": manifest.get("characterCount"),
                            "passageHash": passages.passage_sha256(verified[match]["passage"]) if synchronized
                            else f"legacy:{manifest['passageHash']}",
                            "generatedAt": manifest.get("generatedAt"), "tracks": tracks}
            manifest_path, _ = tx.add_blob(json.dumps(new_manifest).encode(), audio_folder,
                                           f"migrated-{path.name}", "application/json")
            tx.insert("audio_tracks", {
                "id": f"history:{path.stem}", "topic_id": topic_ids[key], "provider": "google-neural2",
                "voice": manifest["voice"], "speaking_rate": manifest["speakingRate"],
                "passage_sha256": new_manifest["passageHash"], "manifest_path": manifest_path,
                "status": "ready" if synchronized else "legacy", "characters": manifest.get("characterCount"),
                "sentence_count": manifest["sentenceCount"],
                "timing": "provider-timepoints (migrated)" if synchronized else None,
                "note": None if synchronized else "Timings belong to an earlier text of this passage; played without "
                                                  "highlighting"})
        eleven = sorted(reading.glob("robin-hood-elevenlabs-part-*.mp3")) if reading.exists() else []
        if eleven:
            parts = []
            for part in eleven:
                path, sha = copy_source_file(tx, source, f"assets/reading/{part.name}", audio_folder)
                parts.append({"path": path, "sha256": sha, "mime": "audio/mpeg"})
            if parts:
                manifest_path, _ = tx.add_blob(json.dumps({"version": 2, "provider": "ElevenLabs", "tracks": parts,
                                                         "note": "Preserved legacy audio; never regenerate"}).encode(),
                                             audio_folder, "migrated-robin-hood-elevenlabs-manifest.json",
                                             "application/json")
                tx.insert("audio_tracks", {
                    "id": "history:robin-hood-elevenlabs", "topic_id": topic_ids["C19-T03"], "provider": "elevenlabs",
                    "voice": "ElevenLabs (Robin Hood)", "manifest_path": manifest_path, "status": "legacy",
                    "note": "Preserved legacy ElevenLabs audio without verified timings; never regenerated"})
        previews = list(reading.glob("gemini-*.wav")) if reading.exists() else []
        if previews:
            report.skipped.append(f"{len(previews)} Gemini voice previews are auditions, not lesson audio")
    staged(store, "import-history-audio", "Cached History narration", audio, report)
    report.count("audio_tracks", imported=len([a for a in store.all("audio_tracks") if a["id"].startswith("history:")]))
    report.notes.append(f"Learner child_id {ids['child']}, History subject_id {ids['subject']}")
    report.ids = ids
    return report


def _topic_from_label(label: str) -> str | None:
    match = re.search(r"c(\d{2})-t(\d{2})", label.lower())
    if match:
        return f"C{match[1]}-T{match[2]}"
    if "robin-hood" in label.lower():
        return "C19-T03"
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, type=Path, help="The Lucas - History folder (read only)")
    parser.add_argument("--dry-run", action="store_true", help="Import into a throwaway copy; change nothing")
    parser.add_argument("--create-unmatched", action="store_true")
    args = parser.parse_args(argv)
    report = Report("import-history" + ("-dry-run" if args.dry_run else ""))
    from app_context import AppContext
    from .common import dry_run_store
    context = AppContext(start_worker=False)
    context.files.require()
    store = dry_run_store(context) if args.dry_run else context.store
    import_history(store, args.source, report, create_unmatched=args.create_unmatched)
    path = report.write(context.config.dir / "migration-reports")
    print(json.dumps(report.as_dict(), indent=2, default=str)[:4000])
    print(f"Report: {path}")
    return 0 if not report.conflicts else 1


if __name__ == "__main__":
    raise SystemExit(main())
