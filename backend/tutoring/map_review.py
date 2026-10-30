"""Parent corrections layered over immutable analysis snapshots, without AI calls.

Reviews belong to a collection and exact source identities. New snapshots reuse
them only when the original evidence and all edited references remain available.
An obsolete correction stays in the audit log and is explicitly reported.
"""
from __future__ import annotations

import copy
import uuid

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from storage.store import RevisionConflict, sha256_text
from .subject_analysis import safe_pages, valid_quote


class ReviewQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unit_id: str = Field(max_length=100)
    page: int = Field(ge=1)
    quote: str = Field(min_length=12, max_length=800)
    page_end: int | None = Field(default=None, ge=1)
    unit_ids: list[str] | None = Field(default=None, max_length=3)


class Changes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=150)
    explanation: str | None = Field(default=None, max_length=650)
    objective: str | None = Field(default=None, max_length=250)
    date_text: str | None = Field(default=None, max_length=120)
    start_year: int | None = Field(default=None, ge=-10000, le=10000)
    end_year: int | None = Field(default=None, ge=-10000, le=10000)
    approximate: bool | None = None
    from_concept: str | None = Field(default=None, max_length=150)
    to_concept: str | None = Field(default=None, max_length=150)
    relationship: str | None = Field(default=None, min_length=1, max_length=120)
    reason: str | None = Field(default=None, max_length=650)
    evidence: list[ReviewQuote] | None = Field(default=None, max_length=5)


class ParentReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    kind: Literal["concept", "event", "connection", "exercise_link", "issue"]
    target_id: str = Field(min_length=1, max_length=180)
    status: Literal["approved", "corrected", "rejected", "unreviewed"]
    note: str = Field(default="", max_length=2000)
    changes: Changes = Field(default_factory=Changes)


FIELDS = {
    "concept": {"title", "explanation", "objective"},
    "event": {"title", "date_text", "start_year", "end_year", "approximate"},
    "connection": {"from_concept", "to_concept", "relationship", "explanation"},
    "exercise_link": {"evidence", "reason"},
    "issue": set(),
}
LISTS = {"concept": "concepts", "event": "events", "connection": "connections", "exercise_link": "exercise_links", "issue": "review_issues"}


def identity(kind, item):
    if kind == "concept":
        value = [item["id"], item["unit_id"], item["evidence"]]
    elif kind == "event":
        value = [item["unit_id"], item["title"], item["evidence"]]
    elif kind == "connection":
        value = [item["from_concept"], item["to_concept"], item["relationship"]]
    elif kind == "exercise_link":
        value = item["exercise_id"]
    else:
        value = item["text"]
    return kind + "-" + sha256_text(value)


def base_map(service, row):
    result = copy.deepcopy(service.public_map(row))
    result["review_issues"] = [{"text": text} for text in result["issues"]]
    for kind, field in LISTS.items():
        # In-memory analysis checkpoints may share concept objects with their
        # section summaries. Keep the API stable across SQLite reloads.
        result[field] = copy.deepcopy(result[field])
        for item in result[field]:
            item["review_id"] = identity(kind, item)
    return result


def source_pages(ctx, row, unit_id):
    data = row["data"]
    section = next((s for s in data["sections"] if s["id"] == unit_id), None)
    if not section:
        raise ValueError("Choose a reading section in this saved map")
    source = next(s for s in data["books"] if s["id"] == section["source_id"])
    if data.get('provider')=='codex' and unit_id in data.get('source_readings',{}):
        # An eight-page cache unit may be incomplete. Retain only the exact
        # checked public excerpts frozen during the offline import.
        return source,{int(n):text for n,text in data['source_readings'][unit_id].items()}
    first, last = section["pages"]
    scan = ctx.subject_analysis.cached_scan(source, {"first": first, "last": last},
        source_review_id=data.get('source_review_ids',{}).get(source['id']))
    if not scan:
        raise ValueError("The saved reading evidence is unavailable; no rescan was requested")
    return source, safe_pages(source, scan["data"])


def validate_changes(ctx, row, kind, changes):
    if set(changes) - FIELDS[kind]:
        raise ValueError("These fields cannot be edited for this item")
    # Null is meaningful only for unknown dates. Other fields need concrete values.
    if any(v is None and k not in ("start_year", "end_year") for k, v in changes.items()):
        raise ValueError("Enter a value for each changed field")
    if any(not changes[k].strip() for k in ("title", "relationship") if k in changes):
        raise ValueError("Enter a title or relationship instead of blank spaces")
    concepts = {c["id"] for c in row["data"]["concepts"]}
    for field in ("from_concept", "to_concept"):
        if field in changes and changes[field] not in concepts:
            raise ValueError("Choose a concept from this map")
    for cite in changes.get("evidence", []):
        if not citation_valid(ctx, row, cite):
            raise ValueError("The quotation must match the selected original PDF page")


