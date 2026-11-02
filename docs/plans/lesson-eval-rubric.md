# Lesson eval rubric

Use with `backend/tools/lesson_eval.py`. The tool counts; this rubric judges.
Score each eval lesson 1–3 per row (1 = problem, 2 = acceptable, 3 = excellent)
while reading the guide beside the original pages. Record totals and one-line
notes in the plan's progress log.

| # | Question | 1 | 3 |
|---|---|---|---|
| 1 | **Faithful** — is all assigned reading present, exact and in order? Any invented facts? | Omissions, paraphrased author text or invented facts | Complete and exact; teacher words clearly separate |
| 2 | **Teaches the central idea** — do explanations illuminate the passage's purpose (cause/effect, argument, theme, method)? | Absent, generic, or plot trivia | Clear, accurate, connects ideas the child would miss alone |
| 3 | **Explanation placement** — do pauses fall where understanding needs them? | Long readings with no teaching, or constant interruptions | Natural breaks; continuity kept for poems/scenes |
| 4 | **Exercises complete and faithful** — every assigned item, original wording/options, sensible grouping? | Missing, altered or duplicated items | All items, original wording, natural grouping |
| 5 | **Waits for the child** — every question that needs an answer is an activity; none answered in narration? | Questions in narration or answers revealed | Every request waits; no leaks |
| 6 | **Right evidence** — typed vs. photo vs. choice fits each task? | Photos for typed answers, or typed answers for handwriting | Each item asks for exactly the evidence it needs |
| 7 | **Voice** — sounds like a warm teacher speaking to this child's age? | Checklist language, repetition, baby talk | Natural, varied, age-appropriate |
| 8 | **Uses learner context** — reviews, pending work, known difficulties included where relevant? | Ignored, or forced in awkwardly | Woven in naturally, only when relevant |

Maximum 24. A change to prompts or contracts should not lower any lesson's
score on rows 1, 4 or 5 (the hard invariants), and should improve rows 2–3
or cost without regressions elsewhere.

## Running an eval

1. Export packets (no cost): `python tools/lesson_workflow.py export --learner L --topic T --out ../tmp/eval/<name>`.
2. Produce a candidate guide — the app's writer in **Test mode**, or a Codex-authored
   `script.json` imported via `lesson_workflow.py import` in Test mode — and save the
   compiled guide JSON as `../tmp/eval/<name>/<label>-guide.json`.
3. Score: `python tools/lesson_eval.py ../tmp/eval --all --guide <label>-guide.json`.
4. Read each guide against the pages and fill in the rubric.
5. Record numbers, cost (`usage.json` if available) and rubric totals in the plan.

Ground truth lives in `docs/plans/eval/<name>.json`; edit it there when an
expectation turns out to be wrong, and note why.
