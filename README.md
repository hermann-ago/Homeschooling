# Homeschooling

A private learning app for one homeschool family. It runs on the family's Windows computer as a **home server**. Other devices on the home network use it in a browser. The family's records live in a **SQLite database** in the project's own `data` folder. Books, handwriting, audio, student work and backups are ordinary files in the **Homeschooling folder** that Google Drive for desktop syncs, organised Kid → Grade → Subject. No Google sign-in or API key is needed for storage.

OpenAI GPT-6 Luna tutors within guided lessons, using each learner's editable subject instructions. Google Gemini Flash-Lite provides expressive narration. A desktop AI tutor (Codex, Claude Desktop or any MCP client) can also run lessons in its own conversation using the same reader, instructions and tutoring records.

## What it does

- **Family books:** **Books** holds the family's 30-title, seven-stage extracurricular reading list, with search, supplied source/store links, PDF upload and a separate list for each child. Originals use `Homeschooling/Family Library/Books`; book preparation, checked readings, topic boundaries, explanations, quizzes, vocabulary and narration are saved for present and future children. Shared artifacts survive their first reader; compatible lessons reuse both writing and review without another provider request. Each child keeps their own conversation, answers, help and progress. The existing reading and activity engine runs these extras outside the school schedule and school progress totals. Files can be added later; this version accepts PDF e-books. See [Family book library](docs/BOOK_LIBRARY.md).
- **Family app:** Today, Plan (week and month), Curriculum, Progress and Settings, for everyone or one learner (each device remembers its choice). It covers scheduling across children and subjects, days off and re-planning, completion tracking with timestamps, and progress against the school year.
- **Lesson:** open it from any lesson (**Open**), or at `/lesson?learner=…&topic=…` (the plan adds `&slot=…` for **Mark lesson done**; the tutor adds `&session=…`).
  - It shows the original PDF pages, so layouts, maps and illustrations stay intact.
  - It marks the assigned start and stop headings, including lessons that begin or end partway down a page.
  - It includes the handwriting tools, **Practice** (AI quiz, summary, key terms, simple explanation) and **Extra pages** from other books. In a tutor session only the pages and the read-along show.
  - It has a read-along panel with play, pause, replay and speed controls. Expressive recordings highlight whole passages and seek to passage boundaries. Existing sentence timings and device speech retain sentence highlighting.
  - **Create read-along voice** builds saved Achird narration through Gemini's Interactions API, within the voice allowance. Completed passages survive interruptions and are reused across devices. Activities stop playback for the learner's answer.
  - **Guided lesson** turns the lesson into a teacher's walk-through: a welcome, the book text in full and in order, explanations between passages and a recap. Teacher scripts can be tidied into spoken teaching. The server rebuilds the plan to preserve book coverage. Guides are saved, versioned and marked out of date when their source changes.
- **Tutoring records:** sessions, handwritten attempts (first answer, help and revision kept separately), reviews, checkpoints and assignments. They sit in the same database as the rest of the app. The lesson reader never shows answer keys or grading evidence.
- **Linked books and workbooks:** Curriculum → subject → **Add books** starts with **Choose from Incoming Books**. Drop future PDFs into `Homeschooling/Incoming Books`, including subfolders, or upload several PDFs in the app. Choose each resource's role and its companion textbook, or select **Textbook + workbook** for a combined book. Link each separate answer key to its exact workbook and edition; individual entries need source evidence. Preparation scans every page in checkpointed batches, builds a versioned exercise catalog and matches questions to supporting reading sections. Clear matches are accepted; uncertain or unreadable work waits for review in **Exercises**. The main textbook drives the reading schedule; workbooks and test booklets supply exercises. Preparation uses the selected provider and book allowance, and resumes unfinished units. **Improve remaining links** reuses saved scans, selects reading per question, and preserves usable exercises through spending pauses.
- **Shared learning records:** **Records** shows each child's answers, help, revisions, lessons, reviews, unfinished work, reading/understanding, book exercises and preparation. Filter by child, subject, date, result or search, sort columns, open complete records and saved work, or download the filtered CSV. The table is read-only and uses no AI credits. Teacher keys and credentials are excluded.
- **Incoming filing:** preparation continues with the browser closed and resumes cached units after a restart. Incoming PDFs move into the selected child's current subject **Books** folder only after a verified destination copy and its database reference exist. Conflicting filenames receive a suffix. Already assigned books can be reused without moving another child's copy.
- **Individual workbook progress:** guides include every eligible unfinished core exercise after its required reading. Optional activities are available separately. Preparing creates no assignments; starting pins the exercise versions and creates or reuses the assigned items. Photos are assessed per exercise, with missing work left pending. **Progress → Workbook progress** shows submissions, feedback, first answers, help and revisions. Skipped work can resume after the final reading topic. Reading completion, exercise completion and independent understanding remain separate. Photos live in **Student Work**; assignments, attempts, corrections and catalog history live in SQLite.
- **Teaching skills:** Curriculum → learner → subject → **Teaching skill** provides a spacious Markdown editor, formatted preview and version history. Each subject has its own copy; History includes the migrated guide and Lucas's handwritten-work instructions adapted to automatic app saving. SQLite stores every version, with readable Markdown exports in the subject's **Teaching Skill** folder. Restoring creates another version, and changing grade keeps the same subject skill.
- **Interactive guided lessons:** **Create guided lesson** includes the saved skill, learner preferences, difficulties, due reviews, assignments and unfinished questions. **Start lesson** resumes the exact saved question first. Student actions pause both device speech and generated narration for typed answers or photos; feedback remains text. **Ask a question** uses the same paused conversation. **Continue lesson** is always manual; **Skip for now** keeps the question pending across completed sessions. Refreshing restores a paused session. **Finish lesson** saves the summary, understanding, topic completion and linked scheduled lesson, including the final subject topic. Progress shows the saved evidence and transcription amendments.
- **Guide versions:** editing the skill or book boundaries shows **Update available**. Regeneration is explicit, and an active session keeps its original guide and skill revision. Preparing, previewing or listening to a guide never completes a lesson.
- **Teaching and cost tracking:** provider selection is explicit, with no automatic model upgrades or provider switches. The app records monthly costs, actual usage and uncertain reservations without imposing spending caps; manage credits and limits with the providers. Host settings manage keys and narrators. One visible **Lesson preparation** bar prepares the guide and voice together, with saved materials reused across devices.
- **Safe saving:** each change is one SQLite transaction with an operation receipt, committed before the reply, so it works without internet. Retries with the same key never duplicate records, and edits based on an old revision are refused instead of overwriting newer work. Files are written into the Drive folder before any record refers to them.
- **Backups:** a verified copy of the database goes to the folder's `_App Backups` every day and whenever the server stops (the newest 30 are kept). A read-only Excel copy of the records, without answer keys, is written next to it.

