"""Reconstructable learning memory derived from actual evidence, never model guesses.

Topic evidence remains useful when no trustworthy concept association is known.
Amendments retain their full lineage; a later check is distinct from a response
with hints. The source graph and each child's observed knowledge stay separate.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from storage.store import RevisionConflict, sha256_text
from .books import norm
from .map_review import effective_map

VERSION = "learning-memory-3"
UNCLEAR = {"Unreadable", "Source disputed"}
LABELS = {"not_checked": "Not checked yet", "clarification": "Needs clarification", "needs_help": "Needs help",
          "independent": "Demonstrated independently", "retained": "Retained on a later check"}


def today():
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()


def serial(value):
    return json.loads(json.dumps(value, default=str, ensure_ascii=False))


def meaningful(value):
    """Commit metadata is not evidence; staged and committed work hash alike."""
    if isinstance(value, dict):
        return {k: meaningful(v) for k, v in value.items() if k not in ("revision", "updated_at")}
    if isinstance(value, list):
        return [meaningful(v) for v in value]
    return value


def evidence_state(attempt):
    result = attempt.get("after_help_result") or attempt["first_result"]
    if result in (None, "Unanswered", "Unassessed", "Not checked"):
        return "not_checked"
    if result in UNCLEAR or (attempt.get("reading_certainty") or "").casefold() in ("unclear", "unreadable", "disputed"):
        return "clarification"
    if attempt["first_result"] == "Correct" and attempt.get("independence") == "independent" and not any(
            attempt.get(k) for k in ("help_given", "revised_answer", "after_help_result")):
        return "independent"
    if result == "Correct" and attempt.get("independence") != "with_help" and not any(attempt.get(k) for k in ("help_given", "revised_answer", "after_help_result")):
        return "not_checked"
    if result in ("Correct", "Partly correct", "Not yet", "With help") or attempt.get("help_given"):
        return "needs_help"
    return "not_checked"


def latest_map(ctx, db, subject_id):
    binding = db.find("subject_collections", subject_id=subject_id)
    jobs = db.find("collection_analysis_jobs", collection_id=binding[0]["collection_id"]) if binding else db.find("collection_analysis_jobs", subject_id=subject_id)
    collection = db.get("book_collections", binding[0]["collection_id"]) if binding else None
    rows = [db.get("subject_maps", j["map_id"]) for j in jobs if j["map_id"]]
    rows = [m for m in rows if m]
    current = [m for m in rows if collection and m["version_id"] == collection["active_version"]]
    rows = sorted(current or rows, key=lambda m: (m["created_at"], m["id"]))
    if not rows:
        selections = db.find("subject_map_selections", subject_id=subject_id)
        saved = max(selections, key=lambda r: r["selection_number"], default=None)
        if saved:
            return {**saved["data"], "id": saved["map_id"], "review_revision": saved["review_number"]}
        return None
    return effective_map(ctx, rows[-1])


def summarize(attempts, reviews):
    independently = [a for a in attempts if a["state"] == "independent"]
    help_sessions = {(a["session_id"], a["date"]) for a in attempts if a["state"] == "needs_help"}
    independent_days = {a["date"] for a in independently}
    open_reviews = [r for r in reviews if r["status"] == "Open"]
    latest = max(attempts, key=lambda a: (a["date"], a["created_at"], a["id"]), default=None)
    if latest and latest["state"] == "clarification":
        state = "clarification"
    elif open_reviews or (latest and latest["state"] == "needs_help"):
        state = "needs_help"
    elif len(independent_days) >= 2:
        state = "retained"
    elif independently:
        state = "independent"
    else:
        state = "not_checked"
    next_due = min((r["next_due"] for r in open_reviews if r.get("next_due")), default=None)
    return {"state": state, "label": LABELS[state], "observations": len(attempts), "independent_checks": len(independently),
        "help_sessions": len(help_sessions), "repeated_difficulty": len(help_sessions) >= 2,
        "last_independent_check": max((a["date"] for a in independently), default=None),
        "last_observed": latest["date"] if latest else None, "next_review": next_due,
        "next_action": "Clarify the handwriting or source before assessing understanding." if state == "clarification" else
            "Ask a short independent recall question; use help one step at a time if needed." if state == "needs_help" else
            "Revisit with a spaced independent check." if state in ("independent", "retained") else "Observe an answer before drawing a conclusion.",
        "evidence_ids": [a["id"] for a in attempts], "review_ids": [r["id"] for r in reviews]}


class LearningMemory:
    def __init__(self, ctx):
        self.ctx = ctx

    def build(self, db, child_id, subject_id):
        subject = db.get("subjects", subject_id)
        if not subject or subject["child_id"] != child_id:
            raise ValueError("This subject does not belong to the selected child")
        topics = {t["id"]: t for t in db.find("topics", subject_id=subject_id)}
        sessions = {s["id"]: s for s in db.find("tutor_sessions", child_id=child_id, subject_id=subject_id)}
        photos = [{k: e[k] for k in ("id", "file_path", "session_id", "filename")} for e in db.find("evidence_files", child_id=child_id) if e["session_id"] in sessions]
        raw = [a for a in db.find("attempts", child_id=child_id) if a["topic_id"] in topics and a["session_id"] in sessions]
        reviews = serial([r for r in db.find("reviews", child_id=child_id) if r["topic_id"] in topics])
        replaced = {a["amends_attempt_id"] for a in raw if a.get("amends_attempt_id")}
        by_id = {a["id"]: a for a in raw}
        actions = {(a["session_id"], a["action_id"]): a for a in db.find("lesson_actions", child_id=child_id, subject_id=subject_id)}
        source_map = latest_map(self.ctx, db, subject_id)
        concepts = {c["id"]: c for c in (source_map or {}).get("concepts", []) if c.get("parent_review", {}).get("status") != "rejected"}
        links = sorted(db.find("learner_concept_links", child_id=child_id, subject_id=subject_id), key=lambda r: r["link_number"])
        current_links = {(r["evidence_kind"], r["evidence_id"]): r for r in links}
        observations = []
        unlinked_reviews = []
        mapped_reviews = {cid: [] for cid in concepts}
        def associated(kind, record, lineage):
            explicit = next((current_links[(kind, eid)] for eid in lineage if (kind, eid) in current_links), None)
            if explicit:
                cid = explicit["concept_id"]
                old_map = db.get("subject_maps", explicit["map_id"]) if explicit.get("map_id") else None
                if not old_map:
                    selected_versions = [s for s in db.find("subject_map_selections", subject_id=subject_id) if s["map_id"] == explicit.get("map_id")]
                    snapshot = max(selected_versions, key=lambda s: s["selection_number"], default=None)
                    old_map = {"data": snapshot["data"]} if snapshot else None
                old = next((c for c in (old_map or {}).get("data", {}).get("concepts", []) if c["id"] == cid), None)
                current = concepts.get(cid)
                if explicit["status"] == "linked" and current and old and old["sha256"] == current["sha256"] and old["evidence"] == current["evidence"]:
                    return [cid], "parent_link"
                return [], "parent_unmapped" if explicit["status"] == "unmapped" else "source_changed"
            if kind == "attempt":
                action = actions.get((record["session_id"], record["question_ref"]))
                ids = (action or {}).get("concept_ids") or []
                selection = db.get("subject_map_selections", action.get("map_selection_id")) if action and action.get("map_selection_id") else None
                prepared = {c["id"]: c for c in (selection or {}).get("data", {}).get("concepts", [])}
                if ids and all(cid in concepts and cid in prepared and concepts[cid]["sha256"] == prepared[cid]["sha256"]
                               and concepts[cid]["evidence"] == prepared[cid]["evidence"] for cid in ids):
                    return ids, "saved_task_objective"
            if kind == "review":
                candidates = [cid for cid, c in concepts.items() if norm(c["title"]) == norm(record["concept"])]
                if len(candidates) == 1:
                    return candidates, "exact_saved_concept_name"
            return [], "unmapped"
        for attempt in raw:
            if attempt["id"] in replaced:
                continue
            lineage, cursor = [], attempt
            while cursor and cursor["id"] not in lineage:
                lineage.append(cursor["id"])
                cursor = by_id.get(cursor.get("amends_attempt_id"))
            ids, origin = associated("attempt", attempt, lineage)
            session = sessions[attempt["session_id"]]
            evidence = serial(attempt)
            evidence["revision"] = evidence["revision"] or 1  # New immutable attempt, staged before commit.
            evidence.update(date=str(session["date"] or attempt["created_at"].astimezone(ZoneInfo("America/Sao_Paulo")).date()), state=evidence_state(attempt),
                topic=topics[attempt["topic_id"]]["title"], concept_ids=ids, mapping_origin=origin, lineage=lineage)
            observations.append(evidence)
        for review in reviews:
            ids, origin = associated("review", review, [review["id"]])
            review.update(concept_ids=ids, mapping_origin=origin, topic=topics[review["topic_id"]]["title"])
            if not ids:
                unlinked_reviews.append(review)
            for cid in ids:
                mapped_reviews[cid].append(review)
        observations.sort(key=lambda a: (a["date"], a["created_at"], a["id"]))
        rows = [{"topic_id": tid, "title": topic["title"], **summarize([a for a in observations if a["topic_id"] == tid],
                   [r for r in reviews if r["topic_id"] == tid])} for tid, topic in topics.items()
                if any(a["topic_id"] == tid for a in observations) or any(r["topic_id"] == tid for r in reviews)]
        concept_rows = [{"concept_id": cid, "title": c["title"], "document_id": c["document_id"], "source_evidence": c["evidence"],
                        **summarize([a for a in observations if cid in a["concept_ids"]], mapped_reviews[cid])} for cid, c in concepts.items()]
        signature = sha256_text([VERSION, child_id, subject_id, meaningful(serial(raw)), meaningful(reviews), meaningful(serial(links)),
                                 (source_map or {}).get("id"), (source_map or {}).get("review_revision"),
                                 [(a["id"], a.get("concept_ids")) for a in actions.values()],
                                 [(s["id"], str(s["date"])) for s in sessions.values()],
                                 [(t["id"], t["title"]) for t in topics.values()], subject["name"], photos])
        return {"fingerprint": signature, "child_id": child_id, "subject_id": subject_id, "subject": subject["name"],
            "map_id": (source_map or {}).get("id"), "map_review_revision": (source_map or {}).get("review_revision", 0),
            "topics": rows, "concepts": concept_rows, "evidence": observations, "reviews": reviews, "photos": photos,
            "unmapped_evidence": [a["id"] for a in observations if not a["concept_ids"]],
            "unmapped_reviews": [r["id"] for r in unlinked_reviews], "link_history": serial(links),
            "link_revision": links[-1]["link_number"] if links else 0,
            "amendment_history": serial([a for a in raw if a["id"] in replaced]),
            "interpretation": "Observed evidence only. Topic summaries can contain mixed results; they do not establish mastery of every concept."}

    def refresh(self, db, child_id, subject_id):
        data = self.build(db, child_id, subject_id)
        existing = db.find("learning_snapshots", child_id=child_id, subject_id=subject_id, fingerprint=data["fingerprint"])
        if existing:
            return existing[0]
        version = max((r["summary_version"] for r in db.find("learning_snapshots", child_id=child_id, subject_id=subject_id)), default=0) + 1
        return db.insert("learning_snapshots", {"id": "learning-" + sha256_text([child_id, subject_id, data["fingerprint"]]),
            "child_id": child_id, "subject_id": subject_id, "fingerprint": data["fingerprint"], "summary_version": version, "data": data})

    def view(self, child_id, subject_id):
        with self.ctx.store.transaction(kind="learning.summary", summary="Updated a derived learning summary without AI") as tx:
            row = self.refresh(tx, child_id, subject_id)
        return {**row["data"], "snapshot_id": row["id"], "summary_version": row["summary_version"], "today": today()}

    def packet(self, child_id, subject_id, topic_id=None, concept_ids=(), *, earlier_topics=()):
        data = self.build(self.ctx.store, child_id, subject_id)
        selected = [r for r in data["concepts"] if r["concept_id"] in concept_ids and r["state"] != "not_checked"]
        relevant_topics = {topic_id, *earlier_topics, *[a["topic_id"] for a in data["evidence"] if any(c in concept_ids for c in a["concept_ids"])]}
        selected += [r for r in data["topics"] if r["topic_id"] in relevant_topics]
        # Preserve older unresolved reviews independently of recent-session limits.
        old = [r for r in data["reviews"] if r["status"] == "Open"]
        if concept_ids or earlier_topics:
            old = [r for r in old if r["topic_id"] in relevant_topics or any(c in concept_ids for c in r["concept_ids"])]
        old.sort(key=lambda r: (r.get("next_due") or "9999", r["id"]))
        chosen = old[:3]
        referenced = {a for r in selected for a in r["evidence_ids"]}
        evidence = [a for a in data["evidence"] if a["id"] in referenced]
        return {"version": data["fingerprint"], "map_id": data["map_id"], "observations": selected[:6],
            "older_reviews": [{k: r[k] for k in ("id", "topic_id", "concept", "status", "last_outcome", "next_due", "next_prompt")} for r in chosen],
            "selected_evidence": [{k: a[k] for k in ("id", "topic_id", "date", "state", "independence", "concept_ids", "mapping_origin")} for a in evidence[-8:]],
            "evidence_count": len(data["evidence"]), "unmapped_count": len(data["unmapped_evidence"]),
            "note": "Unmapped work stays at its recorded topic. Do not infer knowledge of unseen chapters or treat helped responses as independent."}

    def link(self, tx, child_id, subject_id, payload):
        subject = tx.get("subjects", subject_id)
        if not subject or subject["child_id"] != child_id:
            raise ValueError("This subject does not belong to the selected child")
        links = tx.find("learner_concept_links", child_id=child_id, subject_id=subject_id)
        revision = max((l["link_number"] for l in links), default=0)
        if revision != payload.expected_revision:
            raise RevisionConflict("Another parent changed the evidence links. Reload before saving.", {"revision": revision})
        table = "attempts" if payload.evidence_kind == "attempt" else "reviews"
        evidence = tx.get(table, payload.evidence_id)
        topic = tx.get("topics", evidence["topic_id"]) if evidence else None
        if not evidence or evidence["child_id"] != child_id or not topic or topic["subject_id"] != subject_id:
            raise ValueError("Choose evidence from this child and subject")
        if payload.status == "linked":
            row = tx.get("subject_maps", payload.map_id) if payload.map_id else None
            job = tx.get("collection_analysis_jobs", row["job_id"]) if row else None
            if not job or job["subject_id"] != subject_id:
                raise ValueError("Choose this subject's saved source map")
            source_map = effective_map(self.ctx, row)
            concept = next((c for c in source_map["concepts"] if c["id"] == payload.concept_id), None)
            if not concept or concept.get("parent_review", {}).get("status") == "rejected":
                raise ValueError("Choose an available source-supported concept")
        if not payload.note.strip():
            raise ValueError("Explain why this evidence does or does not assess the selected concept")
        tx.insert("learner_concept_links", {"id": "learning-link-" + uuid.uuid4().hex, "child_id": child_id, "subject_id": subject_id,
            "evidence_kind": payload.evidence_kind, "evidence_id": payload.evidence_id,
            "map_id": payload.map_id if payload.status == "linked" else None, "concept_id": payload.concept_id if payload.status == "linked" else None,
            "link_number": revision + 1, "status": payload.status, "note": payload.note.strip()})
        self.refresh(tx, child_id, subject_id)
