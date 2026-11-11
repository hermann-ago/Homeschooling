# Live tutor plan

Status: **not started**. Created 2026-11-11.

The working reference for making the tutor feel like a person teaching this
child, without giving up what the prepared lesson guarantees. Each step is a
self-contained slice: it can be built, tested, tried in one real lesson and
committed on its own. Update the checklist and the progress log after each step.

## Goal

The family's words: "a more free and really good and not robotic AI tutor … it
should feel almost like human tutoring."

Today the warm, spoken part of a lesson is written weeks ahead and cannot react,
and the part that reacts to the child is a silent grader. This plan moves the
words about *this child, right now* to the live tutor, and keeps ahead of time
only what comes from the book.

| Prepared ahead (same for any child) | Said live (depends on this child, now) |
|---|---|
| The book's reading text, recorded narrator | The welcome, linked to last time |
| Each exercise: page, wording, how to answer | The bridge between steps |
| The answer key (private) | Reactions to answers, hints, encouragement |
| Where the book's video plays | The closing, about how the lesson really went |
| Teaching notes for the tutor: key idea, a good example, the usual mistake | |

## Guiding principle

**Hard rules in code, judgment in the prompt** (AGENTS.md) — and now also:
**facts ahead, conversation live.**

Rules the code keeps, whatever the live tutor says:

1. Every assigned reading and exercise is covered; the live tutor cannot skip
   or reorder required book steps.
2. The book's words are read exactly, from the prepared text.
3. A private key answer never reaches the child: every live line is checked
   against the step's key before it is shown or spoken.
4. A lesson still runs when the AI is unreachable, out of credit or slow: a
   prepared line plays instead.
5. Live calls have a spending cap per lesson.
6. What the child types or photographs is evidence, never instructions.

Everything else — wording, warmth, examples, how much to say — is the tutor's
judgment, guided by the family style, the subject notes and what it knows
about the child.

## Current state (2026-11-11)

**Ahead of the lesson** (`tutoring/lesson_prompt.py`, `page_script.py`,
`script_review.py`): one high-reasoning call writes the whole script, every
tutor sentence included; a second call reviews it; the narrator is recorded.

**During the lesson** (`tutoring/interactive.py`, `activity_engine.py`): one
call per answer or typed question. It already receives the family style, the
subject notes, the learning memory, the step's last 16 messages and the private
key (`InteractiveTutor._prompt`), and returns a grading form
(`Assessment`: feedback, result, help, follow_up, …).

Why it feels robotic — verified in the code:

| # | Finding | Where |
|---|---|---|
| F1 | The live AI's standing instructions make it an examiner: "assessing observed student work … Return only the assessment schema" | `interactive.py: SERVER_TUTOR_RULES` |
| F2 | Live replies are silent with the current narrator. The server can voice them with Inworld; the screen only allows three other providers and prints "This reply is text-only with the selected narrator." | `RegistryGuidedLesson.jsx: renderFeedback`; `routers/tutor.py: feedback_audio` already accepts `inworld` |
| F3 | Every bridge, welcome and closing is written before the lesson, so none can mention what the child just did; the closing is told not to say how the child did | `lesson_prompt.py: HOW_TO_TEACH` |
| F4 | The live call only sees the current step's conversation, not the lesson so far (what was read, how earlier exercises went) | `interactive.py: _prompt` (`history`) |
| F5 | The app does not record how long AI calls take, so the wait a child would feel is unknown | `data/ai-usage.sqlite3: requests` has no duration |

Costs since 1 Nov 2026, from the usage log (typical, per item):

| Part | When | Cost |
|---|---|---|
| Writing a script (`AssignedScript`, gpt-6.1-sol) | ahead | $0.12 |
| Reviewing it (`Review`) | ahead | $0.07 |
| Narration (about 30 parts) | ahead, once | $0.17 |
| Checking a typed answer (`BookReadingAssessment`, gpt-6-luna) | live | $0.003 |
| Checking a photo (`PhotoCheckReplyExact`) | live | $0.03 |
| One spoken narration part (Inworld flash) | either | $0.005 |

Money does not decide this; waiting time and trust do.

## Steps

Each step ends with: tests green, one real lesson tried with a child, the
measurements below written into the progress log, commit and push.

- [ ] **Step 0 — Measure first.**
  Record how long every AI and voice call takes (add a duration to the usage
  record). Save one full real lesson as the "before" reference: every line the
  tutor said, live or prepared, with the child's answers. Choose the pilot:
  one Math lesson with Lucas and one Português lesson with Mila.
  *Done when* a lesson's live waits can be listed in seconds.

