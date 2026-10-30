"""Parent-selected source context and bounded, evidence-based adaptive recall.

Selections freeze reviewed material. Retrieval checks original editions and exact
passage boundaries; later chapters never become assumed prior understanding.
"""
import json
import re
import uuid

from storage.store import RevisionConflict, sha256_text
from .map_review import effective_map, citation_valid
from . import passages


def normalized(text):
    return re.sub(r"\s+", " ", text or "").strip().casefold()


def selected(db, subject_id):
    rows = db.find("subject_map_selections", subject_id=subject_id)
    return max(rows, key=lambda r: r["selection_number"], default=None)


def status(ctx, subject_id):
    row = selected(ctx.store, subject_id)
    if not row:
        return {"selection_number": 0, "active": False, "note": "Review source concepts, then select the checked portions for new lessons."}
    data = row["data"]
    valid = all((ctx.store.get("documents", b["document_id"]) or {}).get("sha256") == b["sha256"] for b in data["books"])
    binding = ctx.store.find("subject_collections", subject_id=subject_id)
    collection = ctx.store.get("book_collections", binding[0]["collection_id"]) if binding else None
    valid = valid and bool(collection and collection["active_version"] == data["version_id"])
    latest_review = max((r["review_number"] for r in ctx.store.find("subject_map_reviews", collection_id=collection["id"])), default=0) if collection else 0
    valid = valid and latest_review == row["review_number"]
    return {"id": row["id"], "map_id": row["map_id"], "selection_number": row["selection_number"],
        "review_number": row["review_number"], "fingerprint": row["fingerprint"], "active": valid,
        "concepts": len(data["concepts"]), "partial": not data.get("coverage", {}).get("complete", False),
        "note": "Checked portions are selected; remaining proposals stay out of teaching context." if valid else
                "The collection, source reviews or original editions changed. Review and select the checked map again."}


def publish(ctx, tx, map_id, expected_revision, expected_review_revision, subject_id=None):
    row = tx.get("subject_maps", map_id)
    job = tx.get("collection_analysis_jobs", row["job_id"]) if row else None
    if not job:
        raise ValueError("Choose an available saved subject map")
    subject_id = subject_id if subject_id is not None else job["subject_id"]
    linked = tx.find("subject_collections", subject_id=subject_id)
    if not linked or linked[0]["collection_id"] != row["collection_id"]:
        raise ValueError("This saved map is not assigned to that subject")
    current = selected(tx, subject_id)
    revision = current["selection_number"] if current else 0
    if expected_revision != revision:
        raise RevisionConflict("Another parent changed the active map. Reload before selecting.", {"revision": revision})
    source = effective_map(ctx, row)
    if expected_review_revision != source["review_revision"]:
        raise RevisionConflict("Source reviews changed. Reload and inspect the checked portions.", {"revision": source["review_revision"]})
    collection = tx.get("book_collections", row["collection_id"])
    if row["version_id"] != collection["active_version"]:
        raise ValueError("This map belongs to an older book collection. Select the current collection's checked map")
    def checked(item):
        return item.get("parent_review", {}).get("status") in ("approved", "corrected")
    concepts = [c for c in source["concepts"] if checked(c) and c.get("evidence") and all(
        citation_valid(ctx, row, {"unit_id": c["unit_id"], **cite}) for cite in c["evidence"])]
    if not concepts:
        raise ValueError("Inspect and approve at least one source-supported concept before selecting it for teaching")
    ids = {c["id"] for c in concepts}
    data = {k: source[k] for k in ("books", "sections", "coverage", "version_id")}
    data.update(concepts=concepts, connections=[c for c in source["connections"] if checked(c) and c["from_concept"] in ids and c["to_concept"] in ids],
        events=[e for e in source["events"] if checked(e)],
        exercise_links=[e for e in source["exercise_links"] if checked(e)])
    fingerprint = sha256_text([row["id"], source["review_revision"], data])
    return tx.insert("subject_map_selections", {"id": "teaching-map-" + uuid.uuid4().hex, "subject_id": subject_id, "map_id": map_id,
        "selection_number": revision + 1, "review_number": source["review_revision"], "fingerprint": fingerprint,
        "data": json.loads(json.dumps(data, default=str))})


