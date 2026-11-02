# Lesson package plan

Status: **Steps 0–7 done (2026-11-02)**; open items listed under "Remaining". Created 2026-11-01.

This is the working reference for restructuring lesson preparation so the app
works with any new workbook or subject and uses a strong reasoning model fully.
Each step is a self-contained slice: it can be implemented, tested and committed
on its own. Update the checklist and the progress log at the end of every step.

## Goal

For any assigned lesson, in any subject or language, one preparation produces a
**lesson package**:

- the complete assigned book text, in order and exact;
- AI teaching around it: welcome, explanations between reading sections,
  discussion questions, exercise introductions and a closing;
- every assigned exercise, item by item, with original wording and options;
- a private **teacher annex**: for each item the expected answer from the answer
  key (with key page evidence) when one is supplied, otherwise a tutor rubric,
  plus the evidence type it needs and likely misconceptions.

The child sees the first three. The annex is used only by review and live grading.

## Guiding principle

**Hard invariants live in code; judgment lives in the prompt.**

Hard invariants (enforced by validators, never by repeated prose):

1. The assigned reading is covered completely, in order, within its boundaries.
2. Every original exercise item appears exactly once, with original wording/options.
3. Every answerable item is a waiting activity; narration never answers for the child.
4. Private keys and annex content never reach child-facing payloads.
5. Source references point only to attached student pages.

Everything else — where to pause, what to explain, tone, examples, pacing,
how to group items — is the model's judgment, guided by the family style,
the editable subject skill and the learner context. When a pilot exposes a
problem, first ask: is it a broken invariant (fix the validator) or a judgment
problem (improve the eval set / skill)? Do not add another prohibition to the
prompt by default.

## Current state (diagnosis, 2026-11-01)

Kept as-is — these are good: activity engine and registry, evidence/help/revision
separation, durable jobs and idempotency, caching and cost ledger, pinned guide
versions, keys excluded from child payloads, test mode.

Problems this plan addresses:

| # | Problem | Where |
|---|---|---|
| P1 | Writer prompt stacks ~7 instruction blocks; the same rules repeat 3–4×; several blocks claim to "override older guidance"; subject skills still name retired engine tools that the prompt then says to ignore | `tutoring/page_script.py: prompt`, `content_responsibility.py`, `assessment_policy.py`, `capture_policy.py`, `book_questions.py`, `skills.py: template`, `tutor/subjects/*/GUIDE.md`, `tutor/skills/child-friendly-tutor/SKILL.md` |
| P2 | Pilot-specific rules in generic code/prompt: stroke-order text in the writer prompt; Portuguese regexes (til/acento/caligraf) deciding evidence type; guidance chosen by matching subject names | `page_script.py`, `capture_policy.py`, `skills.py` |
| P3 | Writer must transcribe book text into its own JSON output; `max_output_tokens=16384` shared with high reasoning tokens limits lesson length (symptoms: "compact JSON, no whitespace" instructions, stalled replies) | `page_script.Read.text`, `guide.MAX_PLAN_OUTPUT`, `services/ai_provider.py` |
| P4 | No per-item exercise structure or key extraction at preparation time; `book_work` is one free-text prompt; live grader re-reads PDF + key pages on every answer; automatic key lookup only for binary true/false lines | `page_script.BookWork`, `interactive.py: answer/_prompt`, `source_key.py` |
| P5 | Three writer contracts coexist (`guide.prompt`/`GuidePlan` 23-activity union, `teaching_script`, `page_script`); retired whole-book analysis still imported | `guide.py`, `teaching_script.py`, `subject_analysis.py`, `book_companion.py`, `collections.py`, `map_review.py` |
| P6 | 28 docs, many superseding each other and mixed with pilot logs; coding agents read them and keep patching | `docs/` |

## Target architecture

