# Simple lesson preparation and narration

**October 28 update:** [Chapter maps and original pages](ORIGINAL_PAGES_WORKFLOW.md)
replace the source-inventory and reading/task-ID constraints described below for
new preparation. Existing scripts and recordings retain their saved contracts.

## Natural teaching scripts — October 27, 2026

New API preparation uses `tutoring/teaching_script.py`. One writer sees the assigned
original PDF pages, the age-aware shared style, subject guidance, relevant learning
context and checked reading/task references. The provider writes `welcome`,
`turns` and `closing`; turns are `say`, `read`, `ask` or `practice`. An ordinary
answer needs only a response format. Strict provider schemas omit unrelated fields.
The writer no longer emits the full 23-activity union, engine identities, response
methods, source quotations, completion commands or UI implementation details.

A deterministic local compiler binds reading/task IDs to their checked original
sources and maps these teaching intentions to the same canonical activity engine.
It makes **no additional AI request**. It preserves teacher wording, including
explanations longer than the former 700-character clipping limit. Complete titles,
attribution and continued literary passages remain one reading turn. Related book
items remain individually identifiable within the existing practice-section UI.
Spelling, matching, choice, reasoning and work that really needs physical evidence
reuse the same capture policy and renderers. There is no automatic extra discussion
question in a script which did not ask for one. A worksheet without literary reading
does not invent a reading step just to satisfy the older plan format.

Bound schema validation rejects missing, duplicate, unknown or reordered reading
references, missing/repeated tasks and listening work scheduled before its passage.
It does not invent replacement work. Downstream source, ownership and public-choice
checks still apply. Unindexed text-only material uses exact, complete sentence
ranges; PDF input remains the default. Private answer-key pages stay in the existing
review/assessment bundle and are not copied into the author's child-facing script.

The final AI check focuses on source coverage, exercises/options, answer leakage,
factual contradictions and missing answer pauses. For this preparation version,
tone/pacing preferences are advisory and cannot purchase a rewrite. The original
review proposal is retained privately. Concrete task/waiting blockers retain the
existing single bounded repair and spending safeguards.

OpenAI preparation retains `PREPARATION_MODEL` with **high reasoning**, separate
from live feedback. Curriculum's cost preview shows the actual model and reasoning
setting before purchase. Selecting Google explicitly retains Google's configured
model; the app does not silently switch providers. Source indexing and editorial
review may still incur their existing API charges; local compilation does not.

The raw teaching script and its version are frozen privately with each new guide
for later comparison. Existing guides, pinned sessions, recordings, editable skills,
learner answers and exports retain their established contracts. Preparing an already
saved lesson reuses it; choose **Generate a new tutor script** to apply the new writer
to an existing topic. Nothing is regenerated on server restart.

Verification: synthetic authoring/compiler tests, actual provider-adapter requests
with mocked transport, source/legacy/retry/cap regression tests, and an offline
browser rehearsal via `backend/dev/activity_demo.py --teaching-script`. These prove
the pipeline and controls, not that every future AI-authored lesson is excellent.

### Decluttering follow-up

`guide.prompt`, `ProviderGuidePlan` and `plan_schema` remain compatibility/import
contracts and deterministic compiler validation. They are no longer the new API
writer's prompt/schema. After migrated callers and saved-cache recovery have been
audited, the old authoring prompt can be removed; do not delete historical guide
adapters, recordings, book companions or editable skills as part of that cleanup.
Do not add a second generative conversion service or a separate lesson queue.

## Earlier preparation implementation

Implemented and exercised on October 23, 2026.

## Preparation

The app sends the assigned original pages, child context, shared tutoring style,
subject guidance and checked source obligations. A shorter prompt asks for one
complete teaching script. Existing schemas and coverage checks still preserve
readings, exercises, source boundaries, waiting activities and private keys.
One source/editorial review follows. A concrete editorial blocker (tone, pacing,
waiting or a missing source task) can trigger one revision from the saved findings,
followed by another review. Both drafts and reviews share the original teaching
scope and cap. A second rejection stops; source/factual disputes, answer leakage,
provider failures, refusals and uncertain outcomes do not trigger this repair.
Original drafts and reports remain saved; preparation creates no learner evidence.

