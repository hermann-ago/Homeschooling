# Homeschooling

A private learning app for one homeschool family. It runs on the family's Windows computer as a **home server**. Other devices on the home network use it in a browser. The family's records live in a **SQLite database** in the project's own `data` folder. Books, handwriting, audio, student work and backups are ordinary files in the **Homeschooling folder** that Google Drive for desktop syncs, organised Kid → Grade → Subject. No Google sign-in or API key is needed for storage.

A desktop AI tutor (Codex, Claude Desktop or any MCP client) runs lessons in its own conversation. It uses the app's reader and records progress through the same home server.

## What it does

- **Family app:** Today, Weekly, Daily Canvas, Curriculum, Progress, Calendar and Settings. It covers scheduling across children and subjects, completion tracking with timestamps, AI enrichment (quiz, summary, key terms, simple explanation) and handwriting on PDF pages.
- **Lesson reader:** open it at `/lesson?learner=…&topic=…&session=…`.
  - It shows the original PDF pages, so layouts, maps and illustrations stay intact.
  - It marks the assigned start and stop headings, including lessons that begin or end partway down a page.
  - It includes the handwriting tools.
  - It has a read-along panel with play, pause, replay, speed and sentence highlighting. The highlighting follows real timing data only: Google TTS timepoints or the device voice's own events. Nothing is estimated.
- **Tutoring records:** sessions, handwritten attempts (first answer, help and revision kept separately), reviews, checkpoints and assignments. They sit in the same database as the rest of the app. Teacher-only keys and grading evidence never reach learner devices.
- **Safe saving:** each change is one SQLite transaction with an operation receipt, committed before the reply, so it works without internet. Retries with the same key never duplicate records, and edits based on an old revision are refused instead of overwriting newer work. Files are written into the Drive folder before any record refers to them.
- **Backups:** a verified copy of the database goes to the folder's `_App Backups` every day and whenever the server stops (the newest 30 are kept). A read-only Excel copy of the records, without answer keys, is written next to it.

## Layout

| Path | Contents |
|---|---|
| `data/` | Local only, never committed: the database, local backups, paired devices, the narration ledger and migration exports. |
| `backend/` | FastAPI home server. `storage/` holds the SQLite store, the Drive-folder file access and its Kid → Grade → Subject layout (`layout.py`), backups, `security/` pairing, the network guard and DPAPI secrets, `tutoring/` the tutor service, passages and narration, `routers/` the API, and `migration/` the one-time migration tools. |
| `frontend/` | React + Vite UI, served by the home server after `npm run build`. |
| `launcher/` | `homeschooling.py start / stop / status / pair-agent`. It only stops the process it recorded. |
| `tutor_mcp/bridge.py` | Portable stdio MCP bridge for desktop AI clients (standard library only). |
| `tutor/skills/home-tutor/` | Subject-independent tutoring skill. `tutor/subjects/history/` holds the History guidance. |
| `docs/` | Setup, MCP, and migration/cutover runbooks. |

## Getting started

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for the Windows host, the Drive folder and device pairing. See [docs/MCP.md](docs/MCP.md) for connecting a desktop AI tutor, and [docs/MIGRATION.md](docs/MIGRATION.md) for moving data from the previous hosted app and the History project.

## Development

```bash
cd backend && python -m venv venv && venv/bin/pip install -r requirements-dev.txt && venv/bin/python -m pytest
cd frontend && npm ci --legacy-peer-deps && npm test && npm run lint && npm run build
```

`npm run dev` proxies `/api` to a home server on port 8000. Backend tests use a temporary SQLite database and a temporary folder in place of the Drive folder. They cover restarts, retried requests, revision conflicts, work without internet, an unavailable Drive folder, backups and the migration dry run.