```
1. SOURCE LAYER (deterministic, cached per edition+page, shared across children)
   page images · chapter map · page text layer with stable paragraph/sentence IDs
   (from PDF text, or a one-time cached transcription for scanned/messy pages,
   parent-correctable)
        │
2. AUTHORING (one high-reasoning call, short prompt)
   input : student pages + page text with IDs + key pages (annex only)
           + family style + subject skill + learner context
   output: welcome · turns · closing  (child-facing)
           turns: say | read{ref range} | ask | exercise{items[]}
           annex{item_id → expected answer + key evidence | rubric,
                 evidence_type, misconceptions}  (teacher-only)
        │
3. COMPILE + VALIDATE (code)
   insert exact text for read refs · check invariants 1–5 · map to activity engine
        │
4. REVIEW (one AI call) — invariants it can see that code can't (omitted visual
   tasks, changed options, factual errors, answer leaks in teaching text)
        │
5. LIVE TUTORING — grader receives current item + its annex entry + learner
   memory; PDF pages only as fallback when the annex says "no key / unclear"
```

### Prompt shape (target)

1. **Non-negotiables** — ~10 lines mirroring the hard invariants above.
2. **Family style** — `child-friendly-tutor/SKILL.md`, deduplicated.
3. **Subject skill** — pedagogy only (no engine/tool names, no format rules).
4. **Learner context** — preferences, learning memory, due reviews, pending work.
5. **Lesson facts** — title, boundaries, page map, source text with IDs.
6. **Output format** — the schema, described once.

Read-along books add one short block. Nothing else is appended.

## Steps

Each step: implement → tests → `pytest` + frontend tests if touched → update this
file → commit. Do not start a step while the previous one is uncommitted.

### Step 0 — Baseline
- [x] Commit (or deliberately stash) the 69 currently uncommitted files. (`bc8fb02`)
- [x] Record test counts: `cd backend && venv/Scripts/python -m pytest -q -rfE --tb=line`
      (~17 min). Baseline: **727 passed, 78 failed, 18 errors**. The failing
      list is in [`baseline-test-failures.txt`](baseline-test-failures.txt).
      Nearly all are stale tests for features retired on Oct 28 (26 hit the
      "whole-book scanning is retired" 410/ValueError, 18 are `KeyError: 'contents'`
      in book-companion fixtures, most others assert old prompt wording or old
      preparation contracts). Rule for every step: **no test outside that list
      may start failing**. Stale tests are deleted or rewritten in Step 6, or
      earlier when a step touches the same code.
- [x] Pick eval lessons and export their packets with
      `tools/lesson_workflow.py export` into `tmp/eval/<name>/` (gitignored),
      and save the latest saved guide as `before-guide.json`:

      | Folder | Learner | Topic | Before guide | Author |
      |---|---|---|---|---|
      | `history-380` | Lucas (1) | 380 The Capture of Constantinople, pp. 218–223 | `guide-380-fea06be79e` | API (`gpt-6.1-sol`) |
      | `portugues-979` | Mila (2) | 979 Consoantes – Letra T, pp. 61–74 | `guide-979-bb12086a23` | Codex |
      | `language-arts-1251` | Lucas (1) | 1251 Lesson 21, pp. 86–91 | `guide-1251-371d885c1c` | Codex |
      | `read-along-1689` | Lucas (1) | 1689 A Commons Tragedy, pp. 23–28 | `guide-1689-302d81021f` | Codex |
      | `math-1125` | Mila (2) | 1125 Measuring to the Nearest Centimeter | none | — |

- [ ] Math export fails: *"The visual source does not match the assigned book
      version"* (Mila's Math, document 17). Fix the book/edition record, then
      export `math-1125`. No Math subject has a saved guide yet.

Observations from the baseline: current writer prompts are 20–32 k characters
before any PDF pages. Three of the four reference guides were authored by hand
in Codex rather than by the app's API writer — the in-app writer should become
good enough that this is unnecessary.