The provider schema binds each activity name to its canonical registry content
model, so it cannot pair an explanation with visual-only fields. Catalog exercise
identities in planner source references must be null; the server inserts the
checked workbook tasks, options and versions. The shared prompt distinguishes
that work from AI-authored discussion, preventing duplicate workbook questions.

Original pages also govern substantive captions and footnotes absent from an older
saved text extraction. The planner includes their exact wording in separate
explanation segments near their references. Saved passages and sentence identities
are preserved. The ordinary review compares those additions with the actual PDF.

OpenAI preparation and its review use `gpt-6.1-sol` with high reasoning. Live
feedback and other ordinary requests retain `gpt-6-luna`; explicitly selected
Google requests retain their provider. This is a request-local context, shared
by the lesson and Curriculum preparation routes, not a global model override.
Model-specific rates are used for both reservations and usage accounting.

New script preparations default to a US$2 job cap (editable up to US$5), including
review. This accommodates conservative page/schema estimates. The existing
monthly teaching allowance is unchanged. Saved scripts/sessions are not rewritten
unless explicitly requested. A model upgrade is not a guarantee of correctness.

## Narration

`elevenlabs_audio.py` is a provider adapter behind the existing narration service.
It uses Flash v2.5 (`eleven_flash_v2_5`) and the speech-with-timestamps endpoint,
with explicit English or Portuguese language codes. Requests cover up
to 8,000 characters, independently of paragraphs or lesson pauses. Original-text
character timings map to sentences. The existing WAV clipping and version-4
manifest publisher creates the activity clips; no local speech recognition or
forced-alignment model is required for this provider.

Exact script/model/voice/rate identities reuse recordings and raw responses.
Responses are saved before validation; a timing or storage failure can resume
without another purchase, even at an exhausted job cap. Unknown network outcomes
remain reserved. No automatic provider or narrator fallback is introduced.
Two simultaneous requests for the same track create one purchase.

Timestamp tails may differ from PCM duration by a few milliseconds due to provider
rounding. A 20 ms tail tolerance is accepted; invalid ordering, missing original
text, and substantive truncation still fail. Activity clips retain validated
sentence starts and actual media durations.

The shared voice allowance counts a published starting-rate equivalent
(US$0.04 per 1,000 characters for Flash), not an asserted Starter-plan cash charge.
Subscription credits, taxes, billing and custom voice multipliers can differ.
Narrators resolve by learner and language, then fall back to the family narrator.
Host Settings exposes configured learner overrides. Lucas uses Adam (US English)
and Henrique (Brazilian Portuguese); Mila uses Bella (US English) and Juliana
(Brazilian Portuguese). Both preparation and live feedback use this same selector.
Voice Library narrators must first be added to the account. The user purchased
Starter on October 28; the app does not buy subscriptions or top-ups.
The model remains part of each purchase/cache identity, preserving older recordings.

## Key and UI

The official ElevenLabs CLI created the project key after explicit authorization.
The server loads the gitignored project `.env.local`; no key enters client code,
responses, source control or screenshots. Tests never load that file. The existing
host secret store also accepts an ElevenLabs key through Settings.

Settings → Teaching and voice exposes the provider, narrator choices, key entry,
read-only connection check and separate ElevenLabs enablement. Curriculum can
prepare either advanced provider and identifies which recording is ready.
Lesson selectors, preparation status and retry controls identify ElevenLabs.
Existing Google/local recordings remain available; generation does not switch
providers on failure.

## Real pilot

### History engine audit, October 24

