# Prepare a lesson with Codex

**From 2026-11-05 every script is written by the app's own writer (API).** This
workflow is for *revising* a script the app wrote, when the family asks:

```powershell
backend/venv/Scripts/python.exe backend/tools/lesson_workflow.py revise --learner 1 --topic 383 --out tmp/revise-383
```

`revise` exports the packet plus the lesson's current saved script as
`script.json`. Edit it following `prompt.txt` exactly, then `validate` and
`import` as below: the import is saved marked **Revised**, linked to the
script it changed and to the app's original (`revision_of`). Then judge the
change separately, so the app's own preparation keeps improving. Writing a
script from scratch by hand (`export`) remains possible but is marked
"Written by hand" and hides the app's real quality, so avoid it.


Use the app's source packet, structured compiler and import endpoint. Do not
write directly to guides, learner records or audio tables. Preparation never
creates student answers, completion, mastery or a pretend lesson session.

1. Inspect the child's subjects, completed topics and unfinished sessions through
   the normal APIs. A completed session must agree with topic completion. Verify
   the next topic's full start/stop boundary; do not prepare only the previous
   class's remaining sentences. Keep any genuinely unfinished class available.
2. Export current inputs without paying a lesson-writing API:

   ```powershell
   backend/venv/Scripts/python.exe backend/tools/lesson_workflow.py export --learner 1 --topic 1689 --out tmp/lesson-1689
   ```

   If export answers `exercise_assignment_needed`, the lesson's exercise pages
   are shared with other lessons. Run the app's own assignment first (one small
   AI call per page set), then export again:

   ```powershell
   backend/venv/Scripts/python.exe backend/tools/lesson_workflow.py assign --topic 1689
   ```

3. Read `prompt.txt` — it is exactly what the app's own writer receives, and
   its rules are the rules — inspect `source.pdf`, and write `script.json` to
   `schema.json`. Where NUMBERED PAGE TEXT matches the page, read turns can cite
   `first`/`last` sentence numbers instead of re-typing; transcribe garbled
   stretches (running headers, split words, captions) as `text` with pages.
   When ANSWER KEY PAGES are listed (attached after the student pages), copy
   each book exercise's answers into its teacher-only `answer` / `answer_page`.
   See `docs/LESSON_PIPELINE.md` for the contract.
4. Extra reading books are **read-along**, not workbook assignments. Read printed
   reflection, brainstorming and discussion questions in source order as the
   author's food for thought. Do not omit them, turn them into waiting/graded
   questions or replace them with choice checks. Use read and say turns without
   expecting answers. When the subject's end-of-chapter quiz is on (the prompt
   then says so under READ-ALONG BOOK), finish with that short choice quiz after
   the last reading; otherwise add no quiz. Ordinary curriculum textbooks and
   workbooks retain their required exercises. Answer actual learner questions.
5. Validate, fix any findings, then import through the normal server workflow:

   ```powershell
   backend/venv/Scripts/python.exe backend/tools/lesson_workflow.py validate --packet tmp/lesson-1689/packet.json --script tmp/lesson-1689/script.json
   backend/venv/Scripts/python.exe backend/tools/lesson_workflow.py import --packet tmp/lesson-1689/packet.json --script tmp/lesson-1689/script.json
   ```

   Import checks current source and skill versions, compiles activities, checks
   source coverage, and saves a family/Codex review. It never starts voice.
   Validation also writes `teaching-review.json`, with reading/explanation word
   counts and the number of explanations between readings. For a fuller check,
   copy `saved-guide.json` into an eval folder and run `tools/lesson_eval.py`
   (it flags questions spoken in narration and answers revealed near questions). Review these alongside
   the source: counts are informational, never quotas or a measure of usefulness.
   The compiler rejects answerable activities in read-along scripts, except the
   short choice quiz after the last reading when the subject has it on.
6. Inspect `saved-guide.json`: full class, first introduction, final closing,
   correct source pages, useful explanations/comparisons in the reading flow,
   correct response controls and approved review. Explanations use say turns;
   they are not extra questions and must not be merged into the author's text. Read it
   again through `/api/tutor/reader?learner=1&topic=1689`. Rehearse session launches
   only against a separate test database, never the child's actual records.
7. Only after the script is final, request narration from Lesson & voice. Inspect
   the existing audio and dry-run estimate first. Inworld Flash is the family
   narration default (`inworld-tts-2-flash`); never upgrade the model or switch
   providers automatically. Let the parent audition the free English/Portuguese
   previews before replacing a full recording with a new narrator. Narration
   is billed by characters. Family choices inherit unless a child or lesson has
   an explicit narrator. Both Inworld and ElevenLabs reuse exact saved
   speech with matching voice/model/language/speed and records changed activities
   separately. Do not replace a completed whole recording just to change layout.
   Preserve partial recordings and uncertain purchases; never blindly retry.
   Local dollar estimates are list-price equivalents, not subscription billing.
   Provider credits and plan limits remain authoritative.
8. Verify clip coverage, durations, sentence timings and playback. If credits are
   insufficient, retain script and paid audio; report the actual provider error.
   Do not buy a plan or switch voices/providers without the family's instruction.

When a normal result needs repair, add its regression check to the compiler,
import, completion, source-selection or narration workflow that produced it.
Update this procedure whenever a missing step caused the repair. Do not leave a
one-off corrected lesson as the only fix.

The family repository remains shared. Use Books → Add to [child]'s curriculum to
create that child's separate subject/progress. Removing it pauses membership;
re-adding resumes saved progress. Never assign it to other children automatically.
