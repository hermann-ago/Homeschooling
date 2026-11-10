# Reusable tutoring activities

The guided lesson now runs through the shared activity engine. The book stays beside the tutor. Only the current activity and reached history are sent in the activity state; completed threads retain original answers, help, follow-ups, capture amendments and feedback. Feedback waits for an explicit **Continue lesson**.

## Contracts and implementation

`backend/tutoring/activities.py` owns version 1 Pydantic contracts. The planner and conversational tutor use these same contracts. `backend/tutoring/activity_engine.py` executes them over existing `lesson_actions` and `lesson_playback` records. React renderers are allowlisted in `frontend/src/components/activities/registry.js`; models cannot supply executable components, HTML or styling.

The 23 activities are:

| Activity | Behavior |
|---|---|
| `review_progress` | Reads relevant progress; creates no learner evidence. |
| `prepare_lesson` | Retrieves the running lesson's pinned preparation. New preparation uses the existing preparation UI/API and the same activity schemas. |
| `introduce` | Green introduction using the explicit Figtree style token; Continue acknowledges it. |
| `read_source` | Reads exact, assigned source sentences; saves the narration cursor. |
| `explain_or_observe` | Shows an explanation and returns to its originating activity. |
| `ask_question` | Waits for an actual submitted response. |
| `request_book_work` | Preserves assigned exercise/version; finishing writing opens capture. |
| `capture_and_confirm` | Captures an answer, with confirmation before assessment. |
| `hint_or_follow_up` | Saves assistance or opens a separately identified follow-up. |
| `give_feedback` | Shows feedback; an assessed outcome must reference observed assessment. |
| `record_learning_evidence` | Retrieves saved evidence linked to an actual submission. |
| `close_lesson` | Explicit Finish; reading reached and unresolved work remain separate from understanding. |
| `worked_example` | Reveals stages, then optional practice with its support level preserved. |
| `explain_thinking` | Captures actual reasoning. |
| `check_prerequisite` | Captures a diagnostic response about a named prerequisite. |
| `visual_demonstration` | Renders a checked book illustration, number line, timeline or diagram. |
| `take_break_and_return` | Saves the pending stage/draft/cursor and returns there. |
| `tell_it_back` | Captures the learner's own retelling. |
| `compare_and_connect` | Displays two items and captures their relationship. |
| `predict_then_check` | Saves prediction/reason before reveal; reflection has its own interaction. |
| `find_and_fix_mistake` | Labels a deliberately incorrect example and captures correction/reasoning. |
| `apply_somewhere_new` | Captures transfer in a new situation. |
| `recall_later` | Captures unsupported retrieval before showing support. |

History preserves assigned reading order. Math can interleave eligible exercises at checked prerequisite passage boundaries. Unmatched boundaries leave exercises after the reading. Required exercises retain their assignment snapshot even if the catalog changes. The editable Math teaching guide is `tutor/subjects/math/GUIDE.md`; existing customized subject skills are preserved.

## Capture, assessment and recovery

Typed drafts are kept in browser storage and saved to the server with their own revision. Draft conflicts preserve the local copy. Submission/operation identities are persisted before transport; recover a saved action after an ambiguous connection failure. Durable event uniqueness survives HTTP replay-cache expiry.

Device dictation uses the device's keyboard dictation (for example Windows+H), not app-managed recording. Select **Use device dictation**, dictate into the answer field, submit, then correct/confirm the transcript. Original capture and confirmed interpretation remain separate. A photo without a supplied interpretation is transcribed first through a separate saved job; assessment waits for confirmation. Missing written evidence or disputed/unreadable work goes to explicit parent review, not an automatic knowledge gap.

Spelling, handwriting, diagrams and written methods require photo evidence or parent inspection. Parent review records what was checked and whether independence or assistance was actually observed. A correct parent result alone does not assert independent understanding. On-screen choices require reasoning when the activity explicitly requests it. A simple recognition choice can be submitted alone, without inferring independently explained mastery.

Assessment inputs, provider selection and request identity are frozen. Provider work runs outside database transactions and global lesson locks. Failed or uncertain requests preserve the response and spending reservation; retries reuse the saved job. Original attempts are retained. Assistance is snapshotted when each response is captured, so later help does not rewrite an earlier answer's independence.

One narration controller coordinates reading, prompts and feedback. Explicit breaks/help save the pending activity and cursor. Recordings resume at the saved offset. Device speech may replay the unfinished sentence. Abrupt browser/device failure can lose the last uncheckpointed audio fragment; committed work is preserved. Listening-only replay does not answer or complete activities.

