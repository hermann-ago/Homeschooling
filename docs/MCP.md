# Connecting a desktop AI tutor (MCP)

`tutor_mcp/bridge.py` is a stdio MCP server that uses only the Python standard library. It calls the home server over HTTP with a **tutor** credential. It never opens the database or the Drive folder itself and never sees any Google credential.

## 1. Pair the bridge (on the host computer, with the server running)

```powershell
backend\venv\Scripts\python launcher\homeschooling.py pair-agent --name "Codex"
```

This stores the tutor credential for the current Windows user, protected with DPAPI. A bridge on another computer can take the credential from the `HOMESCHOOLING_AGENT_TOKEN` environment variable instead.

## 2. Register the bridge

**Codex** (`%USERPROFILE%\.codex\config.toml`):

```toml
[mcp_servers.homeschooling]
command = "C:\\Users\\<you>\\source\\Homeschooling\\backend\\venv\\Scripts\\python.exe"
args = ["C:\\Users\\<you>\\source\\Homeschooling\\tutor_mcp\\bridge.py"]
env = { HOMESCHOOLING_URL = "http://127.0.0.1:8000" }
```

**Claude Desktop** (`claude_desktop_config.json`):

```json
{"mcpServers": {"homeschooling": {
  "command": "C:\\Users\\<you>\\source\\Homeschooling\\backend\\venv\\Scripts\\python.exe",
  "args": ["C:\\Users\\<you>\\source\\Homeschooling\\tutor_mcp\\bridge.py"],
  "env": {"HOMESCHOOLING_URL": "http://127.0.0.1:8000"}}}}
```

Set `HOMESCHOOLING_READER_BASE` to the LAN address (for example `http://192.168.1.20:8000`) if the reader links should open on another device.

## 3. Add the skill

Copy or link `tutor/skills/home-tutor` into the client's skills folder, and point the subject project at `tutor/subjects/<subject>/GUIDE.md`. The History project's new entry instructions are rendered by `python -m migration.cutover history-instructions` (see MIGRATION.md).

`lesson_context` also returns the subject's active `teaching_skill`, including its version and editable instructions. Read that copy for subject teaching decisions; the server continues to enforce shared evidence and record-saving rules. Family members edit it in Curriculum → subject → Teaching skill. Preparing a guide never starts or completes a tutor session.

## Tools

### Shared activities

Enable **Lesson options → Allow desktop tutor for this lesson** on a family device before using activity tools for a guided session. `list_activity_definitions` returns the canonical contracts, and the bridge exposes all 23 registered activity names using their server-owned input schemas. Supply `session_id`, `expected_revision`, a stable `operation_id`, validated `content`, and an optional `parent_activity_id`.

A display tool returns a pending handle immediately. Use `get_activity_result` with the session and the last `after` event cursor to retrieve subsequent state and the actual child response. Stop while input is pending; never invent a response or repeatedly display the same task. After a timeout, retry the same operation identity. Student submission/confirmation and parent inspection stay on family devices. Legacy record/finish tools cannot bypass pending activities in an engine-managed session. New lesson preparation remains available through the app's preparation flow; `prepare_lesson` on a running session retrieves its pinned preparation.

See [ACTIVITY_ENGINE.md](ACTIVITY_ENGINE.md) for capture, state, source and narration rules.

### Existing tools

| Tool | Purpose |
|---|---|
| `list_learners` | Learners and subjects |
| `lesson_context` | Phase `start`, `reading` or `closeout` context for the current topic. It includes an unfinished session's exact next prompt. |
| `start_lesson` | Starts, or resumes, a session. Returns `reader_url`, which the client opens and visually verifies. |
| `get_assignments`, `assign_questions` | Test questions mapped to the topic |
| `get_workbook_exercises`, `assign_exercises` | Saved catalog exercises eligible for this reading, and individual versioned assignments. Preparing a guide creates none. |
| `exercise_grading_context` | **Teacher-only** original instructions, pinned exercise sources and grading material for owned assignment items |
| `grading_context` | **Teacher-only** key entries and passage evidence for named questions |
| `record_attempts` | First answers verbatim, reading certainty, results, help, revisions and source notes |
| `save_checkpoint` | Unfinished observations plus the exact next prompt (append-only) |
| `update_reviews` | Specific review concepts, closed only after a later independent check |
| `attach_work` | Photo or PDF of handwritten work, saved to Drive `Student Work` |
| `finish_lesson` | Actual session summary and understanding, plus an explicit next topic or `end_of_subject: true` for the final topic. Closes the reader session. |
| `close_reader` | Closes the lesson's reader. The home server keeps running. |
| `review_passage` | Records a page-by-page review of an extracted passage |
| `narration` | Estimate (the default) or generate one narrator within the shared monthly guard |
| `save_preference` | A confirmed learner or parent preference |
| `storage_status` | Whether the database and the synced Drive folder (books, audio) are available |

Every mutation needs a stable `operation_id`, and session mutations also need the `expected_revision` from the previous response. Each result includes a receipt; `sync_state: saved` means the change is committed to the home server's database. If a call times out, repeat it with the same `operation_id`. The server returns the original result and never creates a duplicate.

Workbook attempts can carry `assignment_item_id` and `exercise_id`; each exercise gets its own attempt, even when several answers share one photo. The original numbered-question tools remain supported. `lesson_context` includes `available_exercises` and `pending_exercise_items`, with student-safe instructions and saved reading requirements. Never use a page or chapter-number coincidence as readiness evidence. Use the saved catalog and leave unresolved mappings pending.

Book preparation interfaces live under `/api`: `GET /books/incoming`, `POST /books/stage`, `POST /subjects/{id}/book-imports`, `GET /subjects/{id}/resources`, `POST /book-imports/{id}/retry`, and `POST /subject-books/{id}/prepare`. Exercise editing/history/filtered PDF previews live at `/exercises/{id}`, `/exercises/{id}/history`, and `/exercises/{id}/preview`. Learner work uses `/tutor/sessions/{id}/exercises` and the existing conversation endpoints. Progress and practice are available at `/workbook-progress/{child_id}` and `/exercises/{id}/practice`.
