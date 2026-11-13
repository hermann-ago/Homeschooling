# Live tutor plan

Status: **Steps 0–3, 4a and 6 done (2026-11-12)**. Postponed by the family: streaming (2c), live explanations (4b). Dropped: Step 5. Created 2026-11-11.

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
| F5 | The app did not record how long AI calls take (fixed in Step 0) | `services/ai_budget.py` |
| F6 | When the app checks an answer itself against the key, the child gets a fixed line: "Correct!", "0 of 1 right. Take another look at: …" — 39 of 136 replies in November | `keyed_assessment.py` |
| F7 | A reply the AI writes takes a median of 8 seconds to appear; 3 of 97 arrived within 3 seconds | measured in Step 0, below |

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

- [x] **Step 0 — Measure first.** (done 2026-11-11, results in the progress log)
  Record how long every AI and voice call takes (add a duration to the usage
  record). Save one full real lesson as the "before" reference: every line the
  tutor said, live or prepared, with the child's answers. Choose the pilot:
  one Math lesson with Lucas and one Português lesson with Mila.
  *Done when* a lesson's live waits can be listed in seconds.

- [x] **Step 1 — The live tutor speaks.** (done 2026-11-11)
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

- [x] **Step 3 — Live bridges, with the prepared line as a safety net.** (done 2026-11-12, built
  differently than first written: see the progress log)
  After an exercise, the tutor says one or two sentences about what just
  happened before the prepared explanation plays. If the live line is not ready
  within the agreed wait, or the AI is unreachable, the lesson simply goes on
  with the prepared line (rule 4).
  *Done when* a lesson with the network unplugged plays exactly as today, and a
  normal lesson has a live sentence after each exercise.

- [~] **Step 4 — Thin the script.** 4a done 2026-11-12 (notes written ahead, used by the live
  replies); 4b (live explanations) waits for a decision — see the progress log.
  New writer contract: a `say` turn becomes teaching notes for the tutor (the
  key idea, a good example, the usual mistake) plus one short prepared line
  used only as the safety net. The reviewer checks the notes. Decide from
  Step 3's numbers whether safety-net lines are recorded ahead or spoken on
  demand. Old scripts keep working unchanged.
  *Done when* a lesson prepared the new way is taught live from its notes, and
  the parent rates it at least as clear as the scripted one.

- [-] **Step 5 — Let it adapt.** (dropped 2026-11-12: the family does not expect it to be useful)
  The tutor may offer bounded choices on its own explanations only: shorten a
  review the child has clearly understood, or add one more example. It can
  never skip a reading or an exercise (rule 1).
  *Done when* a child who gets the first problems right is offered the shorter
  path, and a child who struggles gets the extra example.

- [x] **Step 6 — An honest closing, remembered next time.** (done 2026-11-12)
  The closing is written from the lesson's real results, and a short note is
  saved so the next lesson's welcome can pick it up ("last time the zeros gave
  you trouble; today…").
  *Done when* two lessons in a row show the link.

## What we measure at every step

| Measure | How | Aim |
|---|---|---|
| Wait before the tutor's first live word | `tools/live_tutor.py replies` and `waits` | under 3 seconds (agreed 2026-11-11; faster is better) |
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

Decided with the family on 2026-11-11: the tutor should start talking within
3 seconds (faster is better); the pilots are a Math lesson with Lucas and a
Português lesson with Mila; no spending cap is needed for live calls, since
the amounts are too small to matter (rule 5 stays as tracking only).

## Working rules

- One step at a time; commit and push after each; ask before each paid run.
- Lesson scripts still come from the app's own writer.
- Running sessions, learner records and saved guides are not rewritten; new
  contracts apply to new preparations.
- Rehearse in the app's test mode, switched on from Settings.

## Progress log

