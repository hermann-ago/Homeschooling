"""Where files go in the Homeschooling Drive folder: Kid → Grade → Subject.

    Homeschooling/
      Lucas/
        3rd Grade/
          History/
            Books/           the PDFs the lessons use
            Handwriting/     pen strokes drawn on book pages
            Student Work/    photos of answers and other evidence
            Audio/           read-along narration
            Lesson Content/  AI quizzes, summaries and reviewed passages
      Mila/1st Grade/Math/...
      _App Backups/          database backups and the read-only Excel copy
      _Unassigned Books/     books no subject uses yet (from the migration)
      _Archive/              retired folders, never read by the app

A subject's folder is decided when the subject is created and kept in
``subjects.folder``. Renaming a child or moving up a grade never moves files
that records already point to; next year's subjects get next year's grade.
A child without a grade (for example "N/A") has no grade level in the path.

``db`` below is the store or an open transaction (both offer ``get``/``find``).
"""
from __future__ import annotations

import re

from .files import safe_name

BOOKS = "Books"
HANDWRITING = "Handwriting"
STUDENT_WORK = "Student Work"
AUDIO = "Audio"
LESSON_CONTENT = "Lesson Content"
FILE_KINDS = (BOOKS, HANDWRITING, STUDENT_WORK, AUDIO, LESSON_CONTENT)

BACKUPS = "_App Backups"
UNASSIGNED_BOOKS = "_Unassigned Books"
ARCHIVE = "_Archive"
TOP_LEVEL = (BACKUPS, UNASSIGNED_BOOKS)

_NO_GRADE = {"", "n/a", "na", "none", "-"}


def grade_folder(grade: str | None) -> str | None:
    """'3rd' → '3rd Grade', '4' → '4th Grade', 'Pre-K' stays; no grade → None."""
    text = (grade or "").strip()
    if text.lower() in _NO_GRADE:
        return None
    if text.isdigit():
        number = int(text)
        suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
        text = f"{number}{suffix}"
    if re.fullmatch(r"\d+(st|nd|rd|th)", text, re.IGNORECASE):
        return f"{text} Grade"
    return safe_name(text)


def child_folder(child: dict) -> str:
    return "/".join(p for p in (safe_name(child["name"]), grade_folder(child.get("grade_year"))) if p)


def subject_folder(child: dict, subject_name: str) -> str:
    """The folder a new subject gets, e.g. ``Lucas/3rd Grade/History``."""
    return f"{child_folder(child)}/{safe_name(subject_name)}"


def subject_base(db, subject: dict) -> str:
    return subject.get("folder") or subject_folder(db.get("children", subject["child_id"]), subject["name"])


def for_subject(db, subject_id: int, kind: str) -> str:
    return f"{subject_base(db, db.get('subjects', subject_id))}/{kind}"


def for_topic(db, topic_id: int, kind: str) -> str:
    return for_subject(db, db.get("topics", topic_id)["subject_id"], kind)


def for_session(db, session_id: str, kind: str) -> str:
    return for_subject(db, db.get("tutor_sessions", session_id)["subject_id"], kind)


def for_child_document(db, child_id: int, document_id: int, kind: str) -> str:
    """The child's subject that uses this book, or the child's grade folder when none does."""
    used_by = {t["subject_id"] for t in db.find("topics", document_id=document_id)}
    subjects = sorted((s for s in db.find("subjects", child_id=child_id) if s["id"] in used_by), key=lambda s: s["id"])
    if subjects:
        return for_subject(db, subjects[0]["id"], kind)
    return f"{child_folder(db.get('children', child_id))}/{kind}"


def check_folder(folder: str) -> str:
    """A folder the app may write into: ``<subject path>/<kind>`` or one of the top-level app folders."""
    parts = folder.replace("\\", "/").strip("/").split("/")
    if folder in TOP_LEVEL:
        return folder
    if len(parts) >= 2 and parts[-1] in FILE_KINDS and all(p and p not in (".", "..") for p in parts) \
            and not re.match(r"^[A-Za-z]:", parts[0]) and parts[0] not in (ARCHIVE, *TOP_LEVEL):
        return "/".join(parts)
    raise ValueError(f"Unknown app folder {folder}")
