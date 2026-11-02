# AI tutor foundations: subject knowledge and personal learning

Planning date: 8 October 2026.

Status: Steps 1–6 implemented: saved collections, coordinated source analysis, parent review, lasting learning summaries, checked source context in new lessons, adaptive recall, and reusable passage recordings. The integrated History rehearsal passes technical verification. Per the parent's October 9 instruction, listening, source checks and genuine handwriting review continue during supervised lessons; a separate blanket acceptance step does not block ordinary family use. History collection analysis is now complete after an explicitly authorized job-cap increase. Uncertain source matches and unchecked proposals remain labeled for review along the way. No analysis starts when a collection is saved or opened.

## Intended experience

A parent adds all the books for a subject, identifies their roles and intended reading order, then selects **Understand these books together**. The app builds a saved, source-linked subject map across the selected materials. It prepares each guided lesson near the time a child will use it, using the map, original source passages, and that child's current learning evidence.

The button starts one coordinated project. Internally, extraction, summaries, matching, and synthesis use bounded, checkpointed requests. A later synthesis connects information across the entire collection and can request original passages when summaries are insufficient. Processing sections individually is compatible with understanding the collection together; cross-book synthesis is an explicit stage.

The AI's context window is temporary working memory. The database and original source files hold the durable knowledge. More context alone does not guarantee accurate multi-fact retrieval; relevant source selection remains necessary. [Google context guidance](https://ai.google.dev/gemini-api/docs/long-context).

## Current foundations to preserve

- Multiple selected PDFs, book roles, companion links, and explicit workbook/edition targets for answer keys.
- Saved page scans, original question identities, exercise versions, source evidence, parent corrections, and resumable preparation.
- Guided lessons grounded in the current source passage and teaching instructions.
- Attempts, help, amended transcriptions, conversations, unfinished actions, checkpoints, and scheduled reviews.
- A shared spending ledger with reservations, monthly family allowances, and retained uncertain charges.
- Saved guides and recordings, device speech fallback, and test mode that protects actual student records.
- Read-only parent records and filtered exports.

The collection map now saves source-supported concepts and dates, explicit cross-book synthesis, exercise links, and private key associations separately from existing teaching material. Its AI relationships are proposals awaiting parent review. New guide preparation receives bounded, relevant learning evidence and explicitly selected, checked source context. Unreviewed map proposals stay out of teaching. Started lessons retain their saved context. The collection flow assembles books before paid analysis; legacy individual preparation remains explicitly available.

## Durable information design

Keep three separate layers, with independent versions and ownership.

| Layer | Contents | Changes when |
|---|---|---|
| Subject knowledge | Book identities and editions; source sections; concepts; relationships; chronology; exercise links; private answer-key references | A source, collection membership, parent correction, or relevant analysis instruction changes |
| Child learning | Attempts and evidence; independent success; help; observed difficulties; review checks and next steps | The child submits work or a parent deliberately records or corrects evidence |
| Prepared lesson | Objective, exact reading, explanations, activities, relevant learner context, and audio references | A new lesson is prepared or an explicit update is requested |

Every generated fact or relationship must retain its evidence references, source version, analysis version, review status, and origin. AI inference is distinguishable from a statement in the source. Missing evidence remains unknown; conflicting evidence remains visible. Parent corrections have priority and are preserved when new proposals are generated.

Store structured records in the existing database and retain original files and necessary generated artifacts in the existing file storage. Include new records and files in backup and restore. Export a readable subject overview and source-linked tables without requiring AI generation. A model's provider-side cache is optional acceleration, never the only copy of the map.

Subject knowledge contains no child's performance history. Identical permitted source analysis can be reused within a family, while learner evidence and personalized lessons remain separately scoped. Existing subjects belong to individual children; introduce reusable collection references additively rather than assuming all subjects already share one library. Future support for other families requires explicit account and access boundaries before deployment to them.

## Subject preparation workflow

