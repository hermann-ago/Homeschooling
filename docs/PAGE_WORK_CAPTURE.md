# Book answers together

An original exercise split into labeled parts A–F defaults to one work turn when
its checked source quotes have the same literal instruction and consecutive part
labels on the same page. The child sees that instruction once and all its parts,
completes its parts, then submits those answers together. The whole page is
not required. Each part retains a separate result. Distinct exercise instructions and teaching boundaries stop
the group; choices and prose are not guessed into exercise groups. Existing saved
lessons use the same read-only adapter, without rewriting their scripts or audio.
For tasks accepting typed evidence, the default shows one field per part and a
single **Check answers** button (Enter submits; Shift+Enter adds a newline).
Typed answers bypass transcription and confirmation, and preserve exact spelling
and accents. Blank parts remain open. Any required reasoning has its own field;
handwriting, diagrams and written methods retain their existing evidence rules.
Drafts are stored on the current device, scoped to the session and interaction.
The submitted command is saved before transport; each typed response is saved
before one shared assessment request. Retry reuses that request and its frozen
context, including after restart. Photo capture and individual answering remain
available as options.

When two or more adjacent required book questions share an original PDF page,
the current activity offers **Send this page together**. It collects up to five
webcam photos, transcribes the visible answers once, and shows one editable
confirmation list. Unclear answers start unchecked. Missing answers stay open.
The child confirms the selected answers together, then receives separate feedback
for each question. Continuing skips work already checked in that batch.

This uses the existing activity commands, jobs, response records, attempts,
operation receipts, backups and test-mode storage. There is no second lesson
queue. A batch stops at a different page, a teaching/reading turn, or a detour;
it cannot jump required teaching. The limit is twelve adjacent questions.

The photo is stored once and referenced by each confirmed response. Original
transcription, confirmed interpretation, assistance and later learner revisions
remain distinct. Per-item answer keys override model binary verdicts where a
verified source key exists. Private assessment contexts are frozen for recovery;
they are never included in the child-facing page state. Retries reuse the same
provider request identity and cannot create duplicate responses or attempts.

Preparation encourages related paper tasks to stay together. Source preflight
also supports mixed student/teacher pages through explicit public fragments,
without classifying the whole page as student-safe. Validated visual
transcriptions can replace corrupt native text; human-reviewed passages remain
authoritative, and source edition/range identities must match.

Offline verification: `test_page_work.py`, `test_lesson_source_index.py`, existing
engine/API/capture/assessment suites, and the activity component tests. The
disposable `activity_demo.py --practice-sections --port 8765` rehearses a shared
photo with mocked transcription/assessment, without family records or paid calls.