Schema version 2 adds interactions, responses, drafts, ordered events and durable jobs. Ordinary store backups and isolated test-mode stores include these tables. Job/context material is teacher-only and excluded from general exports. Legacy guides are adapted without regenerating recordings or changing historical answers. Semantic activity normalization happens once per pinned session; raw database column addition alone does not declare legacy work understood.

Preparation accepts `request_book_work` for tasks on the assigned main-book worksheet when its instruction quotation matches both the assigned passage and the specified original PDF page. The server verifies the document checksum, page boundaries and public-source access, and supplies the displayed book/page locator. The model cannot create catalog exercise IDs, assignment IDs or versions. Separate catalog exercises continue through server selection. A source-verified worksheet task retains physical-work declaration, capture and appropriate evidence requirements; it is not silently converted to a generic question. Exact-input cached AI responses can be revalidated after a downstream validation fix without buying another script, and preparation estimates identify that reuse.

## API and desktop clients

The planner receives the registry schemas and emits a structured plan containing
registered activity commands. Preparation validates those commands and the engine
executes them when the child reaches each step. This uses structured output;
it is not a provider function-calling loop that displays every activity while
preparing the script. Live tutoring may request a bounded activity through
`activity_requests`; desktop MCP calls use the same canonical executor. Internal
progress/context collection and evidence persistence remain server-controlled.

All paths below use `/api/tutor`:

| Method/path | Purpose |
|---|---|
| `GET /activity-definitions` | Canonical schemas, renderer keys and policies. |
| `GET /sessions/{id}/activity-state?after={cursor}` | Authoritative state and new event identities. |
| `POST /sessions/{id}/activities` | Invoke a validated activity. |
| `POST /sessions/{id}/activity-events` | Family-device draft, response, confirmation, review and transition commands. |
| `GET /sessions/{id}/activity-events?after={cursor}` | Ordered events for continuation. |
| `POST /sessions/{id}/repeat` | Start or recover one fresh attempt from a completed session, keeping its saved guide and original evidence. |
| `POST /sessions/{id}/activity-access` | Family-only desktop tutor grant for this session. |

Invocation uses `operation_id`, `expected_revision`, `kind`, `content`, and optional `parent_activity_id`/`origin`. Events use the same operation/revision plus `activity_id`, `interaction_id`, `type` and `payload`. Successful mutations return the state and an `activity_result` handle with activity/interaction IDs, status, revision, event cursor and committed receipt. Displaying a question returns `awaiting_input`, never a fabricated answer.

Existing playback, answer, continue, skip and finish routes delegate to the engine for native activity sessions. Legacy sessions retain compatibility; legacy record/finish endpoints cannot bypass a native session's pending work.

The MCP bridge exposes all 23 names using schemas retrieved from the server. A family device must enable **Lesson options → Allow desktop tutor for this lesson**. Display calls return immediately; clients subsequently call `get_activity_result` with session/cursor to retrieve actual saved child responses. They must stop and wait while input is pending. MCP cannot submit a child's answer or perform parent confirmation/review. See [MCP.md](MCP.md).

## Verification and local rehearsal

Backend tests use temporary SQLite databases, generated book fixtures and invented learner responses. Model/planner/transcription requests are mocked. Frontend tests cover drafts, ambiguous submissions, confirmation, hidden content, explicit continuation, narration and recovery.

For a disposable offline browser rehearsal on Windows:

```powershell
cd backend
.\venv\Scripts\python.exe -m dev.activity_demo --port 8766
```

Open the synthetic lesson URL printed by the command. The rehearsal serves the built frontend, creates temporary records outside family storage, and refuses unmocked AI generation. Stop it when finished. Normal exit removes its temporary records; forcibly ending the process may leave the printed temporary folder for later cleanup. Build the frontend first after UI changes.

Real-device keyboard dictation, speakers, recording seek behavior and the family's selected Math exercise mappings still require supervised device/book checks. Synthetic tests do not establish those device-specific or content-specific facts. App-managed microphone/STT and unrestricted generated visuals remain deferred.

## Shared lesson screen and repeated lessons

All lesson options remain in the shared student interface. Recorded-voice preparation is expandable below the current activity. Typed answers use one **Check my answer** command (`submit_response` with `assess_after_save: true`): the response commits before assessment starts, and recovery retains both operation and response identity. This flag cannot bypass transcript/photo confirmation or prediction reveal.

