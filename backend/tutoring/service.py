"""Subject-independent tutoring records shared by the app and the MCP bridge.

Rules enforced here rather than left to the agent:

* An unfinished session is resumed before any new topic starts.
* First answers are immutable. Corrections are separate amendment attempts.
* Work that received help, a clue or a supplied answer is never recorded as
  independent.
* Checkpoint observations are append-only; they are unsaved observations, not
  mastery, and a checkpoint never completes a lesson.
* Finishing needs an explicit next topic. Opening the reader or finishing audio
  never completes anything.
* Every mutation names the session revision it was based on; a stale revision
  is a recoverable conflict.
"""
from __future__ import annotations

import json
import re
import threading
from datetime import date, datetime, timedelta, timezone

from storage import StoreError

from . import audio as audio_mod
from . import passages

RESULTS = ("Correct", "Partly correct", "Not yet", "Unanswered", "Unreadable", "Source disputed")
INDEPENDENCE = ("independent", "with_help", "not_assessed")
UNDERSTANDING = ("Independent", "With help", "Needs help", "Not assessed")
REVIEW_OUTCOMES = ("Independent", "With help", "Not yet")
OPEN_SESSION = ("active", "unfinished")
REVIEW_INTERVALS = (2, 7, 21)


class TutorError(StoreError):
    status_code = 400


class TutorConflict(StoreError):
    status_code = 409


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def _clean(value, limit=4000):
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] if text else None


