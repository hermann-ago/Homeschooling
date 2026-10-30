---
name: homeschooling-material-map
description: Review and maintain source-grounded relationships between textbooks, workbooks and answer keys in the Homeschooling app, without generating personalized lessons or learner evidence.
---

# Homeschooling Material Map

Read the current material-links instructions from `GET /api/material-skills` on the running Homeschooling server, or the starter at `C:/CodingLocal/Homeschooling/tutor/materials/material-links/GUIDE.md` when offline. The same instructions are visible and versioned under Curriculum > subject > Skills dos materiais. Preserve family edits; do not replace them with the starter automatically.

Use the canonical subject-collection and book-companion schemas. Inspect exact PDF editions and confirmed page text. Preserve each book's role, original exercise/subitem identities, source pages and explicit answer-key target. Use the companion skill for page transcription corrections before reviewing dependent relationships.

For source work produced entirely in Codex, use `GET /api/source-map-schema` and import the resulting `homeschooling.source-map` JSON with `POST /api/subjects/{id}/book-collection/import-map`, or **Import Codex overview** in the app. Pin the collection version and all companion content hashes. This path uses no provider generation. `allow_pending_sources` explicitly saves an incomplete checkpoint: unchecked content cannot support concepts or public reading relationships; complete reusable knowledge remains unavailable until review is finished. Never turn this flag into a claim of complete analysis.

One official key may cover multiple volumes: select every exact course/workbook in `answer_for_keys`; never duplicate the key PDF to make single-target links. Record explicit reader chapter assignments with source quotations and exact destination PDF ranges. External apps or books not supplied remain identified dependencies, not invented source content.

When replacing a missing legacy PDF, first match every old lesson to the original volume's TOC. Use the family-only `restore-source` route with expected revisions and literal opening-page quotations. Preserve IDs, completion and learner evidence; add only missing source entries supported by the original index. A different known PDF hash is a new edition, not a metadata correction.

Distinguish passage comprehension, concept practice and self-contained work. A dictation or copy task does not need an invented prerequisite reading. A source quote must support the proposed dependency; shared numbering, proximity or topic similarity alone does not establish it. Cross-book links should identify prerequisite, reinforcement, review or application with source evidence.

Review the existing saved map with the app's source-review API. Preserve immutable proposals and earlier reviews. Pin source hashes and instruction versions, and cite the exact page for each correction. Keep private answer keys out of student context. Missing or contradictory key content remains a specific source-review issue; never fill it by solving the learner's task.

Do not generate guides, schedules, assessments or child history during source integration. Prepare personalized lessons later using the current learner context. Reviewing saved sources in Codex does not require new provider calls; only use the app's paid analysis when specifically requested. Do not instantiate AppContext against a running family database.

Report verified changes, unresolved source questions, and whether anything was activated for teaching. Saving or revising a source map does not itself certify understanding or complete required work.