Current questions keep their answer area and latest feedback together. Prior exchanges collapse beneath them; **Show full lesson thread** expands reached steps, original prompts, follow-ups, learner responses, hints and feedback. Upcoming content remains excluded. Records and learning notes link to the original session. Status labels are presentation only and never rewrite learner evidence.

Draft indicators distinguish this device from an acknowledged home-server draft. Unconfirmed transcript edits remain labeled as device drafts until confirmation.

**Repeat this lesson** uses the saved guide and creates a separate session, or resumes an existing open attempt of that chapter. Its durable operation is recorded against the original session, so retries after restart recover the same session. Unfinished lessons in other chapters do not block starting or repeating the selected chapter. Original sessions, answers, assessments and recordings remain intact. **Prepare a new version** opens the existing preparation flow, with its normal estimate before any paid generation. Repeat itself makes no AI request.

The curriculum check mark, explicit topic completion and checklist completion record `completion_source=manual` plus a timestamp and durable `topic_completion_events` history. They close that chapter's open sessions and checkpoints without changing actual actions, drafts, captures, assessments or understanding. Records also include manual completions with no tutoring session. Unchecking restores the chapter to incomplete without reopening or erasing historical sessions. Startup reconciliation closes legacy open sessions on already-completed topics, preserving unknown historical provenance as `topic_completion` and keeping intentional repeats open. Choosing another chapter does not import unrelated unfinished actions or assignments as mandatory opening work.


## Recap, position and support choices

The activity state now includes an observed `learning_summary` at the recap and after completion: reading reached, saved/checked answers, where help was recorded, and unresolved work. It also includes `attempt_navigation`, with original/repeat links, an unfinished repeat to resume, and the next assigned lesson. These projections do not rewrite immutable attempts or claim mastery. Normal lesson position labels show kinds and numbers, never future prompts. Help detours retain their originating root position.

A family-device `revisit_activity` event from the recap can reactivate a skipped response task in the same session. It creates a fresh interaction, preserves previous captures, and returns to the closing step after that work. Completed sessions remain closed; continuing their unfinished work starts or resumes a separate attempt through the existing repeat flow.

`request_hint` accepts `payload.kind` as `hint`, `explain`, or `example`. Explanation and example prompts have separate teaching instructions, and examples must use different details rather than solve the learner's task. Delivered support is recorded beneath the originating activity before later answers freeze their assistance snapshot. Reading support checkpoints the narration cursor. Failed support retains a canonical request in `pending_support_commands`; recovery reuses the original operation, and deferral permits progress without inventing an answer or buying the same request again. Activity-event requests bypass the short-lived HTTP response cache because the engine already supplies durable identity checks and needs to recover current job state.
# Step replay and starting over

The family-only activity events `go_back` and `restart_lesson` use the same expected-revision and durable operation receipts as responses. The lesson options menu exposes both; back is disabled at the first step. Each back press selects the preceding main step (or the parent of a help detour). Completed/skipped targets reopen with a fresh interaction, the original prompt/stage and a new narration cursor identity. Still-pending work retains its interaction, drafts and parked audio offset when returning forward. A break may be left explicitly through either navigation command.

Starting over replays the saved plan from its beginning, without regenerating the guide or recordings. Previously reached future steps are reinitialized lazily as they are reached again. Superseded adaptive detours stay in history but no longer block completion. Immutable attempts, responses, transcripts, confirmations, assistance and dialogue are retained; earlier assistance is still included in later response support snapshots. Replay metadata (`is_replay`, optional `replay_of`, dialogue sequence boundary) distinguishes new input/feedback from earlier exchanges and permits reuse of an exactly matching planned recording. Audio offsets and response drafts belong to interaction identities, so a fresh replay does not inherit the prior attempt's final audio position or unsubmitted photo selection.

For an already finished lesson, the menu requests a new repeat with `from_beginning: true`; normal completion-screen repeats keep their existing unfinished-work behavior. Creating and initializing this repeat is recoverable/idempotent across retries. Original completion and evidence remain unchanged. Nullable navigation/replay metadata extends the existing playback/interactions tables; older rows require no reinterpretation or semantic backfill, and normal backup/Test Mode handling includes these fields.

## Answer controls selected by the planner

