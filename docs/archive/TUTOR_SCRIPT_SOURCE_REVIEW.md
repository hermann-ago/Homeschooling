# Preparing a source-faithful tutoring script

The letter R review (21 October 2026) found that a valid, playable guide could
promise to read a poem while omitting every verse. Audio faithfully narrated
the incomplete script. Transport/schema validation alone did not detect this.

## Preparation sequence

1. Inspect the assigned original PDF pages, including visual instructions.
   Certify only pages actually reviewed in the book JSON companion. Keep
   original text and illustrations separate from interpretation and answer keys.
2. Identify the original reading blocks and worksheet tasks. Checked companion
   pages supply them directly. For opt-in visual lessons with unchecked pages,
   the app now runs a source-only inventory first, using the existing book scan
   schemas and normalization. It is cached by PDF checksum, range, schema version
   and material-skill hash in `book_units`, without certifying or overwriting the
   portable companion. The inventory and script share the preparation cap.
   Text-only preparation retains its existing path.
3. Plan literary readings using the exact `source_block_id`. The server inserts
   their original text. A teacher's directions may be simplified; a promised
   poem or story excerpt must not become an instruction to listen to it.
4. Give each original worksheet task a waiting activity with its document,
   page and exact instruction reference. Avoid reading a direction, repeating
   it as an explanation, and then repeating it as a question.
5. Validate the provider reply against source obligations before accepting it.
   Validate the final built guide again before saving or generating narration.
   Missing/paraphrased/duplicated readings and omitted tasks stop preparation.
6. Rehearse the complete flow with disposable learners and stubbed assessment.
   Check actual source reading, pauses, physical evidence, simple selections,
   draft/restart recovery and completion. Do not submit invented answers to
   the family's sessions.
7. Generate advanced narration only for the accepted guide. Verify the voice
   job and alignment state; audio readiness does not establish teaching quality.

These checks cover companion-certified or automatically inventoried content.
The latter remains AI interpretation rather than a human visual certification.
They establish content coverage, not factual correctness, learner understanding
or completion. Ambiguous matching directions must remain faithful to the page;
do not invent an official pairing rule.

Full literal `read_source` activity content and legacy reading segments share
the same source binding. Only an exact complete reading can be mapped to a
checked block ID; a title or paraphrase still fails. A task may cite its full
instruction, consecutive instruction fragments, or a substantial exact excerpt
unique among tasks on that original page. Every task retains its own waiting step.
When new source obligations expose an old script omission, future preparation
marks that guide outdated while preserving historical pinned sessions.

## Reviewed scripts from Codex

`POST /api/tutor/reader/guide/import` accepts a family-reviewed `GuidePlan`,
learner/topic, the current passage SHA-256 and expected subject-skill version.
It uses the same source checks and saved-guide format as ordinary preparation,
labels the model `codex-reviewed`, and makes no paid script or voice request.
Use a stable idempotency key. A stale source or skill version returns 409.

The import also accepts `script` in the current `page_script.Script` format
(`welcome`, typed `turns`, `closing`). Supply exactly one of `script` or the
legacy `plan`. Structured imports use the same context-bound compiler as API
preparation, preserve their original JSON privately, enforce the Books choice
policy and selected student-page bounds, and retain paragraph breaks. They make
no paid writer, reviewer or narration call; the existing family/Codex review
path records approval after the source checks. Prepare narration separately.

Prepare audio through the normal curriculum preparation flow. Switching an
active session to the new script uses the existing `replace-script` transition:
the original thread and answers stay saved, and a new session starts at the
new introduction. Historical evidence is never rewritten.

## Letter R outcome

The reviewed pages 33–46 contain two complete printed reading excerpts and 13
original tasks. The replacement contains 23 steps, including two brief extra
checks. The previous guide had 31 steps but omitted both excerpts and repeated
directions. Letter recognition accepts a selection without demanding typed
reasoning. A choice alone does not establish independently explained mastery;
activities that explicitly require reasoning still require it.

Subject teaching guidance is saved as version 5. General source-fidelity rules
are also kept in `tutor/skills/child-friendly-tutor/SKILL.md`. Reviewed book
companion pages and guide source-coverage metadata remain versioned alongside
the PDF and saved guides.

## History preparation review: Forbidden City

The app-generated draft for topic 375 preserved the full passage but had excessive
paragraph commentary. Version 2 of the subject's editable teaching guidance asks
for connected reading, concise scaffolding and one retelling when required book
questions already provide substantial practice. The reviewed plan retains all 60
source sentences, six reading stretches and the nine eligible original questions.
Book references sort numerically within each page; uppercase section headings
are excluded from binary subpart counts, and lowercase a–d options retain their
actual source IDs and labels. Ambiguous multiline layouts still use text capture.

Source corrections are explicit teacher commentary, never silent edits to the
assigned book. The History guidance records provenance for the construction-date
correction, uncertainty about a North America voyage, relative publication dates,
and the brick/mortar source conflict. A source dispute remains unassessed and
revisitable rather than becoming an incorrect knowledge event.

Narration alignment accepts locale-correct grouped integers without changing the
display text. English four-digit years can use a year-style pronunciation only
when the independent acoustic decoding hears that exact same integer at its
original position; missing or changed years still fail. This reuses saved raw
audio and does not purchase a replacement. Original filenames stay on book-work
cards while spoken locators use natural wording such as “your book”.

Aligned larger-block narration also retains definite provider content refusals
as explicit text-only sections and continues other blocks. These placeholders
have coverage but no fabricated audio/timings; version-4 manifests validate both
types. Unknown purchase outcomes, quota errors and uncertain alignment still
pause. Re-entry reuses a saved refusal and raw successful audio rather than
resending the refused passage or changing its wording. A finished partial
recording is `ready_with_fallback`, visibly distinct from complete Google audio.

An explicit missing-audio retry is available from the lesson voice notice. It
requests each declined block once with the exact same model, wording, style and
boundaries. The original refusal and successful recordings remain saved. Stable
retry identities prevent duplicate purchases after refresh or an ambiguous reply;
unknown results retain reservations. Repeated declines stay text-only, without
rewriting, splitting the refused text, switching providers or automatically trying
again. When recordings are repaired, the reader refreshes the existing manifest
without changing the learner's activity or answers.