### Step 1 — Eval set and rubric (do early; used by every later step)
- [x] `backend/tools/lesson_eval.py`: given an eval folder, report deterministic
      metrics (reading coverage %, items found vs. expected, duplicates, answer
      leaks next to questions, questions spoken in narration, explanation
      count/words/placement, activities, prompt size; `usage.json` if present).
      Tests: `tests/test_lesson_eval.py`.
- [x] `docs/plans/lesson-eval-rubric.md`: 8-row human rubric + how to run an eval.
- [x] Expected-item lists written by hand from the PDFs: `docs/plans/eval/<name>.json`
      (committed; exported packets stay in gitignored `tmp/eval/`).
- [ ] Math expectations once `math-1125` can be exported.
- Done when: running the tool on the "before" guides produces a baseline table
  recorded in the progress log. ✅

**Baseline (before guides, 2026-11-01):**

| Eval | Reading covered | Exercises found | Answer leaks | Narration questions | Explanations | Explanation words | Reading words | Activities | Prompt chars |
|---|---|---|---|---|---|---|---|---|---|
| history-380 | 100% | 7/7 | 0 | 0 | 3 (1 between) | 94 | 1029 | 8 | 27574 |
| language-arts-1251 | 100% | 19/19 | 0 | 0 | 2 (0 between) | 75 | 1558 | 15 | 20724 |
| portugues-979 | 100% | 13/13 | 0 | 0 | 9 (5 between) | 332 | 84 | 15 | 31651 |
| read-along-1689 | 98% | — | 0 | 0 | 2 (2 between) | 170 | 1620 | 0 | 19574 |

Read-along's missing 2% are commentary sub-headings (Brainstorming, Background…).