def packet(ctx, topic, passage):
    active = status(ctx, topic["subject_id"])
    empty = {"selection": active, "current_concepts": [], "earlier_concepts": [], "connections": [], "events": [],
        "note": "Unseen later chapters are excluded. Reading completion is not proof of understanding. Private keys are excluded."}
    if not active["active"]:
        return empty
    row = selected(ctx.store, topic["subject_id"]); data = row["data"]
    child_id = ctx.store.get("subjects", topic["subject_id"])["child_id"]
    observed = {a["topic_id"] for a in ctx.store.find("attempts", child_id=child_id)}
    earlier = [t for t in ctx.store.find("topics", subject_id=topic["subject_id"])
        if t["id"] != topic["id"] and (t["completed"] or t["id"] in observed)
        and (t.get("chapter_order") or 0) < (topic.get("chapter_order") or 0)]
    current_text = normalized(" ".join(s["text"] for s in passage["sentences"]))
    current = [c for c in data["concepts"] if c["document_id"] == topic["document_id"] and all(
        normalized(cite["quote"]) in current_text for cite in c["evidence"])]
    current_ids = {c["id"] for c in current}
    # Only explicitly checked neighbors can supply earlier context.
    relations = [r for r in data["connections"] if {r["from_concept"], r["to_concept"]} & current_ids]
    neighbors = {cid for r in relations for cid in (r["from_concept"], r["to_concept"])} - current_ids
    prior = []
    for c in data["concepts"]:
        if c["id"] not in neighbors:
            continue
        for t in earlier:
            if t["document_id"] != c["document_id"]:
                continue
            try:
                original = passages.load(ctx, t)
            except (ValueError, OSError):
                continue
            text = normalized(" ".join(s["text"] for s in original["sentences"]))
            if all(normalized(cite["quote"]) in text for cite in c["evidence"]):
                prior.append({**c, "topic_id": t["id"], "reading_completed": bool(t["completed"]), "has_observed_work": t["id"] in observed})
                break
        if len(prior) == 4:
            break
    allowed = current_ids | {c["id"] for c in prior}
    def public(c):
        return {k: c[k] for k in ("id", "title", "objective", "explanation", "document_id", "evidence", "topic_id", "reading_completed", "has_observed_work") if k in c}
    return {**empty, "current_concepts": [public(c) for c in current[:8]], "earlier_concepts": [public(c) for c in prior],
        "connections": [{k: r[k] for k in ("from_concept", "to_concept", "relationship", "explanation")} for r in relations
                        if r["from_concept"] in allowed and r["to_concept"] in allowed][:6],
        "events": [e for e in data["events"] if e["document_id"] == topic["document_id"] and
                   normalized(e["evidence"]["quote"]) in current_text][:4]}


def preparation(ctx, child_id, topic, passage):
    from .navigation import selections, checked_selections
    selected_pages = checked_selections(ctx.store, topic, selections(ctx, topic))
    sources = {'selection': {'active': False}, 'page_structure': [], 'current_concepts': [],
               'earlier_concepts': [], 'connections': [], 'events': []}
    source_requirements = {'readings': [], 'tasks': [], 'checked_pages': [], 'policy': 'original-pages-2'}
    concepts = [c["id"] for c in sources["current_concepts"] + sources["earlier_concepts"]]
    earlier_ids = {c["topic_id"] for c in sources["earlier_concepts"]}
    memory = ctx.learning_memory.packet(child_id, topic["subject_id"], topic["id"], concepts, earlier_topics=earlier_ids)
    reviews = [r for r in memory["older_reviews"] if r["topic_id"] in earlier_ids | {topic["id"]} and r.get("next_prompt")]
    # Reuse the actual saved question rather than generating and paying for a new one.
    warmup = reviews[0] if reviews else None
    from .family_skill import packet as family_packet
    family = family_packet(ctx.store, child_id)
    from .source_annotations import packet as annotation_packet
    notes=annotation_packet(ctx.store,topic)
    return {"selected_source_pages": selected_pages, "subject_sources": sources, "source_requirements":source_requirements, "learning_memory": memory, "adaptive_warmup": warmup,
            "source_annotations":notes,"family_tutoring": family,
            "fingerprint": sha256_text([sources,source_requirements,memory,warmup,family['sha256'],notes])}