1. **Assemble the collection.** Upload or select existing books without starting new paid analysis. Choose the main reading sequence, optional references, textbook/workbook/combined/test/answer-key roles, editions, and exact key targets. Multiple textbook volumes are supported. Existing reviewed associations are reused.
2. **Preview the work.** Show materials included, existing work that can be reused, pages not yet processed, analysis stages, estimated cost range, and a parent-selected maximum for this job within the monthly book allowance. Unknown costs are labeled; there is no unsupported promise that a large library fits US$2.
3. **Extract missing source material.** Save page and section results individually. Separate student reading, exercises, teacher instructions, and key answers even inside a combined book. Record extraction problems and coverage gaps.
4. **Build book and chapter summaries.** Identify objectives, concepts, vocabulary, events, and useful connections with references back to the actual source. Preserve original question numbering and edition identity.
5. **Connect the full collection.** Combine the summaries and outline across all selected books; fetch supporting original passages for proposed relationships. Connect exercises to every necessary reading section and keys to exact questions. Handle activities spanning chapters or volumes.
6. **Validate and review.** Check coverage, source references, question identities, chronology conflicts, missing keys, and ambiguous relationships. Parents inspect flagged issues and representative samples. Publish usable reviewed portions without falsely describing the full collection as complete.
7. **Save an active map version.** New lessons use that version. Adding a source or correcting a section updates affected relationships and summaries, followed by any necessary global synthesis. Unchanged scans and reviewed work are reused. Existing started lessons retain their original snapshots.

For History, retain both the intended lesson order and historical dates or ranges. They are different: a textbook may revisit an earlier period or describe simultaneous events in different places. Represent approximate dates and uncertainty, avoid inventing dates from chapter position, and distinguish an evidenced causal connection from simple chronological order. Other subjects use their own progression and prerequisite relationships without requiring a timeline.

Proposed parent controls: **Understand these books together**, **View subject map**, **Review flagged links**, **Continue preparation**, and **Update changed material**. Display progress by stage and statuses such as queued, preparing, paused for allowance, needs review, partially ready, and ready. Completed coverage and unresolved items must be visible separately.

## Personal learning memory

Build summaries from existing saved evidence and update them incrementally after assessed work. Retain the raw evidence so a summary can be checked and reconstructed.

Per child and concept, record observed outcome, evidence and date, independence or help, repeated difficulties where supported, last independent check, next review, and recommended next action. Also retain preferences, unfinished work, and source disputes.

Use cautious labels: not checked yet, needs clarification, needs help, demonstrated independently, and retained on a later check. A single response is evidence, not a permanent judgment. Unreadable handwriting, a disputed source, and lack of submitted work must not become evidence of misunderstanding. A response awaiting assessment cannot establish mastery.

Lesson selection should consider relevant older evidence and due reviews as well as recent sessions. Choose a small useful subset; do not replay every historic error or bury the current lesson in unrelated reviews. A new assessment or parent correction updates the derived summary without destroying prior evidence. Test-mode answers remain outside the real child's memory.

