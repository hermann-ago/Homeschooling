# Notes for coding agents

Read `docs/ARCHITECTURE.md`, then `docs/LESSON_PIPELINE.md` for anything about
preparing lessons. Active plans live in `docs/plans/`. `docs/archive/` is
history only and may describe retired workflows.

## Ground rules

- **Hard rules in code, judgment in the prompt.** Do not fix a bad lesson by
  adding another "do not…" line to a prompt or skill. Fix broken rules in a
  validator (`page_script.compile_script`, review) and judgment problems in the
  family style or subject notes, then check with `backend/tools/lesson_eval.py`.
- **State each rule once.** The writer prompt is composed in
  `tutoring/lesson_prompt.py`; do not add parallel policy blocks elsewhere.
- **No subject-specific code.** Behaviour must not depend on a subject's name or
  a particular book. Language comes from topics; evidence from each exercise's
  declared response format.
- **No whole-book extraction.** The writer reads the lesson's original PDF pages.
- **Teacher material stays private** (keys, key pages, grading context).
- **Never rewrite learner records**, running sessions or saved guides as a side
  effect; new contracts apply to new preparations.

## Commands

```bash
cd backend && venv/Scripts/python -m pytest -q tests/test_<area>.py   # the tests for what you changed
cd backend && venv/Scripts/python -m pytest -q -n auto  # full suite in parallel, ~4 min; before larger commits
cd frontend && npm test && npm run lint && npm run build
python backend/tools/lesson_workflow.py export --learner L --topic T --out tmp/lesson-T
python backend/tools/lesson_eval.py tmp/eval --all --guide before-guide.json
```

The home server must be restarted (`launcher/homeschooling.py stop` / `start`)
to load backend changes, and the frontend rebuilt to serve UI changes.
