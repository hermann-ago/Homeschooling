"""Read-only family learning records; deliberately not an arbitrary database browser."""
import csv
import io
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from dependencies import require_family, store, context
from app_context import request_operation as write
from pydantic import BaseModel, Field
from storage.store import RevisionConflict

router = APIRouter(prefix="/records", dependencies=[Depends(require_family)])


@router.get("/learning/{child_id}/{subject_id}")
def learning_summary(child_id: int, subject_id: int):
    try:
        return context().learning_memory.view(child_id, subject_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class EvidenceConceptLink(BaseModel):
    expected_revision: int = Field(ge=0)
    evidence_kind: Literal["attempt", "review"]
    evidence_id: str = Field(min_length=1, max_length=300)
    map_id: str | None = Field(default=None, max_length=150)
    concept_id: str | None = Field(default=None, max_length=150)
    status: Literal["linked", "unmapped"]
    note: str = Field(min_length=1, max_length=2000)


@router.post("/learning/{child_id}/{subject_id}/link")
def link_learning_evidence(child_id: int, subject_id: int, payload: EvidenceConceptLink):
    try:
        with write("learning.link", "Parent associated observed evidence with a source concept") as tx:
            context().learning_memory.link(tx, child_id, subject_id, payload)
        return context().learning_memory.view(child_id, subject_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class AnswerClarification(BaseModel):
    expected_revision: int = Field(ge=1)
    transcription: str = Field(min_length=1, max_length=4000)
    note: str = Field(min_length=5, max_length=2000)
    result: Literal["Unanswered", "Correct", "Partly correct", "Not yet", "Source disputed"] = "Unanswered"


@router.post("/learning/{child_id}/{subject_id}/attempts/{attempt_id}/clarify")
def clarify_saved_answer(child_id: int, subject_id: int, attempt_id: str, payload: AnswerClarification):
    import uuid
    try:
        if not payload.transcription.strip() or len(payload.note.strip()) < 5:
            raise ValueError("Enter the clarified answer and explain the correction")
        with write("learning.clarify", "Parent amended a saved answer; original evidence retained") as tx:
            original = tx.get("attempts", attempt_id)
            topic = tx.get("topics", original["topic_id"]) if original else None
            if not original or original["child_id"] != child_id or not topic or topic["subject_id"] != subject_id:
                raise ValueError("Choose saved work from this child and subject")
            if original["revision"] != payload.expected_revision or any(a["amends_attempt_id"] == attempt_id for a in tx.find("attempts", child_id=child_id)):
                raise RevisionConflict("This answer already has a correction. Reload and inspect the latest evidence.", original)
            assisted = bool(original.get("help_given") or original.get("revised_answer") or original.get("after_help_result") or original.get("independence") == "with_help")
            values = {k: v for k, v in original.items() if k not in ("id", "revision", "updated_at", "created_at")}
            values.update(id="parent-attempt-" + uuid.uuid4().hex, amends_attempt_id=attempt_id,
                first_answer=payload.transcription.strip(), first_result=payload.result, reading_certainty="clear",
                revised_answer=None, after_help_result=None, source_note="Parent clarification: " + payload.note.strip(),
                independence="independent" if payload.result == "Correct" and not assisted else "with_help" if assisted else "not_assessed")
            tx.insert("attempts", values)
            context().learning_memory.refresh(tx, child_id, subject_id)
        return context().learning_memory.view(child_id, subject_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
View = Literal["answers", "lessons", "reviews", "pending", "reading", "exercises", "preparation"]
LABELS = {"answers": "Answers and help", "lessons": "Lessons", "reviews": "Topics to revisit",
          "pending": "Unfinished work", "reading": "Reading and understanding", "exercises": "Book exercises", "preparation": "Book preparation"}
COMMON = [("date", "Date"), ("child", "Child"), ("subject", "Subject"), ("topic", "Topic")]
COLUMNS = {
    "answers": COMMON + [("reference", "Question"), ("first_answer", "Original answer"), ("status", "First result"), ("help", "Help given"), ("revised_answer", "Revised answer"), ("outcome", "After help"), ("independence", "Independence")],
    "lessons": COMMON + [("status", "Status"), ("difficulty", "Difficulty"), ("help", "Help that worked"), ("next", "Next step")],
    "reviews": COMMON + [("concept", "Concept"), ("status", "Status"), ("outcome", "Last outcome"), ("due", "Review due"), ("next", "Next prompt")],
    "pending": COMMON + [("kind", "Work"), ("status", "Status"), ("next", "Resume with")],
    "reading": COMMON + [("pages", "Printed pages"), ("status", "Reading"), ("understanding", "Understanding"), ("next", "Next step")],
    "exercises": COMMON + [("book", "Book"), ("reference", "Exercise"), ("pages", "PDF pages"), ("status", "Reading links"), ("key_status", "Answer key"), ("work", "Student work")],
    "preparation": COMMON + [("book", "Book"), ("role", "Role"), ("status", "Status"), ("pages", "Pages saved"), ("next", "Stage / pause reason")],
}


class Filters:
    def __init__(self, view: View = "answers", child_id: int | None = None, subject_id: int | None = None,
                 date_from: date | None = None, date_to: date | None = None,
                 q: str = Query("", max_length=200), status: str = Query("", max_length=80),
                 sort: str = Query("date", max_length=40), order: Literal["asc", "desc"] = "desc"):
        self.view, self.child_id, self.subject_id = view, child_id, subject_id
        self.date_from, self.date_to, self.q, self.status = date_from, date_to, q.strip().casefold(), status
        self.sort, self.order = sort, order
        if date_from and date_to and date_from > date_to:
            raise HTTPException(400, "The start date must be before the end date")
        if sort not in dict(COLUMNS[view]):
            raise HTTPException(400, "Choose a column shown in this records view")


def date_text(value):
    if isinstance(value, datetime):
        return value.astimezone(ZoneInfo("America/Sao_Paulo")).date().isoformat()
    return value.isoformat() if isinstance(value, date) else str(value or "")[:10]


def rows_for(db, view):
    children = {r["id"]: r for r in db.all("children")}
    subjects = {r["id"]: r for r in db.all("subjects")}
    topics = {r["id"]: r for r in db.all("topics")}
    sessions = {r["id"]: r for r in db.all("tutor_sessions")}
    books = {r["id"]: r for r in db.all("subject_books")}
    documents = {r["id"]: r for r in db.all("documents")}
    rows = []

    def add(row, values, details=None, subject_id=None, when=None):
        topic = topics.get(row.get("topic_id"), {})
        subject = subjects.get(subject_id or row.get("subject_id") or topic.get("subject_id"), {})
        child_id = row.get("child_id") or subject.get("child_id")
        if child_id not in children or not subject:
            return
        session_id = row.get("session_id") or row.get("evidence_session_id") or (row["id"] if row["id"] in sessions else None)
        session = sessions.get(session_id, {})
        lesson_path = f"/lesson?learner={child_id}&topic={session['topic_id']}&session={session_id}" if session.get("topic_id") else None
        rows.append({"id": str(row["id"]), "child_id": child_id, "subject_id": subject["id"],
            "date": date_text(when or row.get("date") or row.get("created_at") or row.get("updated_at")),
            "child": children[child_id]["name"], "subject": subject["name"], "topic": topic.get("title", ""),
            **values, "lesson_path": lesson_path, "details": details or {}})

    captures = {}
    for response in db.all("activity_responses"):
        captures.setdefault((response["session_id"], response["activity_id"]), []).append({
            "id": response["id"], "capture_method": response["method"], "original": response["original"],
            "proposed_transcript": response.get("proposed_text"), "confirmed_answer": response["confirmed_text"],
            "reasoning": response["reasoning"], "assessment_status": response["status"],
            "help_before_response": (response.get("support_snapshot") or {}).get("this"),
            "parent_observation": response.get("parent_observation"), "interaction_id": response["interaction_id"]})
    if view == "answers":
        evidence = {r["file_path"]: {"id": r["id"], "filename": r["filename"]} for r in db.all("evidence_files")}
        for r in db.all("attempts"):
            session = sessions.get(r["session_id"], {})
            add(r, {"reference": r["question_ref"], "first_answer": r["first_answer"], "status": r["first_result"],
                "help": r["help_given"], "revised_answer": r["revised_answer"], "outcome": r["after_help_result"], "independence": r["independence"]},
                {"Full question": r["question_text"], "Reading certainty": r["reading_certainty"], "Recheck date": date_text(r["recheck_date"]),
                 "Amends earlier record": r["amends_attempt_id"], "Session": r["session_id"],
                 "Capture history": captures.get((r["session_id"], r["question_ref"]), []),
                 "evidence": [evidence[p] for p in r["evidence_paths"] or [] if p in evidence]}, when=session.get("date"))
    elif view == "lessons":
        conversations, photos, observations = {}, {}, {}
        for message in sorted(db.all("lesson_dialogue"), key=lambda m: (m["sequence"] or 0, m["created_at"])):
            conversations.setdefault(message["session_id"], []).append({"role": message["role"], "text": message["text"], "status": message["status"]})
        for photo in db.all("evidence_files"):
            photos.setdefault(photo["session_id"], []).append({"id": photo["id"], "filename": photo["filename"]})
        for checkpoint in db.all("checkpoints"):
            observations.setdefault(checkpoint["session_id"], []).extend(checkpoint["observations"] or [])
        for r in sessions.values():
            add(r, {"status": r["status"], "difficulty": r["difficulty"], "help": r["help_that_worked"], "next": r["next_action"]},
                {"Completion source": r.get('completion_source'), "Learner explained": r["learner_explained"], "Parent observation": r["parent_observation"],
                 "Evidence": r["evidence"], "Minutes": r["minutes"], "Phase": r["phase"], "Reading mode": r["reading_mode"],
                 "Completion summary": r.get("completion_summary"),
                 "conversation": conversations.get(r["id"], []), "evidence": photos.get(r["id"], []), "Saved discussion": observations.get(r["id"], []),
                 "Activity captures": [capture for (sid, _), captured in captures.items() if sid == r["id"] for capture in captured]})
        for event in db.all('topic_completion_events'):
            if event['completed'] and not event.get('closed_session_ids'):
                add(event,{'status':'Completed by user'}, {'Completion source':'manual','Note':'Marked complete by the user; no tutoring assessment was inferred.'},when=event['recorded_at'])
    elif view == "reviews":
        for r in db.all("reviews"):
            add(r, {"concept": r["concept"], "status": r["status"], "outcome": r["last_outcome"], "due": date_text(r["next_due"]), "next": r["next_prompt"]},
                {"Evidence": r["evidence"], "Last practice": date_text(r["last_practice"]), "Interval days": r["interval_days"],
                 "Next action": r["action"], "Session": r["evidence_session_id"]}, when=r["last_practice"] or r["updated_at"])
    elif view == "pending":
        assignments = {r["id"]: r for r in db.all("assignments")}
        for table, kind in (("checkpoints", "Lesson checkpoint"), ("lesson_actions", "Lesson activity"), ("assignment_items", "Book exercise")):
            for r in db.all(table):
                if r["status"] in ("closed", "completed", "reviewed", "done", "resolved"):
                    continue
                session_id = r.get("session_id") or assignments.get(r.get("assignment_id"), {}).get("session_id")
                session = sessions.get(session_id, {})
                if session.get("status") in ("closed", "completed", "finished"):
                    continue
                add({**r, "id": f"{table}:{r['id']}"}, {"kind": kind, "status": r["status"], "next": r.get("next_prompt") or r.get("prompt") or (r.get("snapshot") or {}).get("prompt", "")},
                    {"Session": session_id, "Phase": r.get("phase"), "Help given": r.get("help_given"), "Saved discussion": r.get("observations")}, when=session.get("date"))
    elif view == "reading":
        for r in topics.values():
            if r["archived"]:
                continue
            add(r, {"pages": f"{r['page_start']}–{r['page_end']}", "status": "Completed" if r["completed"] else "To read",
                "understanding": r["understanding"] or "Not checked", "next": r["next_step"]},
                {"Source reference": r["source_key"], "Last checked": date_text(r["last_checked"]), "Evidence session": r["evidence_session_id"]}, when=r["last_checked"] or r["updated_at"])
    elif view == "exercises":
        versions = {r["id"]: r for r in db.all("exercise_versions")}
        work = {}
        for item in sorted(db.all("assignment_items"), key=lambda r: r["created_at"]):
            work[item["exercise_id"]] = item["status"]
        attempts = {r["id"]: r for r in db.all("attempts")}
        for link in db.all("exercise_attempt_links"):
            attempt = attempts.get(link["attempt_id"], {})
            outcome = attempt.get("after_help_result") or attempt.get("first_result")
            status = ("Reviewed" if outcome in ("Correct", "With help") else
                      "Needs practice" if outcome in ("Not yet", "Partly correct") else
                      "Needs clarification" if outcome in ("Unreadable", "Source disputed") else "Not checked")
            work.setdefault(link["exercise_id"], status)
        for r in db.all("exercises"):
            book = books.get(r["book_id"], {})
            version = versions.get(r["active_version"], {})
            d = version.get("data", {})
            if r["archived"] or book.get("archived") or book.get("role") == "answer_key" or not d:
                continue
            add(r, {"book": d.get("book_name", ""), "reference": d.get("reference", ""), "pages": ", ".join(map(str, d.get("pages", []))),
                "status": d.get("status", ""), "key_status": d.get("answer_link_status", "Not linked"), "work": work.get(r["id"], "Not attempted")},
                {"Instructions": d.get("prompt") if d.get("student_safe") or d.get("source_reviewed") else "Source review required",
                 "Reading sections": [topics.get(req["topic_id"], {}).get("title", "") for req in d.get("requirements", [])],
                 "Mapping note": d.get("mapping_note"), "Version": r["active_version"]}, subject_id=book["subject_id"])
    elif view == "preparation":
        from tutoring.books import book_name
        for r in db.all("book_imports"):
            book = books.get(r["book_id"], {})
            if not book or book["archived"]:
                continue
            doc = documents[book["document_id"]]
            add(r, {"book": book_name(doc["original_filename"]), "role": book["role"], "status": r["status"],
                "pages": f"{r['done'] or 0} / {r['total'] or 0}", "next": r["error"] or r["stage"]},
                {"Stage": r["stage"], "Pause reason": r["error"], "Reading links only": r.get("mode") == "rematch"}, subject_id=book["subject_id"])
    return rows


def filtered(filters):
    db = store()
    if filters.child_id is not None and not db.get("children", filters.child_id):
        raise HTTPException(404, "Child not found")
    if filters.subject_id is not None:
        subject = db.get("subjects", filters.subject_id)
        if not subject or filters.child_id and subject["child_id"] != filters.child_id:
            raise HTTPException(400, "Choose a subject belonging to this child")
    rows = [r for r in rows_for(db, filters.view) if
        (filters.child_id is None or r["child_id"] == filters.child_id) and
        (filters.subject_id is None or r["subject_id"] == filters.subject_id) and
        (not filters.date_from or r["date"] >= filters.date_from.isoformat()) and
        (not filters.date_to or r["date"] <= filters.date_to.isoformat()) and
        (not filters.q or filters.q in str(r).casefold())]
    statuses = sorted({r.get("status", "") for r in rows if r.get("status")})
    if filters.status:
        rows = [r for r in rows if r.get("status") == filters.status]
    rows.sort(key=lambda r: r["id"])
    rows.sort(key=lambda r: str(r.get(filters.sort) or "").casefold(), reverse=filters.order == "desc")
    return rows, statuses


@router.get("/options")
def options():
    return {"views": [{"id": key, "label": label} for key, label in LABELS.items()],
        "subjects": [{"id": r["id"], "child_id": r["child_id"], "name": r["name"]} for r in store().all("subjects")]}


@router.get("")
def records(filters: Filters = Depends(), page: int = Query(1, ge=1), limit: int = Query(25, ge=1, le=100)):
    rows, statuses = filtered(filters)
    return {"view": filters.view, "columns": [{"key": k, "label": label} for k,label in COLUMNS[filters.view]],
        "rows": rows[(page-1)*limit:page*limit], "total": len(rows), "page": page, "limit": limit, "statuses": statuses}


@router.get("/export")
def export(filters: Filters = Depends()):
    rows, _ = filtered(filters)
    if len(rows) > 50000:
        raise HTTPException(400, "Choose a smaller date range to download at most 50,000 records")
    body = io.StringIO(newline="")
    writer = csv.writer(body)
    columns = COLUMNS[filters.view] + [("id", "Record ID")]
    writer.writerow([label for _,label in columns])
    def cell(value):
        text = str(value) if value is not None else ""
        return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text
    writer.writerows([[cell(row.get(k)) for k,_ in columns] for row in rows])
    return Response(body.getvalue().encode("utf-8-sig"), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="learning-records-{filters.view}.csv"', "Cache-Control": "private, no-store"})