- 2026-11-11 — Plan written after the research discussion.
- 2026-11-11 — **Step 0 done.**
  - Every AI and voice call now records its duration (`requests.seconds` in
    the usage ledger). `backend/tools/live_tutor.py` reports them (`waits`),
    reports the wait a child felt in past lessons (`replies`) and saves a
    lesson as taught (`transcript`).
  - "Before" references saved under `tmp/live-tutor/` (learner records, not in
    git): Lucas, Math Lesson 19 (`2026-11-06-c1-01`: 29 prepared lines, 25 live)
    and Mila, Letra K (`2026-11-11-c2-02`: 22 prepared, 3 live).
  - Past lessons since 1 Nov: 136 live replies. 39 were checked by the app at
    once and got a fixed line (F6). The 97 written by the AI took a median of
    8 s, 9 in 10 within 17 s; only 3 arrived within 3 s (F7).
  - Timing probe, three short tutor replies with no book pages attached: the
    fast model (gpt-6-luna) took 2.4–3.5 s to write one or two sentences; the
    narrator took 0.5–1.7 s to voice each (69–108 characters). Written and
    spoken one after the other: about 3.5–5 s.
  - What this means for the next steps: the 3-second aim is reachable only if
    the live call is small. Today's call carries about 22,000 tokens (book
    pages, notes, history) and its reply is also the grade. Step 2 should
    split a short spoken line (small prompt built from the prepared notes and
    the result) from the fuller grading, and Step 1 should start speaking the
    first sentence as soon as it exists. Where the app already knows the
    result at once (F6), the spoken line can be requested without waiting for
    any grading.
- 2026-11-11 — **Step 1 done.**
  - Live replies are spoken with the lesson's own narrator on Inworld too (the
    screen had allowed only three other providers), played automatically, and
    stopped by the same rule that keeps the recorded voice and the video from
    talking over each other. The control is one small speaker icon that repeats
    the reply; the full audio player and its caption are gone.
  - Tried in test mode on Lucas's Lesson 20: a typed question was answered and
    the answer was heard in Brian's voice (15 s of speech) without any tap.
    Real records were checked untouched.
  - Measured for that reply: the AI took 9.8 s to write it (today's large live
    call, F7) and the narrator 1.6 s to voice it, so about 11.5 s from sending
    the question to the first spoken word. Four spoken replies cost 0.1–0.3
    cents each. A repeated line reuses its recording at no cost.
  - The voice adds 1–2 s; the wait is almost all in the AI call. Step 2 has to
    bring that call under about 2 s to meet the 3-second aim.
- 2026-11-11 — **Step 2 built, switched off, waiting for the family's go-ahead.**
  - `tutoring/tutor_voice.py`: after the grade is settled, one small fast call
    words what the child hears. It gets the family style, the lesson so far,
    its own last lines, the try number, the checker's note, the exact parts
    still wrong and (privately) the book's answer. The code withholds any line
    that states a key answer the child has not given, and falls back to the
    earlier words if the call fails. Setting: `ai.tutor_voice` (off).
  - `tools/live_tutor.py replay` writes the saved replies of a lesson beside
    the new ones. Replayed: Lucas Math 19, Lucas Portuguese 6, Mila Letra K.
  - What the replays showed, and what changed because of it:
    - First version was formulaic ("You did X… Nice work"), praised things it
      could not see, and repeated one hint through five misses. Fixed in the
      instructions: brief for easy answers, varied openings, only what the
      answer shows, a different approach on each miss.
    - Examples in the instructions were copied ("Yes, exactly" five times);
      removed.
    - The fast model twice said a part was "right now" when it was not, and
      once named the wrong place value. A rule did not fix it; giving it the
      exact list of parts still wrong and the book's answer did. Lesson:
      give the fast model facts, not rules, wherever accuracy matters.
    - Where the AI grader already writes the reply (97 of 136), the new line
      was only a shorter rewording at a cost of 2 more seconds. So the tutor
      voice applies **only to answers the app checks itself** (the fixed
      "Correct!" / "0 of 1 right" lines, F6). The grader's replies stay.
  - Numbers: 17 app-checked replies in Math 19, written in a median 2.1 s
    (longest 3.8 s), none withheld. With the narrator's 1–2 s, the child hears
    the first word about 3–4 s after answering, where the fixed line used to
    appear at once. Each line costs well under a cent.
  - Still open in Step 2: the AI grader's own wait (median 8 s, F7) is
    untouched. Next: time a grading call with and without the attached book
    pages to see what makes it slow.