Use short recall checks, opportunities to explain reasoning, and delayed revisits. These choices are consistent with recommendations for spaced study, retrieval practice, and explanatory questions. [IES practice guide](https://ies.ed.gov/ncee/wwc/PracticeGuide/1).

## Guided lesson and voice workflow

Prepare the next lesson on demand, with an optional parent action to prepare the next one or two. Do not automatically generate an entire year's personalized lessons or recordings.

The preparation packet contains the active subject map, the exact current source passage, relevant prerequisite or earlier passages, eligible exercises, teaching instructions, and the child's evidence-based learning summary. Known earlier material can support connections; unseen later chapters must not be treated as already learned.

The lesson follows a consistent structure: welcome and purpose; brief relevant recall; reading and explanation; one clear task and a real pause; feedback or additional help; an independent check; recap and saved next step. Existing source coverage and exercise rules still apply. Adapt the pacing and difficulty to evidence without silently skipping required book content or completing assignments.

Keep reusable reading and explanations separate from changeable review questions and feedback. Cache voice passages by exact text, provider, model, voice, language, and delivery. The narration does not need to be regenerated whenever the learning summary changes. Generate new audio only for changed or new spoken text. Keep activity stops, passage highlighting, saved feedback playback, and device fallback.

Before starting a saved guide, check whether relevant new learner evidence calls for an updated warm-up or review. Record the learner-summary version and selected review evidence. A running session keeps its guide, exercises, map references, and checkpoint stable; new adaptive turns may use explicitly recorded current evidence. Whole-guide rewriting remains an explicit operation with a cost preview.

Private key answers and content derived from them cannot enter student introductions, general search results, narration, or reusable student summaries. Grading retrieves only the relevant private entries after an attempt. Key/exercise associations can appear in a public map as references without exposing answers.

## Implementation sequence and acceptance checks

### Step 1: collection and storage foundation

Back up data. Add collection identity, book roles/order/edition references, and immutable collection versions. Add an assemble-first flow while preserving existing prepared resources. Analysis versions and durable execution jobs follow in Step 2 when the analysis worker is implemented. No paid analysis is needed to validate this step.

Accept when a parent can select existing books plus staged uploads; save and reopen a collection; link keys unambiguously; and see all current guides, records, and audio unchanged. New tables participate in backup, restore, and access filtering.

### Step 2: coordinated subject analysis

Implement the subject-wide job, bounded extraction and summaries, cross-book synthesis, incremental updates, source validation, and use of the existing paid-generation service and spending ledger.

Accept when interruptions resume unfinished units; simultaneous clicks or workers do not duplicate a stage or its paid request; spending pauses preserve progress; incomplete coverage is labeled; and a changed book leaves unaffected scans and reviewed links reusable. Provider requests run outside long database transactions. Ambiguous provider outcomes stay reserved and cannot be blindly resubmitted.

### Step 3: parent map and correction view

Show books, reading sequence, History timeline, concepts, exercise/source connections, and flagged issues. Let parents inspect original evidence and save corrections without AI calls. Parent edits take priority over later generated proposals.

Accept when a parent can trace representative connections to actual pages, see an uncertain or disputed relationship, correct one, and reopen/export the saved result. Original exercise numbers remain stable and no key answer appears in a student-facing result.

### Step 4: lasting child learning summaries

Derive concept-level summaries from existing evidence, map reviews to concepts where evidence permits, and add incremental updates and parent inspection. Unmapped legacy evidence remains available instead of being forced into guessed concept links.

Accept when older relevant difficulties survive recent-session truncation; help is distinguished from independent success; corrected handwriting updates the summary with an audit trail; and test-mode activity changes no real child records or summaries.

### Step 5: context-aware guided lessons

Connect map selection, original passages, learner memory, due reviews, and unfinished tasks to lesson preparation and live tutoring. Add the freshness check for the adaptive warm-up while preserving started-session versions.

Accept when a lesson demonstrably uses a relevant earlier concept and observed difficulty; avoids future-material assumptions; follows source coverage; pauses for work; withholds answers before attempts; and resumes the exact unfinished activity. A saved lesson can be replayed with no generation request.

### Step 6: voice reuse and parent preparation controls

Connect stable passage audio and small adaptive additions to the updated lesson structure. Show preparation and voice estimates, completed parts, and interrupted jobs. Preserve the currently selected providers and monthly limits unless the parent changes them.

Accept on desktop and mobile when passage highlighting, activity stops, pause/resume, feedback playback, and fallback work; repeated identical audio uses the cache; and a changed warm-up leaves unchanged recordings reusable. Test model/source combinations directly; the earlier voice introductions did not establish that every verbatim book passage is accepted by Google.

### Step 7: History pilot, then other subjects

Use Lucas's actual History collection for the first integrated check, reusing saved work. Inspect Genghis Khan, the Mongol conquest, and Marco Polo for continuity where the source supports it. Review representative workbook/key links across the supplied collection. Broader unfinished analysis remains labeled and resumes within allowance.

Run the first learner interaction in test mode. Verify representative typed and photographed answers, independent and helped responses, unreadable input, disputed source material, older reviews, and retained checkpoints. Measure actual preparation, teaching, and voice costs within a small declared job maximum and the existing monthly allowances. Do not automatically purchase credits or increase limits.

Verify record isolation, resume behavior, cache reuse and representative teaching behavior technically. Parents check source accuracy, pronunciation and real responses as they supervise the next History lessons. Exercise separate textbook/workbook/key arrangements and combined books with isolated tests, and continue checking real examples during use. Do not mark unobserved learning or unchecked map proposals as approved.

## Implementation boundaries

Continue using the existing home-server database and file storage; a new vector database or additional paid service is not a prerequisite. Start with explicit source-linked records and indexed lookup, and measure retrieval quality before adding infrastructure.

Use the existing configured provider service. Never silently upgrade models, switch providers, expand allowances, or repeat an uncertain paid request. Reprocessing is driven by tracked changes or an explicit parent action, not ordinary page opening.

Reuse old data additively. Do not renumber reviewed topics, replace active assignments, rebuild every guide, or mark reading as understanding during migration. Validate meaningful failure cases and the user flow at each implementation step before advancing.

Microphone conversations, deployment to other families, and automatic full-year narration are outside this initial sequence. Shared source knowledge and private learner evidence are separated now so those future decisions do not require mixing children's records.

## Immediate next implementation step

Continue supervised use of Lucas's unfinished Genghis Khan lesson, with parent listening and source review along the way. Consistent local narration and the integrated rehearsal have passed technical checks. History analysis has completed at US$0.280554 after the parent authorized a US$1 lifetime job limit. Review and explicitly select checked source-map portions as needed for new lessons; no parent source approval has been asserted on their behalf. Real learner records and the original checkpoint remain unchanged.

## Step 2 implementation notes

The worker pins collection membership, source checksums, provider/model and existing exercise versions. It reuses full saved scan batches, summarizes verified student reading, retains verbatim page evidence, matches original question identities with bounded source follow-ups, and synthesizes summaries across the whole collection. Hierarchical synthesis distinguishes reading order from source-supported historical dates; every original event remains in the saved map even when upper-level working summaries use a bounded selection of anchors.

Each paid request reserves against both the job's lifetime total and the family monthly book allowance atomically. A month change does not reset the job total. Parent pauses prevent further reservations; an already sent request may finish and be saved. Restarted running jobs wait for explicit continuation. Completed provider responses survive failures before the main database checkpoint. Unknown charges remain reserved without a blind resend.

New `collection_analysis_jobs`, `collection_analysis_units` and `subject_maps` tables are included in normal backups. The map endpoint uses an explicit public-field allowlist; raw key text remains private. Existing prepared exercises, reviewed mappings, guides, recordings and learner tables are not rewritten. Test mode uses separate jobs and maps, while sharing the exact-input paid response cache and family ledger. It cannot pause or continue a copied real in-flight job.

The initial live job is limited to US$0.25. This is a partial-run limit, not a promise that the full collection fits that amount. Estimates are planning ranges rather than provider token quotes. Missing or disputed evidence is flagged instead of automatically regenerated. The parent must explicitly choose any later increase to the total job limit.

The whole-book synthesis is saved before the longer exercise-matching stage. A spending pause can therefore leave an immutable overview available, with unfinished links explicitly marked pending. Completing the job creates a separate final snapshot. Restarted matching retains its fixed question batches and reuses both supported proposals and flagged batch checkpoints. Original numbered exercises stay in source order.

Evidence retrieval shares its bounded page space across every question and supports a bounded follow-up for other sections. Identifier choices are constrained to actual source records. Preserved citations honor printed-to-PDF offsets, current section boundaries, and quotations crossing page boundaries. A known unusable paid reply becomes a review item; it is not blindly sent again or treated as provider credit exhaustion. Interrupted/uncertain requests remain reserved and stop their stage until reconciled.

### Initial History analysis pilot — October 8, 2026

Lucas's saved collection reused all 610 cached pages from the textbook and test book. The worker processed all 78 source units and saved a proposed overview containing 212 concepts, 103 source-linked timeline entries, 63 connections, and 767 original exercises. Its latest immutable snapshot has 88 pending exercise links and 216 flagged review items. Coverage remains explicitly incomplete; the proposals are not active lesson context yet.

The job paused at US$0.245612 across 125 paid requests, within its US$0.25 lifetime cap. No uncertain charges remain. Reopening and restarting at the unchanged cap added zero requests and zero charges. The monthly book allowance still has funds; this pause is the separate job cap, not evidence of exhausted provider credits. Continuing requires an explicit parent choice about the total job cap.

The pre-change backup comparison found all 42 existing data tables unchanged, including four children and 34 saved attempts. Saved guides, audio, prepared exercises, and current learner records remain intact. Verification covers concurrent spending, incomplete and uncertain replies, restarts, month changes, source citations and page boundaries, private keys, immutable partial snapshots, test-mode isolation, and cached source facts associated with each collection's selected documents. Backend and frontend checks pass; the live curriculum flow was checked on desktop and a narrow mobile viewport. A final normal backup preserves the pilot's saved work and ledger.

### History analysis completion — October 9, 2026

The parent authorized loosening the budgets and continuing while provider credits remained available. OpenAI Billing showed US$7.15 before continuation and US$7.11 after; Google AI Studio showed R$25.44. Automatic reload remains off for both. These are dated billing-page observations saved in Settings, not an automatic balance synchronization.

The History job's lifetime limit was explicitly raised from US$0.25 to US$1. The existing US$3 teaching, US$2 book and US$2 paid-voice monthly allowances were sufficient and stayed unchanged. Twelve remaining exercise-link batches cost US$0.034942, bringing the full job total to US$0.280554 with no uncertain charges. Cached scans, summaries and whole-book synthesis were reused; no voice generation was purchased.

The final immutable map covers two books, all 610 pages, 55 reading summaries and 767 uniquely numbered exercises, with zero pending AI-processing items. It retains 212 concepts, 103 timeline entries and 63 connections. Exercise relationships comprise 306 preserved links, 312 proposals and 149 needing source review. There are 238 flagged items across the map. Analysis completion does not approve every relationship or replace live exercise versions: the saved status is `needs_review`, and unchecked map proposals are not yet active teaching context. Parents can review relevant portions during supervised lessons.

Verification compared all 50 pre-existing data tables. Only operation receipts, analysis jobs/units and the new map snapshot changed. Four children, 34 attempts, six real guides, fourteen real audio tracks, all earlier map snapshots and the original unfinished lesson were preserved; no source review or teaching selection was invented. Before/after normal backups are `homeschooling-20261009T111627Z.sqlite3` and `homeschooling-20261009T112127Z.sqlite3`, with corresponding spending-ledger backups. Detailed results: `data/artifacts/history-analysis-completion.json`.

The pilot and implementation notes below retain their historical checkpoint costs and caps; this completion record supersedes their earlier paused status.

## Step 3 implementation notes

**View saved overview** now opens the parent source map: overview, ordered books and companion/key references, reading order, historical timeline, concepts, connections, original numbered exercises and their proposed reading evidence, source warnings, and parent history. Search, review filters, and bounded pages keep large lists usable. Small screens present review rows vertically. Historical dates remain distinct from book reading order; unknown dates are labeled.

Parents can inspect exact saved quotations, complete checked reading excerpts, and a checked original PDF page without generation. Mixed reading/workbook pages expose only their saved safe reading blocks, and private or unchecked pages and answer-key PDFs are refused by the map source endpoint. Key associations remain references, without answer contents.

`subject_map_reviews` is an append-only, teacher-only collection history included in normal backups. A collection-wide review number prevents concurrent overwrites. Original analysis snapshots, exercises, grades, guides, audio and learner evidence are not modified. Parent-approved content is frozen alongside corrections, so later AI wording does not silently replace what was checked. A later map applies a review only to the same source identity with valid edited references; missing or changed evidence leaves an explicit unapplied history entry. Parent correction/rejection requires a note; restore adds a new unreviewed entry instead of deleting history. Exercise evidence must match actual checked original pages, including bounded page-spanning quotations.

The JSON export contains the safe map, effective parent reviews and audit history; it excludes private answers. Inspection, correction, restoration and export do not use the provider service. Test-mode reviews stay in its separate database. The initial History map remains paused at its unchanged US$0.25 cap with 88 originally pending links; this step has made no new generation requests. Step 4 will derive child learning summaries, and Step 5 will explicitly connect approved source context to new guided lessons.

Verification passed 31 source-map/analysis backend checks, 10 test-mode checks, 14 related frontend checks, lint and production build. The live flow traced Marco Polo's concept to the book's printed page 202 (PDF page 217), rendered the checked original page on desktop and a 390-pixel mobile viewport, and downloaded the safe JSON export. All 45 pre-existing data tables were unchanged apart from operation receipts; the new parent-review table is empty because the live inspection was cancelled without asserting a parent decision. The ledger remains at 125 pilot requests and US$0.245612. Before/after normal backups: `homeschooling-20261009T012958Z.sqlite3` and `homeschooling-20261009T014956Z.sqlite3` (UTC filenames, local date October 8).

## Step 4 implementation notes

Progress now includes a lasting learning summary for each child and subject. It reconstructs topic and concept observations from actual attempts and reviews, distinguishes independent success from help, requires later-day evidence for retention, and counts repeated difficulties across distinct lessons. Unreadable, disputed and awaiting-assessment responses require clarification. Completion alone supplies no mastery evidence. Older open reviews survive the two-recent-lesson window.

Immutable `learning_snapshots` and append-only `learner_concept_links` retain versioned summaries and deliberate parent associations. Legacy work remains at its topic when its concept cannot be established; only an unambiguous exact saved concept name or an explicit parent link associates old reviews. Raw evidence remains inspectable. Parents can amend a saved transcription or assessment with a reason, preserving the complete lineage and any assistance. An amendment retains the original lesson date and is not counted as a new later check. Conflicting concurrent corrections are refused. Summaries update inside evidence transactions, use semantic fingerprints that remain stable after commit, and can be reconstructed after restart without AI.

These tables participate in normal backups and remain teacher-only. Family routes validate child/subject ownership; tutor bridge access is refused. Test-mode amendments and summaries remain in its separate database and do not publish into real learning memory. Snapshot creation changes only derived data, with no provider request.

Verification: 66 related backend checks, three new frontend checks, lint and production build passed. The live Progress view shows Lucas's 34 effective History observations and their five topic summaries; all 34 legacy attempts conservatively remain without concept links. Comparison with the pre-step backup found no changes to existing tables apart from operation receipts. Six guides and fourteen audio tracks remain unchanged. Before/after normal backups: `homeschooling-20261009T020248Z.sqlite3` and `homeschooling-20261009T021532Z.sqlite3`; the latter includes the first derived learning summary. No new generation charges were incurred.


## Step 5 implementation notes

Parents explicitly select checked portions of a source map for new lessons. Immutable teaching selections freeze the reviewed concepts, connections, chronology and exercise references. Source edition, collection membership and parent review changes require a fresh explicit selection; neither old guides nor started lessons are silently rewritten. Only concepts quoted inside the exact current passage enter its context. Relevant earlier, observed material can supply original supporting passages; unseen later chapters never become assumed prior learning. Private answers remain outside this context.

New guides save the selected source version and relevant learning snapshot. Model-proposed activity concept identifiers must belong to the supplied context. One relevant older recall task can be prepared separately from stable reading and explanations. Learner evidence changes update that task without rewriting the guide or its audio. Started lessons pin the source context, activity identities and exact checkpoint; subsequent feedback records its current observed evidence separately.

## Step 6 implementation notes

Curriculum can preview and prepare the next one or two unfinished lessons. Estimates and a maximum per guide are checked against the shared monthly teaching allowance; successful first results survive a later failure. Explicit rewriting uses a cost preview. Exact-text voice parts are keyed by provider, model, voice, language, pace and delivery settings, independent of guide version or passage position. Unchanged parts and valid legacy recordings are reused and remapped to their current passage ranges. Completed parts survive interruption, while sent uncertain identities remain reserved and are never blindly retried.

New recordings respect original paragraph boundaries and activity pauses. Manifests retain provider, model, actual job charges, status and passage ranges. Saved feedback and adaptive tasks use server-retrieved text for read-aloud, with cached replay and device fallback. Generation runs outside long database transactions. Optional lifetime caps for a pilot conversation and narration persist across restart and cannot be enlarged merely by resuming.

A fresh test-mode session retains a read-only snapshot of partial real source analysis under a separate job identity. It can inspect and rehearse source selections, but cannot pause or resume the real analysis. Rehearsal source changes cannot publish personalized guides into real lessons; exact audio parts remain reusable. Child observations and parent corrections stay in the rehearsal database.

## Step 7 technical rehearsal — October 9, 2026

The saved rehearsal inspects source-supported continuity across Genghis Khan, the Mongol conquest and Marco Polo. Three concepts and two corrected connections were checked against original quotations in test mode, with explicit rehearsal notes; these are not parent approvals in the real collection. Two guided lessons were prepared with US$0.03 maxima each. Genghis resumed its exact original discussion checkpoint. A wrong typed response, a blank photographed input, a printed answer photograph and a later independent recall exercised saved feedback, help, clarification lineage and adaptive memory. The printed photograph is a test fixture; actual child handwriting still needs parent inspection. Disputed-source behavior, combined books and separate workbook/key arrangements have also been checked with isolated tests.

The next lesson received fresh recall from the newly observed difficulty while retaining its prepared guide. Marco Polo's free preparation preview excludes the unobserved conquest chapter as prior learning. Current prompts keep saved review questions outside new stable narration, and a selected adaptive warm-up suppresses a second automatic general review. Existing guides and started sessions keep their original words and tasks. A closed review alone cannot establish retention: the summary requires independent checks on separate days. Rule changes create new derived snapshots and preserve older evidence and summaries.

The Mongol conquest guide is saved with 86 sentences across 28 passage parts: 25 Google WAV recordings and three device-speech parts after definite Google content refusals. Original words are retained; refused parts are recorded and not resent. The manifest covers every sentence. Reopening, restarting, replaying the guide and replaying saved tutor feedback added zero provider requests. Desktop playback, passage highlighting, pause, speed, manual seeking between recorded and device parts, saved feedback and mobile activity controls were checked. Human listening is still needed for pronunciation and delivery. A playback regression found during the rehearsal was fixed and covered by a test.

Incremental costs were US$0.005601 for guides and tutoring, US$0 for book processing, and US$0.063693 for lesson and feedback voice: **US$0.069294 total**. These are within the declared US$0.21 text/teaching and US$0.10 voice maxima and the existing family allowances. No uncertain charges remain. The original collection job remains paused at US$0.245612 of its unchanged US$0.25 lifetime maximum.

Focused backend checks for costs, voice reuse, test-mode isolation, guides, lesson context, tutoring and learning-memory changes passed, as did 16 related frontend checks, lint and the production build. Normal quick-pause cancellation is handled without a false playback warning. Comparison against the pre-step backup found all 49 existing tables unchanged: four children, 34 real attempts, six real guides and fourteen real audio tracks remain intact. All rehearsal observations and source reviews are private to test mode. A normal backup of the real database and shared ledger was saved locally and to the configured Drive folder as `homeschooling-20261009T102727Z.sqlite3` and its corresponding `ai-usage` backup. Detailed results are in `data/artifacts/history-pilot-verification.json`.

The rehearsal can be resumed through Settings' saved test-session link, then opened at **The Mongol Conquest of China → Guided lesson**. Listening preview uses saved audio without recording an answer. The saved interactive rehearsal also retains its recall answer and unfinished activities. Parents review alongside the child during use; the technical check does not change Lucas's real unfinished Genghis lesson.

## Consistent local narration

Kokoro v1.0 runs on the home computer with a pinned ONNX runtime and verified model/voice files. English Michael/Heart and Brazilian Portuguese Dora/Alex can be selected explicitly in host Settings. Local inference has no API charge and requires no provider key or monthly spending reservation. It uses CPU, electricity and storage; initial generation takes time. Google remains an explicit alternative with its own billing enablement and existing saved recordings.

Exact original text, model asset identities, runtime/delivery settings, voice, language and pace identify reusable parts. Local jobs save each completed WAV independently and resume missing parts after interruption. They stop on failure rather than changing narrator mid-lesson. Manifests retain truthful passage ranges, provider/model, zero API cost and job status. Playback and spoken feedback use the same selected narrator; device feedback is an explicit choice after failure. Local generation runs outside database transactions. Existing Google recordings remain intact and selectable, including visibly labeled legacy mixed recordings.

The October 9 local check saved the complete Mongol conquest rehearsal: 28 WAV passages, all 86 sentences, 470.04 seconds, no fallback parts and no added API requests or charges. The three exact passages declined by Google now have local recordings. Brazilian Portuguese Dora produced a separate sample with intact Portuguese text. Saved feedback uses Michael and cached replay adds no inference or charge. Comparison with the pre-change backup found all 50 existing tables unchanged, including four children, 34 attempts, six real guides and fourteen real audio tracks. The new guide recording remains in test mode, with immutable passage files reusable later. Details: `data/artifacts/local-narration-verification.json`. Parents judge pronunciation and delivery during supervised use; this is a technical check, not a recorded parent approval.

## Family source reuse and visible activity pauses — October 9, 2026

The parent chose personalized lesson preparation for each child, while reusing the initial subject/grade source analysis. Completed collections now write versioned JSON archives under **Subject Knowledge** in the subject folder. Format 1 preserves source fingerprints, roles/editions/order, raw scans, section summaries, concepts, chronology, exercise references, cross-book relationships, warnings and parent source reviews. Raw scans and key entries remain explicitly teacher-only. No learner history or personalized guides are included. The original PDFs must be retained. See `SUBJECT_KNOWLEDGE_FORMAT.md`.

**Use saved subject knowledge** links another child's subject to the same completed family collection after verifying original PDF bytes. Source results and reviews are shared without a new provider request. Each subject keeps its own checked teaching selection, guides, topic assignments, attempts, summaries and unfinished lessons. Existing different books cannot be silently replaced. Editing a shared book collection creates an independent collection instead of changing another child's materials. This phase reuses registered collections on the same server; arbitrary-file import into another installation is not implemented.

The reading preview previously bypassed activity callbacks. It now pauses at saved actions and offers **Start answering** or **Continue preview without answering**, without writing learner evidence while previewing. Active lessons show text/photo input, adaptive follow-up prompts and an explicit continue. Genuine sentence timings stop older recordings at a question inside a part; untimed passages that cross an action cannot silently play through it. New guide prompts require response-seeking questions to be actions. Existing guides, original book words and recordings stay intact.

Verification: 41 source/analysis/map/context backend checks, 27 knowledge/test-mode/interactive checks and 29 frontend checks passed, together with lint and production build. The saved Conquest WAV played its first question and automatically stopped after 7.672 seconds; starting the test lesson restored saved feedback and continuing exposed a real exercise's typing/photo controls. No new provider request was made. A phone viewport override was attempted but the browser kept desktop dimensions, so an actual mobile-browser check remains unconfirmed.

All 50 real tables remained unchanged after deployment and file creation: four children, 34 attempts, six guides, fourteen audio tracks, zero parent map reviews and zero teaching selections. The API request count stayed at 353. The real History archive is `Lucas/4th Grade/History/Subject Knowledge/subject-knowledge-v1-bbc407b1852e82a9.json`; it covers 610 pages and 767 exercises. Backups before/after: `homeschooling-20261009T120818Z.sqlite3` and `homeschooling-20261009T122411Z.sqlite3`. Details: `data/artifacts/reusable-knowledge-verification.json`.