Qualitative notes from reading the guides:
- **history-380 (API writer):** faithful and complete, but barely teaches — a
  534-word reading with no teaching inside; of 3 explanations, 2 are transitions
  ("Now let's turn to Constantinople"); the only real teaching is defining
  *siege*. The recap and one explanation add viewpoint caveats ("a difficult
  part of history…", "their belief… not proof") despite the family policy being
  repeated several times in the prompt. Rubric rows 2–3: 1.
- **read-along-1689 (Codex):** explanations are genuinely good (incentives,
  garden comparison, shared resource), but the final 748-word commentary has
  no teaching. Rows 2: 3, 3: 2.
- Fidelity (rows 1, 4) is already strong everywhere; the gap is **teaching
  depth and placement**. That is what Steps 2–3 should move.

### Step 2 — One prompt builder, no duplicates (P1, part of P2)
- [x] New `tutoring/lesson_prompt.py` composes: lesson facts → NON_NEGOTIABLES →
      HOW_TO_TEACH → READ_ALONG (book reading only) → family style → subject
      skill (labelled: teaching parts now, grading later, non-negotiables win)
      → learner (preferences + learning memory without record IDs) → compact
      page map → boundaries → source notes → revision feedback → OUTPUT_FORMAT.
      `page_script.prompt` delegates to it, so the app writer and the Codex
      export share it. Writer version bumped to `original-pages-3`.
- [x] The writer no longer receives `TEACHING_POLICY`, `assessment_policy` /
      `capture_policy` `PREPARATION_INSTRUCTIONS` or `book_questions.AUTHORING`;
      their writing-relevant content is folded into the blocks once. Those
      constants remain for the live tutor, reviewer and legacy writers.
- [x] Removed the route's extra "Use the attached original pages…" suffix.
- [x] Stroke-order guidance kept as one generic line (any handwriting model).
- [x] Engine tool names removed from `skills.template`, `tutor/subjects/history`
      and `math` guides (the live tutor gets its own activity list from code).
      Template "short teacher explanations" → "teach while reading".
- [x] Repo default family style (`child-friendly-tutor/SKILL.md`) rebased on the
      family's saved v4, minus parts now covered by the composed blocks.
- [ ] **Reviewer** still has its own stacked policies (`script_review.run`);
      fold it onto the same blocks after the eval shows the writer change helps
      (kept separate so effects can be measured one at a time). Its focused
      check now accepts any `original-pages-*` policy.
- [ ] Saved family/subject skills in the DB — proposals generated in
      `tmp/skill-proposals/` (family v4→v5, History v3→v4, Português v5→v6,
      8 untouched template v1→v2). Save via the normal skill API only after
      the family approves; older versions stay restorable.
- [x] Saved skill versions approved by the family (2026-11-01): family v5,
      History v4 (also "follow the book's own framing"), Português v6, and
      template skills v2 for Math ×2, Science ×2, Language Arts ×2, Portuguese.
- [ ] Eval: prepare the 4 sample lessons with the new writer in Test mode
      and compare with the baseline table. Server restarted on `efff777`;
      dry-run ceilings US$0.69–0.89 each (past actuals US$0.15–0.40).
      **Blocked 2026-11-01:** OpenAI returned `provider_quota` (no API credit);
      nothing charged. Re-run with `python ../tmp/eval/run_prep.py history-380 1 380 v3`
      (from `backend/`, Test-mode token in `tmp/eval/test-mode-token.txt`)
      once credit is restored; check History's actual cost before the rest.

Prompt size (characters, before PDF pages) — app-owned instructions went from
~6.5 k with repetition to ~4.1 k without; totals are dominated by the family's
own documents until the skill proposals are applied:

| Eval | v2 prompt | v3 prompt | of which family style + subject skill |
|---|---|---|---|
| history-380 | 27,574 | 23,384 | 7,678 + 6,645 |
| portugues-979 | 31,651 | 27,549 | 7,678 + 13,040 |
| language-arts-1251 | 20,724 | 16,470 | — |
| read-along-1689 | 19,574 | 15,369 | — |

Finding: the History subject skill (v3) itself told the writer to add only
"short explanations" and avoid comments between paragraphs — a direct cause of
the thin teaching in the baseline. Português v5 carried instructions for the
retired formats (`explain_or_observe`, `request_book_work` fields,
`source_block_id`, "modo tidy").

### Step 3 — Book text by reference, bigger budget (P3)

**Design constraint (family decision, Oct 2026):** whole-book conversion to JSON
was tried and abandoned — images and unusual lesson layouts made it unreliable.
The model keeps receiving the **original lesson PDF pages** and reasoning over
them directly. This step must not reintroduce whole-book extraction or an
exercise catalog. It only lets the writer *point at* plain reading text on the
lesson's own pages (extracted on demand, per lesson, from the PDF text layer)
instead of re-typing it. Where the text layer is missing or unreliable, or the
layout is unusual, the writer keeps transcribing from the page image (`text`),
as today. Both forms are valid in one script.
- [x] Source layer: the lesson package's own `sentences` (already extracted per
      lesson from the PDF text layer within boundaries, with `paragraphIndex`)
      are the reference IDs — no new extraction module or whole-book pass.
- [x] PDF lessons with a text layer get a NUMBERED PAGE TEXT block and two read
      forms: (a) `first/last` sentence references — preferred where the numbered
      text matches the page; (b) transcribed `text` + pages for anything the text
      layer lacks or garbles (other books, headers inside sentences, split words,
      line-laid poems). Strict schema: all fields present, unused ones null.
      Pages without a text layer keep transcription only.
- [x] `page_script.compile_script` turns references into the exact text with
      paragraph breaks, split at paragraphs into ≤11,000-character segments
      (GuideSegment holds 12,000), keeps `from/to` source positions, and rejects
      references that repeat or go backwards.
- [x] No per-page AI transcription cache: transcription stays inside the writer
      call (family decision), so nothing new is purchased.
- [ ] Full coverage validator for mixed scripts: not possible deterministically
      for transcribed stretches; the reviewer and `lesson_eval.py` cover it.
- [x] `MAX_PLAN_OUTPUT` 16,384 → 32,768 (US$10/M output ⇒ +US$0.16 worst-case
      reservation). The model's documented maximum was not checked online.