- 2026-11-12 — **Step 2 switched on** (`ai.tutor_voice` in the host config) with the family's go-ahead.
  - **Reply held until its voice is ready** (the family's idea): a new reply
    shows three dots, then its words and voice together; never longer than 6 s,
    and at once if the voice cannot be made. `FeedbackVoice.jsx`.
  - **Bug found and fixed while testing:** after "Start lesson over" or "Go
    back one step" the grader was still shown the earlier attempt's
    conversation, so an old right answer and its praise vouched for a new wrong
    one (182,561 accepted for 400,000 − 217,438). The grader and the tutor
    voice now see only the current attempt (`interactive.attempt_start`).
  - Tried end to end in test mode on Lesson 20: a wrong answer to a keyed
    exercise got a spoken hint that did not state the answer.
  - **Measured, click to first spoken word: 6.6 s** for that keyed answer. The
    AI line took 1.7 s and the narrator 1.2 s; the other ~3.7 s is the app's own
    work around them (the answer request took 3.3 s in all, the voice request
    2.8 s). The prompt builder, state and key lookup were timed and are fast
    (0.1–0.3 s), so the cause is still unknown. **Open: find it** — profile one
    answer request and one feedback-audio request on the running server.
  - **Why the AI grader is slow (F7), measured** by sending saved grading
    requests again with and without the attached book pages:

    | Lesson | With pages | Without pages |
    |---|---|---|
    | Lucas Portuguese 6 (0.4 MB of pages) | 6.0 s, 6.5 s | 3.3 s, 3.0 s — same grades |
    | Lucas Math 19 (5.4 MB of pages) | 14.4 s, 16.4 s, 17.9 s | 3.0 s, 4.4 s, 3.4 s — one grade wrong |

    The pages cost 3–14 s per answer. But in Math they also carry the answer
    key: without them the fast model doubted a correct 9-digit sum. So the
    pages cannot simply be dropped.
  - What follows for **Step 2b**: an exercise whose answer is already in the
    script (the key's answer, or a proposed answer a grown-up approved) can be
    graded without the pages, or checked by the app at once. Lesson 20's video
    exercise had correct proposed answers waiting unapproved, which is why the
    slow grader was used at all. The fast path is more answers settled ahead
    of the lesson — "facts ahead" again — and pages attached only when an
    exercise has no settled answer or needs the picture.
- 2026-11-12 — **Step 2b, speed work.**
  - Lesson-time AI requests are sent once. Before, every request was sent
    twice: once to have the provider count its size for the spending record,
    then for real. The size is now estimated locally (generously) for teaching
    requests; preparation keeps the exact count. `services/ai_provider.py`.
  - A typed or chosen answer to an exercise whose answer is settled (from the
    key, or approved by a grown-up) is graded **without the book pages**; the
    pages are added back if the grader cannot decide (`Source disputed`,
    `Unreadable`), and always for photos, handwriting and written methods.
    Re-grading 12 real AI-graded answers this way: 12 of 12 same results,
    median 2.9 s, where the same requests with pages took 5–18 s.
    `interactive.settled_answer`.
  - The narrator's voice list is kept 12 hours for speaking a line (still 5
    minutes for browsing voices): saved 0.8 s per spoken reply.
  - Measured end to end again (test mode, Lesson 20, wrong answers to the
    Martha problem, steady state): **4.9 s and 6.4 s** from click to words and
    voice. The provider calls alone are about 3.5 s in sequence (line 1.9–2.2 s,
    voice 1.6 s); the app's own work around them is 1.3–2.6 s.
  - **Open decision (2c):** the 3-second aim cannot be met while the line is
    written in full and then voiced in full. Meeting it needs streaming: speak
    the first sentence while the rest is still being written. The remaining
    app overhead (the separate voice estimate, the state refresh before the
    voice is requested) is worth about 1 s and can be trimmed either way.
- 2026-11-12 — Family decision: 5–6 s with the dots is fine for now; **streaming
  (2c) is postponed** to a later time.
- 2026-11-12 — **Last-second trim.** The live reply's voice is requested at once
  (no separate price check; the server still refuses a voice it may not buy);
  the activity catalog is built once. Fresh replies measured at 4.9–5.6 s, the
  app's own share now 1.2–1.5 s (was 1.3–2.6 s). Tried and reverted: building
  the grading request only when the AI is asked; an app-checked answer must
  still freeze which key it was checked against.
  - Bug found: test mode shared only `narration-*` recordings with the real
    folder, so Inworld/ElevenLabs recordings made in one test copy were missing
    in the next while the shared usage record said they existed. All three
    name patterns are shared now (`services/test_mode.py: RECORDINGS`).
- 2026-11-12 — **Step 3 done, as a lead-in inside the reply.** A separate live
  sentence when Continue is pressed would add 4–5 s to every step after an
  exercise. Instead, when an answer finishes a step and the lesson changes gear
  next (a reading, an explanation or the end), the tutor's reply ends with one
  short sentence turning the page toward it. No extra call, no extra wait; with
  the AI unreachable the lesson plays exactly as before. Both the tutor voice
  and the AI grader get the next step (`tutor_voice.coming_next`).
  - Replays: asked to lead in "only sometimes", the fast model did it on every
    right answer, mostly "Now let's…" into the next exercise. Fixed with facts,
    not rules: the code passes a next step only where the lesson changes gear,
    and otherwise says "the next exercise appears by itself". Result in Lucas
    Math 19: two lead-ins, both where an explanation follows; between exercises
    short clean replies. AI-graded examples: Portuguese ("Agora vamos observar
    o som de S e SS entre vogais"), History ("That's the last question—nice
    work finishing this lesson").
- 2026-11-12 — **Step 4a: notes for the live tutor, written ahead.**
  - The writer now adds private `notes` to every explanation (the idea to land,
    an example, the usual mistake) and to every exercise (what it checks, the
    usual mistake). Notes are never compiled into child content; the reviewer
    sees and checks them; older scripts and their reviews are unchanged.
  - The live tutor voice and the AI grader get **the exercise's own notes** when
    they reply. A first try took the notes of the nearest explanation instead
    and produced a hint about number lines for a picture exercise: notes must
    belong to the exercise, written beside its page.
  - Pilot: Lucas, Math Lesson 21 (not started), prepared by the app twice. 15 of
    15 explanations and 13 of 13 exercises got notes; reviewer approved. Cost of
    the last run $0.49 writing (one writer retry) + $0.09 review.
  - Hints with notes name the real trap without the answer, e.g. "this number
    line is divided into sixths, so how many of those parts make up the
    distance to A?" (without notes: "how many equal spaces are there…").
  - **4b, live explanations, measured but not built.** The fast model rewrote
    an explanation from the prepared text plus notes accurately in 2.3–2.6 s,
    but at ~1.8× the length, so ~5 s at Continue unless prepared in advance.
    In Lesson 21 only 1 of 9 explanations follows an exercise on the same idea
    (most come right after a reading), and Step 3's lead-in already covers that
    moment. Building it needs advance preparation and a new way to play an
    explanation. Recommendation: keep prepared explanations; revisit 4b
    together with streaming, or with explanations that adapt to the learning
    memory (Step 6).
- 2026-11-12 — Family decisions: live explanations (4b) wait for another time;
  Step 5 is dropped; **a right answer gets no explanation** — the AI grader
  now confirms a correct answer in a few words (one line in its instructions);
  the tutor voice already did. Regrading six real right answers: "Correct—
  455,898 altogether." in place of explanations of why it was right.
- 2026-11-12 — Tests: the full suite runs in parallel (`pytest -q -n auto`,
  pytest-xdist): **4 minutes instead of 15**. Per the family, only the tests
  for what changed run after a small change.
- 2026-11-12 — **Step 6 done.** When a lesson is finished, the tutor writes a
  two-or-three-sentence look back from the lesson's record (each task and how
  its tries went), knowing the next lesson's title, voices it with the
  lesson's narrator and keeps both with the finished lesson
  (`tutor_voice.remember_closing`, in the background: Finish does not wait).
  The next lesson's warm-up card shows and plays it under "Last time" in place
  of the prepared closing words, and the live tutor knows it during that
  lesson. Off with the tutor voice. Examples from real lessons:
  "Rounding the kookaburra population to the nearest hundred million took
  some help, so we'll keep an eye on which place value to check together as
  we start fractions and mixed numbers." / "…na próxima aula, vamos ficar de
  olho juntos em como seguir as setas ao escrever o W." A first version did
  not know the next lesson and told Mila they would continue with K.
- 2026-11-13 — **Voice started on the server** (`tutoring/reply_voice.py`). Once
  a reply in a lesson has played by itself, the next replies start voicing the
  moment they are saved, in the voice the screen used; the screen's own request
  waits for that recording and buys nothing. Measured in test mode on Lesson 21:
  about 0.3 s sooner, not the hoped-for 1 s — the screen already asked for the
  voice within 40 ms of the reply, so only the server's state build overlaps.
  The voice itself is ~1.0–1.6 s at Inworld plus ~0.2 s of saving. Photo
  replies are not voiced ahead (the child has usually moved on).
  Bigger finding: a question typed in the chat box waits 9–12 s, because the
  grader reads the book pages for every question (8–10.6 s at gpt-6-luna).
