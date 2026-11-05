"""Subject-independent tutoring records shared by the app and the MCP bridge.

Rules enforced here rather than left to the agent:

* Explicit topic selection resumes that topic only; other unfinished lessons stay saved.
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

from storage import StoreError, layout

from . import audio as audio_mod
from . import guide as guide_mod
from . import passages
from . import skills
from .automatic_voice import status as voice_preparation_status

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
        from .interactive import InteractiveTutor
        self.interactive = InteractiveTutor(self)

    @property
    def store(self):
        return self.ctx.store

    # ── selection and context ───────────────────────────────────────────────
    def learners(self) -> list[dict]:
        result = []
        for child in sorted(self.store.all("children"), key=lambda c: c["id"]):
            subjects = sorted((s for s in self.store.find("subjects", child_id=child["id"]) if s.get('purpose') != 'library_paused'), key=lambda s: s["name"])
            result.append({"child_id": child["id"], "name": child["name"],
                           "subjects": [{"subject_id": s["id"], "name": s["name"]} for s in subjects]})
        return result

    def _subject(self, child_id: int, subject_id: int) -> dict:
        subject = self.store.get("subjects", subject_id)
        if not subject or subject["child_id"] != child_id:
            raise TutorError("That subject does not belong to this learner")
        return subject

    def _topics(self, subject_id: int) -> list[dict]:
        return sorted((t for t in self.store.find("topics", subject_id=subject_id) if not t.get("archived") and t["is_core"]), key=lambda t: t["chapter_order"] or 0)

    def open_session(self, child_id: int, subject_id: int, topic_id: int | None = None) -> dict | None:
        sessions = [s for s in self.store.find("tutor_sessions", child_id=child_id, subject_id=subject_id)
                    if s["status"] in OPEN_SESSION and (topic_id is None or s['topic_id']==topic_id)]
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
            candidate=self.store.get("topics", finished[-1]["next_topic_id"])
            if candidate and not candidate.get('completed') and not candidate.get('archived'):
                return candidate,None
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
        from .family_skill import packet as family_packet
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
        subject_actions = self.store.find("lesson_actions", child_id=child_id, subject_id=subject_id)
        replaced_actions = {a["source_action_id"] for a in subject_actions if a["source_action_id"]}
        recent = sorted((s for s in self.store.find("tutor_sessions", child_id=child_id, subject_id=subject_id)
                         if s["status"] == "completed"), key=lambda s: (s["date"] or today, s["id"]))[-2:]
        packet = {
            "learner": {"child_id": child_id, "name": child["name"]},
            "subject": {"subject_id": subject_id, "name": subject["name"]},
            "teaching_skill": skills.packet(self.store, subject),
            "family_tutoring": family_packet(self.store, child_id),
            "pending_assignments": [a for a in self.store.find("assignments", child_id=child_id)
                                    if a["topic_id"] in subject_topics and a["status"] == "assigned"],
            "pending_actions": [a for a in subject_actions if a["status"] in ("pending", "skipped") and a["id"] not in replaced_actions
                                and (self.store.get('tutor_sessions', a['session_id']) or {}).get('status') != 'superseded'
                                and (self.store.get('tutor_sessions', a['session_id']) or {}).get('completion_source') not in ('manual','topic_completion')],
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
            "storage": {k: v for k, v in self.store.status().items() if k in ("state", "drive_folder_available")},
            "reminders": ["An unfinished lesson is saved; resume it or choose another chapter." if session else
                          "Begin with a short welcome and at most one recall question.",
                          "Checkpoints and open readers are not completion or mastery."],
        }
        if hasattr(self.ctx, "books"):
            packet["available_exercises"] = self.ctx.books.eligible(topic, include_optional=True) if topic else []
            packet["pending_exercise_items"] = [{"id": i["id"], "exercise_id": i["exercise_id"], "version_id": i["version_id"],
                "topic_id": i["topic_id"], "status": i["status"], **self.ctx.books.public(i["snapshot"])}
                for i in self.store.find("assignment_items", child_id=child_id) if i["topic_id"] in subject_topics and i["status"] != "reviewed"]
        packet["learning_memory"] = self.ctx.learning_memory.packet(child_id, subject_id, topic["id"] if topic else None)
        from .source_annotations import packet as annotation_packet
        packet['source_annotations']=annotation_packet(self.store,topic) if topic else []
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
        from .source_annotations import packet as annotation_packet
        return {"chapter": chapter["chapter"], "source_annotations":annotation_packet(self.store,topic,assessment=True),
                "test_pdf_pages": [chapter["test_pdf_start"], chapter["test_pdf_end"]],
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
                                  "session_type", "completion_source", "learner_explained", "difficulty", "next_action", "next_topic_id")}

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
        topic, session = (self.store.get('topics',topic_id),self.open_session(child_id,subject_id,topic_id)) if topic_id else self.current_topic(child_id, subject_id)
        if topic_id and (not topic or topic['subject_id']!=subject_id):
            raise TutorError('That topic is not part of this subject')
        if session and (tx.get('tutor_sessions', session['id']) or {}).get('status') not in OPEN_SESSION:
            session = None  # a replacement can retire the old session in this transaction
        if session:
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
                "session_type": "repeat" if topic.get('completed') else "lesson", "started_at": _now(), "source": "integrated tutor"})
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
            checkpoint_id = f"{session_id}-cp"
            if tx.get("checkpoints", checkpoint_id):
                checkpoint_id = f"{session_id}-cp-{len(tx.find('checkpoints', session_id=session_id)) + 1}"
            tx.insert("checkpoints", {"id": checkpoint_id, "session_id": session_id,
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
            if independence == "independent" and first_result != "Correct":
                raise TutorError("Only a correct, unassisted answer can establish independent understanding")
            if first_result == "Unreadable" and item.get("after_help_result") == "Not yet":
                raise TutorError("Illegibility is not an error; ask about the answer instead")
            amends = item.get("amends_attempt_id")
            amended = tx.get("attempts", amends) if amends else None
            if amends and (not amended or amended["child_id"] != session["child_id"] or
                           amended["session_id"] != session_id):
                raise TutorError("The amended attempt must belong to this session")
            topic_id = item.get("topic_id") or session["topic_id"]
            related = tx.get("topics", topic_id)
            if not related or related["subject_id"] != session["subject_id"]:
                raise TutorError("The attempt topic must belong to this subject")
            paths = item.get("evidence_paths") or []
            owned = {e["file_path"] for e in tx.find("evidence_files", session_id=session_id)}
            if any(p not in owned for p in paths):
                raise TutorError("Evidence must belong to this session")
            assigned = tx.get("assignment_items", item.get("assignment_item_id")) if item.get("assignment_item_id") else None
            if item.get("exercise_id") and not assigned:
                raise TutorError("An exercise attempt needs its owned assignment item")
            if item.get("assignment_item_id"):
                book = tx.get("subject_books", tx.get("exercises", assigned["exercise_id"])["book_id"]) if assigned else None
                if not assigned or assigned["child_id"] != session["child_id"] or not book or book["subject_id"] != session["subject_id"] or assigned["exercise_id"] != item.get("exercise_id"):
                    raise TutorError("The exercise must belong to this learner and subject")
                if amended and amended.get("assignment_item_id") != assigned["id"]:
                    raise TutorError("The amendment must refer to the same exercise item")
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
                "recheck_date": item.get("recheck_date"), "evidence_paths": item.get("evidence_paths"),
                "source_note": _clean(item.get("source_note")), "tutor_created": bool(item.get("tutor_created")),
                "amends_attempt_id": amends, "assignment_item_id": item.get("assignment_item_id"), "exercise_id": item.get("exercise_id")}))
            if assigned and not amends:
                result = item.get("after_help_result") or first_result
                tx.update("assignment_items", assigned["id"], {"status": "reviewed" if result == "Correct" else "pending"})
                siblings = tx.find("assignment_items", assignment_id=assigned["assignment_id"])
                tx.update("assignments", assigned["assignment_id"], {"status": "reviewed" if all(i["status"] == "reviewed" for i in siblings) else "assigned"})
        self.ctx.learning_memory.refresh(tx, session["child_id"], session["subject_id"])
        return {"session_id": session_id, "attempts": [a["id"] for a in saved]}

    def reviews(self, tx, session_id: str, expected_revision: int, items: list[dict]) -> dict:
        session = self.guard(tx, session_id, expected_revision)
        today = date.today()
        saved = []
        for item in items:
            review_id = item.get("id")
            current = tx.get("reviews", review_id) if review_id else None
            topic_id = item.get("topic_id") or (current or {}).get("topic_id") or session["topic_id"]
            related = tx.get("topics", topic_id)
            if not related or related["subject_id"] != session["subject_id"] or (current and current["child_id"] != session["child_id"]):
                raise TutorError("The review must belong to this learner and subject")
            exercise_id = item.get("exercise_id") or (current or {}).get("exercise_id")
            assigned_id = item.get("assignment_item_id") or (current or {}).get("assignment_item_id")
            if exercise_id:
                exercise = tx.get("exercises", exercise_id)
                book = tx.get("subject_books", exercise["book_id"]) if exercise else None
                assigned = tx.get("assignment_items", assigned_id) if assigned_id else None
                if not book or book["subject_id"] != session["subject_id"] or (assigned_id and (not assigned or assigned["exercise_id"] != exercise_id or assigned["child_id"] != session["child_id"])):
                    raise TutorError("The review exercise must belong to this learner and subject")
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
            if exercise_id:
                values.update(exercise_id=exercise_id, assignment_item_id=assigned_id)
            if current:
                if item.get("evidence"):
                    values["evidence"] = (current["evidence"] + "\n" if current["evidence"] else "") + item["evidence"]
                saved.append(tx.update("reviews", current["id"], values))
            else:
                if not item.get("concept") or not item.get("evidence"):
                    raise TutorError("A new review needs a specific concept and the observed evidence")
                new_id = review_id or f"{session_id}-R{len(tx.find('reviews', evidence_session_id=session_id)) + 1:02d}"
                saved.append(tx.insert("reviews", {"id": new_id, "child_id": session["child_id"],
                                                   "topic_id": topic_id,
                                                   "concept": _clean(item["concept"], 300),
                                                   "evidence": _clean(item["evidence"]), **values}))
        self.ctx.learning_memory.refresh(tx, session["child_id"], session["subject_id"])
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
                 note: str | None, action_id: str | None = None) -> dict:
        session = self.guard(tx, session_id, expected_revision)
        if action_id:
            playback = tx.get("lesson_playback", session_id)
            action = tx.get("lesson_actions", f"{session_id}:{action_id}")
            if not playback or playback["action_id"] != action_id or not action or action["status"] != "pending":
                raise TutorConflict("Attach the photo to the current paused student action")
        if not mime_type.startswith("image/") and mime_type != "application/pdf":
            raise TutorError("Attach a photo or PDF of the learner's work")
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)[:80] or "work.jpg"
        path, sha = tx.add_blob(data, layout.for_session(tx, session_id, layout.STUDENT_WORK), f"{session_id}-{safe}",
                                mime_type)
        number = len(tx.find("evidence_files", session_id=session_id)) + 1
        row = tx.insert("evidence_files", {"id": f"{session_id}-E{number}", "child_id": session["child_id"],
                                           "session_id": session_id, "file_path": path, "sha256": sha,
                                           "filename": safe, "mime_type": mime_type, "note": _clean(note),
                                           "action_id": action_id, "size_bytes": len(data)})
        return {"session_id": session_id, "evidence_id": row["id"]}

    def finish(self, tx, session_id: str, expected_revision: int, payload: dict) -> dict:
        session = self.guard(tx, session_id, expected_revision)
        next_topic_id = payload.get("next_topic_id")
        next_topic = tx.get("topics", next_topic_id) if next_topic_id else None
        end_of_subject = payload.get("end_of_subject") is True
        remaining = [t for t in self._topics(session["subject_id"]) if t["id"] != session["topic_id"] and not t["completed"]]
        if end_of_subject and (next_topic_id or remaining):
            raise TutorError("End of subject is only valid when no other topics remain")
        if not end_of_subject and (not next_topic or next_topic["subject_id"] != session["subject_id"] or next_topic_id == session["topic_id"]):
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
            topic_changes['completion_source']='tutor'
        tx.update("topics", session["topic_id"], topic_changes)
        if payload.get("complete_topic") is True:
            from services.completion_tracking import complete_scheduled_history
            complete_scheduled_history(tx, {session["topic_id"]}, _now())
        for chapter_update in payload.get("chapter_updates") or []:
            chapter = next((c for c in tx.find("chapters", subject_id=session["subject_id"])
                            if c["chapter"] == chapter_update.get("chapter")), None)
            if not chapter:
                raise TutorError("Unknown chapter")
            allowed = {k: v for k, v in chapter_update.items()
                       if k in ("test_status", "test_date", "items_to_revisit", "note")}
            tx.update("chapters", chapter["id"], {**allowed, "session_id": session_id})
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

    def _resume_same(self, session, guide):
        """This lesson's unfinished session. When it runs an earlier version of
        the script than the one now prepared, say so: the family chooses whether
        to continue it or start the updated lesson."""
        playback = self.store.get('lesson_playback', session['id']) if session else None
        if not playback:
            return None
        earlier = bool(guide and guide.get('current') and guide['guide_id'] != playback['guide_id'])
        return {"path": self.reader_path(session), "session_id": session['id'], "revision": session['revision'],
                "earlier_version": earlier, **({"updated_guide_id": guide['guide_id']} if earlier else {})}

    def reader(self, child_id: int, topic_id: int, session_id: str | None) -> dict:
        topic = self.store.get("topics", topic_id)
        subject = self.store.get("subjects", topic["subject_id"]) if topic else None
        if not topic or subject["child_id"] != child_id:
            raise TutorError("This lesson is not assigned to that learner")
        if session_id:
            session = self.store.get("tutor_sessions", session_id)
            if not session or session["topic_id"] != topic_id or session["child_id"] != child_id:
                raise TutorError("This reader link does not match the lesson")
        playback = self.store.get("lesson_playback", session_id) if session_id else None
        pinned = self.store.get("guides", playback["guide_id"]) if playback else None
        package = (pinned or {}).get("source_snapshot") or passages.load(self.ctx, topic)
        guide = self.guide(topic, package, playback["guide_id"] if playback else None)
        unfinished = self.open_session(child_id, subject["id"])
        same_lesson = self.open_session(child_id, subject['id'], topic_id) if not session_id else None
        resume_lesson = None
        if unfinished and unfinished["topic_id"] != topic_id:
            resume_lesson = {"title": self.store.get("topics", unfinished["topic_id"])["title"],
                             "path": self.reader_path(unfinished)}
        return {"learner": {"child_id": child_id, "name": self.store.get("children", child_id)["name"]},
                "subject_name": subject["name"], "language": audio_mod.language_of(self.store, subject),
                "session_id": session_id,
                "interactive": bool(playback), "resume_lesson": resume_lesson,
                "resume_current_lesson": self._resume_same(same_lesson, guide),
                "reader_state": self.reader_state(session_id) if session_id else "open",
                "passage": package,
                "audio": self.audio_tracks(topic, package, exclude=guide["passage_sha256"] if guide else None),
                "guide": {**guide, "audio": self.audio_tracks(topic, guide, only=guide["passage_sha256"]),
                          "voice_preparation": voice_preparation_status(self.ctx, guide["guide_id"])}
                if guide else None,
                "warm_up": None if session_id else self.warm_up(topic)}

    def warm_up(self, topic: dict) -> dict | None:
        """Before a lesson starts: where it sits (last, today, next) and the
        tutor's closing words from the last finished lesson, with their saved
        recording when one exists. Nothing to answer."""
        order = lambda t: (t.get("chapter_order") or 0, t["id"])
        topics = sorted((t for t in self.store.find("topics", subject_id=topic["subject_id"])
                         if t.get("is_core") and not t.get("archived")), key=order)
        if not any(t["id"] == topic["id"] for t in topics):
            return None
        here = next(i for i, t in enumerate(topics) if t["id"] == topic["id"])
        last = next((t for t in reversed(topics[:here]) if t["completed"]), None)
        upcoming = next((t for t in topics[here + 1:] if not t["completed"]), None)
        return {"last": last and {"title": last["title"], **self._closing_words(last)},
                "today": topic["title"], "next": upcoming and upcoming["title"]}

    def _closing_words(self, topic: dict) -> dict:
        rows = sorted(self.store.find("guides", topic_id=topic["id"]), key=lambda g: str(g.get("created_at")), reverse=True)
        for row in rows:
            try:
                content = json.loads(self.ctx.file_bytes(row["guide_path"], row.get("guide_file_sha256")))
            except Exception:
                continue
            closing = next((a for a in content.get("activities", []) if a.get("kind") == "close_lesson"), None)
            text = ((closing or {}).get("content") or {}).get("text")
            if not text:
                continue
            words = {"summary": text}
            track = next((t for t in self.store.find("audio_tracks", topic_id=topic["id"])
                          if t["passage_sha256"] == row["guide_sha256"] and t.get("manifest_path") and t.get("status") in (None, "ready")), None)
            if track and closing.get("start_sentence") is not None:
                try:
                    parts = json.loads(self.ctx.file_bytes(track["manifest_path"], None)).get("tracks", [])
                    start = closing["start_sentence"]
                    part = next((i for i, p in enumerate(parts) if p.get("startSentence") is not None
                                 and p["startSentence"] <= start < p["startSentence"] + (p.get("sentenceCount") or 0)), None)
                    if part is not None:
                        words["audio"] = {"track_id": track["id"], "part": part}
                except Exception:
                    pass
            return words
        return {}

    def guide(self, topic: dict, package: dict, guide_id: str | None = None) -> dict | None:
        """The lesson's guided walk-through, if one was written (see tutoring/guide.py)."""
        skill = skills.packet(self.store, self.store.get("subjects", topic["subject_id"]))
        row, fresh = guide_mod.current_row(self.store, topic["id"], package["passage_sha256"], skill["sha256"])
        from . import library_materials
        shared_book = library_materials.book_for(self.store, topic['subject_id'])
        if row:
            from .visual_source import current as current_sources
            fresh = fresh and current_sources(self.ctx,row,topic)
            from .source_annotations import packet as annotation_packet
            frozen_notes=(row.get('context_snapshot') or {}).get('source_annotations') or []
            fresh=fresh and frozen_notes==annotation_packet(self.store,topic)
            from .family_skill import packet as family_packet
            family = family_packet(self.store, self.store.get('subjects', topic['subject_id'])['child_id'])
            if shared_book:
                from .family_skill import current, digest
                common = current(self.store)
                family = {**family, 'sha256': digest(common['content'], {})}
                frozen = row.get('context_snapshot') or {}
                fresh = fresh and frozen.get('library_shared_policy') == library_materials.VERSION
                material = library_materials.latest(self.store, frozen.get('library_material_key')) if frozen.get('library_material_key') else None
                if material:
                    fresh = fresh and guide_mod.guide_sha(material['data']['built']['sentences']) == row['guide_sha256']
            recorded_family = (row.get('context_snapshot') or {}).get('family_tutoring')
            fresh = fresh and (recorded_family.get('sha256') == family['sha256'] if recorded_family else family['version'] == 0)
        if row and hasattr(self.ctx, "books"):
            recorded = (row.get("context_snapshot") or {}).get("workbook_fingerprint")
            books = self.store.find("subject_books", subject_id=topic["subject_id"])
            has_catalog = any(b["active_index"] for b in books)
            if not shared_book:
                fresh = fresh and (recorded == self.ctx.books.fingerprint(topic["subject_id"]) or (recorded is None and not has_catalog))

        if guide_id:
            row = self.store.get("guides", guide_id)
            if row and row["topic_id"] != topic["id"]:
                raise TutorError("The guide does not belong to this topic")
            fresh = True  # active sessions keep their prepared guide and instructions
        if not row:
            return None
        try:
            result = guide_mod.package(self.ctx, row, fresh)
            if not guide_id:
                from .lesson_context import preparation
                subject = self.store.get("subjects", topic["subject_id"])
                adaptive = preparation(self.ctx, subject["child_id"], topic, package)
                if shared_book:
                    shared_source = library_materials.neutral_context(self.ctx, adaptive)
                    if (row.get('context_snapshot') or {}).get('visual_source'):
                        shared_source['subject_sources'].pop('page_structure', None)
                    expected = library_materials.key(self.ctx, topic, package, row['language'], skill, shared_source)
                    result['current'] = result['current'] and expected == (row.get('context_snapshot') or {}).get('library_material_key')
                from . import lesson_quality
                try:
                    from .source_spacing import reading_requirements
                    requirements=reading_requirements(adaptive['source_requirements'],
                        (row.get('context_snapshot') or {}).get('source_spacing'))
                    lesson_quality.validate({'activities':result['activities']},requirements)
                except guide_mod.GuideError:
                    # Newly indexed source obligations can expose an omission in
                    # an older guide. Preserve that thread but never reuse its
                    # script/audio as current preparation for a new lesson.
                    result['current']=False
                recorded = (row.get("context_snapshot") or {}).get("fingerprint")
                old_source = (row.get("context_snapshot") or {}).get("subject_sources", {}).get("selection", {})
                new_source = adaptive["subject_sources"]["selection"]
                if old_source.get("fingerprint") or new_source.get("active"):
                    result["current"] = result['current'] and fresh and new_source.get("active", False) and old_source.get("fingerprint") == new_source.get("fingerprint")
                result["adaptive_context"] = {"fresh": recorded == adaptive["fingerprint"],
                    "warmup": adaptive["adaptive_warmup"], "source_selection": new_source,
                    "note": "Starting a new lesson refreshes a relevant saved recall question without rewriting the guide or its audio."}
            return result
        except Exception:  # an unreadable guide file must not hide the reader
            return None

    def audio_tracks(self, topic: dict, package: dict, *, exclude: str | None = None,
                     only: str | None = None) -> list[dict]:
        """Voices for the passage, or (``only``) for a guide; ``exclude`` leaves out the guide's voices."""
        tracks = []
        preferred_provider = self.ctx.config.get("tts", {}).get("provider", "google-gemini")
        tts = self.ctx.config.get("tts", {})
        preferred_voice = "Achird"
        from .imported_audio import PREFERRED
        explicit = next((t['id'] for t in self.store.find('audio_tracks', topic_id=topic['id'])
                         if t.get('note') == PREFERRED and t['passage_sha256'] == package['passage_sha256']), None)
        if preferred_provider == 'elevenlabs':
            from .elevenlabs_audio import narrator
            subject = self.store.get('subjects', topic['subject_id'])
            from .voice_choices import selected
            preferred_voice = selected(self.store, topic['id']) or narrator(self.ctx, audio_mod.language_of(self.store, subject), subject['child_id'])
        if preferred_provider == 'inworld':
            from .inworld_voices import narrator, selected
            subject = self.store.get('subjects', topic['subject_id'])
            choice = selected(self.store, topic['id'])
            preferred_voice = choice or narrator(self.ctx, audio_mod.language_of(self.store, subject), subject['child_id'])
            if choice:
                explicit = None
        if preferred_provider == "kokoro-local":
            from .local_audio import narrator
            subject = self.store.get("subjects", topic["subject_id"])
            preferred_voice = narrator(self.ctx, audio_mod.language_of(self.store, subject))
        rows = {r['id']: r for r in self.store.find("audio_tracks", topic_id=topic["id"])}
        from .library_materials import book_for, audio_rows
        book = book_for(self.store, topic['subject_id'])
        if book:
            rows.update({r['id']: r for r in audio_rows(self.store, book) if r['passage_sha256'] == package['passage_sha256']})
        for row in rows.values():
            if (row.get("note") or "").startswith("feedback:"):
                continue
            if (only and row["passage_sha256"] != only) or (exclude and row["passage_sha256"] == exclude):
                continue
            synchronized = False
            manifest = {}
            reason = row["note"] or ""
            if row["status"] == "ready" and row["timing"] and row["manifest_path"]:
                try:
                    manifest = json.loads(self.ctx.file_bytes(row["manifest_path"], None))
                    synchronized, reason = audio_mod.validate_manifest(manifest, package["passage_sha256"],
                                                                       len(package["sentences"]))
                except Exception as error:  # an unreadable manifest must not hide the reader
                    reason = f"Timing unavailable: {error}"
            from .voice_choices import name as narrator_name
            tracks.append({"track_id": row["id"], "provider": row["provider"], "voice": row["voice"],
                           'voice_name': narrator_name(self.ctx, row['voice']) if row['provider']=='elevenlabs' else row['voice'],
                           "preferred": row['id'] == explicit if explicit else (row["provider"] == preferred_provider and row["voice"] == preferred_voice
                                         and row["speaking_rate"] == (tts.get("rate") or audio_mod.DEFAULT_RATE)),
                           "model": manifest.get("model"), "cost_usd": manifest.get("cost_usd"),
                           "job_status": manifest.get("job_status"), "fallback_parts": manifest.get("fallback_parts", 0),
                           "speaking_rate": row["speaking_rate"], "status": row["status"],
                           "timing": row["timing"],
                           "synchronized": synchronized, "note": None if synchronized else reason})
        return tracks
