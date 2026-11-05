# What still needs an outside helper to prepare lessons

Written 2026-11-04, after preparing Lucas's Math Lesson 19 (topic 1797),
Português Lição 6 (1309) and Jonathan Gullible ch. 7 (1693) through the
Codex/Claude workflow. The goal: once API credits are back, the app should keep
lessons ready by itself. This lists what the app already did on its own, what an
outside helper (Claude) did by hand, and which gaps to patch.

## What the app already does by itself

| Step | How | Today's evidence |
|---|---|---|
| Run the lesson, grade answers, give help | OpenAI `gpt-6-luna` (photos: `gpt-6.1-sol`) | 3 lessons; 30 assessments, 2 hints, 4 transcriptions, about $0.09 in total |
| Check keyed blanks and true/false without AI | `keyed_assessment.py` | Math 18 blanks checked locally |
| Tick the daily task when a topic finishes | `complete_scheduled_history` (commit 85ebe59) | Slots 5331 and 5333 ticked |
| Find book video lessons | `topic_videos`, source `found` | Lessons 18–20 matched to the publisher's Vimeo videos |
| Find answer-key pages | `answer_keys.for_lesson`, locally | Math 4 key page 22 for Lesson 19 |
| Compile, check coverage, keep answers private | `page_script.compile_script` | Both imports passed |
| Record narration with timings | Inworld Flash, family narrators | Lesson 19: $0.088; Lição 6: $0.087 |
| Prepare script and voice in one job | `curriculum_preparation` (`target: both`, caps of $2.00 for the script and $0.75 for audio) | Last tried 2026-11-01: **429 from the provider** |

## What was done outside the app, and whether it needs a patch

1. **Choosing what to prepare next.** I read the database directly to see
   which topics were finished today and which next topics have no guide. The
   app prepares only the topic a parent picks in Prepare lesson.
   **Gap (largest):** no "keep the next lesson ready" step. Proposal: after a
   topic completes (the same finish transaction that ticks the daily task),
   queue a `lesson_preparation_jobs` row for the subject's next unfinished,
   unarchived topic in `chapter_order`, with the subject's normal caps. Skip it
   when a current guide exists, a job is active, or Settings pauses automatic
   preparation. Never start a session. Subjects with two books (Português has
   the *ortografia* book as a reference) follow the subject's main book only.

2. **Writing the script.** I read `prompt.txt`, looked at the PDF pages as
   images and wrote `script.json` by hand. This is exactly the app's own writer
   call (`gpt-6.1-sol`, one request per lesson). **No patch is needed**: the app
   fails only because the provider returns 429 (quota or billing). Once credits are
   added, run one Prepare lesson end to end and confirm the job reaches
   `completed` with audio.

3. **Script review.** Codex imports record a *family* review, which was my own
   reading, instead of the AI `script_review`. With credits the AI review runs on
   its own. On 2026-11-01 it stopped with "review could not finish" (the same
   429).

4. **Quality checks I ran with `tools/lesson_eval.py`.** This is a developer
   tool with hand-written expectations, so it is not part of the app. One of its
   checks catches something the app does not: **a teacher line that asks a
   question but never waits for an answer** (two in Lição 6, which I reworded).
   **Patch:** move that check into `compile_script` (or a review advisory) so
   the API writer's output is held to it too. Answer-leak checks are already in
   the compiler.

5. **Asking for voice.** I ran a dry run first, then recorded. The app's
   preparation job already does both within the audio cap. Nothing to patch.

6. **Test-mode rehearsal in the browser.** This was verification only: the
   welcome autoplayed and the video step showed the Lesson 19 player. Nothing
   to patch.

## Problems found today, with suggested fixes

1. **Wrong answer key attached (fixed in this commit).** Lição 6 of the main
   Portuguese book received page 5 of the *ortografia* book's gabarito
   (M/N, letter X) only because both books have a "Lição 6". An API writer is
   told to copy answers from those pages. `answer_keys.keys_for` now searches only
   keys declared for one of the lesson's own books, plus undeclared keys.

2. **The same question asked five times (Lição 5, today).** My quick check
   "qual animal é o campeão da mudança de cor?" was ambiguous. The text says the
   pitu changes colour *even better than* the chameleon, and calls the solha *a*
   champion. Lucas answered "pitu" each time. The tutor marked it Not yet and
   generated three more versions of the same question. Two fixes:
   - Judgment (prompt or family style): quick checks need one answer that the
     text states plainly.
   - Code: cap generated follow-ups at one per original activity. After the
     second miss, explain and move on. The family style already says "avoid
     repeated rephrasing of the same question". Look at `interactive.py` and
     `activity_requests` in `activity_engine.py`.

3. **Number words rejected (Math 18).** "Hours: ONE / Minutes: FIFTEEN" was
   marked wrong by the local blanks check, which expects digits. The AI accepted
   the same answer later. Patch `keyed_assessment._short_answer` to read
   number words (en and pt, 0–100 at least) as numbers.

4. **Personal answers (Math 18, "What fraction of your family is older than
   10?").** The first verdict was "Source disputed" because the key says
   "Answers may vary". Consider treating a key that says answers vary as
   "accept any well-formed answer", or preparing such items as `parent_check`.

5. **Accents in an exercise about the letter H (Lição 5).** "helicoptero" and
   "historia" were marked Partly correct. The prompt asks for accents in typed
   spelling, so this is consistent with the rules, but it is the family's call
   whether accents should count when the exercise is about something else.

6. **Mila's Math book page returns an error 500.** `GET /api/subjects/10/navigation`
   fails in `navigation.identity` because the Math 1 PDF has no file or
   checksum (the book still needs to be added). Show "book file missing"
   instead of a server error.

7. **Proposed answers waiting for approval.** Lesson 18's and Lesson 19's
   Video Lesson boxes and three Lição 6 exercises have no printed key. Their
   expected answers wait for a grown-up's approval, and until then the AI grades
   them. That works without anyone, but the queue grows. Consider listing them in
   the daily parent summary (idea 5, postponed).

8. **Stale workflow doc (fixed in this commit).** `CODEX_LESSON_WORKFLOW.md`
   said read-along books never get a quiz. It is a per-subject option
   (`book_questions.end_quiz`), and Jonathan Gullible has it on.