Lucas's next History topic, 377, **Ivan the Great and Ivan the Terrible**, was
requested through `/api/tutor/preparation` with target `guide`, original pages,
the configured model and a US$2 script cap. No teaching text was manually authored
or imported. The first run was deliberately performed before changing its inputs.

| Run | Engine time | Actual teaching charge | Outcome |
| --- | --- | --- | --- |
| Original workflow | 120.65 s | US$0.154754 | Invalid tool/content pairing; cached reply preserved |
| Bound activity schemas | 138.49 s | US$0.183668 | App review detected two omitted source footnotes |
| Updated source instructions and saved review feedback | 124.40 s | US$0.180573 | Approved; no manual script edits |

The final guide `guide-377-52a205926a` retains all 63 saved source sentences in
order, both substantive PDF footnotes, nine required workbook tasks exactly once,
the original choice/true-false controls and a distinct reasoning question. It has
21 activities and 109 narration sentences. One non-blocking review note questions
the book's illustration caption; the script attributes that caption to the book
and does not independently assert the building's identity.

Total experiment charge was US$0.518995, including the two earlier drafts and
reviews; engine time was 383.55 s, excluding debugging and tests. Audio was not
requested. Hashes of attempts, responses, dialogue, sessions, playback, assignment
items, reviews and topic completion records were unchanged. All 73 focused tests
passed, including one-repair limits, shared spending caps, source disputes,
provider failures, canonical schema matching and legacy guide behavior.

Evidence and exact API/ledger measurements are in the local task folder
`.tmp-data/ivan-engine-20261024/`, including `audit-final.json`. The one-attempt
automatic repair path was verified with synthetic providers; the final real run
passed its first review and did not need that extra attempt.

### Earlier Portuguese and voice pilot

- Mila, Letra S, topic 978: one API-written script, one AI review, approved with no
  findings. Guide `guide-978-e1be01de91`: 27 activities, both required readings
  preserved and all 13 source tasks represented. No manual teaching-text edits.
- Script and review cost US$0.374852 in the app ledger. No second planner draft.
- One Juliana request received HTTP 402; zero charge recorded. Voice Library API
  use is unavailable on the current free account. The library voice remains saved
  for later use if the family chooses an eligible plan.
- Bella generated all 5,291 characters of the Portuguese script in one request.
  A 1.5 ms timestamp tail initially failed the overly strict check. Recovery used
  the saved response without a new request. Track
  `dd77c917553a70fb04925df5679741274f088166f80c0f09a23ac3f25f28b04b`
  has 27 clips, 77 sentence timings, 406.9065 seconds and zero text-only sections.
- A separate 693-character English sample from Lucas's actual History reading
  generated 51.7805 seconds with valid original-text timing.
- These two accepted narration requests consumed 5,984 account characters. Their
  local allowance equivalent is US$0.478721; that is not a paid subscription bill.
- Sorted-row hashes for attempts, responses, dialogue, sessions, playback,
  assignments, reviews and topics match before/after. No student answers, saved
  positions or completion records changed.

Synthetic regressions cover provider timing, activity cuts, duplicate requests,
lost responses, cached recovery with no spending room, secret isolation, scoped
preparation models and the existing preparation/playback paths. Browser checks
verify the configured provider and lesson-ready state. All 27 steps were traversed
in the listening preview without answers or a real session. The introduction
played to its actual 39.137-second end and stopped; Continue started step two,
and the audio element reported advancing playback with no media error. Voice warmth/pronunciation
still need family listening; this pilot does not prove universal reliability.

## Keep the app small

Guided narration requests may explicitly select `provider: google-gemini` while
the family's default remains another provider. The reader chooses Google's own
narrator and uses the existing aligned-audio service, key, spending ledger,
review gate and saved-request identities. This does not change settings or enable
automatic provider fallback. Omitting the field retains configured behavior.

### Long preparation requests and explicit paid retries