class TutorService:
    def __init__(self, ctx):
        self.ctx = ctx
        self._readers_path = ctx.config.dir / "readers.json"
        self._lock = threading.Lock()
        self._readers = json.loads(self._readers_path.read_text()) if self._readers_path.exists() else {}

    @property
    def store(self):
        return self.ctx.store

    # ── selection and context ───────────────────────────────────────────────
    def learners(self) -> list[dict]:
        result = []
        for child in sorted(self.store.all("children"), key=lambda c: c["id"]):
            subjects = sorted(self.store.find("subjects", child_id=child["id"]), key=lambda s: s["name"])
            result.append({"child_id": child["id"], "name": child["name"],
                           "subjects": [{"subject_id": s["id"], "name": s["name"]} for s in subjects]})
        return result

    def _subject(self, child_id: int, subject_id: int) -> dict:
        subject = self.store.get("subjects", subject_id)
        if not subject or subject["child_id"] != child_id:
            raise TutorError("That subject does not belong to this learner")
        return subject

    def _topics(self, subject_id: int) -> list[dict]:
        return sorted(self.store.find("topics", subject_id=subject_id), key=lambda t: t["chapter_order"] or 0)

    def open_session(self, child_id: int, subject_id: int) -> dict | None:
        sessions = [s for s in self.store.find("tutor_sessions", child_id=child_id, subject_id=subject_id)
                    if s["status"] in OPEN_SESSION]
        return max(sessions, key=lambda s: (s["started_at"] or _now(), s["id"])) if sessions else None

    def open_checkpoint(self, session_id: str) -> dict | None:
        rows = [c for c in self.store.find("checkpoints", session_id=session_id) if c["status"] == "open"]
        return rows[-1] if rows else None

    def current_topic(self, child_id: int, subject_id: int) -> tuple[dict | None, dict | None]:
        session = self.open_session(child_id, subject_id)
        if session:
            return self.store.get("topics", session["topic_id"]), session
        finished = sorted((s for s in self.store.find("tutor_sessions", child_id=child_id, subject_id=subject_id)
                           if s["status"] == "completed" and s["next_topic_id"]),
                          key=lambda s: (s["finished_at"] or s["updated_at"], s["id"]))
        if finished:
            return self.store.get("topics", finished[-1]["next_topic_id"]), None
        return next((t for t in self._topics(subject_id) if not t["completed"]), None), None

    def _topic_summary(self, topic: dict | None) -> dict | None:
        if not topic:
            return None
        pdf_start, pdf_end = passages.pdf_range(topic)
        chapter = self._chapter_for(topic)
        verified = any(p["status"] == "verified" for p in self.store.find("passages", topic_id=topic["id"]))
        return {"topic_id": topic["id"], "source_key": topic["source_key"], "title": topic["title"],
                "chapter": chapter["chapter"] if chapter else None, "chapter_title": chapter["title"] if chapter else None,
                "printed_pages": [topic["page_start"], topic["page_end"]], "pdf_pages": [pdf_start, pdf_end],
                "start_at": topic["start_at"], "stop_before": topic["stop_before"], "completed": topic["completed"],
                "understanding": topic["understanding"] or "Not assessed", "passage_reviewed": verified,
                "next_step": topic["next_step"]}

    def _chapter_for(self, topic: dict) -> dict | None:
        match = re.match(r"C(\d+)-", topic.get("source_key") or "")
        if not match:
            return None
        return next((c for c in self.store.find("chapters", subject_id=topic["subject_id"])
                     if c["chapter"] == int(match[1])), None)

    def context(self, child_id: int, subject_id: int, phase: str = "start", questions: list[int] | None = None) -> dict:
        child = self.store.get("children", child_id)
        if not child:
            raise TutorError("Unknown learner")
        subject = self._subject(child_id, subject_id)
        topic, session = self.current_topic(child_id, subject_id)
        today = date.today()
        reviews = self.store.find("reviews", child_id=child_id)
        subject_topics = {t["id"] for t in self._topics(subject_id)}
        reviews = [r for r in reviews if r["topic_id"] in subject_topics]
        checkpoint = self.open_checkpoint(session["id"]) if session else None
        recent = sorted((s for s in self.store.find("tutor_sessions", child_id=child_id, subject_id=subject_id)
                         if s["status"] == "completed"), key=lambda s: (s["date"] or today, s["id"]))[-2:]
        packet = {
            "learner": {"child_id": child_id, "name": child["name"]},
            "subject": {"subject_id": subject_id, "name": subject["name"]},
            "preferences": {p["key"]: p["value"] for p in self.store.find("preferences", child_id=child_id)},
            "topic": self._topic_summary(topic),
            "session": self._session_view(session) if session else None,
            "resume": ({"session_id": session["id"], "phase": (checkpoint or session)["phase"],
                        "next_prompt": checkpoint["next_prompt"] if checkpoint else None,
                        "observations": checkpoint["observations"] if checkpoint else [],
                        "basis": checkpoint["basis"] if checkpoint else None}
                       if session else None),
            "recent_sessions": [{k: s[k] for k in ("id", "date", "topic_id", "learner_explained", "difficulty",
                                                   "next_action")} for s in recent],
            "due_reviews": [self._review_view(r) for r in reviews if r["status"] == "Open"
                            and r["next_due"] and r["next_due"] <= today],
            "open_reviews": sum(1 for r in reviews if r["status"] == "Open"),
            "sync": {k: v for k, v in self.store.status().items()
                     if k in ("state", "pending", "needs_reconciliation", "maintenance", "online", "auth_required")},
            "reminders": ["Resume the saved next prompt before anything new." if session else
                          "Begin with a short welcome and at most one recall question.",
                          "Checkpoints and open readers are not completion or mastery."],
        }
        if phase == "reading":
            if not topic:
                raise TutorError("No current topic")
            packet["reading"] = passages.load(self.ctx, topic)
        elif phase == "grading":
            if not questions:
                raise TutorError("Name the question numbers to grade; the whole key is never loaded")
            packet["grading"] = self.grading(topic, questions)
        elif phase == "closeout":
            packet["prior_attempts"] = [self._attempt_view(a) for a in self.store.find("attempts", child_id=child_id)
                                        if topic and a["topic_id"] == topic["id"]]
            packet["open_reviews_detail"] = [self._review_view(r) for r in reviews if r["status"] == "Open"]
            packet["next_topic_candidates"] = self._next_candidates(topic)
        elif phase != "start":
            raise TutorError("Phase must be start, reading, grading or closeout")
        return packet

    def _next_candidates(self, topic):
        if not topic:
            return []
        ordered = self._topics(topic["subject_id"])
        index = next(i for i, t in enumerate(ordered) if t["id"] == topic["id"])
        return [{"topic_id": t["id"], "source_key": t["source_key"], "title": t["title"]} for t in ordered[index + 1:index + 3]]

    def grading(self, topic: dict | None, questions: list[int]) -> dict:
        """Teacher-only key entries and passage evidence for the requested questions only."""
        if not topic:
            raise TutorError("No current topic")
        chapter = self._chapter_for(topic)
        if not chapter:
            raise TutorError("This topic is not linked to a chapter test")
        maps = {m["question"]: m for m in self.store.find("question_maps", subject_id=topic["subject_id"],
                                                          chapter=chapter["chapter"])}
        unmapped = [q for q in questions if q not in maps]
        if unmapped:
            raise TutorError(f"Questions {unmapped} are not mapped to chapter {chapter['chapter']}")
        other_topic = [q for q in questions if maps[q]["topic_id"] != topic["id"]]
        keys = self.store.find("teacher_keys", subject_id=topic["subject_id"], chapter=chapter["chapter"])
        items = []
        for number in questions:
            key = next((k for k in keys if k["question_start"] <= number <= k["question_end"]), None)
            items.append({"question": number, "topic_id": maps[number]["topic_id"], "anchor": maps[number]["anchor"],
                          "passage_evidence": maps[number]["evidence"], "note": maps[number]["note"],
                          "key_answer": key["answer"] if key else None, "key_exception": key["exception"] if key else None,
                          "key_pdf_page": key["key_pdf_page"] if key else chapter["key_pdf_page"]})
        return {"chapter": chapter["chapter"], "test_pdf_pages": [chapter["test_pdf_start"], chapter["test_pdf_end"]],
                "test_printed_pages": [chapter["test_print_start"], chapter["test_print_end"]],
                "items": items, "outside_current_topic": other_topic,
                "reminder": "Read the actual question and passage before grading; key text alone is insufficient. "
                            "Never show key material to the learner before an attempt."}

    def assignments(self, topic: dict) -> dict:
        chapter = self._chapter_for(topic)
        maps = [m for m in self.store.find("question_maps", topic_id=topic["id"])]
        return {"topic_id": topic["id"], "chapter": chapter["chapter"] if chapter else None,
                "questions": sorted(m["question"] for m in maps),
                "test_document_id": chapter["test_document_id"] if chapter else None,
                "test_pdf_pages": [chapter["test_pdf_start"], chapter["test_pdf_end"]] if chapter else None,
                "test_printed_pages": [chapter["test_print_start"], chapter["test_print_end"]] if chapter else None,
                "scope": "Subsection practice does not complete a whole-chapter test."}

    # ── views ─────────────────────────────────────────────────────────────────
    @staticmethod
    def _session_view(s):
        return {k: s[k] for k in ("id", "child_id", "subject_id", "topic_id", "date", "status", "phase", "revision",
                                  "session_type", "learner_explained", "difficulty", "next_action", "next_topic_id")}

    @staticmethod
    def _review_view(r):
        return {k: r[k] for k in ("id", "topic_id", "concept", "evidence", "last_practice", "interval_days",
                                  "next_due", "status", "last_outcome", "next_prompt")}

    @staticmethod
    def _attempt_view(a):
        return {k: a[k] for k in ("id", "session_id", "question_ref", "first_answer", "first_result", "help_given",
                                  "revised_answer", "after_help_result", "independence", "amends_attempt_id")}

    # ── sessions ─────────────────────────────────────────────────────────────
    def _new_session_id(self, child_id: int, day: date) -> str:
        prefix = f"{day.isoformat()}-c{child_id}-"
        existing = [s["id"] for s in self.store.all("tutor_sessions") if s["id"].startswith(prefix)]
        return f"{prefix}{len(existing) + 1:02d}"

    def start(self, tx, child_id: int, subject_id: int, topic_id: int | None = None) -> dict:
        self._subject(child_id, subject_id)
        topic, session = self.current_topic(child_id, subject_id)
        if session:
            if topic_id and topic_id != session["topic_id"]:
                raise TutorConflict(f"Session {session['id']} for this learner is unfinished; resume or finish it "
                                    "before starting another topic")
            session = tx.update("tutor_sessions", session["id"], {"status": "active"})
            resumed = True
        else:
            if topic_id:
                topic = self.store.get("topics", topic_id)
                if not topic or topic["subject_id"] != subject_id:
                    raise TutorError("That topic is not part of this subject")
            if not topic:
                raise TutorError("Every topic in this subject is complete")
            today = date.today()
            session = tx.insert("tutor_sessions", {
                "id": self._new_session_id(child_id, today), "child_id": child_id, "subject_id": subject_id,
                "topic_id": topic["id"], "date": today, "status": "active", "phase": "start",
                "session_type": "lesson", "started_at": _now(), "source": "integrated tutor"})
            resumed = False
        checkpoint = self.open_checkpoint(session["id"])
        return {"session_id": session["id"], "resumed": resumed, "topic": self._topic_summary(topic),
                "next_prompt": checkpoint["next_prompt"] if checkpoint else None,
                "reader_path": self.reader_path(session)}

    def reader_path(self, session: dict) -> str:
        return (f"/lesson?learner={session['child_id']}&topic={session['topic_id']}&session={session['id']}")

    def guard(self, tx, session_id: str, expected_revision: int) -> dict:
        session = tx.get("tutor_sessions", session_id)
        if not session:
            raise TutorError("Unknown session")
        if session["status"] not in OPEN_SESSION:
            raise TutorConflict("This session is already finished")
        if expected_revision is None:
            raise TutorError("expected_revision is required for tutoring records")
        if session["revision"] != expected_revision:
            raise TutorConflict(f"Session {session_id} changed (revision {session['revision']}, expected "
                                f"{expected_revision}); reload context before saving")
        tx.touch("tutor_sessions", session_id)
        return session

    def checkpoint(self, tx, session_id: str, expected_revision: int, phase: str, next_prompt: str,
                   observations: list[dict], basis: str | None = None, minutes: int | None = None) -> dict:
        session = self.guard(tx, session_id, expected_revision)
        if not _clean(next_prompt):
            raise TutorError("A checkpoint needs the exact next prompt")
        clean_obs = []
        for item in observations:
            unknown = set(item) - {"prompt", "first_response", "help", "revision", "explanation_supplied", "note"}
            if unknown or not item.get("prompt") or "first_response" not in item:
                raise TutorError("Each observation needs prompt and first_response (verbatim); optional help, "
                                 "revision, explanation_supplied and note")
            clean_obs.append({k: _clean(v) for k, v in item.items() if v is not None})
        existing = next((c for c in tx.find("checkpoints", session_id=session_id) if c["status"] == "open"), None)
        if existing:
            earlier = existing["observations"] or []
            if clean_obs[:len(earlier)] != earlier:
                raise TutorError("Earlier observations are preserved exactly; add new observations after them "
                                 "(use 'note' for a correction)")
            tx.update("checkpoints", existing["id"], {"phase": phase, "next_prompt": _clean(next_prompt),
                                                      "observations": clean_obs})
        else:
            tx.insert("checkpoints", {"id": f"{session_id}-cp", "session_id": session_id,
                                      "child_id": session["child_id"], "topic_id": session["topic_id"],
                                      "phase": phase, "status": "open", "next_prompt": _clean(next_prompt),
                                      "observations": clean_obs, "basis": _clean(basis)
                                      or "Observed in the tutoring conversation; not a completed session or mastery"})
        changes = {"status": "unfinished", "phase": phase}
        if minutes is not None:
            changes["minutes"] = minutes
        tx.update("tutor_sessions", session_id, changes)
        return {"session_id": session_id, "observations": len(clean_obs), "status": "unfinished",
                "note": "Checkpoint saved as unfinished observations; this is not a completed lesson."}

    def attempts(self, tx, session_id: str, expected_revision: int, items: list[dict]) -> dict:
        session = self.guard(tx, session_id, expected_revision)
        saved = []
        for item in items:
            question_ref = _clean(item.get("question_ref"), 200)
            first_result = item.get("first_result")
            if not question_ref or first_result not in RESULTS:
                raise TutorError(f"Each attempt needs question_ref and first_result in {RESULTS}")
            help_given = _clean(item.get("help_given"))
            revised = _clean(item.get("revised_answer"))
            independence = item.get("independence")
            assisted = bool(help_given or revised or item.get("after_help_result"))
            if independence is None:
                independence = "with_help" if assisted else (
                    "independent" if first_result == "Correct" else "not_assessed")
            if independence not in INDEPENDENCE:
                raise TutorError(f"independence must be one of {INDEPENDENCE}")
            if independence == "independent" and assisted:
                raise TutorError(f"{question_ref}: assisted work cannot be recorded as independent")
            if first_result == "Unreadable" and item.get("after_help_result") == "Not yet":
                raise TutorError("Illegibility is not an error; ask about the answer instead")
            amends = item.get("amends_attempt_id")
            if amends and not tx.get("attempts", amends):
                raise TutorError(f"Attempt {amends} does not exist")
            topic_id = item.get("topic_id") or session["topic_id"]
            base = f"{session_id}-{re.sub(r'[^A-Za-z0-9]+', '', question_ref)[:40] or 'Q'}"
            attempt_id = item.get("id") or base
            suffix = 2
            while tx.get("attempts", attempt_id):
                if item.get("id"):
                    raise TutorError(f"Attempt {attempt_id} already exists; first answers are immutable. "
                                     "Record a correction with amends_attempt_id")
                attempt_id = f"{base}-{suffix}"
                suffix += 1
            chapter = self._chapter_for(tx.get("topics", topic_id) or {})
            saved.append(tx.insert("attempts", {
                "id": attempt_id, "session_id": session_id, "child_id": session["child_id"], "topic_id": topic_id,
                "chapter": item.get("chapter") or (chapter["chapter"] if chapter else None),
                "question_ref": question_ref, "question_text": _clean(item.get("question_text")),
                "first_answer": item.get("first_answer"), "reading_certainty": _clean(item.get("reading_certainty"), 40),
                "first_result": first_result, "help_given": help_given, "revised_answer": revised,
                "after_help_result": _clean(item.get("after_help_result"), 40), "independence": independence,
                "recheck_date": item.get("recheck_date"), "evidence_file_ids": item.get("evidence_file_ids"),
                "source_note": _clean(item.get("source_note")), "tutor_created": bool(item.get("tutor_created")),
                "amends_attempt_id": amends}))
        return {"session_id": session_id, "attempts": [a["id"] for a in saved]}

    def reviews(self, tx, session_id: str, expected_revision: int, items: list[dict]) -> dict:
        session = self.guard(tx, session_id, expected_revision)
        today = date.today()
        saved = []
        for item in items:
            review_id = item.get("id")
            current = tx.get("reviews", review_id) if review_id else None
            outcome = item.get("outcome")
            if outcome is not None and outcome not in REVIEW_OUTCOMES:
                raise TutorError(f"outcome must be one of {REVIEW_OUTCOMES}")
            status = item.get("status") or (current["status"] if current else "Open")
            if status == "Closed":
                if outcome != "Independent":
                    raise TutorError("Close a review only after a later independent check")
                if current and current["last_practice"] and current["last_practice"] >= today and \
                        current["evidence_session_id"] == session_id:
                    raise TutorError("The closing check must come in a later lesson than the difficulty")
            interval = item.get("interval_days")
            if interval is None:
                prior = current["interval_days"] if current else None
                if outcome == "Independent" and prior in REVIEW_INTERVALS[:-1]:
                    interval = REVIEW_INTERVALS[REVIEW_INTERVALS.index(prior) + 1]
                else:
                    interval = REVIEW_INTERVALS[0]
            values = {"last_practice": today if outcome else (current or {}).get("last_practice"),
                      "interval_days": interval, "status": status,
                      "next_due": None if status == "Closed" else today + timedelta(days=interval),
                      "last_outcome": outcome or (current or {}).get("last_outcome"),
                      "next_prompt": _clean(item.get("next_prompt")) or (current or {}).get("next_prompt"),
                      "evidence_session_id": session_id}
            if current:
                if item.get("evidence"):
                    values["evidence"] = (current["evidence"] + "\n" if current["evidence"] else "") + item["evidence"]
                saved.append(tx.update("reviews", current["id"], values))
            else:
                if not item.get("concept") or not item.get("evidence"):
                    raise TutorError("A new review needs a specific concept and the observed evidence")
                new_id = review_id or f"{session_id}-R{len(tx.find('reviews', evidence_session_id=session_id)) + 1:02d}"
                saved.append(tx.insert("reviews", {"id": new_id, "child_id": session["child_id"],
                                                   "topic_id": item.get("topic_id") or session["topic_id"],
                                                   "concept": _clean(item["concept"], 300),
                                                   "evidence": _clean(item["evidence"]), **values}))
        return {"session_id": session_id, "reviews": [r["id"] for r in saved]}

    def assign(self, tx, session_id: str, expected_revision: int, questions: list[int], note: str | None) -> dict:
        session = self.guard(tx, session_id, expected_revision)
        topic = tx.get("topics", session["topic_id"])
        available = set(self.assignments(topic)["questions"])
        outside = [q for q in questions if q not in available]
        if outside:
            raise TutorError(f"Questions {outside} are not mapped to this topic")
        number = len(tx.find("assignments", session_id=session_id)) + 1
        row = tx.insert("assignments", {"id": f"{session_id}-A{number}", "session_id": session_id,
                                        "child_id": session["child_id"], "topic_id": session["topic_id"],
                                        "questions": sorted(questions), "note": _clean(note), "status": "assigned"})
        return {"session_id": session_id, "assignment_id": row["id"], "questions": row["questions"]}

    def evidence(self, tx, session_id: str, expected_revision: int, filename: str, data: bytes, mime_type: str,
                 note: str | None) -> dict:
        session = self.guard(tx, session_id, expected_revision)
        if not mime_type.startswith("image/") and mime_type != "application/pdf":
            raise TutorError("Attach a photo or PDF of the learner's work")
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)[:80] or "work.jpg"
        file_id, sha = tx.add_blob(data, "Student Work", f"{session_id}-{safe}", mime_type)
        number = len(tx.find("evidence_files", session_id=session_id)) + 1
        row = tx.insert("evidence_files", {"id": f"{session_id}-E{number}", "child_id": session["child_id"],
                                           "session_id": session_id, "file_id": file_id, "sha256": sha,
                                           "filename": safe, "mime_type": mime_type, "note": _clean(note)})
        return {"session_id": session_id, "evidence_id": row["id"]}

    def finish(self, tx, session_id: str, expected_revision: int, payload: dict) -> dict:
        session = self.guard(tx, session_id, expected_revision)
        next_topic_id = payload.get("next_topic_id")
        next_topic = tx.get("topics", next_topic_id) if next_topic_id else None
        if not next_topic or next_topic["subject_id"] != session["subject_id"] or next_topic_id == session["topic_id"]:
            raise TutorError("Choose one explicit next topic in this subject (not the current one)")
        if not _clean(payload.get("learner_explained")):
            raise TutorError("Record what the learner actually explained or did")
        understanding = payload.get("understanding")
        if understanding is not None and understanding not in UNDERSTANDING:
            raise TutorError(f"understanding must be one of {UNDERSTANDING}")
        attempts = tx.find("attempts", session_id=session_id)
        if understanding == "Independent" and attempts and all(a["independence"] == "with_help" for a in attempts):
            raise TutorError("Every recorded attempt in this session had help; independent understanding needs a "
                             "fresh explanation without a substantive clue")
        tx.update("tutor_sessions", session_id, {
            "status": "completed", "phase": "finished", "finished_at": _now(), "next_topic_id": next_topic_id,
            "learner_explained": _clean(payload.get("learner_explained")),
            "difficulty": _clean(payload.get("difficulty")), "help_that_worked": _clean(payload.get("help_that_worked")),
            "next_action": _clean(payload.get("next_action")), "parent_observation": _clean(payload.get("parent_observation")),
            "minutes": payload.get("minutes"), "session_type": _clean(payload.get("session_type"), 80) or session["session_type"],
            "reading_mode": _clean(payload.get("reading_mode"), 80)})
        for checkpoint in tx.find("checkpoints", session_id=session_id):
            if checkpoint["status"] == "open":
                tx.update("checkpoints", checkpoint["id"], {"status": "resolved"})
        topic_changes = {"evidence_session_id": session_id, "last_checked": date.today()}
        if understanding:
            topic_changes["understanding"] = understanding
        if payload.get("next_step"):
            topic_changes["next_step"] = _clean(payload["next_step"])
        if payload.get("complete_topic") is True:
            topic = tx.get("topics", session["topic_id"])
            topic_changes["completed"] = True
            topic_changes["completed_at"] = topic["completed_at"] or _now()
        tx.update("topics", session["topic_id"], topic_changes)
        for chapter_update in payload.get("chapter_updates") or []:
            chapter = next((c for c in tx.find("chapters", subject_id=session["subject_id"])
                            if c["chapter"] == chapter_update.get("chapter")), None)
            if not chapter:
                raise TutorError("Unknown chapter")
            allowed = {k: v for k, v in chapter_update.items()
                       if k in ("test_status", "test_date", "items_to_revisit", "note")}
            tx.update("chapters", chapter["id"], {**allowed, "session_id": session_id})
        self.close_reader(session_id)
        return {"session_id": session_id, "status": "completed", "next_topic_id": next_topic_id,
                "topic_completed": payload.get("complete_topic") is True}

    def preference(self, tx, child_id: int, key: str, value, confirmed_by: str) -> dict:
        if not self.store.get("children", child_id):
            raise TutorError("Unknown learner")
        if not confirmed_by:
            raise TutorError("Record only preferences the learner or parent confirmed")
        preference_id = f"{child_id}:{key}"
        values = {"child_id": child_id, "key": key, "value": value, "confirmed_by": confirmed_by,
                  "confirmed_at": _now()}
        if tx.get("preferences", preference_id):
            tx.update("preferences", preference_id, values)
        else:
            tx.insert("preferences", {"id": preference_id, **values})
        return {"preference": preference_id}

    # ── reader (learner-safe) ────────────────────────────────────────────────
    def _save_readers(self):
        self._readers_path.write_text(json.dumps(self._readers), encoding="utf-8")

    def open_reader(self, session_id: str):
        with self._lock:
            self._readers[session_id] = {"state": "open", "opened_at": _now().isoformat()}
            self._save_readers()

    def close_reader(self, session_id: str):
        with self._lock:
            entry = self._readers.setdefault(session_id, {})
            entry.update(state="closed", closed_at=_now().isoformat())
            self._save_readers()

    def reader_state(self, session_id: str) -> str:
        session = self.store.get("tutor_sessions", session_id)
        if not session or session["status"] not in OPEN_SESSION:
            return "closed"
        return self._readers.get(session_id, {}).get("state", "open")

    def reader(self, child_id: int, topic_id: int, session_id: str | None) -> dict:
        topic = self.store.get("topics", topic_id)
        subject = self.store.get("subjects", topic["subject_id"]) if topic else None
        if not topic or subject["child_id"] != child_id:
            raise TutorError("This lesson is not assigned to that learner")
        if session_id:
            session = self.store.get("tutor_sessions", session_id)
            if not session or session["topic_id"] != topic_id or session["child_id"] != child_id:
                raise TutorError("This reader link does not match the lesson")
        package = passages.load(self.ctx, topic)
        return {"learner": {"child_id": child_id, "name": self.store.get("children", child_id)["name"]},
                "subject_name": subject["name"], "session_id": session_id,
                "reader_state": self.reader_state(session_id) if session_id else "open",
                "passage": package, "audio": self.audio_tracks(topic, package)}

    def audio_tracks(self, topic: dict, package: dict) -> list[dict]:
        tracks = []
        for row in self.store.find("audio_tracks", topic_id=topic["id"]):
            synchronized = False
            reason = row["note"] or ""
            if row["status"] == "ready" and row["timing"] and row["manifest_file_id"]:
                try:
                    manifest = json.loads(self.ctx.file_bytes(row["manifest_file_id"], None))
                    synchronized, reason = audio_mod.validate_manifest(manifest, package["passage_sha256"],
                                                                       len(package["sentences"]))
                except Exception as error:  # an unreadable manifest must not hide the reader
                    reason = f"Timing unavailable: {error}"
            tracks.append({"track_id": row["id"], "provider": row["provider"], "voice": row["voice"],
                           "speaking_rate": row["speaking_rate"], "status": row["status"],
                           "synchronized": synchronized, "note": None if synchronized else reason})
        return tracks