Question content supports `answer_format`: `text`, `true_false`, `single_choice`, or `multiple_select`.
Choice tasks use `response_modes: ["choice", "text"]` and public `choices: [{id,label}]`.
True/false uses IDs `true` and `false`, with labels in the lesson's language. Legacy choice lists
normalize to single choice. The UI opens choice controls first, without submitting on selection;
Enter submits, and an optional explanation is saved separately as reasoning. `require_reasoning`
requires that explanation. Written-work evidence requirements still apply.

Source inventories and portable book companions retain the same public format/options. New script
preparation copies checked book options over generated alternatives and preserves exercise identity,
source order and version. A book's several independently answerable statements need separate activities.
Legacy catalog entries can use explicit true/false directions, or a clear A..L option list with a
choice instruction; wrapped/ambiguous lists and grouped binary statements retain text capture.
The model selects registered controls, never executable UI or correct-answer flags. Existing pinned
lessons and records are not rewritten. Newly prepared scripts can use the new formats.

The executor validates choice ownership, uniqueness and cardinality, stores labels as the assessment
text and IDs as original capture, and saves multiple selections in source order. A plain follow-up
with a different prompt uses text capture rather than inheriting stale choices. Choosing an option
alone retains the existing recognition-only independence policy. Narration, confirmation, durable
drafts and idempotent submission use the same paths as typed answers.

Offline browser rehearsal: `python -m dev.activity_demo --port 8779 --answer-controls` from `backend`.
It uses invented records, mock feedback and temporary storage, with no paid provider requests.

Generated discussion feedback uses `tutoring/assessment_policy.py`, shared by the
assessor prompt and engine progression. Adaptive retellings and conversational
questions accept the main idea, briefly fill minor omissions and allow Continue.
Core misconceptions still merit a focused follow-up. Required-book work, assigned
exercises, written evidence and adaptive detours rooted in required work retain
source-bound assessment. Neither the learner nor a model chooses this policy.

An assessed Correct/Partly correct generated discussion can offer Continue even
when an older tutor reply requested another detail. The unanswered follow-up is
deferred, not recorded as a learner answer. The original response, assessment,
assistance and any existing review stay intact; continuing does not claim mastery.
Frozen earlier assessment requests remain frozen and are never repurchased merely
because this feedback policy changes.

Capture requirements are also source-bound (`tutoring/capture_policy.py`). A
checked comprehension blank explicitly requesting words from the passage, or a
checked choice task, can correct an older generated `handwriting` gate to
`answer`. The original task, book, script and recording remain unchanged. This
does not relax copying/marking/method requirements, uncertain
source pages or versioned assignment evidence policies. Preparation applies the
same correction before saving new scripts, and runtime derives it for old ones.

Photo capture requires an actual image. Confirming a transcript can request
assessment in the same durable command; prediction remains gated by its reveal.
Legacy empty-photo captures stranded at parent review can be checked as words
only when the source-bound evidence target is answer, the transcript is already
confirmed and no assessment exists. Their original capture record is retained.

Computer spelling and accent tasks accept typed words, with photos optional.
Checked accent-placement instructions can correct an old generated handwriting
gate to spelling, including the saved written-steps capture used by an earlier
UI. Exact letters and diacritics remain the assessment target; device dictation
does not establish spelling. These tasks open their typed response immediately,
without a compulsory physical-book completion click. Actual handwriting, visual
marking and written calculations retain their own evidence requirements.

### Reusable practice and feedback, October 27

`exercise_sections.sections` projects consecutive required spelling, true/false
and choice items from their exact source document/page and format. A practice
section is presentation metadata, not another queue. Every activity, interaction,
response, assessment and recording keeps its original identity. Help children do
not split the originating section. Future payloads disclose section counts and
allowlisted labels, never future prompts or keys. The header counts a section
once; the composer shows its current item and saved count. Enter submits an answer,
then the focused Next item/Next word control acknowledges feedback. It does not
automatically accept incorrect work or invent responses.

Question content optionally carries `matching: {items, options, allow_reuse}`.
Both columns use bounded public `{id,label}` values; there is no solution field.
Required-task labels are checked against the original task. The form saves partial
`matches` in the existing interaction draft. Submission validates all IDs and reuse,
then saves the actual mapping and canonical pair text in the original response.
Matching with an answer target opens directly; actual handwriting/diagram tasks
retain their evidence requirements. Existing scripts and audio are not rewritten.

`assessment_policy.PREPARATION_INSTRUCTIONS` supplies the shared expectations to
preparation, editorial review and assessment. Generated discussion accepts the
main idea; keyed work keeps its source requirements. Feedback normally uses one
or two useful sentences. Subject skills provide teaching priorities and cannot
override engine capture/completion rules.