def citation_valid(ctx, row, cite):
    source, pages = source_pages(ctx, row, cite["unit_id"])
    pages = dict(pages)
    for unit in cite.get("unit_ids") or []:
        other, extra = source_pages(ctx, row, unit)
        if other["document_id"] != source["document_id"] or other["sha256"] != source["sha256"]:
            return False
        pages.update(extra)
    last = cite.get("page_end") or cite["page"]
    if last < cite["page"] or last - cite["page"] > 15:
        return False
    selected = list(range(cite["page"], last + 1))
    if not all(p in pages for p in selected):
        return False
    joined = " ".join(pages[p] for p in selected)
    return valid_quote(cite, {cite["page"]: joined})


def effective_map(ctx, row):
    result = base_map(ctx.subject_analysis, row)
    history = sorted(ctx.store.find("subject_map_reviews", collection_id=row["collection_id"]), key=lambda r: r["review_number"])
    latest = {(r["kind"], r["target_id"]): r for r in history}
    result["review_revision"] = history[-1]["review_number"] if history else 0
    result["review_history"] = history
    result["unapplied_reviews"] = []
    applied = set()
    for kind, field in LISTS.items():
        for item in result[field]:
            review = latest.get((kind, item["review_id"]))
            if not review:
                continue
            # A parent checks the displayed content, not future wording from
            # another generation. Freeze its reviewed fields with the decision.
            changes = {k: v for k, v in review["original"].items() if k in FIELDS[kind]}
            changes.update(review["changes"])
            try:
                validate_changes(ctx, row, kind, changes if review["status"] in ("approved", "corrected") else review["changes"])
            except ValueError:
                continue
            applied.add((kind, item["review_id"]))
            item["ai_proposal"] = copy.deepcopy(item)
            item["parent_review"] = {k: review[k] for k in ("id", "status", "note", "review_number", "created_at")}
            if review["status"] in ("approved", "corrected"):
                item.update(changes)
    result["unapplied_reviews"] = [r for key, r in latest.items() if key not in applied and r["status"] != "unreviewed"]
    result["review_counts"] = {status: sum(i.get("parent_review", {}).get("status", "unreviewed") == status
        for field in LISTS.values() for i in result[field]) for status in ("unreviewed", "approved", "corrected", "rejected")}
    return result


def save(ctx, tx, row, payload):
    history = tx.find("subject_map_reviews", collection_id=row["collection_id"])
    revision = max((r["review_number"] for r in history), default=0)
    if payload.expected_revision != revision:
        raise RevisionConflict("Another parent changed this map. Reopen it before saving your correction.", {"revision": revision})
    original = next((i for i in base_map(ctx.subject_analysis, row)[LISTS[payload.kind]] if i["review_id"] == payload.target_id), None)
    if original is None:
        raise ValueError("This item is not in the selected map")
    changes = payload.changes.model_dump(exclude_unset=True)
    validate_changes(ctx, row, payload.kind, changes)
    if payload.status != "corrected" and changes:
        raise ValueError("Choose 'Corrected' when changing the proposed content")
    if payload.status in ("corrected", "rejected") and not payload.note.strip():
        raise ValueError("Add a parent note explaining the correction or rejection")
    updated = {**original, **changes}
    if payload.kind == "event":
        start, end = updated.get("start_year"), updated.get("end_year")
        if start == 0 or end == 0 or (start is not None and end is not None and end < start):
            raise ValueError("Use BCE as negative years, without year zero, and place the end after the start")
    if payload.kind == "exercise_link" and payload.status in ("approved", "corrected"):
        exercise = next(e for e in row["data"]["exercises"] if e["id"] == original["exercise_id"])
        if not exercise["student_safe"] or not updated.get("evidence"):
            raise ValueError("A reading link needs a safe exercise and verified source evidence before approval")
        if not all(citation_valid(ctx, row, cite) for cite in updated["evidence"]):
            raise ValueError("The original reading evidence needs review before approval")
    return tx.insert("subject_map_reviews", {"id": "map-review-" + uuid.uuid4().hex, "collection_id": row["collection_id"],
        "map_id": row["id"], "review_number": revision + 1, "kind": payload.kind, "target_id": payload.target_id,
        "status": payload.status, "changes": changes, "note": payload.note.strip(), "original": original})


def reading_source(ctx, row, unit_id):
    source, pages = source_pages(ctx, row, unit_id)
    return {"name": source["name"], "document_id": source["document_id"], "unit_id": unit_id,
        "pages": [{"page": p, "text": text, "pdf_available": source["role"] in ("textbook", "reference")} for p, text in sorted(pages.items())]}


def pdf_page(ctx, row, document_id, page):
    """Only positively checked original reading pages; never private key pages."""
    source = next((b for b in row["data"]["books"] if b["document_id"] == document_id), None)
    if not source or source["role"] not in ("textbook", "reference"):
        raise ValueError("Original PDF viewing is available only for checked reading pages; other books use safe excerpts")
    section = next((s for s in row["data"]["sections"] if s["document_id"] == document_id and s["pages"][0] <= page <= s["pages"][1]), None)
    if not section or page not in source_pages(ctx, row, section["id"])[1]:
        raise ValueError("This page is private, unchecked, or outside the saved reading coverage")
    doc = ctx.store.get("documents", document_id)
    if not doc or doc["sha256"] != source["sha256"]:
        raise ValueError("The original source edition is unavailable")
    return ctx.file_bytes(doc["file_path"], source["sha256"])
