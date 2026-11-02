# Prepare a lesson with Codex

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

3. Read `prompt.txt`, inspect the original `source.pdf` pages, and write
   `script.json` using `schema.json`. Follow the supplied skill, source ownership,
   page map, source coverage and content responsibility policy. Storybook pages
   attached to a class must include their complete final paragraphs. Never add
   unsolicited content warnings or reminders to disagree with the author.
   Identify the passage's purpose and central meaning in context before adding
   explanations: an argument, theme, concept or story's significance, as appropriate
   to its genre. Explain useful relationships and reasoning rather than incidental
   plot trivia. Use relevant examples and comparisons. Pacing follows understanding,
   with no target number of pauses, fixed spacing or explanation word minimum.
   Preserve a scene, poem or argument's continuity when appropriate.
4. Extra reading books are **read-along**, not workbook assignments. Read printed
   reflection, brainstorming and discussion questions in source order as the
   author's food for thought. Do not omit them, turn them into waiting/graded
   questions, replace them with choice checks or add an automatic quiz. Use read
   and say turns without expecting answers. Ordinary curriculum textbooks and
   workbooks retain their required exercises. Answer actual learner questions.
5. Validate, fix any findings, then import through the normal server workflow:

   ```powershell
   backend/venv/Scripts/python.exe backend/tools/lesson_workflow.py validate --packet tmp/lesson-1689/packet.json --script tmp/lesson-1689/script.json
   backend/venv/Scripts/python.exe backend/tools/lesson_workflow.py import --packet tmp/lesson-1689/packet.json --script tmp/lesson-1689/script.json
   ```

   Import checks current source and skill versions, compiles activities, checks
   source coverage, and saves a family/Codex review. It never starts voice.
   Validation also writes `teaching-review.json`, with reading/explanation word
   counts and the number of explanations between readings. Review these alongside
   the source: counts are informational, never quotas or a measure of usefulness.
   The compiler rejects answerable activities in new read-along book scripts.
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
