# Lesson package plan

Status: **planned** — no step started. Created 2026-11-01.

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
- [ ] Source layer: `tutoring/page_text.py` returning per-page paragraphs and
      sentences with stable IDs (`p<page>.<para>.<sent>`), built from the PDF
      text layer (`passages.extract`/`split_sentences` already exist).
- [ ] For pages with no/poor text layer: one-time cached AI transcription per
      page (category `books`), stored by document sha256 + page, parent-correctable;
      reuse the existing spacing/hyphenation-only correction rules.
- [ ] `Read` turn becomes `{type:'read', from:'<id>', to:'<id>'}`; compiler
      inserts the exact text and source refs. Keep `text` accepted for old saved
      scripts only.
- [ ] Coverage validator: every assigned sentence ID inside boundaries is read
      exactly once, in order (reuses the earlier coverage idea, without forcing
      one turn per block).
- [ ] Confirm the preparation model's real maximum output and raise
      `MAX_PLAN_OUTPUT` accordingly (separate constant from other callers);
      update the cost preview ceiling in `routers/tutor.py`.
- [ ] Remove the "compact JSON / no whitespace" prompt workarounds if no longer needed.
- Done when: the long History eval chapter prepares in one call with full
  coverage and output tokens well under the limit.

### Step 4 — Exercises as items + teacher annex with keys (P4)
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

### Step 6 — Retire old contracts and old pipelines (P5)
- [ ] Audit callers of `guide.prompt`/`ProviderGuidePlan`, `teaching_script`,
      `subject_analysis`, `book_companion`, `collections`, `map_review`.
- [ ] Keep only what's needed to **read** historical guides/sessions and
      recordings; delete authoring paths and their tests.
- [ ] Verify historical playback and an existing pinned session still open.
- Done when: one writer contract remains; backend line count drops noticeably.

### Step 7 — Docs consolidation (P6)
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

## Progress log

| Date | Step | Result / numbers | Commit |
|---|---|---|---|
| 2026-11-01 | — | Plan written after code review of the preparation pipeline | `f264483` |
| 2026-11-01 | 0 | Baseline committed; 4 eval packets exported (Math blocked by book-version mismatch); tests 727 pass / 78 fail / 18 error, list saved | `37f7166` |
| 2026-11-01 | 1 | `lesson_eval.py` + rubric + ground truth for 4 lessons; baseline table above. Fidelity strong, teaching thin (History 94 explanation words / 1029 read) | `f365b1e` |
| 2026-11-01 | 2 | Composed writer prompt, book's-point-of-view rule, cleaned guides/templates; family-approved skill versions saved. Tests: 737 pass, same 96 baseline failures, no new ones. Eval blocked by OpenAI quota | `efff777` + (this commit) |