- [x] "Compact JSON" stays (harmless); the whitespace-stall comment concerns
      nested schemas, not size.
- Done when: … ✅ for History (Codex-path authoring below); a 20-page chapter
  has not been tried.

**Step 2+3 eval — History 380, authored via the Codex workflow (2026-11-01):**
the script was written by Claude following `prompt.txt` exactly (this measures
the prompt/contract, not `gpt-6.1-sol`'s behaviour), validated, imported into
production records as `guide-380-f0458a8b2e` (review: family_review approved).

| Guide | Reading covered | Exercises | Leaks | Narration questions | Explanations | Explanation words |
|---|---|---|---|---|---|---|
| before (API, v2 prompt) | 100% | 7/7 | 0 | 0 | 3 (1 between) | 94 |
| v3 + references | 100% | 7/7 | 0 | 0 | 9 (6 between) | 710 |

All 1,022 reading words came from 7 sentence references — the writer re-typed
none. The first draft had 3 rhetorical questions in narration; `lesson_eval`
flagged them and they were rewritten before import.

### Step 4 — Exercises as items + teacher annex with keys (P4)
**Status (2026-11-02): done as below — a smaller design than first sketched.**
- [x] `tutoring/answer_keys.py`: local, AI-free detection. A key section is a
      page with an "Answer Key / Answers / Gabarito / Respostas…" heading (or a
      whole PDF linked with role `answer_key`); answers are found under the label
      the lesson carries in its title or exercise pages ("Chapter 24", "Lição 3"),
      continuing onto the next page unless that page opens with the next label.
      History: Chapter 24 → SOTW2_Tests p. 174, Chapter 25 → p. 174, verified.
- [x] `navigation.attach` adds detected key pages to the private review bundle
      when the family selected none; family selections always win.
- [x] The writer receives that private bundle (key pages labelled teacher-only
      in ANSWER KEY PAGES); the child's planner PDF and page map never include
      them (tested).
- [x] Instead of a separate annex/`exercise.items` contract, each `book_work`
      turn gained teacher-only `answer` + `answer_page`. One turn = one compiled
      activity, so alignment is by construction. Compile rejects an answer that
      appears in the turn's open prompt or the explanation right before it
      (binary and choice answers exempt).
- [x] Grading: `page_script.answer_for` finds the pinned guide's answer for the
      current activity and passes it as teacher-only grading context; the PDF and
      key pages are still attached for disputes.
- [x] Family view: Curriculum → Prepare lesson → Script review → **Answer key
      (teacher only)**, from `GET /tutor/guides/{id}/review` (family-only).
- [ ] Separate key PDFs linked per workbook: supported through role
      `answer_key` in the subject's books, untested on real family data.
- [ ] Evidence types stay on `response.format` (see Step 5).

Real lessons prepared through the Codex workflow, imported to production:
`guide-380-48d79c89bf` (Constantinople, with key answers) and
`guide-382-5f2fe8306b` (**The Plague**, Lucas's next History lesson: garbled
text layer, so all readings transcribed; 98% coverage, 12/12 items, 0 leaks,
7 explanations / 496 words; key answers for all 9 exercise turns).

Original sketch, kept for reference:
- [ ] **Answer-key map (family idea, 2026-11-01):** when the chapter map is
      built (no AI: bookmarks/contents), also detect answer-key locations —
      contents entries such as "Answer Key", "Answers", "Respostas", "Gabarito",
      "Teacher's Guide", or a separate PDF with role `answer_key` — and store
      per-chapter key page ranges alongside `book_navigation`, editable by the
      parent in **Chapter maps**. Do **not** extract all answers up front
      (same failure mode as whole-book JSON). At lesson preparation, attach only
      that chapter's key pages to the writer call (teacher-only), and the writer
      fills the annex from them.
- [ ] Replace `book_work` with `exercise`: `{type:'exercise', document_id, page,
      number, instruction, items:[{item_id, label, prompt, options?, response}]}`.
      One exercise = one waiting turn; items keep individual identity.
- [ ] Add `annex: [{item_id, expected | null, key_evidence{document_id,page,quote} | null,
      rubric, evidence_type, misconceptions[]}]` to the authoring schema.
      Key pages are attached to this call, clearly marked teacher-only; the
      validator rejects any key quote or expected answer appearing in child text.
- [ ] Store the annex privately with the guide (same place as review snapshots);
      never include it in reader/child API responses. Add a test asserting this.
- [ ] Live grading: `interactive._prompt` receives the item and its annex entry;
      attach PDF/key pages only when `expected` is null or flagged uncertain.
- [ ] Review checks annex entries against key pages (spot-check, not regenerate).
- [ ] Parent view: show the annex next to the lesson in Curriculum (read-only
      first; editing later).
- Done when: Portuguese and Math eval lessons have per-item keys, grading uses
  them without re-reading pages, and no annex content appears in child payloads.

### Step 5 — Evidence type from authoring; delete subject special cases (P2)
- [ ] `evidence_type` from the annex (answer | spelling | handwriting |
      written_steps | diagram | observe) drives capture controls.
- [ ] Remove the regex heuristics in `capture_policy.py` and subject-name
      matching in `skills.template` (subject skills become plain editable docs
      seeded from a generic template; the parent can pick a starter guide).
- [ ] Keep locale strings (True/False labels, etc.) but key them by curriculum
      language, not by "Portuguese".
- Done when: a subject named anything, in English or Portuguese, gets correct
  capture behaviour from the item's declared evidence type.

**Status (2026-11-02): done.**
- [x] Evidence: the writer's `response.format` (text, spelling, handwriting,
      written_steps, diagram, observe, choices) already compiles to the capture
      contract. `capture_policy.activity_content` no longer second-guesses it for
      original-page scripts (`writer_declared`); its Portuguese regexes and
      companion lookups now apply only to older guides.
