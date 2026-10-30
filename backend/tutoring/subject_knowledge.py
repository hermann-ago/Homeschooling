"""Versioned family source knowledge files; never contain a child's learning history.

The JSON is a parent-owned archive, not tutor input. Raw scans and answer keys
are in teacher_only. Reuse binds another subject to the exact saved collection;
no learner, topic, guide, assignment or teaching-selection rows are copied.
"""
import copy
import hashlib
import json

from storage import layout
from storage.store import RevisionConflict
from .collections import binding
from .books import UNIT_PAGES

FORMAT = "homeschooling.subject-knowledge"
VERSION = 1


def latest(ctx, subject_id):
    linked = binding(ctx.store, subject_id)
    collection = ctx.store.get("book_collections", linked["collection_id"]) if linked else None
    if not collection:
        return None
    rows = [m for m in ctx.store.find("subject_maps", collection_id=collection["id"])
            if m["version_id"] == collection["active_version"] and m["data"]["coverage"]["complete"]]
    return max(rows, key=lambda r: (r["created_at"], r["id"]), default=None)


def archive(ctx, subject_id):
    row = latest(ctx, subject_id)
    if not row:
        raise ValueError("Finish this collection's source analysis before saving reusable knowledge")
    subject = ctx.store.get("subjects", subject_id)
    version = ctx.store.get("collection_versions", row["version_id"])
    data = copy.deepcopy(row["data"])
    scans = []
    sources = []
    for source in data["books"]:
        doc = ctx.store.get("documents", source["document_id"])
        if not doc or doc["sha256"] != source["sha256"]:
            raise ValueError("The original book edition changed; keep its matching PDF before reusing knowledge")
        sources.append({k: source[k] for k in ("id", "name", "sha256", "pages", "role", "edition", "position", "is_main", "companion_id", "answer_for_id")})
        sources[-1]['answer_for_ids']=source.get('answer_for_ids') or ([source['answer_for_id']] if source.get('answer_for_id') else [])
        for first in range(1, source["pages"] + 1, UNIT_PAGES):
            scan = ctx.subject_analysis.cached_scan(source, {"first": first, "last": min(first + UNIT_PAGES - 1, source["pages"])},
                source_review_id=data.get('source_review_ids', {}).get(source['id']))
            if not scan:
                raise ValueError("Some saved source pages are missing; restore them before saving this knowledge file")
            scans.append({k: copy.deepcopy(scan[k]) for k in ("id", "sha256", "role", "version", "first_page", "last_page", "data")})
    # Paths and child's grade folder are deliberately absent from the contents.
    for source in data["books"]:
        source.pop("document_id", None)
    private = data.pop("private_answers", [])
    private_relationships = data.pop('private_book_relationships', [])
    reviews = [{k: r[k] for k in ("review_number", "kind", "target_id", "status", "changes", "note", "original", "created_at")}
               for r in sorted(ctx.store.find("subject_map_reviews", collection_id=row["collection_id"]), key=lambda r: r["review_number"])]
    body = {"format": FORMAT, "format_version": VERSION, "subject": subject["name"], "intended_grade": subject.get("grade"),
            "collection_version": version["number"], "analysis_version": data["analysis_version"],
            "material_skills": data.get('material_skills', {}),
            "sources": sources, "knowledge": data, "parent_reviews": reviews,
            "teacher_only": {"raw_scan_units": scans, "answer_key_entries": private,'book_relationships':private_relationships},
            "reuse_rules": {"original_pdfs_required": True, "match_by": "sha256 and source role/edition",
                           "child_records_included": False, "personalized_lessons_included": False}}
    from .book_companion import row_id
    body["book_companions"] = [{"pdf_sha256": source["sha256"], "role": source["role"],
                                "content_sha256": companion["content_sha256"], "format_version": 1}
                               for source in data["books"]
                               if (companion := ctx.store.get("book_companions", row_id(source["sha256"], source["role"])))]
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return row, body, digest


def save(ctx, subject_id):
    row, body, digest = archive(ctx, subject_id)
    envelope = {"content_sha256": digest, "contents": body}
    payload = json.dumps(envelope, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    path, sha = ctx.files.write(layout.for_subject(ctx.store, subject_id, layout.SUBJECT_KNOWLEDGE),
                               f"subject-knowledge-v{VERSION}-{digest[:16]}.json", payload)
    return {"path": path, "sha256": sha, "map_id": row["id"], "content_sha256": digest,
            "format_version": VERSION, "books": body["knowledge"]["coverage"]["books"],
            "pages": body["knowledge"]["coverage"]["pages"], "exercises": body["knowledge"]["coverage"]["exercises"]}


def ensure(ctx, collection_id=None):
    """Best-effort material archive; an unavailable Drive never invalidates analysis."""
    import logging
    for linked in ctx.store.all("subject_collections"):
        if collection_id and linked["collection_id"] != collection_id:
            continue
        if latest(ctx, linked["subject_id"]):
            try:
                save(ctx, linked["subject_id"])
            except (ValueError, OSError):
                logging.getLogger(__name__).exception("Subject knowledge archive is unavailable")


def available(ctx):
    result = []
    for subject in ctx.store.all("subjects"):
        row = latest(ctx, subject["id"])
        if row:
            result.append({"source_subject_id": subject["id"], "collection_id": row["collection_id"],
                           "subject": subject["name"], "grade": subject.get("grade"),
                           "collection_name": ctx.store.get("book_collections", row["collection_id"])["name"],
                           "coverage": row["data"]["coverage"]})
    return result


def reuse(ctx, tx, subject_id, source_subject_id, expected_revision, expected_version_id, source_version_id):
    source = binding(tx, source_subject_id)
    target = binding(tx, subject_id)
    current = tx.get("book_collections", target["collection_id"]) if target else None
    if expected_revision != (current["revision"] if current else 0) or expected_version_id != (current["active_version"] if current else None):
        raise RevisionConflict("This subject's books changed. Reopen before using saved knowledge.", current)
    row = latest(ctx, source_subject_id)
    if not source or not row:
        raise ValueError("Choose a collection with completed source analysis")
    if row["version_id"] != source_version_id:
        raise ValueError("The saved source collection changed. Reopen before reusing it")
    source_docs = {b["document_id"] for b in row["data"]["books"]}
    existing_docs = {b["document_id"] for b in tx.find("subject_books", subject_id=subject_id) if not b["archived"]}
    existing_docs.update(t["document_id"] for t in tx.find("topics", subject_id=subject_id) if t["document_id"] and not t["archived"])
    if existing_docs - source_docs:
        raise ValueError("This subject already has different books. Keep them in their own collection rather than replacing them")
    if any(j["status"] in ("queued", "running") for j in tx.find("collection_analysis_jobs", subject_id=subject_id)):
        raise ValueError("Pause this subject's preparation before choosing another collection")
    if current and target["collection_id"] != source["collection_id"]:
        existing = tx.get("collection_versions", current["active_version"])
        if existing and any(b["document_id"] not in source_docs for b in existing["manifest"]["books"]):
            raise ValueError("This subject already has different books. Keep them in their own collection rather than replacing them")
    if target:
        if target["collection_id"] == source["collection_id"]:
            return
        tx.update("subject_collections", target["id"], {"collection_id": source["collection_id"]})
    else:
        tx.insert("subject_collections", {"id": f"subject-collection-{subject_id}", "subject_id": subject_id, "collection_id": source["collection_id"]})