The active teacher reply and saved history support recorded feedback. New replies
can prepare speech in the background, following the selected lesson recording's
provider, voice and speed, with a per-reply cap and normal monthly allowance.
Refresh/back navigation does not automatically purchase historical speech. The
header menu's Speak new teacher replies setting controls autoplay; history is
on demand. Leaving an activity cancels playback and suppresses late autoplay,
while an already-sent purchase retains its cached outcome. Imported Inworld
narrators remain text-only for new replies until an API adapter exists.

Google feedback uses the exact-text recording cache without full lesson acoustic
alignment. A real 35-character Portuguese reply took 7.735 seconds and cost
US$0.000679; its recording is saved for replay. This path currently waits for the
short recording, not provider-level PCM streaming. Text and navigation never wait
for speech. The latency measurement does not establish instantaneous delivery or
universal provider reliability. Audit: `.tmp-data/permanent-interactions-20261027/`.

Curriculum preparation also accepts an optional `audio_provider: google-gemini`.
The dialog exposes that choice without changing family settings. Jobs retain it,
including during restart recovery and progress reporting; omitted/configured
selection preserves older request fingerprints. The nullable job column uses the
normal storage upgrade and remains in ordinary backups and test-mode isolation.

## Book work done in the book (paced subjects)

A subject's `book_work` setting (Curriculum → subject → **Book exercises**) is
`tutor` (default: the child sends answers and the tutor checks them) or `paced`.
The mode is frozen into `lesson_playback.navigation_state.book_work` when a
lesson's activities first start; saved guides, running lessons and earlier
records are unchanged, and the same prepared lesson and voice work in either mode.

In a paced lesson the tutor reads each exercise and the child presses **Done in
my book** (`done_in_book`). The exercise, and the rest of its practice section
(same page and format, for example all statements of a true/false exercise),
become `in_book`: finished, not graded, never "to revisit", and never passed to a
later lesson as pending work. No answer box, skip, hints for answers or page
photos are offered for that step.

At the closing step a grown-up can photograph the pages (`submit_book_check`,
up to 8 photos attached to the closing step). `book_check.py` makes one AI
request that reads the child's answers against the private keys and marks each
`looks_right`, `check_again`, `not_found` or `unclear`, with a short note that
does not give the answer. It is a note for the family: it creates no attempts or
assessed responses. A failed check keeps its photos (`retry_book_check`). The
completion summary records `book_work: {mode, in_book, check}`.

Rehearse offline with `backend/dev/activity_demo.py --practice-sections --paced-book-work`.

## Book work answered with a photo (the default)

In a subject whose book exercises are checked by the tutor, a required book
exercise shows one main button, **Photo of my work** (`active_activity.snap`).
The camera opens in the card, Space takes the picture and it is sent after a
moment (`snap_work`, 1–3 photos attached to that exercise). The exercise, and
the still-pending rest of its practice section, become `checking` and the
lesson moves on at once. **Answer here instead** keeps the typed/choice flow.

`photo_check.py` runs one AI request per photo on a background thread (inline
when `engine.background_checks` is false, as in tests): it copies the child's
answer and assesses it against the private key. Results are saved through the
ordinary path (`activity_responses`, `lesson_dialogue`, `interactive._apply`,
attempts and reviews), so progress and learning records are real. A right answer
is `answered`; anything else is `fix`. An unsure reading is `Unreadable`, never
wrong; a reviewed true/false key decides a clear reading. A result that arrives
after the child went back to the exercise, restarted or finished is kept on the
job and not applied. Waiting checks restart from `state()` after a server restart;
a failed one keeps its photo (`retry_photo_check`).

`progress.items[].outcome` adds `checking`, `fix` and `unchecked`, each with a
`check` (prompt, what was read, feedback). The tracker chips open it; **Fix it
now** (`fix_work`) reopens that exercise with a return cursor, and a new photo, an
on-screen answer or **Back to the lesson** (`fix_later`) returns to the step the
child was on. Finish waits for running checks. Anything still `fix` at the end is
recorded as "to practise" (`completion_summary.photo_checks`) and is not carried
into later lessons as pending work.

Rehearse offline with `backend/dev/activity_demo.py --practice-sections` (the
`photo-demo` launch configuration): the mocked check takes five seconds and
returns one answer to fix.