Background script generation and review allow a 600-second read timeout; normal
live tutoring keeps its existing timeout. A timed-out request remains uncertain,
with its spending reservation retained. Ordinary retries cannot repurchase it.
After explicit family authorization, the preparation API accepts
`retry_uncertain: true` with a new `operation_id`. That identity is saved on the
job and scopes its provider requests; duplicate delivery or execution does not
create another purchase. The earlier uncertain reservation is not cleared or
reported as a confirmed charge. This flag is a paid new attempt, not recovery of
the old response. Complete cached replies remain reusable without another request.

Checked worksheet tasks can combine a shared instruction with a later subitem or
word table. The paper-work validator accepts an exact reviewed task quote on its
pinned document/page and removes an incompatible guessed sentence index; it does
not accept invented quotes, other editions or other pages. Original API replies
remain unchanged in the cache.

Editorial review receives the registry's actual waiting/completion policies.
Observation and gesture activities wait for explicit Continue, without creating
an assessed answer. Review schemas enumerate the actual activity IDs so a model
cannot concatenate identifiers to evade a finding's bounded list.

### Lucas's first Portuguese 3rd grade pilot, October 26

Topic 1304 assigns only pages 9–11 of the main student book: the complete fable,
glossary acting game, four comprehension subitems, six til subitems and the
red/blue vowel/consonant notebook task. The API wrote all teaching text in guide
`guide-1304-583eee3d30`; source-validation recovery reused that exact cached plan.
Coverage verifies all seven source blocks and eleven written tasks. The final AI
review approved it, with one nonblocking note about legacy PDF spacing in source
words (for example `A o` and `fi cava`). Clean that source typography before
recording narration; no narration was purchased in this pilot.

Confirmed script/review charges total US$0.306178, including the earlier review
whose malformed IDs were rejected. The first transport timeout remains separately
uncertain at US$0.232; it was not cleared or claimed as a confirmed charge. All
eight snapshotted learner-record tables remained unchanged. Source-page images,
cached plan, reviews, ledger measurements and audit are under
`.tmp-data/lucas-portuguese-first-20261026/` on the development machine.

The follow-up narration uses native Portuguese male narrator Heitor, Inworld
TTS 2. One 4,261-character portal request used approximately US$0.11 of free
credit (US$0.33 remained). The original 277.2-second recording contained one
six-second repeat of two gesture prompts. That duplicate was removed locally;
no extra synthesis was purchased. Track
`fcc8b9dae8b7f491fb5a52d050f234ebc58013f19b7a7ed31f21721883237210`
covers all 69 sentences in 34 activity clips, 270.96 seconds, with no fallback
parts. The imported recording is preferred in the app and Curriculum reports it
ready. Original source/script versions and all learner records are retained.

The host-only workflow can save a whitespace-only source revision before
narration. It retains the API's teaching text/model and original guide, records
the declared corrections, and rechecks coverage using that exact formatting
provenance. It never changes letters, punctuation, task identities or answers.
This is reviewed source correction, not automatic factual editing.

Local acoustic emissions are cached by recording hash, language and model
revision; every use still checks script coverage. Very short cues may be checked
inside their bounded engine activity with an independent confidence floor.
They cannot borrow confidence across a pause or rescue an absent cue. Import
passes every activity boundary to this check. Synthetic tests cover missing
speech, activity cuts, altered audio, broken caches and record preservation.

Automation limit: Inworld synthesis remains a portal/manual-import workflow;
there is no Inworld API adapter or saved project key yet. This pilot also needed
manual duplicate-audio cleanup. Script preparation/review and imported-media
verification are reusable app functionality; do not claim this establishes an
unattended end-to-end narration workflow. Evidence is in
`.tmp-data/lucas-portuguese-voice-20261026/`.

Do not add another lesson queue, source-conversion requirement, bespoke subject
renderer or autonomous repair agent. Keep the existing registry/engine and shared
skills. Review the older PDF-first cleanup ledger before removing companions or
legacy adapters. Retain sources, scripts and recordings referenced by sessions.