- [ ] **Step 1 — The live tutor speaks.**
  Let the screen voice live replies with the lesson's own narrator (F2), played
  automatically like prepared lines, and never talking over the recorded voice
  or the video. Check the cap and the cost per reply.
  *Done when* a reply to a wrong answer is heard in the narrator's voice, and
  the wait from sending the answer to the first spoken word is measured.

- [ ] **Step 2 — A tutor, not an examiner.**
  Separate what the child hears from the grading record. The live call gets a
  tutor's role (F1) and the lesson so far (F4): what was read, how earlier
  steps went, what comes next. It returns a short spoken reply plus the private
  grading fields. Add the code check that no reply reveals the step's key
  (reuse `page_script.reveals_answer`'s comparison) and a length limit.
  Extend `backend/tools/lesson_eval.py` to replay saved answers through the old
  and the new instructions and print both replies side by side.
  *Done when* the side-by-side on the "before" lesson reads clearly warmer and
  more specific, with no key revealed and no grade changed.

- [ ] **Step 3 — Live bridges, with the prepared line as a safety net.**
  After an exercise, the tutor says one or two sentences about what just
  happened before the prepared explanation plays. If the live line is not ready
  within the agreed wait, or the AI is unreachable, the lesson simply goes on
  with the prepared line (rule 4).
  *Done when* a lesson with the network unplugged plays exactly as today, and a
  normal lesson has a live sentence after each exercise.

- [ ] **Step 4 — Thin the script.**
  New writer contract: a `say` turn becomes teaching notes for the tutor (the
  key idea, a good example, the usual mistake) plus one short prepared line
  used only as the safety net. The reviewer checks the notes. Decide from
  Step 3's numbers whether safety-net lines are recorded ahead or spoken on
  demand. Old scripts keep working unchanged.
  *Done when* a lesson prepared the new way is taught live from its notes, and
  the parent rates it at least as clear as the scripted one.

- [ ] **Step 5 — Let it adapt.**
  The tutor may offer bounded choices on its own explanations only: shorten a
  review the child has clearly understood, or add one more example. It can
  never skip a reading or an exercise (rule 1).
  *Done when* a child who gets the first problems right is offered the shorter
  path, and a child who struggles gets the extra example.

- [ ] **Step 6 — An honest closing, remembered next time.**
  The closing is written from the lesson's real results, and a short note is
  saved so the next lesson's welcome can pick it up ("last time the zeros gave
  you trouble; today…").
  *Done when* two lessons in a row show the link.

## What we measure at every step

| Measure | How | Aim |
|---|---|---|
| Wait before the tutor's first live word | Step 0's timing | to agree after Step 1; a starting guess is under 3 seconds |
| Share of live lines that fell back to the prepared line | engine log | low, and never a stuck lesson |
| Cost of one lesson run (AI + voice) | usage log | stays near today's, cap respected |
| Key answers revealed | code check, counted | zero |
| First-try results on exercises | attempts | not worse than before |
| Parent's rating of the lesson, and the child's | asked after the pilot lesson | better than before |

## Risks and open questions

- **Waiting.** The largest unknown (F5). If a live line cannot be fast enough
  with a good model, Step 3 stays as "a short reaction" and Step 4 keeps more
  prepared text. Step 0 and 1 answer this before anything bigger changes.
- **Review cannot see live words ahead.** Every live line is saved, so Script
  review can show "what the tutor said" after the lesson.
- **Voice paid per run.** Live lines are spoken each time a lesson is run,
  about half a cent each; repeated lessons pay again.
- **Which model speaks.** Checks use the fast model today. Bridges may need the
  stronger one; compare both in Step 2's side-by-side.
- **Young children.** The outside studies behind this direction involved
  teenagers and adults; our own pilot lessons are the evidence that counts.

Decisions for the family before Step 1: the longest acceptable wait, the two
pilot lessons, and the spending cap for live calls in one lesson.

## Working rules

- One step at a time; commit and push after each; ask before each paid run.
- Lesson scripts still come from the app's own writer.
- Running sessions, learner records and saved guides are not rewritten; new
  contracts apply to new preparations.
- Rehearse in the app's test mode, switched on from Settings.

## Progress log

- 2026-11-11 — Plan written after the research discussion. Nothing built yet.
