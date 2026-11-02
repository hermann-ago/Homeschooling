"""One versioned, editable teaching skill per learner's subject."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from storage import FileUnavailable, RevisionConflict, layout


def template(db, subject: dict) -> str:
    name = subject["name"]
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "subject"
    topics = db.find("topics", subject_id=subject["id"])
    books = {t["pdf_filename"] for t in topics if t.get("pdf_filename")}
    for topic in topics:
        document = db.get("documents", topic["document_id"]) if topic.get("document_id") else None
        if document and document.get("original_filename"):
            books.add(document["original_filename"])
    books = sorted(books)
    notes = {
        "math": "Ask the learner to show their reasoning. Use concrete examples before abstractions. Separate arithmetic slips from conceptual misunderstandings.",
        "science": "Invite observations, predictions and explanations supported by evidence. Distinguish observations from guesses. Activities needing equipment or supervision should be described for the parent first.",
        "language arts": "Separate reading comprehension, spelling and writing conventions. Ask for evidence from the passage and accept equivalent wording.",
        "portuguese": "Teach in Brazilian Portuguese. Separate compreensão, ortografia and handwriting. Use vocabulary appropriate to the learner and the assigned text.",
        "português": "Teach in Brazilian Portuguese. Separate compreensão, ortografia and handwriting. Use vocabulary appropriate to the learner and the assigned text.",
    }.get(name.lower(), "Use the assigned curriculum and its actual exercises. Adapt explanations to observed understanding; do not infer mastery from grade or age.")
    if "history" in name.lower():
        notes = (Path(__file__).resolve().parents[2] / "tutor/subjects/history/GUIDE.md").read_text(encoding="utf-8")
        notes = notes.replace("Use with the `home-tutor` skill. Learner-specific IDs and the entry instructions live in the History project's `AGENTS.md`.",
                              "Use the learner and subject supplied by the app. The home server's database is authoritative.")
        notes += "\n\n" + (Path(__file__).resolve().parents[2] / "tutor/subjects/history/QUIZ_GUIDE.md").read_text(encoding="utf-8")
    elif any(word in name.casefold() for word in ("math", "matem")):
        notes = (Path(__file__).resolve().parents[2] / "tutor/subjects/math/GUIDE.md").read_text(encoding="utf-8")
    elif any(word in name.casefold() for word in ("portuguese", "português")):
        notes = (Path(__file__).resolve().parents[2] / "tutor/subjects/portuguese/GUIDE.md").read_text(encoding="utf-8")
    return f'''---
name: {slug}-tutor
description: {json.dumps(f'Prepare guided lessons and tutor this learner in {name} using the Homeschooling app.')}
---

# {name} teaching skill

These notes are only for what is particular to {name}: how its ideas are best
explained, how its books are laid out, which answers count and what the tutor
should watch for. The family teaching style already sets the voice, pacing and
feedback, and the app enforces complete readings, waiting questions and private
answer keys. Edit freely; the newest version is used for new lessons.

## Subject-specific guidance
{notes}

## Books
{chr(10).join('- ' + b for b in books) or 'Use the books and lesson boundaries configured for this subject.'}
'''


def current(db, subject_id: int) -> dict | None:
    return max(db.find("subject_skills", subject_id=subject_id), key=lambda r: r["version"], default=None)


def view(row: dict) -> dict:
    return {k: row[k] for k in ("id", "subject_id", "version", "content", "sha256", "file_path", "created_at")}


def packet(db, subject: dict) -> dict:
    row = current(db, subject["id"])
    if row:
        return view(row)
    content = template(db, subject)
    return {"id": None, "subject_id": subject["id"], "version": 0, "content": content,
            "sha256": hashlib.sha256(content.encode()).hexdigest(), "file_path": None, "created_at": None}


def save(tx, subject: dict, content: str, expected_version: int) -> dict:
    previous = current(tx, subject["id"])
    actual = previous["version"] if previous else 0
    if expected_version != actual:
        raise RevisionConflict("The teaching skill changed. Reload it before saving.", previous)
    content = content.strip()
    if not content or len(content) > 30000:
        raise ValueError("Teaching instructions must contain 1–30,000 characters")
    if previous and previous["content"] == content:
        return previous
    version = actual + 1
    path = None
    try:
        path, _ = tx.add_blob(content.encode("utf-8"), layout.for_subject(tx, subject["id"], layout.TEACHING_SKILL),
                              f"SKILL-v{version}.md", "text/markdown")
    except FileUnavailable:
        # Instructions are still usable without Drive; file export can be retried later.
        pass
    return tx.insert("subject_skills", {"subject_id": subject["id"], "version": version, "content": content,
                                       "sha256": hashlib.sha256(content.encode()).hexdigest(), "file_path": path})


def ensure(ctx):
    missing = [s for s in ctx.store.all("subjects") if not current(ctx.store, s["id"])]
    if missing:
        with ctx.store.transaction(kind="skills.seed", summary="Created subject teaching skills") as tx:
            for subject in missing:
                save(tx, subject, template(tx, subject), 0)


def export(ctx, subject_id: int):
    row = current(ctx.store, subject_id)
    if row and not row["file_path"]:
        with ctx.store.transaction(kind="skills.export") as tx:
            path, _ = tx.add_blob(row["content"].encode("utf-8"), layout.for_subject(tx, subject_id, layout.TEACHING_SKILL),
                                  f"SKILL-v{row['version']}.md", "text/markdown")
            tx.update("subject_skills", row["id"], {"file_path": path})
    return current(ctx.store, subject_id)
