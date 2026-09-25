# Homeschooling

A private learning app for one homeschool family. It runs on the family's Windows computer as a **home server**. Other devices on the home network use it in a browser. **Google Drive** stores books and files, and one **Google Sheets** workbook (*Homeschooling Database*) is the authoritative record.

A desktop AI tutor (Codex, Claude Desktop or any MCP client) runs lessons in its own conversation. It uses the app's reader and records progress through the same home server.

## What it does

- **Family app:** Today, Weekly, Daily Canvas, Curriculum, Progress, Calendar and Settings. It covers scheduling across children and subjects, completion tracking with timestamps, AI enrichment (quiz, summary, key terms, simple explanation) and handwriting on PDF pages.
- **Lesson reader:** open it at `/lesson?learner=…&topic=…&session=…`.
  - It shows the original PDF pages, so layouts, maps and illustrations stay intact.
  - It marks the assigned start and stop headings, including lessons that begin or end partway down a page.
  - It includes the handwriting tools.
  - It has a read-along panel with play, pause, replay, speed and sentence highlighting. The highlighting follows real timing data only: Google TTS timepoints or the device voice's own events. Nothing is estimated.
- **Tutoring records:** sessions, handwritten attempts (first answer, help and revision kept separately), reviews, checkpoints and assignments. They sit in the same workbook as the rest of the app. Teacher-only keys and grading evidence never reach learner devices.
- **Safe saving:** every change is written to a durable local queue first. It is then saved to Google Sheets in one atomic batch with a receipt, and the save is verified. The app shows one of three states:
  - **Saved to Google**
  - **Pending sync**, for example while offline
  - **Needs reconciliation**, for example after a direct spreadsheet edit

  Retries never duplicate records.

## Layout

| Path | Contents |
|---|---|
| `backend/` | FastAPI home server. `storage/` holds the Sheets store and Drive/Sheets gateways, `google_io/` the OAuth, Drive and Sheets REST clients, `security/` pairing, the network guard and DPAPI secrets, `tutoring/` the tutor service, passages and narration, `routers/` the API, and `migration/` the one-time migration tools. |
| `frontend/` | React + Vite UI, served by the home server after `npm run build`. |
| `launcher/` | `homeschooling.py start / stop / status / pair-agent`. It only stops the process it recorded. |
| `tutor_mcp/bridge.py` | Portable stdio MCP bridge for desktop AI clients (standard library only). |
| `tutor/skills/home-tutor/` | Subject-independent tutoring skill. `tutor/subjects/history/` holds the History guidance. |
| `docs/` | Setup, MCP, and migration/cutover runbooks. |

## Getting started

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for the Windows host, Google connection and device pairing. See [docs/MCP.md](docs/MCP.md) for connecting a desktop AI tutor, and [docs/MIGRATION.md](docs/MIGRATION.md) for moving data from the previous hosted app and the History project.

## Development

```bash
cd backend && python -m venv venv && venv/bin/pip install -r requirements-dev.txt && venv/bin/python -m pytest
cd frontend && npm ci --legacy-peer-deps && npm test && npm run lint && npm run build
```

`npm run dev` proxies `/api` to a home server on port 8000. Backend tests use in-memory fakes of Sheets and Drive that interpret the real API request bodies. They include outage, lost-response, revoked-authorization and conflict scenarios.
