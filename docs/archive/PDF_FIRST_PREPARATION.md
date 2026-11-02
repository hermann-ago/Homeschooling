# PDF-first lesson preparation and cleanup ledger

**Current default:** [chapter maps and original lesson pages](ORIGINAL_PAGES_WORKFLOW.md).
New scripts no longer run the source-inventory preflight described in this ledger.

See [the simpler preparation and ElevenLabs pilot](SIMPLE_LESSON_PREPARATION.md)
for the October 23 model, prompt, narration and cost updates.

New API preparation selects original assigned PDF pages by edition and page range,
then attaches them to the existing structured lesson planner. It includes current
learner evidence, age-aware family style and subject teaching instructions. A
whole-book JSON companion is optional, not a preparation prerequisite.

Related exercise pages come from server-selected immutable exercise versions.
The planner sees student pages only. The reviewer receives those same original
pages, with explicitly mapped answer-key pages added privately when a document
and edition are available. Legacy keys with only a textual reference retain their
existing assessment path; the app does not guess a key PDF location.

The same `/api/tutor/reader/guide` executor serves lesson and curriculum preparation.
No new queue, import format, provider adapter, parent interface or preparation
button is needed. Exact selected PDFs, page maps, boundaries and hashes are saved
with each new guide using normal durable file storage. Review retries use that
snapshot, even if the original book is subsequently replaced. No child responses
or completion records are created during preparation.

## Coverage and limits

- Partial boundary pages retain `start_at` / `stop_before`; numbered passage text
  still restricts exact reading. Shared-page neighbors are context, not new work.
- Full-page lessons lacking checked coverage use the existing cached **lesson-only**
  source inventory. This inventories assigned readings and waiting tasks, not an
  entire book. Existing checked inventories remain usable.
- The independent reviewer sees actual pages and must check omissions even when
  an inventory missed them. Blocking findings prevent a new audio purchase;
  there is no silent rewrite, provider switch or automatic paid replacement.
- Keep native extracted text for exact quotation and narration. Entirely image-only
  books still need usable source transcription before the current reading engine
  can narrate them. PDF-first planning is not a replacement for that requirement.
- Mixed student/teacher PDFs marked `hide_pdf` retain their checked student-text
  path. Raw private pages never enter the child-facing planner.
- Explicit `lesson_source: text` in teaching-skill front matter retains text-only
  preparation. Otherwise original PDFs are the default, across subjects.
- Up to 20 assigned pages, 40 total including linked sources, and 20 MB per bundle.
  Oversize or edition/ownership mismatch stops preparation explicitly.
- Review and any needed lesson inventory share the existing teaching cap; audio
  retains its own cap. Page-token estimates include linked review-only pages.
- Existing saved sessions, scripts, approvals and recordings are reused. They are
  not automatically regenerated or charged by adopting this workflow.

## Removal candidates — record now, remove after comparison

| Candidate | Current decision | Evidence required before removing |
| --- | --- | --- |
| Mandatory whole-book visual-to-JSON conversion before teaching | No longer required by preparation; keep optional import/review tooling | History, visual Portuguese and Math pilots succeed without companions |
| `lesson_source: visual_pages` opt-in convention | Compatible but redundant because PDF is now default | Custom skills and documentation audited; explicit `text` remains supported |
| Duplicate full page descriptions in planner context | Removed from PDF-first input after the October 23 pilot; retained in stored inventories and explicit text-only input | Continue comparing visual-task omissions and total tokens |
| Full-book source-analysis UI as a routine preparation step | Keep accessible for existing mappings/corrections; do not add new UI | A simple page/mapping workflow replaces its necessary functions |
| Historical companion adapters and caches | Keep for historical guides, source corrections and existing maps | Dependency audit, backup/restore test, historical playback test |
| Lesson-only coverage inventory | Keep; protects literal readings and waiting tasks | Remove only if an equally testable coverage mechanism replaces it |

Keep permanently: original PDFs, edition/page mappings, exercise/key relationships,
versioned reusable teaching skills, structured lesson activity output, ownership
checks, learner evidence, review results and narration checkpoints.

Do not delete existing companions or stored material until representative real
API lessons have been inspected against their pages. Mocked tests establish
transport, isolation, persistence and gates; they cannot prove teaching quality,
vision accuracy or lower costs. Record completeness, source fidelity, pacing,
manual repairs and actual combined preparation/review cost during that pilot.

## October 23 pilot hardening

The live pilot exposed omitted literary readings, omitted visual work and an
activity-content union serialization failure. The compact source output contract
now shows actual required reading segments, and the provider schema limits their
source-block IDs. Explicit listen-then-work directions are validated against their
same-page reading dependency; their work pause must follow the complete reading.
Provider content is rebound to its registered concrete activity model before
serialization, so unrelated empty union fields cannot invalidate a saved reply.

Explicit rewrites receive editorial review findings, including approved advice,
and up to ten earlier correction constraints from the same topic/source lineage.
They must not fix one problem by reintroducing an earlier omission. This is not an
automatic paid repair loop. Source/key disputes still need source review; feedback
cannot change a PDF, key or child record. Review approval remains fallible and is
not a replacement for evaluating representative real lessons.
