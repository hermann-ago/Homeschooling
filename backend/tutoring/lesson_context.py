"""The learner context a new lesson is prepared with: selected pages, learning
memory, a saved recall question, the family style and source notes."""
from storage.store import sha256_text


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
