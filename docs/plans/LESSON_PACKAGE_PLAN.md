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
- [ ] Commit (or deliberately stash) the 69 currently uncommitted files.
- [ ] Record test counts: `cd backend && venv/Scripts/python -m pytest -q`.
- [ ] Pick 4 eval lessons and export their packets with
      `tools/lesson_workflow.py export` into `tmp/eval/<name>/`:
      one History chapter (long reading), one Portuguese workbook spread,
      one Math page, one read-along book chapter. Save current saved guides
      for those topics as the "before" reference.

### Step 1 — Eval set and rubric (do early; used by every later step)
- [ ] `backend/tools/lesson_eval.py`: given an eval folder, report deterministic
      metrics (reading coverage %, items found vs. expected, answerable items
      not waiting, key leaks, explanation count/words, output tokens, cost).
- [ ] `docs/plans/lesson-eval-rubric.md`: short human rubric (faithful? teaches
      the central idea? explanations useful? pacing natural? exercises complete?).
- [ ] Expected-item lists per eval lesson written by hand once (ground truth).
- Done when: running the tool on the "before" guides produces a baseline table
  recorded in the progress log.

### Step 2 — One prompt builder, no duplicates (P1, part of P2)
- [ ] New `tutoring/lesson_prompt.py` that composes the six blocks above; the
      writer, the reviewer and the Codex export all use it.
- [ ] Fold `TEACHING_POLICY`, `PREPARATION_INSTRUCTIONS` (assessment + capture)
      and read-along `AUTHORING` into the non-negotiables / family style once;
      delete the "overrides older guidance" sentences.
- [ ] Remove engine tool names (`read_source`, `tell_it_back`, …) and format
      rules from `skills.template` and `tutor/subjects/*/GUIDE.md`; keep pedagogy.
- [ ] Move stroke-order guidance out of the generic prompt into the subject
      skill(s) that need it (handwriting/Portuguese).
- [ ] Existing saved subject skills in the DB: provide an explicit, versioned
      "clean up skill" migration the parent can accept; never overwrite silently.
- Done when: prompt length is reduced substantially (record before/after
  characters), tests pass, eval set is no worse.

### Step 3 — Book text by reference, bigger budget (P3)
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
| 2026-11-01 | — | Plan written after code review of the preparation pipeline | — |