### Meaningful turns, October 26 follow-up

Lucas's first three-page Portuguese lesson exposed a distinction between source
inventory and student turns. Its 34 activities included standalone title/attribution
readings and a paragraph split at a page boundary. New preparation joins adjacent,
contiguous checked reading blocks before building activities. It retains all original
block IDs and page references, checks full coverage, and never crosses a teaching or
work activity. Loading an existing guide does not regroup its queue or alter audio.

The planner now receives the family skill and source contract once instead of also
repeating both inside context. It plans coherent readings and concise work turns;
the source inventory is a coverage contract, not a click-per-block instruction.
The shared Portuguese guide lives in `tutor/subjects/portuguese/GUIDE.md`; subject
names such as “Portuguese 3rd grade” now select it. Existing custom subject skills
are not overwritten automatically. Lucas's subject was explicitly saved as v2.

A second-lesson baseline revealed a contradictory review demanding photos for
typed spelling because of the old subject skill. Preparation and editorial review
now share the same capture instructions from `capture_policy.py`, with explicit
precedence over older guidance. Generated discussion still accepts the main idea;
keyed exercises retain their source expectations.

Checked page transcriptions may correct spacing and line-wrap hyphenation only
when all letters, case and other punctuation agree with the original reading.
The manifest retains the original excerpt and typography provenance. No dictionary
guesses, generated wording or silent companion edits are involved. An explicit
true/false stem followed by complete separate statement lines is adapted into
individual source-bound tasks, each with its own identity and binary controls.
Ambiguous or wrapped layouts are not split automatically.

The second Portuguese pilot (topic 1305, pages 12–14) passed AI review without
editorial repair after these changes: four source blocks, 21 original tasks, nine
true/false controls and nine typed spelling items. Its first rewritten plan still
exposed a shared-sentence title/story boundary in the flattened extraction. The
compiler now handles that case too. The host-only `reading-layout` operation
versions an already approved script, verifies the unchanged spoken stream and
source coverage, and records `layout_review` based on the exact earlier review.
It makes no provider request and preserves the original model and guide. Existing
sessions retain their pinned guide; new preparations apply this compiler normally.

Final guide `guide-1305-a148cf6ac0` has two complete reading turns and 29 activities
(mostly the book's own individually assessed work). Writing and AI review of the
revised plan cost US$0.268026; the baseline and its unsuccessful automatic repair
cost US$0.457002, for US$0.725028 total. No audio was purchased. The live reader
shows the lesson ready to start; no student session or attempt was created for it,
and the first lesson remains pinned to its original guide. Evidence and cost rows
are under `.tmp-data/portuguese-flow-review-20261026/` on the development machine.

Official references checked:
- https://developers.openai.com/api/docs/models/gpt-6.1-sol
- https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps
- https://elevenlabs.io/pricing/api
- https://elevenlabs.io/docs/eleven-creative/voices/voice-library

### Source-bound true/false assessment

Compiled main-book questions retain their original quotations on the action,
separately from renderer content. Feedback reads both locations, including after
a follow-up, and preserves qualifiers such as “rapidamente”. `source_key.py`
resolves a private binary key only from the preparation's pinned subject map,
the explicit answer-key target, matching PDF hashes, checked source pages and
the complete annotated statement. Page number or semantic similarity alone never
selects a key. Unmatched, disputed, or reasoning-dependent work keeps the tutor
assessment path. This adapter currently recognizes explicitly marked binary
statement lines; it does not claim to parse arbitrary key layouts.

Verified binary verdicts run without another model request, accepting V/F as
well as full words. The key and its provenance are frozen in the teacher-only
assessment job; they never enter the child activity payload. Existing misgrades
can use the same `recheck_key` command as workbook assignments. It adds an
assessment amendment, preserves the child's original answer and original attempt,
withdraws an untouched review created solely by that error, and restores Continue.
