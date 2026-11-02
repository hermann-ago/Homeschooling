# How a lesson is made

This is the current, complete description of lesson preparation. Older write-ups
are in `docs/archive/` for history only; when they disagree with this file, this
file is right. The plan that produced it is `docs/plans/LESSON_PACKAGE_PLAN.md`.

**Guiding rule: hard rules live in code; judgment lives in the prompt.** When a
prepared lesson goes wrong, first decide which it is. A broken rule (missing
reading, missing exercise, an answer leak, a question that doesn't wait) is fixed
in a validator. A judgment problem (thin teaching, awkward pacing, wrong tone) is
fixed in the family style, a subject's notes, or the teaching guidance — and
checked with the eval set — not by adding another prohibition to the prompt.

## 1. Sources (no AI)

- **Books** belong to a subject with a role: textbook, workbook, test, combined,
  answer_key, reference. A **topic** is one lesson: a page range of the main
  book with optional `start_at` / `stop_before` headings, and a recorded
  `language` (which sets the lesson and narration language).
- **Adding books** (Curriculum → Books & lessons → Add books / Organize books):
  saving the collection sets up each new book in the background
  (`BookService.prepare_collection` → import job): its chapter map from the
  contents (bookmarks only when they are real chapters; contents pages that wrap
  titles and leader dots are handled; numbered lessons are preferred over unit
  headings), lessons from the main book, the PDF filed into the child's subject
  folder, and the book's text fingerprint for answer keys. No AI is involved.
- **Lesson pages** (`navigation.selections`) add exercise or reference pages from
  other books in the subject. Chapter maps make choosing them quick.
- **Answer keys** (`answer_keys.py`) are found locally, from a per-book
  fingerprint cached by checksum (headings, labels and phrase hashes per page):
  - a *labelled key section* — a page headed "Answer Key / Answers / Gabarito /
    Respostas" with answers under labels such as "Chapter 24 Test" or "Lição 3";
    the lesson's own label picks the pages;
  - a *filled-in copy* — a separate key PDF (role `answer_key`) that reproduces
    the student pages with answers: each lesson page is matched to the key page
    repeating its printed text (e.g. Math 4 Lesson 1 → key page 3).
  Pages the family selects with role `answer_key` take precedence.
- **Bundles** (`navigation.attach`): the *student* PDF (assigned + linked pages)
  and the *private* PDF (the same plus key pages). The child only ever sees the
  student bundle.
- **Numbered page text**: the lesson's own sentences from the PDF text layer
  (`passages.load`), with paragraph numbers. No whole-book extraction.

## 2. Writing (one AI call, or Codex)

`lesson_prompt.writer_prompt` composes, once each:

1. Lesson facts and the preparation policy (`page_script.VERSION`).
2. **Non-negotiables** — the six rules the app checks, including teaching from
   the book's point of view (no disclaimers distancing the tutor from the book).
3. **How to teach** — the model's judgment: find the passage's purpose, teach at
   the natural breaks, explain what the child would miss, choose the evidence
   each exercise needs.
4. Read-along rules (extra reading books only).
5. The family teaching style (editable in Settings) and the subject's notes
   (editable per subject; teaching parts apply now, grading parts later).
6. What the app knows about the learner (preferences, learning memory).
7. Page map, boundaries, answer-key pages (teacher-only), source notes, revision
   feedback, output format, numbered page text.

The writer receives the private bundle when key pages exist, otherwise the
student bundle. Output: `welcome`, `turns`, `closing`, where a turn is

- `say` — teaching; waits for Continue.
- `read` — either `first/last` numbered sentences (the app inserts the exact
  words) or transcribed `text` with its pages (for garbled or missing text
  layers, captions, other books).
- `ask` — the tutor's own question (discussion, retelling, reasoning).
- `book_work` — an original exercise with its page and response format, plus
  teacher-only `answer` / `answer_page` copied from the key.

Model and budget: `gpt-6.1-sol`, high reasoning, `MAX_PLAN_OUTPUT` 32,768 tokens.

## 3. Compiling and checking (no AI)

`page_script.compile_script` turns the script into the activity engine's guide:
references become exact text (split at paragraphs into ≤11,000-character
segments); reading pages must be attached student pages; book work must point at
student pages; a key answer may not appear in its own open prompt or in the
explanation just before it; read-along books may not ask for answers. Answers
stay in the frozen raw script (`guides.context_snapshot.teaching_script`), never
in child content.

## 4. Review (one AI call, or the family)

`script_review` checks the compiled lesson against the private bundle: omitted
reading or exercises, changed options, answer leaks, factual contradictions,
questions that don't wait. Tone and pacing are advice only. Codex imports are
recorded as a family review. Narration can be bought only after approval.

## 5. The lesson

The running session pins its guide, sources and skill version. For book work the
grader receives the pinned key answer (`page_script.answer_for`) as teacher-only
context, plus the private bundle for disputes. Evidence type comes from the
exercise's declared response format. Hands-on work judged by looking (lines,
colouring, tracing) uses `parent_check`: the step waits until a grown-up taps
**Looks good** (or **Let's try again**) and records no grade. A grown-up can
also confirm any other unassigned book exercise from the lesson help. The family sees every recorded answer in
Curriculum → Prepare lesson → Script review → **Answer key (teacher only)**.

## Preparing with Codex or Claude instead of the API

See `CODEX_LESSON_WORKFLOW.md`: export the packet (free), write `script.json`
to `schema.json` following `prompt.txt` and `source.pdf`, validate, import.

## Measuring changes

`backend/tools/lesson_eval.py` scores a prepared guide against hand-written
expectations in `docs/plans/eval/` (reading coverage, exercises, answer leaks,
questions in narration, explanation density). Use it with
`docs/plans/lesson-eval-rubric.md` before and after any prompt or contract change.
