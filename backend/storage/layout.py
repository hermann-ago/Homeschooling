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

Each subject has its own grade (``subjects.grade``), because a child can be in
4th grade for Math while still finishing 3rd grade History. A new subject starts
at the child's grade. The subject's folder is kept in ``subjects.folder``; when a
subject moves to another grade it gets that grade's folder (created at once,
with its Books, Handwriting, … folders) and new files go there. Files already
saved never move: their records keep pointing at them. Renaming a child or a
subject does not move folders either. No grade (for example "N/A") means no
grade level in the path.

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


_CHILDS_GRADE = object()


def subject_folder(child: dict, subject_name: str, grade=_CHILDS_GRADE) -> str:
    """A subject's folder, e.g. ``Lucas/3rd Grade/History``: at ``grade`` (None: no grade level), or at the
    child's grade when none is given."""
    level = grade_folder(child.get("grade_year") if grade is _CHILDS_GRADE else grade)
    return "/".join(p for p in (safe_name(child["name"]), level, safe_name(subject_name)) if p)


def stored_grade(grade: str | None) -> str:
    """How a grade is recorded: as typed ('4th', 'Pre-K'), or 'N/A' for no grade level."""
    text = (grade or "").strip()
    return "N/A" if text.lower() in _NO_GRADE else text


def grade_of_folder(folder: str | None) -> str | None:
    """The grade a recorded folder is at: 'Lucas/3rd Grade/History' → '3rd', 'Olivia/Pre-K/Math' → 'Pre-K',
    'Joshua/Reading' → None."""
    parts = (folder or "").split("/")
    if len(parts) < 3:
        return None
    level = parts[1]
    return level[:-len(" Grade")] if level.endswith(" Grade") else level


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