## Layout

| Path | Contents |
|---|---|
| `data/` | Local only, never committed: the database, local backups, the tutor credential, the narration ledger and migration exports. |
| `backend/` | FastAPI home server. `storage/` holds the SQLite store, the Drive-folder file access and its Kid → Grade → Subject layout (`layout.py`), backups, `security/` the network guard, the tutor credential and DPAPI secrets, `tutoring/` the tutor service, passages and narration, `routers/` the API, and `migration/` the one-time migration tools. |
| `frontend/` | React + Vite UI, served by the home server after `npm run build`. Colours and fonts are Tailwind tokens in `src/index.css`, shared components live in `src/ui/` (shown together at `/styleguide`), and screens read data through the hooks in `src/api/queries.js`. |
| `launcher/` | `homeschooling.py start / stop / status / pair-agent / autostart`. It only stops the process it recorded. |
| `tutor_mcp/bridge.py` | Portable stdio MCP bridge for desktop AI clients (standard library only). |
| `tutor/skills/home-tutor/` | Subject-independent tutoring skill. `tutor/subjects/history/` holds the History guidance. |
| `docs/` | Setup, MCP, and migration/cutover runbooks. |

## Getting started

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for the Windows host, the Drive folder and using the app on other devices. See [docs/MCP.md](docs/MCP.md) for connecting a desktop AI tutor, and [docs/MIGRATION.md](docs/MIGRATION.md) for moving data from the previous hosted app and the History project.

For webcams on other home computers, use **Settings → Camera access on other devices**
to enable the secure LAN connection and complete the one-time certificate trust
setup on that device. See [docs/CAMERA_ACCESS.md](docs/CAMERA_ACCESS.md). Ordinary HTTP
network addresses cannot provide a live browser camera preview; saved-photo uploads
remain available.

Guided lessons use reusable tutoring activities, durable answer capture and a shared lesson engine. Parents and human tutors choose and review the material. The AI teaches the assigned source without adding unsolicited content warnings, judgments about its viewpoint, or reminders that the learner need not agree with the author. The book's original words and questions remain intact. See [docs/ACTIVITY_ENGINE.md](docs/ACTIVITY_ENGINE.md) for the 23 activities, confirmation/parent review, recovery, desktop access and the disposable offline rehearsal.

Lesson preparation reads each lesson's original PDF pages, finds its answer-key pages, and writes a teacher's script with the book text, explanations, every exercise and teacher-only key answers. See [docs/LESSON_PIPELINE.md](docs/LESSON_PIPELINE.md) for how it works and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the overall layout. Coding agents start with [AGENTS.md](AGENTS.md).

## Development

For hands-on testing, use **Settings → Test mode** in the normal app at **http://localhost:8000**.
The browser shows **TEST MODE** on every screen. Other devices continue normally. Each entry
starts a fresh, private working set from current student records; all ordinary record changes,
answers, reviews, completion, preferences, handwriting and uploads remain in `data/test-mode/`.
Existing books are read directly, with lazy copies before file edits, instead of duplicating
the app or copying every book. Turning the mode off never merges pretend work into real records.

AI remains available using the actual home-server credentials and the **same family spending
ledger** and provider connection settings. Test mode cannot add keys
or alter real host/storage/billing controls. Preparing an unchanged lesson uses real observed
learning and saves its guide for normal use. Content-addressed narration is saved for reuse.
Successful AI outputs are cached against their exact inputs (provider/model, source/context,
instructions, schema, media and output limit), including across restarts and mode changes.
Changed questions, context or sources can require new paid requests; a cache does not make
all tutoring free. Test-only source/skill changes do not overwrite normal prepared guides.

Mode selection uses a request-scoped context, including synchronous handlers and idempotency.
Loaded tabs keep their original mode header until reloaded; closed or invalid test sessions
are refused rather than silently writing real records. Media/download URLs carry the mode,
and browser caches vary by mode/cookie. Other tabs in this browser reload when the toggle changes.
Private test working sets are retained locally for recovery and never used as student evidence.

```bash
cd backend && python -m venv venv && venv/bin/pip install -r requirements-dev.txt && venv/bin/python -m pytest
cd frontend && npm ci --legacy-peer-deps && npm test && npm run lint && npm run build
```

`npm run dev` proxies `/api` to the home server on port 8000. Enable Test mode before interactive UI experiments. Backend tests use a temporary SQLite database and a temporary folder in place of the Drive folder. They cover restarts, retried requests, revision conflicts, work without internet, an unavailable Drive folder, backups, the migration dry run, simultaneous normal/test requests and reusable material caches.