- [x] Language: `audio.language_of(store, subject)` uses the most common
      language recorded on the subject's topics (the books' language), falling
      back to the name only when none is recorded. All 17 call sites moved from
      `language_for(subject['name'])`. A Portuguese "Ciências" now teaches in pt-BR.
- [x] New-subject template slimmed to subject-specific notes + book list (the
      family style and the app's rules cover the rest). Starter guides are still
      suggested by name for History/Math/Portuguese — a convenience only.
- [x] Locale labels (Verdadeiro/Falso) were already keyed by language.

### Step 6 — Retire old contracts and old pipelines (P5)
- [ ] Audit callers of `guide.prompt`/`ProviderGuidePlan`, `teaching_script`,
      `subject_analysis`, `book_companion`, `collections`, `map_review`.
- [ ] Keep only what's needed to **read** historical guides/sessions and
      recordings; delete authoring paths and their tests.
- [ ] Verify historical playback and an existing pinned session still open.
- Done when: one writer contract remains; backend line count drops noticeably.

**Status (2026-11-02): done for tests and dead code; module removal deferred.**
- [x] Triage of all 96 baseline failures: every one tested a retired feature or
      an intentionally changed contract (whole-book scanning/analysis → 410,
      book-companion creation, exercise catalog in guides, lesson source
      inventory, spending caps that refuse requests, old prompt wording). None
      was a live bug. 1 test was fixed (Codex import for a read-along book);
      66 stale tests were removed and 5 wholly stale files deleted.
- [x] Unreachable code after the 7 retired endpoints' `raise HTTPException(410)`
      removed (`routers/books.py`).
- [x] Reviewer now receives the writer's NON_NEGOTIABLES and, for scripts with
      recorded answers, the `answer_key` to spot-check (older guides' review
      identities unchanged).
- [ ] Deleting retired modules (`subject_analysis`, `book_companion`,
      `map_review`, `collections`, `lesson_source_index`, the legacy `guide`
      prompt): still imported by read paths for saved maps, historical guides
      and legacy grading. Removing them needs a call-graph audit and a backup
      restore + historical playback test; deferred as low value / non-zero risk.

### Step 7 — Docs consolidation (P6)

**Status (2026-11-02): done.** `docs/LESSON_PIPELINE.md` (the pipeline as
built), `docs/ARCHITECTURE.md`, root `AGENTS.md` (+ `CLAUDE.md` importing it),
15 superseded docs and 2 retired Codex skills moved to `docs/archive/` and
`tutor/archive/`; README, BOOK_LIBRARY and CODEX_LESSON_WORKFLOW repointed.

- [ ] `docs/ARCHITECTURE.md` (layers, invariants, data ownership) and
      `docs/LESSON_PIPELINE.md` (the five stages above, as built).
- [ ] Move pilot logs and superseded workflow docs to `docs/archive/`.
- [ ] Add a root `AGENTS.md` (short) pointing to these two docs and to this plan,
      stating the guiding principle so coding agents don't re-add prompt patches.

## Risks and rules while implementing

- Never rewrite saved guides, sessions, recordings or learner records; new
  contracts apply to new preparations only. Old formats remain readable.
- No automatic paid regeneration; eval runs are explicit and use Test mode.
- Keys/annex leaking to the child is the highest-severity bug — test it at the
  API boundary in every step that touches payloads.
- Measure with the eval set before and after Steps 2–5; record numbers below.

## Remaining (2026-11-02)

- **Mila's Math is blocked by a missing file, not code:** document 17
  (*Good and Beautiful Math 1_compressed.pdf*) was marked `missing` at migration
  and is not in the Drive folder. Add the PDF to that subject's books. Also
  missing: documents 12–14 (duplicate Português workbook records) and 16/18
  (*Sparks And Stars Parent Guide*).
- **API-writer eval:** prepare the sample lessons with `gpt-6.1-sol` once
  OpenAI API credit is restored, and compare with the Codex-authored ones.
- **Answer keys as separate PDFs:** first real use will be *Math 4 Course Book* +
  *Math 4 Answer Key* in Incoming Books; give the key the `answer_key` role.
- **Retired modules** (see Step 6) — deferred.
- Frontend: `ActivityLesson.test.jsx › keeps the latest feedback visible…` is a
  timing flake under the full parallel run (passes alone, also at baseline).

## Progress log

| Date | Step | Result / numbers | Commit |
|---|---|---|---|
| 2026-11-01 | — | Plan written after code review of the preparation pipeline | `f264483` |
| 2026-11-01 | 0 | Baseline committed; 4 eval packets exported (Math blocked by book-version mismatch); tests 727 pass / 78 fail / 18 error, list saved | `37f7166` |
| 2026-11-01 | 1 | `lesson_eval.py` + rubric + ground truth for 4 lessons; baseline table above. Fidelity strong, teaching thin (History 94 explanation words / 1029 read) | `f365b1e` |
| 2026-11-01 | 2 | Composed writer prompt, book's-point-of-view rule, cleaned guides/templates; family-approved skill versions saved. Tests: 737 pass, same 96 baseline failures, no new ones. Eval blocked by OpenAI quota | `efff777` + (this commit) |
| 2026-11-02 | 3 | Sentence references + 32k output; History 380 authored via Codex path: 710 explanation words vs 94 | `2325fa4` |
| 2026-11-02 | 4 | Local answer-key detection, teacher-only answers in scripts, grading lookup, family view; The Plague prepared | `98395f4` |
| 2026-11-02 | 5 | Language from topics; writer-declared evidence; slim subject template | `e00c54e` |
| 2026-11-02 | 6 | 96 stale failures triaged; suite green (753 pass); dead endpoint code removed; reviewer gets writer rules | `ffac55b` |
| 2026-11-02 | 7 | LESSON_PIPELINE, ARCHITECTURE, AGENTS.md; 15 docs archived | `214fec7` |
