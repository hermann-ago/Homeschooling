# Architecture

A private home server (FastAPI + SQLite) that family devices use in a browser.
Files live in the Google Drive-synced Homeschooling folder; records live in
`data/homeschooling.sqlite3`. See `README.md` for features and setup.

## Layers

| Layer | Where | Owns |
|---|---|---|
| Storage | `backend/storage/` | SQLite store with revisions and idempotent writes; Drive folder layout (Kid → Grade → Subject); backups |
| Sources | `tutoring/passages.py`, `navigation.py`, `visual_source.py`, `answer_keys.py` | Lesson page ranges, student and private PDF bundles, numbered page text, answer-key pages |
| Lesson writing | `tutoring/lesson_prompt.py`, `page_script.py` | The writer's prompt and script contract; compiling scripts into guides |
| Guides and review | `tutoring/guide.py`, `script_review.py` | Saved, versioned guides; the pre-narration review |
| Activity engine | `tutoring/activity_engine.py`, `activities.py`, `interactive.py` | Running lessons: activities, answers, help, revisions, grading |
| Learning records | `tutoring/learning_memory.py`, `service.py` | Attempts, reviews, checkpoints, the learning summary |
| Narration | `tutoring/narration.py` and provider adapters | Recorded voice, timings, reuse |
| AI provider | `services/ai_provider.py`, `ai_budget.py` | Requests, caching by exact input, cost ledger |
| API | `backend/routers/` | HTTP surface; family-only routes for teacher material |
| UI | `frontend/src/` | React screens; data through `src/api/queries.js` |
| Desktop tutors | `tutor_mcp/bridge.py`, `tutor/skills/` | MCP bridge and the skills Codex/Claude use |

## Invariants

- The child never receives answer keys, key pages or grading context. Teacher
  material is served only by family-only routes and stays in private bundles and
  frozen snapshots.
- Saved learner evidence is append-only in spirit: first answers, help and
  revisions are kept separately; corrections are amendments.
- A running lesson is pinned to its guide, sources and skill version; preparing
  a new guide never changes it.
- AI output is cached by its exact inputs and spending is recorded; there is no
  automatic provider switch or paid retry of an uncertain request.
- Reading completion, submitted work and assessed understanding stay distinct.

## Where to start

Lesson preparation: `docs/LESSON_PIPELINE.md`. Running lessons and activities:
`docs/ACTIVITY_ENGINE.md`. Desktop tutors: `docs/MCP.md`. Ongoing work:
`docs/plans/`.
